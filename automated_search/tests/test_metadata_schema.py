#!/usr/bin/env python3
"""
Tests that lock the metadata.json contract (Schema v1).

Inputs:
- None (tests build metadata dicts in-memory).

Outputs:
- None permanent.

Run with:
    cd automated_search && python3 -m pytest tests/test_metadata_schema.py
"""

import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "scripts" / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from search_run import _empty_metadata, _validate_metadata  # type: ignore[import-not-found]


def _good_meta() -> dict:
    m = _empty_metadata("2026_05_14_120000__test_slug")
    m["search_query"] = "example"
    m["search_term_label"] = "(example)"
    return m


def test_minimal_valid_metadata_passes():
    _validate_metadata(_good_meta())


def test_with_optional_fields_populated():
    m = _good_meta()
    m["collision_suffix"] = 2
    m["finished_at"] = "2026-05-14T13:00:00Z"
    m["r2_synced_at"] = "2026-05-14T13:01:00Z"
    m["input_count"] = 100
    m["download_success"] = 80
    m["download_fail"] = 15
    m["download_skipped_existing"] = 5
    m["merged_from"] = ["2026_05_14_120000__test_slug"]
    m["error_summary"] = {"paywall_detected": 10, "timeout": 5}
    m["notes"] = "smoke ok"
    _validate_metadata(m)


def test_rejects_extra_keys():
    m = _good_meta()
    m["unexpected_key"] = "x"
    with pytest.raises(ValueError, match="unknown keys"):
        _validate_metadata(m)


def test_rejects_bad_generator():
    m = _good_meta()
    m["_generated_by"] = "evil.py"
    with pytest.raises(ValueError, match="_generated_by"):
        _validate_metadata(m)


def test_rejects_wrong_schema_version():
    m = _good_meta()
    m["schema_version"] = 99
    with pytest.raises(ValueError, match="schema_version"):
        _validate_metadata(m)


def test_rejects_bad_run_id_shape():
    m = _good_meta()
    m["run_id"] = "2026-05-14T12:00:00--test"
    with pytest.raises(ValueError, match="run_id"):
        _validate_metadata(m)


def test_rejects_bad_collision_suffix():
    m = _good_meta()
    m["collision_suffix"] = 1
    with pytest.raises(ValueError, match="collision_suffix"):
        _validate_metadata(m)


def test_rejects_empty_search_query():
    m = _good_meta()
    m["search_query"] = "   "
    with pytest.raises(ValueError, match="search_query"):
        _validate_metadata(m)


def test_rejects_empty_label():
    m = _good_meta()
    m["search_term_label"] = ""
    with pytest.raises(ValueError, match="search_term_label"):
        _validate_metadata(m)


def test_rejects_non_iso_started_at():
    m = _good_meta()
    m["started_at"] = "2026/05/14 12:00:00"
    with pytest.raises(ValueError, match="started_at"):
        _validate_metadata(m)


def test_rejects_iso_without_z():
    m = _good_meta()
    m["finished_at"] = "2026-05-14T13:00:00"
    with pytest.raises(ValueError, match="finished_at"):
        _validate_metadata(m)


def test_rejects_negative_count():
    m = _good_meta()
    m["download_fail"] = -1
    with pytest.raises(ValueError, match="download_fail"):
        _validate_metadata(m)


def test_rejects_non_int_count():
    m = _good_meta()
    m["input_count"] = "100"
    with pytest.raises(ValueError, match="input_count"):
        _validate_metadata(m)


def test_rejects_non_string_merged_from():
    m = _good_meta()
    m["merged_from"] = ["ok", 123]
    with pytest.raises(ValueError, match="merged_from"):
        _validate_metadata(m)


def test_rejects_negative_error_count():
    m = _good_meta()
    m["error_summary"] = {"paywall_detected": -3}
    with pytest.raises(ValueError, match="error_summary"):
        _validate_metadata(m)


def test_rejects_pipeline_version_too_long():
    m = _good_meta()
    m["pipeline_version"] = "x" * 41
    with pytest.raises(ValueError, match="pipeline_version"):
        _validate_metadata(m)
