#!/usr/bin/env python3
"""
Batch-run the full literature pipeline for every catalog entry that defines
`slug` and `label` in visualizer_nlp_lit_review/config.py::COMMON_SEARCH_TERMS.

Inputs:
- visualizer_nlp_lit_review/config.py (COMMON_SEARCH_TERMS: query, slug, label per entry).
- Environment and CLI flags expected by automated_search/scripts/auto_search_wrapper.py
  (e.g. NCBI_EMAIL, LIT_REVIEW_PDF_REMOTE or LIT_REVIEW_PDF_STORE).

Outputs:
- No files written by this script. Each wrapper run updates automated_search/searches/,
  visualizer_nlp_lit_review/RIS_source_files/, the PDF store, and (unless disabled) R2.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_common_search_terms() -> dict[str, dict[str, Any]]:
    root = _repo_root()
    config_path = root / "visualizer_nlp_lit_review" / "config.py"
    if not config_path.is_file():
        raise FileNotFoundError(f"Missing visualizer config: {config_path}")
    spec = importlib.util.spec_from_file_location(
        "viz_lit_review_config",
        config_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {config_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    terms = getattr(mod, "COMMON_SEARCH_TERMS", None)
    if not isinstance(terms, dict):
        raise RuntimeError("config.py must define COMMON_SEARCH_TERMS as a dict")
    return terms  # type: ignore[return-value]


def _iter_refresh_entries(
    terms: dict[str, dict[str, Any]],
) -> list[tuple[str, str, str, str]]:
    """Return list of (query_name, query, slug, label) for batch runs."""
    out: list[tuple[str, str, str, str]] = []
    for name, info in terms.items():
        if not isinstance(info, dict):
            continue
        slug = info.get("slug")
        label = info.get("label")
        query = info.get("query")
        if not slug or not label or not query:
            continue
        if not str(slug).strip() or not str(label).strip() or not str(query).strip():
            continue
        out.append((name, str(query), str(slug), str(label)))
    return out


def _shellish_repr(s: str) -> str:
    return repr(s)


def _stream_command(cmd: list[str], cwd: Path) -> int:
    """Run *cmd* and copy its merged stdout/stderr to this process's stdout in real time."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:
        return proc.wait()
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run auto_search_wrapper end-to-end for each COMMON_SEARCH_TERMS entry "
            "that includes slug, label, and query."
        ),
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all catalog entries even if one fails; exit 1 if any failed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print wrapper commands only; do not run the pipeline.",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    terms = _load_common_search_terms()
    entries = _iter_refresh_entries(terms)
    if not entries:
        print(
            "No batch entries found. Add non-empty `query`, `slug`, and `label` "
            "to COMMON_SEARCH_TERMS in visualizer_nlp_lit_review/config.py.",
            file=sys.stderr,
        )
        return 1

    wrapper = root / "automated_search" / "scripts" / "auto_search_wrapper.py"
    if not wrapper.is_file():
        print(f"ERROR: wrapper not found: {wrapper}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for query_name, query, slug, label in entries:
        cmd = [
            sys.executable,
            "-u",
            str(wrapper),
            "--query",
            query,
            "--slug",
            slug,
            "--label",
            label,
        ]
        print("=" * 70, flush=True)
        print(f"Catalog entry: {query_name} (slug={slug})", flush=True)
        print("=" * 70, flush=True)
        if args.dry_run:
            shown = (
                f"{sys.executable} -u {wrapper} "
                f"--query {_shellish_repr(query)} "
                f"--slug {_shellish_repr(slug)} "
                f"--label {_shellish_repr(label)}"
            )
            print(f"DRY-RUN: {shown}", flush=True)
            continue
        rc = _stream_command(cmd, cwd=root)
        if rc != 0:
            msg = f"{query_name} (exit {rc})"
            failures.append(msg)
            print(f"ERROR: wrapper failed for {msg}", file=sys.stderr, flush=True)
            if not args.continue_on_error:
                return rc if rc else 1

    if failures:
        print("\nFailed entries:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\nDry run complete; no searches executed.", flush=True)
    else:
        print("\nAll catalog refreshes finished.", flush=True)
        print(
            "Remember to commit and push updated RIS under "
            "visualizer_nlp_lit_review/RIS_source_files/ if the site should pick up changes.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
