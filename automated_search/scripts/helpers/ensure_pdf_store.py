#!/usr/bin/env python3
"""
PDF store resolution, validation, and content-addressable layout helpers.

Inputs:
- LIT_REVIEW_PDF_STORE environment variable (required for non-legacy callers):
  absolute path to a directory used as the canonical PDF store. Typically an
  rclone-mounted Google Drive folder, e.g. ~/gdrive_lit_review.
- A reference dict (parsed from RIS) containing some subset of:
  pmid, doi, title, record_number. Used by `cas_key_for_reference` to derive a
  content-addressable key.

Outputs:
- No files written by this module directly.
- `health_check` writes and removes a small sentinel file
  `<store>/.lit_review_health_<pid>` to confirm the mount is still alive
  mid-run; the sentinel is always removed before this function returns.

This module exists because:
- V4 used to hardcode `automated_search/found_papers/downloaded_papers/...`
  and re-walk that tree per reference. The new store is env-driven and flat
  (content-addressable), with one O(scandir) pass at startup.
- rclone mounts (Google Drive in particular) drop silently mid-run, so V4
  calls `health_check` periodically.

See automated_search/SCHEMA.md for the on-disk layout.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Union


PDF_STORE_ENV_VAR = "LIT_REVIEW_PDF_STORE"
PDF_REMOTE_ENV_VAR = "LIT_REVIEW_PDF_REMOTE"
PDFS_SUBDIR = "pdfs"
R2_PUBLIC_URL_BASE = "https://pub-d9c17dcc87a846d9ba3abbbbc811018d.r2.dev"


class PdfStoreUnavailable(RuntimeError):
    """Raised when the configured PDF store path is missing or unwritable."""


@dataclass(frozen=True)
class PdfStore:
    root: Path           # the env-var path (e.g. ~/gdrive_lit_review)
    pdfs_dir: Path       # root / "pdfs"


def resolve_pdf_store(*, allow_missing_env: bool = False) -> Optional[PdfStore]:
    """Resolve `$LIT_REVIEW_PDF_STORE` to a `PdfStore`, validating writability.

    Args:
        allow_missing_env: if True and the env var is unset, returns None
            instead of raising. Used by --legacy callers that still rely on
            the old hardcoded path.

    Raises:
        PdfStoreUnavailable: when the env var points at a missing or
            unwritable directory. The error message includes troubleshooting
            hints for rclone mounts.
    """
    raw = os.environ.get(PDF_STORE_ENV_VAR)
    if not raw:
        if allow_missing_env:
            return None
        raise PdfStoreUnavailable(
            f"{PDF_STORE_ENV_VAR} is not set. Export it to an absolute path "
            f"(typically an rclone-mounted Google Drive folder, e.g. "
            f"~/gdrive_lit_review) before running. See automated_search/README.md."
        )

    root = Path(raw).expanduser().resolve()
    validate_store(root)
    pdfs_dir = root / PDFS_SUBDIR
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    return PdfStore(root=root, pdfs_dir=pdfs_dir)


def validate_store(path: Path) -> None:
    """Confirm `path` exists, is a directory, and is writable.

    Raises:
        PdfStoreUnavailable: with rclone-aware troubleshooting hints.
    """
    if not path.exists():
        raise PdfStoreUnavailable(
            f"PDF store root does not exist: {path}\n"
            f"  - If using rclone, confirm the mount is up: `rclone listremotes` "
            f"and `mount | rg <mountpoint>`.\n"
            f"  - To mount Google Drive: `rclone mount gdrive:nlp_lit_review "
            f"{path} --vfs-cache-mode=full --daemon`."
        )
    if not path.is_dir():
        raise PdfStoreUnavailable(
            f"PDF store root is not a directory: {path}"
        )
    if not os.access(path, os.W_OK):
        raise PdfStoreUnavailable(
            f"PDF store root is not writable: {path}\n"
            f"  - Check file permissions.\n"
            f"  - If this is an rclone mount, the underlying remote may be "
            f"read-only or the mount may have dropped to read-only mode."
        )


def health_check(path: Path) -> None:
    """Write/read/delete a sentinel file to confirm the mount is live.

    Called by V4 every N papers (default 25) so a silently-dropped rclone
    mount fails loudly instead of corrupting the run.

    Raises:
        PdfStoreUnavailable: if any step (write, read, contents match,
            delete) fails.
    """
    sentinel = path / f".lit_review_health_{os.getpid()}"
    payload = f"ok:{os.getpid()}"
    try:
        sentinel.write_text(payload, encoding="utf-8")
        read_back = sentinel.read_text(encoding="utf-8")
        if read_back != payload:
            raise PdfStoreUnavailable(
                f"PDF store sentinel read mismatch at {sentinel}: "
                f"wrote {payload!r}, read {read_back!r}. Mount may be stale."
            )
    except OSError as exc:
        raise PdfStoreUnavailable(
            f"PDF store health check failed at {path}: {exc}. "
            f"The rclone mount may have dropped mid-run."
        ) from exc
    finally:
        try:
            sentinel.unlink(missing_ok=True)
        except OSError:
            pass


def _normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    doi = re.sub(r"\[doi\]", "", doi, flags=re.IGNORECASE)
    return doi.strip().lower().replace(" ", "")


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower()
    t = " ".join(t.split())
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip()


def cas_key_for_reference(ref: Dict[str, object]) -> Optional[str]:
    """Derive a content-addressable key for a reference dict.

    Priority order:
        1. pmid_<digits>
        2. doi_<sha1(normalized_doi)[:16]>
        3. title_<sha1(normalized_title)[:16]>

    Returns None if no usable identifier is present.
    """
    pmid = ref.get("pmid")
    if pmid:
        digits = re.sub(r"\D", "", str(pmid))
        if digits:
            return f"pmid_{digits}"

    doi = ref.get("doi")
    if doi:
        norm = _normalize_doi(str(doi))
        if norm:
            return f"doi_{hashlib.sha1(norm.encode('utf-8')).hexdigest()[:16]}"

    title = ref.get("title")
    if title:
        norm = _normalize_title(str(title))
        if norm:
            return f"title_{hashlib.sha1(norm.encode('utf-8')).hexdigest()[:16]}"

    return None


def cas_path_for_key(store: PdfStore, key: str) -> Path:
    """Return the absolute path for a given CAS key within the store."""
    return store.pdfs_dir / f"{key}.pdf"


def build_cas_index(store: PdfStore) -> Dict[str, Path]:
    """One-shot O(scandir) index of {key -> absolute path} for the CAS store.

    Used by V4 at startup to replace the per-iteration `rglob` over the entire
    downloaded_papers/ tree. Lookups become O(1).
    """
    index: Dict[str, Path] = {}
    if not store.pdfs_dir.exists():
        return index
    with os.scandir(store.pdfs_dir) as it:
        for entry in it:
            if not entry.is_file():
                continue
            name = entry.name
            if not name.endswith(".pdf"):
                continue
            key = name[:-4]
            index[key] = Path(entry.path)
    return index


def link_into_run(cas_pdf: Path, run_pdfs_dir: Path, key: str) -> Path:
    """Create a relative symlink at `<run_pdfs_dir>/<key>.pdf` pointing into the CAS.

    Falls back to copying the file when the platform does not support
    symlinks (rare on darwin/linux; matters mostly on Windows or some
    network filesystems).

    Returns the path of the created symlink/copy.
    """
    run_pdfs_dir.mkdir(parents=True, exist_ok=True)
    dst = run_pdfs_dir / f"{key}.pdf"
    if dst.exists() or dst.is_symlink():
        return dst
    try:
        rel = os.path.relpath(cas_pdf, run_pdfs_dir)
        os.symlink(rel, dst)
    except (OSError, NotImplementedError):
        shutil.copy2(cas_pdf, dst)
    return dst


# --------------------------------------------------------------------------- #
# rclone-copy mode (no FUSE mount required)
# Used on macOS 26+ where macFUSE is not yet compatible.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PdfRemote:
    """Represents a rclone remote path used as the PDF store (no local FUSE mount)."""
    remote_path: str   # e.g. "gdrive:nlp_lit_review_1_papers/pdfs"


def resolve_pdf_remote(remote_path: Optional[str] = None) -> PdfRemote:
    """Validate rclone is available and the remote prefix is configured.

    Args:
        remote_path: Override; defaults to ``$LIT_REVIEW_PDF_REMOTE``.

    Raises:
        PdfStoreUnavailable: when rclone is missing or the remote is not
            in ``rclone listremotes``.
    """
    if remote_path is None:
        remote_path = os.environ.get(PDF_REMOTE_ENV_VAR)
    if not remote_path:
        raise PdfStoreUnavailable(
            f"{PDF_REMOTE_ENV_VAR} is not set. Export it to an rclone remote path "
            f"(e.g. gdrive:nlp_lit_review_1_papers/pdfs). See automated_search/README.md."
        )
    if shutil.which("rclone") is None:
        raise PdfStoreUnavailable(
            "rclone is not in $PATH. Install with `brew install rclone` and "
            "configure gdrive: and r2: remotes with `rclone config`."
        )
    prefix = remote_path.split(":")[0] + ":"
    try:
        result = subprocess.run(
            ["rclone", "listremotes"], capture_output=True, text=True, timeout=15
        )
        configured = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        if prefix not in configured:
            raise PdfStoreUnavailable(
                f"rclone remote {prefix!r} is not configured. "
                f"Configured remotes: {sorted(configured)}. "
                f"Run `rclone config` to add it."
            )
    except subprocess.TimeoutExpired:
        raise PdfStoreUnavailable("rclone listremotes timed out after 15s.")
    return PdfRemote(remote_path=remote_path)


def resolve_pdf_backend() -> Union[PdfStore, PdfRemote]:
    """Return the active PDF backend.

    Checks ``$LIT_REVIEW_PDF_REMOTE`` first (rclone-copy mode, no FUSE
    required). Falls back to ``$LIT_REVIEW_PDF_STORE`` (local-mount mode).
    Raises ``PdfStoreUnavailable`` if neither is set or reachable.
    """
    remote = os.environ.get(PDF_REMOTE_ENV_VAR)
    if remote:
        return resolve_pdf_remote(remote)
    return resolve_pdf_store()


def build_remote_index(remote_path: str) -> Dict[str, str]:
    """List PDFs at ``remote_path`` via ``rclone lsf``.

    Returns ``{key -> "remote_path/key.pdf"}``.  Returns an empty dict on
    error (first run, non-existent remote dir) without raising — the caller
    treats an absent key as "not yet downloaded."
    """
    try:
        result = subprocess.run(
            ["rclone", "lsf", remote_path, "--include=*.pdf"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"WARNING: rclone lsf timed out or failed for {remote_path}: {exc}", flush=True)
        return {}
    index: Dict[str, str] = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            fname = line.strip()
            if fname.endswith(".pdf"):
                key = fname[:-4]
                index[key] = f"{remote_path}/{fname}"
    else:
        err = (result.stderr or result.stdout or "").strip()
        print(
            f"WARNING: rclone lsf failed (exit {result.returncode}) for {remote_path}: "
            f"{err[:300]}",
            flush=True,
        )
    print(f"  Drive PDF index: {len(index)} file(s) at {remote_path}", flush=True)
    return index


def find_newest_master_ris_path(ris_source_dir: Path) -> Optional[Path]:
    """Newest ``pubmed_*.txt`` under the visualizer RIS source folder."""
    if not ris_source_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for path in ris_source_dir.glob("pubmed_*.txt"):
        if path.is_file() and not path.name.endswith((".bak", ".bak2")):
            candidates.append((path.stat().st_mtime, path))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


_CAS_KEY_IN_PATH = re.compile(
    r"(pmid_\d+|doi_[a-f0-9]{16}|title_[a-f0-9]{16})\.pdf",
    re.IGNORECASE,
)


def _ris_field_has_pdf_attachment(value: str) -> bool:
    v = value.strip()
    if not v:
        return False
    low = v.lower()
    return (
        ".pdf" in low
        or low.startswith("http://")
        or low.startswith("https://")
        or "internal-pdf" in low
    )


def build_master_pdf_skip_keys(master_ris_path: Optional[Path]) -> Set[str]:
    """CAS keys for papers that already have L1/L2/L3 in the merged master RIS.

    Used so V4 does not re-attempt Selenium downloads for papers we already
    catalogued with a PDF path, even if the Drive index missed them.
    """
    if master_ris_path is None or not master_ris_path.is_file():
        return set()
    skip: Set[str] = set()
    content = master_ris_path.read_text(encoding="utf-8", errors="replace")
    entries = re.split(r"^ER\s+-\s*$", content, flags=re.MULTILINE)
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        doi: Optional[str] = None
        pmid: Optional[str] = None
        title: Optional[str] = None
        attachments: list[str] = []
        for line in entry.split("\n"):
            line_stripped = line.rstrip()
            m_field = re.match(r"^([A-Z0-9]{2})\s+-\s+(.*)$", line_stripped)
            if m_field:
                tag = m_field.group(1)
                value = m_field.group(2).strip()
                if tag == "DO":
                    doi = value
                elif tag == "AN":
                    pmid = value
                elif tag == "TI":
                    title = value
                elif tag in ("L1", "L2", "L3"):
                    attachments.append(value)
            elif title is not None and line_stripped:
                title += " " + line_stripped.strip()
        if not any(_ris_field_has_pdf_attachment(a) for a in attachments):
            continue
        ref: Dict[str, object] = {"doi": doi, "pmid": pmid, "title": title}
        key = cas_key_for_reference(ref)
        if key:
            skip.add(key)
        for att in attachments:
            m = _CAS_KEY_IN_PATH.search(att)
            if m:
                skip.add(m.group(1).lower())
    return skip


def pdf_already_on_file(
    ref: Dict[str, object],
    drive_index: Dict[str, object],
    master_skip_keys: Set[str],
) -> bool:
    """True when this reference's PDF is already on Drive or recorded in master RIS."""
    key = cas_key_for_reference(ref)
    if not key:
        return False
    return key in drive_index or key in master_skip_keys


def upload_pdf_to_remote(
    local_path: Path,
    remote_path: str,
    *,
    delete_after: bool = True,
) -> str:
    """``rclone copy`` *local_path* into *remote_path*, preserving the filename.

    Deletes the local file on success when ``delete_after=True``.

    Returns the remote file path string (``remote_path/filename``).

    Raises RuntimeError on non-zero rclone exit.
    """
    if shutil.which("rclone") is None:
        raise RuntimeError("rclone is not in $PATH.")
    result = subprocess.run(
        ["rclone", "copy", str(local_path), remote_path],
        capture_output=True, timeout=180,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"rclone copy failed (exit {result.returncode}): {stderr.strip()}"
        )
    remote_file = f"{remote_path}/{local_path.name}"
    if delete_after:
        try:
            local_path.unlink(missing_ok=True)
        except OSError:
            pass
    return remote_file


def r2_url_for_key(key: str) -> str:
    """Return the public Cloudflare R2 URL for a CAS key after sync.

    The URL uses the flat key-based filename (e.g. ``pmid_12345678.pdf``),
    which matches the layout that ``sync_pdfs_to_r2.py`` syncs to R2.
    """
    return f"{R2_PUBLIC_URL_BASE}/{key}.pdf"
