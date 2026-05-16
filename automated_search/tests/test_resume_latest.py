"""
Tests for latest-run resume gating.

Inputs:
- Temporary automated_search/searches-like directories.

Outputs:
- None; locks the rule that only the newest run may auto-resume, and complete
  newest runs produce a no-op decision.
"""

from __future__ import annotations

import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "scripts" / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from resume_latest import latest_resume_decision  # type: ignore[import-not-found]
from search_run import SearchRun, save_metadata  # type: ignore[import-not-found]


def _make_run(searches_dir: Path, run_id: str, *, complete: bool, input_ris: bool = True) -> SearchRun:
    root = searches_dir / run_id
    root.mkdir(parents=True)
    run = SearchRun.for_root(root)
    if input_ris:
        run.input_ris.write_text("TY  - JOUR\nTI  - Example\nER  -\n", encoding="utf-8")
    save_metadata(
        run,
        search_query="example",
        search_term_label="(example)",
        source_db="pubmed",
        query_source="entrez",
    )
    if complete:
        run.summary_path.write_text("# Summary\n", encoding="utf-8")
        save_metadata(run, finished_at="2026-05-14T13:00:00Z", merged_from=[run_id])
    return run


def test_latest_complete_noops_even_if_older_incomplete(tmp_path):
    searches = tmp_path / "searches"
    _make_run(searches, "2026_05_14_120000__older", complete=False)
    latest = _make_run(searches, "2026_05_15_120000__latest", complete=True)

    decision = latest_resume_decision(searches)

    assert decision.run is not None
    assert decision.run.run_id == latest.run_id
    assert decision.can_resume is False
    assert "complete" in decision.reason


def test_latest_incomplete_with_input_ris_can_resume(tmp_path):
    searches = tmp_path / "searches"
    latest = _make_run(searches, "2026_05_15_120000__latest", complete=False)

    decision = latest_resume_decision(searches)

    assert decision.run is not None
    assert decision.run.run_id == latest.run_id
    assert decision.can_resume is True
    assert "resumable" in decision.reason


def test_latest_incomplete_without_input_ris_noops(tmp_path):
    searches = tmp_path / "searches"
    latest = _make_run(searches, "2026_05_15_120000__latest", complete=False, input_ris=False)

    decision = latest_resume_decision(searches)

    assert decision.run is not None
    assert decision.run.run_id == latest.run_id
    assert decision.can_resume is False
    assert "no input/found RIS" in decision.reason
