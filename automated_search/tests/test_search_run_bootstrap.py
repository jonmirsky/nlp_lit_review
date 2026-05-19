#!/usr/bin/env python3
"""
Smoke tests for the SearchRun bootstrap path.

Inputs:
- tests/fixtures/five_refs.ris (5-reference RIS for the manual_export path)

Outputs:
- None permanent. Each test creates a temporary searches/ directory under
  pytest's tmp_path and removes it at end-of-test.

Run with:
    cd automated_search && python3 -m pytest tests/

These tests cover Phases 0, 1, 3 of the recordkeeping refactor:
- slug normalization
- second-precision timestamps
- run-folder allocation with auto-suffix on collision
- metadata.json schema (draft) validation
- progress.jsonl appender shape
- manual_export bootstrap end-to-end (no network)
"""

import json
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "scripts" / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from search_run import (  # type: ignore[import-not-found]
    SCHEMA_VERSION,
    SearchRun,
    _empty_metadata,
    _validate_metadata,
    allocate_run_dir,
    append_progress,
    bootstrap_search_run,
    query_hash_for_text,
    normalize_slug,
    read_metadata,
    read_progress,
    save_metadata,
    utc_timestamp,
)


FIXTURE_RIS = Path(__file__).resolve().parent / "fixtures" / "five_refs.ris"


def test_normalize_slug_basic():
    assert normalize_slug("NLP_Extraction") == "nlp_extraction"
    assert normalize_slug("nlp-extraction") == "nlp_extraction"
    assert normalize_slug("  spacey slug  ") == "spacey_slug"
    assert normalize_slug("A!B@C#") == "a_b_c"


def test_normalize_slug_rejects_empty():
    with pytest.raises(ValueError):
        normalize_slug("")
    with pytest.raises(ValueError):
        normalize_slug("   ")
    with pytest.raises(ValueError):
        normalize_slug("###")


def test_utc_timestamp_shape():
    ts = utc_timestamp()
    assert len(ts) == len("YYYY_MM_DD_HHMMSS")
    parts = ts.split("_")
    assert len(parts) == 4
    assert all(p.isdigit() for p in parts)


def test_allocate_run_dir_no_collision(tmp_path):
    run_dir, suffix = allocate_run_dir("test_slug", searches_dir=tmp_path, timestamp="2026_05_14_120000")
    assert run_dir.exists()
    assert run_dir.name == "2026_05_14_120000__test_slug"
    assert suffix is None


def test_allocate_run_dir_auto_suffix(tmp_path):
    first, s1 = allocate_run_dir("test_slug", searches_dir=tmp_path, timestamp="2026_05_14_120000")
    second, s2 = allocate_run_dir("test_slug", searches_dir=tmp_path, timestamp="2026_05_14_120000")
    third, s3 = allocate_run_dir("test_slug", searches_dir=tmp_path, timestamp="2026_05_14_120000")
    assert s1 is None
    assert s2 == 2
    assert s3 == 3
    assert first.name == "2026_05_14_120000__test_slug"
    assert second.name == "2026_05_14_120000__test_slug-2"
    assert third.name == "2026_05_14_120000__test_slug-3"


def test_empty_metadata_passes_validator():
    meta = _empty_metadata("2026_05_14_120000__test_slug")
    meta["slug"] = "test_slug"
    meta["base_query"] = "anything"
    meta["query_hash"] = query_hash_for_text("anything")
    meta["search_query"] = "anything"
    meta["search_term_label"] = "(test)"
    _validate_metadata(meta)


def test_validator_rejects_missing_keys():
    meta = _empty_metadata("2026_05_14_120000__test_slug")
    meta["search_query"] = "x"
    meta["search_term_label"] = "(x)"
    del meta["finished_at"]
    with pytest.raises(ValueError, match="missing required keys"):
        _validate_metadata(meta)


def test_validator_rejects_bad_run_id():
    meta = _empty_metadata("not-a-valid-run-id")
    meta["search_query"] = "x"
    meta["search_term_label"] = "(x)"
    with pytest.raises(ValueError, match="run_id"):
        _validate_metadata(meta)


def test_validator_rejects_bad_enum():
    meta = _empty_metadata("2026_05_14_120000__test_slug")
    meta["slug"] = "test_slug"
    meta["base_query"] = "x"
    meta["query_hash"] = query_hash_for_text("x")
    meta["search_query"] = "x"
    meta["search_term_label"] = "(x)"
    meta["source_db"] = "google_scholar"
    with pytest.raises(ValueError, match="source_db"):
        _validate_metadata(meta)


