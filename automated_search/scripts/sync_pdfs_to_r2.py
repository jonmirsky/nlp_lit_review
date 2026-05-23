#!/usr/bin/env python3
"""
Sync PDFs from the local Google Drive store to the Cloudflare R2 bucket.

Both endpoints are rclone remotes (already configured: `gdrive:` and `r2:`).
This script is a thin wrapper around `rclone sync` so the visualizer's R2
bucket always mirrors the canonical store at $LIT_REVIEW_PDF_STORE.

Inputs:
- $LIT_REVIEW_PDF_STORE  : absolute path to the rclone-mounted Google Drive
                           folder used as the canonical store (e.g.
                           ~/gdrive_lit_review).
- $LIT_REVIEW_R2_REMOTE  : optional rclone remote destination; defaults to
                           `r2:nlp-lit-review-pdfs`.
- $LIT_REVIEW_GDRIVE_REMOTE : optional rclone source remote; defaults to
                           `gdrive:nlp_lit_review/pdfs`. Used when the local
                           mount is unreachable or when the caller passes
                           --remote-source.

Outputs:
- No files written by this script. rclone's logs go to stdout/stderr; when
  called with --run <run_dir>, the script also updates
  <run_dir>/metadata.json::r2_synced_at on success.

Usage:
    # On-demand reconciliation (uses local mount path as source by default):
    python3 automated_search/scripts/sync_pdfs_to_r2.py

    # Use the gdrive remote directly (handy when the mount is dead):
    python3 automated_search/scripts/sync_pdfs_to_r2.py --remote-source

    # End-of-run hook (also invoked automatically from the wrapper):
    python3 automated_search/scripts/sync_pdfs_to_r2.py --run automated_search/searches/<run_id>

    # See what would change, transfer nothing:
    python3 automated_search/scripts/sync_pdfs_to_r2.py --dry-run

Requires:
    rclone v1.50+ in $PATH. `rclone listremotes` must include both the
    gdrive and r2 remotes.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

HELPERS_DIR = Path(__file__).resolve().parent / "helpers"
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))

from search_run import SearchRun, save_metadata, utc_iso_now  # type: ignore[import-not-found]


DEFAULT_R2_REMOTE = "r2:nlp-lit-review-pdfs"
DEFAULT_GDRIVE_REMOTE = "gdrive:nlp_lit_review/pdfs"


class RcloneUnavailable(RuntimeError):
    pass


def _check_rclone() -> None:
    if shutil.which("rclone") is None:
        raise RcloneUnavailable(
            "`rclone` is not in $PATH. Install with `brew install rclone` "
            "and configure the gdrive: and r2: remotes (`rclone config`)."
        )


def _check_remote(name: str) -> None:
    """Confirm `name:` is a configured rclone remote."""
    _check_rclone()
    result = subprocess.run(
        ["rclone", "listremotes"], capture_output=True, text=True, check=True
    )
    remotes = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    short = name.split(":")[0] + ":"
    if short not in remotes:
        raise RcloneUnavailable(
            f"rclone remote {short!r} is not configured. Run `rclone config` "
            f"to add it. Existing remotes: {sorted(remotes)}"
        )


def resolve_source(*, remote_source: bool) -> str:
    """Pick the source argument for ``rclone sync``.

    Resolution order (first match wins):

    1. ``--remote-source`` flag / ``$LIT_REVIEW_GDRIVE_REMOTE``:
       use the gdrive remote path directly (e.g.
       ``gdrive:nlp_lit_review_1_papers/pdfs``).
    2. ``$LIT_REVIEW_PDF_REMOTE``: the rclone-copy-mode remote configured for
       V4 downloads.  Avoids the need for a FUSE mount entirely.
    3. ``$LIT_REVIEW_PDF_STORE/pdfs``: the locally-mounted folder (legacy FUSE
       path).  Fails fast if the path does not exist.
    """
    if remote_source:
        return os.environ.get("LIT_REVIEW_GDRIVE_REMOTE", DEFAULT_GDRIVE_REMOTE)

    pdf_remote = os.environ.get("LIT_REVIEW_PDF_REMOTE")
    if pdf_remote:
        return pdf_remote

    store = os.environ.get("LIT_REVIEW_PDF_STORE")
    if not store:
        raise SystemExit(
            "ERROR: neither $LIT_REVIEW_PDF_REMOTE nor $LIT_REVIEW_PDF_STORE is set. "
            "Export $LIT_REVIEW_PDF_REMOTE (e.g. gdrive:nlp_lit_review_1_papers/pdfs) "
            "or pass --remote-source to sync from the gdrive: remote directly. "
            "See automated_search/README.md."
        )
    src = Path(store).expanduser() / "pdfs"
    if not src.exists():
        raise SystemExit(
            f"ERROR: source path does not exist: {src}. "
            f"If rclone mount is unavailable, set $LIT_REVIEW_PDF_REMOTE instead of "
            f"$LIT_REVIEW_PDF_STORE and re-run."
        )
    return str(src)


def run_rclone_copy(
    *,
    source: str,
    destination: str,
    dry_run: bool = False,
    progress: bool = True,
    extra_args: Optional[list[str]] = None,
) -> int:
    """Invoke non-destructive `rclone copy` in the foreground.

    The visualizer bucket also contains legacy flattened EndNote assets named
    `NLP_v4_*` / `zotero_v3_*`.  The automated pipeline's CAS store is flat
    (`pmid_*.pdf`, `doi_*.pdf`, `title_*.pdf`).  Using `rclone sync` at the
    bucket root can delete those legacy assets, so this script only copies new
    or changed files into R2.
    """
    _check_rclone()
    cmd: list[str] = ["rclone", "copy", source, destination]
    if progress:
        cmd.append("--progress")
    if dry_run:
        cmd.append("--dry-run")
    if extra_args:
        cmd.extend(extra_args)
    print(f"\n$ {' '.join(cmd)}\n", flush=True)
    return subprocess.run(cmd, check=False).returncode


def run_rclone_sync(
    *,
    source: str,
    destination: str,
    dry_run: bool = False,
    progress: bool = True,
    extra_args: Optional[list[str]] = None,
) -> int:
    """Backward-compatible alias for the now non-destructive copy operation."""
    return run_rclone_copy(
        source=source,
        destination=destination,
        dry_run=dry_run,
        progress=progress,
        extra_args=extra_args,
    )


def sync_run_to_r2(
    run: SearchRun,
    *,
    remote_source: bool = False,
    dry_run: bool = False,
) -> None:
    """Sync the global PDF store to R2 and record `r2_synced_at` in metadata.

    Called from the wrapper's Step 3 tail after `summary.md` is written.
    """
    destination = os.environ.get("LIT_REVIEW_R2_REMOTE", DEFAULT_R2_REMOTE)
    _check_remote(destination)
    source = resolve_source(remote_source=remote_source)
    rc = run_rclone_sync(source=source, destination=destination, dry_run=dry_run)
    if rc != 0:
        raise RuntimeError(f"rclone sync exited with code {rc}")
    if not dry_run:
        save_metadata(run, r2_synced_at=utc_iso_now())
        print(f"\nR2 sync complete. metadata.r2_synced_at updated.")


def _cli() -> int:
    p = argparse.ArgumentParser(
        prog="sync_pdfs_to_r2",
        description="Copy PDFs from the configured PDF store to Cloudflare R2 via rclone.",
    )
    p.add_argument("--run", type=Path, help="Optional run folder; updates metadata.r2_synced_at on success.")
    p.add_argument("--remote-source", action="store_true",
                   help="Use the gdrive: remote directly instead of the local mount.")
    p.add_argument("--dry-run", action="store_true", help="Pass --dry-run to rclone (no transfer).")
    p.add_argument("--no-progress", action="store_true", help="Disable rclone's --progress flag.")
    args = p.parse_args()

    destination = os.environ.get("LIT_REVIEW_R2_REMOTE", DEFAULT_R2_REMOTE)
    try:
        _check_remote(destination)
    except RcloneUnavailable as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.run:
        run = SearchRun.for_root(args.run.resolve())
        if not run.metadata_path.exists():
            print(f"ERROR: no metadata.json at {run.metadata_path}")
            return 1
        try:
            sync_run_to_r2(run, remote_source=args.remote_source, dry_run=args.dry_run)
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return 3
        return 0

    source = resolve_source(remote_source=args.remote_source)
    rc = run_rclone_sync(
        source=source,
        destination=destination,
        dry_run=args.dry_run,
        progress=not args.no_progress,
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(_cli())
