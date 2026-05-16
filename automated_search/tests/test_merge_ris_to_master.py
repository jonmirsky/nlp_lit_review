#!/usr/bin/env python3
"""Tests for merging query labels into the master RIS."""

import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "scripts" / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from merge_ris_to_master import merge_ris_to_master  # type: ignore[import-not-found]


def test_duplicate_reference_gets_new_rn_label(tmp_path):
    ris_dir = tmp_path / "RIS_source_files"
    ris_dir.mkdir()
    master = ris_dir / "pubmed_NLP_v4_old.txt"
    master.write_text(
        "TY  - JOUR\n"
        "TI  - Shared Paper\n"
        "DO  - 10.1000/shared\n"
        "RN  - ( NLP extraction )\n"
        "ER  -\n\n",
        encoding="utf-8",
    )
    incoming = tmp_path / "incoming.ris"
    incoming.write_text(
        "TY  - JOUR\n"
        "TI  - Shared Paper\n"
        "DO  - 10.1000/shared\n"
        "RN  - ( Custom query )\n"
        "ER  -\n\n",
        encoding="utf-8",
    )

    out = merge_ris_to_master(incoming, ris_dir, output_path=ris_dir / "pubmed_NLP_v4_new.txt")
    text = out.read_text(encoding="utf-8")

    assert text.count("TY  - JOUR") == 1
    assert "RN  - ( NLP extraction )" in text
    assert "RN  - ( Custom query )" in text


def test_duplicate_reference_does_not_repeat_existing_rn_label(tmp_path):
    ris_dir = tmp_path / "RIS_source_files"
    ris_dir.mkdir()
    master = ris_dir / "pubmed_NLP_v4_old.txt"
    master.write_text(
        "TY  - JOUR\n"
        "TI  - Shared Paper\n"
        "AN  - 12345\n"
        "RN  - ( Same query )\n"
        "ER  -\n\n",
        encoding="utf-8",
    )
    incoming = tmp_path / "incoming.ris"
    incoming.write_text(
        "TY  - JOUR\n"
        "TI  - Shared Paper\n"
        "AN  - 12345\n"
        "RN  - ( Same query )\n"
        "ER  -\n\n",
        encoding="utf-8",
    )

    out = merge_ris_to_master(incoming, ris_dir, output_path=ris_dir / "pubmed_NLP_v4_new.txt")
    text = out.read_text(encoding="utf-8")

    assert text.count("TY  - JOUR") == 1
    assert text.count("RN  - ( Same query )") == 1
