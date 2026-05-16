#!/usr/bin/env python3
"""
Find and classify the latest automated-search run for safe resume behavior.

Inputs:
- automated_search/searches/<run_id>/metadata.json
- Optional run artifacts: input.ris, found/found.ris, summary.md

Outputs:
- Pure helper decisions used by auto_search_wrapper.py and admin_gui.py.
  This module does not mutate files or start jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_run import SEARCHES_DIR, SearchRun, read_metadata


@dataclass(frozen=True)
class ResumeDecision:
    run: SearchRun | None
    can_resume: bool
    reason: str


def find_latest_run(searches_dir: Path = SEARCHES_DIR) -> SearchRun | None:
    """Return the newest run folder that has metadata.json, or None."""
    if not searches_dir.exists():
        return None
    candidates = []
    for child in searches_dir.iterdir():
        if child.is_dir() and (child / "metadata.json").is_file():
            candidates.append(child)
    if not candidates:
        return None
    return SearchRun.for_root(max(candidates, key=lambda p: p.name))


def is_run_complete(run: SearchRun, meta: dict[str, Any] | None = None) -> bool:
    """True only after the full pipeline completed and wrote a summary.

    V4 writes metadata.finished_at before the post-scrape merge. The wrapper
    then records the run_id in metadata.merged_from and writes summary.md.
    Requiring both avoids treating "scrape done, merge interrupted" as done.
    """
    meta = meta if meta is not None else read_metadata(run)
    merged_from = meta.get("merged_from") or []
    return bool(meta.get("finished_at")) and run.run_id in merged_from and run.summary_path.is_file()


def is_run_resumable(run: SearchRun, meta: dict[str, Any] | None = None) -> bool:
    """True when the latest incomplete run has enough state to resume safely."""
    meta = meta if meta is not None else read_metadata(run)
    if is_run_complete(run, meta):
        return False
    if meta.get("query_source") == "byo_found_ris" and run.found_ris.is_file():
        return True
    if run.input_ris.is_file() and run.input_ris.stat().st_size > 0:
        return True
    if run.found_ris.is_file() and run.found_ris.stat().st_size > 0:
        return True
    return False


def latest_resume_decision(searches_dir: Path = SEARCHES_DIR) -> ResumeDecision:
    """Classify only the latest run.

    If the latest run is complete, this intentionally returns can_resume=False
    even when older runs are incomplete. This matches the operator contract:
    automatic reboot resume should only act when the most recent run needs it.
    """
    run = find_latest_run(searches_dir)
    if run is None:
        return ResumeDecision(None, False, f"No run folders with metadata found under {searches_dir}")

    meta = read_metadata(run)
    if is_run_complete(run, meta):
        return ResumeDecision(run, False, f"Latest run is complete: {run.run_id}")
    if is_run_resumable(run, meta):
        return ResumeDecision(run, True, f"Latest run is incomplete and resumable: {run.run_id}")
    return ResumeDecision(
        run,
        False,
        f"Latest run is incomplete but has no input/found RIS to resume safely: {run.run_id}",
    )
