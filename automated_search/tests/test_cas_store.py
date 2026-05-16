#!/usr/bin/env python3
"""
Smoke tests for the content-addressable PDF store helpers.

Inputs:
- None (tests fabricate small files under tmp_path).

Outputs:
- None permanent.

Run with:
    cd automated_search && python3 -m pytest tests/test_cas_store.py
"""

import os
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "scripts" / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from ensure_pdf_store import (  # type: ignore[import-not-found]
    PdfStore,
    PdfStoreUnavailable,
    build_cas_index,
    cas_key_for_reference,
    cas_path_for_key,
    health_check,
    link_into_run,
    resolve_pdf_store,
    validate_store,
)


def test_resolve_pdf_store_requires_env(monkeypatch):
    monkeypatch.delenv("LIT_REVIEW_PDF_STORE", raising=False)
    with pytest.raises(PdfStoreUnavailable, match="LIT_REVIEW_PDF_STORE"):
        resolve_pdf_store()


def test_resolve_pdf_store_allows_missing_env(monkeypatch):
    monkeypatch.delenv("LIT_REVIEW_PDF_STORE", raising=False)
    assert resolve_pdf_store(allow_missing_env=True) is None


def test_resolve_pdf_store_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("LIT_REVIEW_PDF_STORE", str(tmp_path))
    store = resolve_pdf_store()
    assert store is not None
    assert store.root == tmp_path.resolve()
    assert store.pdfs_dir == (tmp_path / "pdfs").resolve()
    assert store.pdfs_dir.exists()


def test_validate_store_missing(tmp_path):
    with pytest.raises(PdfStoreUnavailable, match="does not exist"):
        validate_store(tmp_path / "nope")


def test_validate_store_not_writable(tmp_path):
    target = tmp_path / "readonly"
    target.mkdir()
    target.chmod(0o500)
    try:
        with pytest.raises(PdfStoreUnavailable, match="not writable"):
            validate_store(target)
    finally:
        target.chmod(0o700)


def test_health_check_passes(tmp_path):
    health_check(tmp_path)
    leftovers = list(tmp_path.glob(".lit_review_health_*"))
    assert leftovers == []


def test_cas_key_priority_pmid_over_doi():
    key = cas_key_for_reference({"pmid": "11111111", "doi": "10.1234/foo", "title": "Anything"})
    assert key == "pmid_11111111"


def test_cas_key_doi_when_no_pmid():
    key1 = cas_key_for_reference({"doi": "10.1234/Foo  "})
    key2 = cas_key_for_reference({"doi": "10.1234/foo"})
    assert key1 == key2
    assert key1.startswith("doi_")
    assert len(key1.split("_", 1)[1]) == 16


def test_cas_key_title_fallback():
    key = cas_key_for_reference({"title": "Some Example Title!!"})
    assert key is not None
    assert key.startswith("title_")


def test_cas_key_none_when_no_identifiers():
    assert cas_key_for_reference({}) is None


def test_build_cas_index_and_link(tmp_path):
    store = PdfStore(root=tmp_path, pdfs_dir=tmp_path / "pdfs")
    store.pdfs_dir.mkdir()
    pdf_a = store.pdfs_dir / "pmid_11111111.pdf"
    pdf_a.write_bytes(b"%PDF-1.4 fake")
    pdf_b = store.pdfs_dir / "doi_abc123.pdf"
    pdf_b.write_bytes(b"%PDF-1.4 fake")
    (store.pdfs_dir / "notes.txt").write_text("ignored", encoding="utf-8")

    index = build_cas_index(store)
    assert set(index.keys()) == {"pmid_11111111", "doi_abc123"}
    assert index["pmid_11111111"].name == "pmid_11111111.pdf"

    run_pdfs = tmp_path / "run" / "pdfs"
    link_into_run(pdf_a, run_pdfs, "pmid_11111111")
    linked = run_pdfs / "pmid_11111111.pdf"
    assert linked.exists() or linked.is_symlink()
    assert linked.read_bytes().startswith(b"%PDF-1.4")
