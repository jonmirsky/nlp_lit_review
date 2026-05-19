#!/usr/bin/env python3
"""Tests for schema-v2 incremental refresh bookkeeping."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "scripts" / "helpers"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for p in (HELPERS, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import auto_search_wrapper  # type: ignore[import-not-found]
import refresh_catalog  # type: ignore[import-not-found]
from resume_latest import latest_resume_decision  # type: ignore[import-not-found]
from search_run import (  # type: ignore[import-not-found]
    SearchRun,
    append_progress,
    build_known_paper_skip_sets,
    edat_mindate_from_started_at,
    filter_ris_by_known_papers,
    find_completed_anchor,
    normalize_query_text,
    query_hash_for_text,
    save_metadata,
)


def _save_v2(
    searches: Path,
    run_id: str,
    *,
    slug: str,
    query: str,
    complete: bool = True,
    started_at: str = "2026-05-14T12:34:56Z",
) -> SearchRun:
    root = searches / run_id
    root.mkdir(parents=True)
    run = SearchRun.for_root(root)
    save_metadata(
        run,
        slug=slug,
        base_query=normalize_query_text(query),
        query_hash=query_hash_for_text(query),
        search_query=normalize_query_text(query),
        search_term_label=f"({slug})",
        source_db="pubmed",
        query_source="entrez",
        started_at=started_at,
    )
    if complete:
        save_metadata(run, finished_at="2026-05-14T13:00:00Z", merged_from=[run_id])
    return run


def _save_v1(searches: Path, run_id: str) -> SearchRun:
    root = searches / run_id
    root.mkdir(parents=True)
    run = SearchRun.for_root(root)
    run.metadata_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "search_query": "example",
                "finished_at": "2026-05-14T13:00:00Z",
                "merged_from": [run_id],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return run


def test_query_normalization_and_hash():
    assert normalize_query_text("  foo\n\tbar   baz  ") == "foo bar baz"
    assert query_hash_for_text("foo bar baz") == query_hash_for_text("  foo\nbar\tbaz ")


def test_completed_anchor_selection_by_slug_and_query_hash(tmp_path):
    searches = tmp_path / "searches"
    old = _save_v2(
        searches,
        "2026_05_14_120000__topic",
        slug="topic",
        query="foo bar",
        started_at="2026-05-14T12:00:00Z",
    )
    latest = _save_v2(
        searches,
        "2026_05_15_120000__topic",
        slug="topic",
        query=" foo   bar ",
        started_at="2026-05-15T12:00:00Z",
    )
    _save_v2(searches, "2026_05_16_120000__topic", slug="topic", query="different")
    _save_v2(searches, "2026_05_17_120000__topic", slug="topic", query="foo bar", complete=False)
    _save_v1(searches, "2026_05_18_120000__topic")

    anchor = find_completed_anchor(slug="topic", query_hash=query_hash_for_text("foo bar"), searches_dir=searches)

    assert anchor is not None
    assert old.run_id != latest.run_id
    assert anchor[0].run_id == latest.run_id


def test_schema_v1_ignored_for_skips_and_resume(tmp_path):
    searches = tmp_path / "searches"
    v1 = _save_v1(searches, "2026_05_16_120000__legacy")
    append_progress(v1, record_number="1", identifier_used="pmid:111", outcome="success", paper_key="pmid_111")
    v2 = _save_v2(searches, "2026_05_15_120000__current", slug="current", query="example", complete=False)
    v2.input_ris.write_text("TY  - JOUR\nTI  - Example\nER  -\n", encoding="utf-8")

    success_keys, failure_keys = build_known_paper_skip_sets(searches)
    decision = latest_resume_decision(searches)

    assert "pmid_111" not in success_keys
    assert failure_keys == set()
    assert decision.run is not None
    assert decision.run.run_id == v2.run_id
    assert decision.can_resume is True


def test_edat_mindate_derived_from_anchor_started_at():
    assert edat_mindate_from_started_at("2026-05-14T23:59:58Z") == "2026/05/14"


def test_known_success_failure_skip_sets_from_paper_key(tmp_path):
    searches = tmp_path / "searches"
    run = _save_v2(searches, "2026_05_14_120000__topic", slug="topic", query="example")
    append_progress(run, record_number="1", identifier_used="pmid:111", outcome="success", paper_key="pmid_111")
    append_progress(run, record_number="2", identifier_used="pmid:222", outcome="skipped_existing", paper_key="pmid_222")
    append_progress(run, record_number="3", identifier_used="pmid:333", outcome="fail", paper_key="pmid_333")

    success_keys, failure_keys = build_known_paper_skip_sets(searches)

    assert success_keys == {"pmid_111", "pmid_222"}
    assert failure_keys == {"pmid_333"}


def test_input_all_vs_filtered_input_ris(tmp_path):
    input_all = tmp_path / "input_all.ris"
    filtered = tmp_path / "input.ris"
    input_all.write_text(
        "TY  - JOUR\nTI  - Success\nAN  - 111\nER  -\n\n"
        "TY  - JOUR\nTI  - Failure\nAN  - 222\nER  -\n\n"
        "TY  - JOUR\nTI  - Keep\nAN  - 333\nER  -\n",
        encoding="utf-8",
    )

    counts = filter_ris_by_known_papers(
        input_all,
        filtered,
        known_success_keys={"pmid_111"},
        known_failure_keys={"pmid_222"},
    )

    assert counts == {
        "candidate_count_before_skip": 3,
        "known_success_skip_count": 1,
        "known_failure_skip_count": 1,
        "candidate_count_after_skip": 1,
    }
    text = filtered.read_text(encoding="utf-8")
    assert "AN  - 333" in text
    assert "AN  - 111" not in text
    assert "AN  - 222" not in text


def test_check_only_does_not_create_run_or_launch_selenium(tmp_path, monkeypatch, capsys):
    searches = tmp_path / "searches"
    monkeypatch.setattr(auto_search_wrapper, "build_known_paper_skip_sets", lambda: ({"pmid_111"}, set()))

    def fake_fetch(query, out_path, **kwargs):
        out_path.write_text(
            "TY  - JOUR\nTI  - Known\nAN  - 111\nER  -\n\n"
            "TY  - JOUR\nTI  - New\nAN  - 222\nER  -\n",
            encoding="utf-8",
        )
        return 2

    monkeypatch.setattr(auto_search_wrapper, "fetch_pubmed_via_entrez", fake_fetch)
    monkeypatch.setattr(auto_search_wrapper, "run_full_text_scrape", lambda *a, **k: pytest.fail("selenium launched"))
    monkeypatch.setattr(auto_search_wrapper, "bootstrap_search_run", lambda *a, **k: pytest.fail("run folder created"))

    rc = auto_search_wrapper.main(
        ["--query", "example", "--slug", "topic", "--label", "(topic)", "--check-only"]
    )

    assert rc == 0
    assert not searches.exists()
    assert "before_skip=2" in capsys.readouterr().out


def test_refresh_catalog_command_construction():
    wrapper = Path("/repo/automated_search/scripts/auto_search_wrapper.py")

    full = refresh_catalog._build_wrapper_command(
        wrapper=wrapper,
        query="q",
        slug="s",
        label="l",
        source_db="pubmed",
        full_search=True,
    )
    inc = refresh_catalog._build_wrapper_command(
        wrapper=wrapper,
        query="q",
        slug="s",
        label="l",
        source_db="pubmed",
        incremental_refresh=True,
    )
    check = refresh_catalog._build_wrapper_command(
        wrapper=wrapper,
        query="q",
        slug="s",
        label="l",
        source_db="pubmed",
        incremental_refresh=True,
        check_only=True,
    )

    assert "--incremental-refresh" not in full
    assert "--incremental-refresh" in inc
    assert "--check-only" in check