def test_metadata_atomic_roundtrip(tmp_path):
    run_dir, _ = allocate_run_dir("rt", searches_dir=tmp_path, timestamp="2026_05_14_120000")
    run = SearchRun.for_root(run_dir)
    save_metadata(
        run,
        search_query="example",
        search_term_label="(example)",
        source_db="pubmed",
        query_source="entrez",
    )
    assert run.metadata_path.exists()
    loaded = read_metadata(run)
    assert loaded["search_query"] == "example"
    assert loaded["schema_version"] == SCHEMA_VERSION
    assert loaded["_generated_by"] == "automated_search/scripts/auto_search_wrapper.py"

    save_metadata(run, download_success=42, finished_at="2026-05-14T12:30:00Z")
    loaded2 = read_metadata(run)
    assert loaded2["download_success"] == 42
    assert loaded2["search_query"] == "example"
    assert loaded2["finished_at"] == "2026-05-14T12:30:00Z"


def test_progress_appender(tmp_path):
    run_dir, _ = allocate_run_dir("prog", searches_dir=tmp_path, timestamp="2026_05_14_120000")
    run = SearchRun.for_root(run_dir)
    save_metadata(run, search_query="x", search_term_label="(x)")

    append_progress(run, record_number="1001", identifier_used="pmid:11111111", outcome="success", elapsed_ms=2500)
    append_progress(run, record_number="1002", identifier_used="doi:10.1234/foo", outcome="fail", error_reason="paywall_detected", elapsed_ms=4000)
    append_progress(run, record_number="1003", identifier_used="pmid:33333333", outcome="skipped_existing")

    entries = read_progress(run)
    assert len(entries) == 3
    assert entries[0]["outcome"] == "success"
    assert entries[1]["error_reason"] == "paywall_detected"
    assert entries[2]["outcome"] == "skipped_existing"


def test_bootstrap_manual_export_end_to_end(tmp_path, monkeypatch):
    searches_dir = tmp_path / "searches"
    monkeypatch.delenv("LIT_REVIEW_PDF_REMOTE", raising=False)
    monkeypatch.setenv("LIT_REVIEW_PDF_STORE", str(tmp_path / "pdf_store"))
    (tmp_path / "pdf_store").mkdir()

    run = bootstrap_search_run(
        slug="Smoke Test 1",
        search_query="example query",
        search_term_label="(smoke)",
        source_db="manual",
        query_source="manual_export",
        input_ris=FIXTURE_RIS,
        searches_dir=searches_dir,
    )

    assert run.root.exists()
    assert run.root.parent == searches_dir
    assert run.run_id.endswith("__smoke_test_1")
    assert run.input_ris.exists()
    assert run.input_all_ris.exists()
    assert run.found_dir.exists()
    assert run.missing_dir.exists()
    assert run.pdfs_dir.exists()

    meta = read_metadata(run)
    assert meta["input_count"] == 5
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["slug"] == "smoke_test_1"
    assert meta["base_query"] == "example query"
    assert meta["query_hash"] == query_hash_for_text("example query")
    assert meta["candidate_count_before_skip"] == 5
    assert meta["candidate_count_after_skip"] == 5
    assert meta["search_term_label"] == "(smoke)"
    assert meta["query_source"] == "manual_export"
    assert meta["source_db"] == "manual"
    assert meta["pdf_store_root"] == str(tmp_path / "pdf_store")


def test_bootstrap_dry_run(tmp_path):
    searches_dir = tmp_path / "searches"
    run = bootstrap_search_run(
        slug="dry",
        search_query="example",
        search_term_label="(dry)",
        source_db="pubmed",
        query_source="entrez",
        dry_run=True,
        searches_dir=searches_dir,
    )
    assert run.root.exists()
    assert run.input_ris.exists()
    assert run.input_ris.stat().st_size == 0
    meta = read_metadata(run)
    assert meta["input_count"] == 0


def test_bootstrap_byo_found_ris(tmp_path):
    searches_dir = tmp_path / "searches"
    run = bootstrap_search_run(
        slug="byo",
        search_query="N/A (BYO)",
        search_term_label="(byo)",
        source_db="byo",
        query_source="byo_found_ris",
        found_ris=FIXTURE_RIS,
        searches_dir=searches_dir,
    )
    assert run.found_ris.exists()
    meta = read_metadata(run)
    assert meta["input_count"] == 5
    assert meta["query_source"] == "byo_found_ris"


def test_bootstrap_rejects_missing_required_args(tmp_path):
    searches_dir = tmp_path / "searches"
    with pytest.raises(ValueError, match="manual_export.*requires input_ris"):
        bootstrap_search_run(
            slug="bad",
            search_query="x",
            search_term_label="(x)",
            source_db="manual",
            query_source="manual_export",
            searches_dir=searches_dir,
        )
    with pytest.raises(ValueError, match="byo_found_ris.*requires found_ris"):
        bootstrap_search_run(
            slug="bad",
            search_query="x",
            search_term_label="(x)",
            source_db="byo",
            query_source="byo_found_ris",
            searches_dir=searches_dir,
        )
