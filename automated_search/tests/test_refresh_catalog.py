#!/usr/bin/env python3
"""Tests for refresh query bookkeeping."""

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import refresh_catalog  # type: ignore[import-not-found]


def test_refresh_terms_include_common_and_custom_queries(tmp_path, monkeypatch):
    config_dir = tmp_path / "visualizer_nlp_lit_review"
    manual_dir = config_dir / "RIS_source_files" / "manual_groupings"
    manual_dir.mkdir(parents=True)
    (config_dir / "config.py").write_text(
        "COMMON_SEARCH_TERMS = {\n"
        "    'NLP_Extraction': {\n"
        "        'query': 'nlp query',\n"
        "        'slug': 'nlp_extraction',\n"
        "        'label': '( NLP extraction )',\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    (manual_dir / "custom_queries.json").write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "name": "Custom_Query",
                        "query": "custom query",
                        "slug": "custom_query",
                        "label": "( Custom query )",
                        "source_db": "pubmed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(refresh_catalog, "_repo_root", lambda: tmp_path)

    terms = refresh_catalog._load_refresh_terms()
    entries = refresh_catalog._iter_refresh_entries(terms)

    assert "NLP_Extraction" in terms
    assert "Custom_Query" in terms
    assert ("NLP_Extraction", "nlp query", "nlp_extraction", "( NLP extraction )", "pubmed") in entries
    assert ("Custom_Query", "custom query", "custom_query", "( Custom query )", "pubmed") in entries
