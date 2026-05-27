#!/usr/bin/env python3
"""
Audit visualizer paper-to-PDF links for title/full-text mismatches.

The script uses the same query/RIS resolution path as the website, applies the
same manual PDF override registry, resolves local PDFs through PDFResolver when
possible, and inspects the first 1-3 pages with pdftotext.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

import requests

VISUALIZER_DIR = Path(__file__).resolve().parents[1]
if str(VISUALIZER_DIR) not in sys.path:
    sys.path.insert(0, str(VISUALIZER_DIR))

from config import R2_BUCKET_NAME, get_queries_with_ris_files
from overlap_calculator import OverlapCalculator
from pdf_overrides import (
    apply_pdf_overrides,
    canonical_paper_key,
    load_pdf_overrides,
    normalize_title,
    save_pdf_overrides,
)
from pdf_resolver import PDFResolver


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "based", "by", "for", "from",
    "in", "into", "is", "of", "on", "or", "the", "to", "using", "with",
    "study", "review", "analysis", "development", "validation",
}


def title_tokens(text: str) -> Set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_title(text))
        if len(token) > 2 and token not in STOPWORDS
    }


def first_author_surname(paper: Any) -> str:
    if not getattr(paper, "authors", None):
        return ""
    author = str(paper.authors[0])
    if "," in author:
        return author.split(",", 1)[0].strip().lower()
    parts = author.split()
    return parts[-1].strip().lower() if parts else ""


def extract_pdf_text(pdf_path: str, pages: int) -> tuple[str, str]:
    if shutil.which("pdftotext") is None:
        return "", "pdftotext not found"
    with tempfile.NamedTemporaryFile(suffix=".txt") as out:
        cmd = [
            "pdftotext",
            "-f",
            "1",
            "-l",
            str(max(1, min(3, pages))),
            "-layout",
            pdf_path,
            out.name,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            return "", (result.stderr or result.stdout or f"pdftotext exited {result.returncode}").strip()
        return Path(out.name).read_text(encoding="utf-8", errors="ignore"), ""


def maybe_check_url(url: str) -> tuple[bool | None, str]:
    try:
        response = requests.head(url, allow_redirects=True, timeout=8)
    except requests.RequestException as exc:
        return None, type(exc).__name__
    return response.status_code == 200, str(response.status_code)


def r2_urls_for_internal_path(resolver: PDFResolver, pdf_path: str) -> List[str]:
    with contextlib.redirect_stdout(io.StringIO()):
        return resolver.get_all_r2_urls(pdf_path)


def score_pdf_text(paper: Any, text: str) -> Dict[str, Any]:
    text_l = text.lower()
    metadata_title_tokens = title_tokens(getattr(paper, "title", ""))
    overlap_count = sum(1 for token in metadata_title_tokens if token in text_l)
    title_overlap = overlap_count / len(metadata_title_tokens) if metadata_title_tokens else 0.0

    doi = str(getattr(paper, "doi", "") or "").strip().lower()
    doi_present = bool(doi and doi in text_l)
    pmid = str(getattr(paper, "pmid", "") or "").strip()
    pmid_present = bool(pmid and pmid in text)
    author = first_author_surname(paper)
    author_present = bool(author and author in text_l)
    year = str(getattr(paper, "year", "") or "").strip()
    year_present = bool(year and year in text)

    # A low metadata-title overlap plus title-looking text in the first page is
    # the pattern that caught the Yamagishi -> Real-MedNLP mismatch.
    first_lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 20][:12]
    best_line_overlap = 0.0
    best_line = ""
    for line in first_lines:
        line_tokens = title_tokens(line)
        if not line_tokens:
            continue
        line_overlap = len(metadata_title_tokens & line_tokens) / len(metadata_title_tokens) if metadata_title_tokens else 0.0
        if line_overlap > best_line_overlap:
            best_line_overlap = line_overlap
            best_line = line
    obvious_unrelated_title = bool(first_lines and title_overlap < 0.25 and best_line_overlap < 0.25)

    score = 0
    score += 3 if title_overlap >= 0.65 else 1 if title_overlap >= 0.35 else 0
    score += 2 if doi_present else 0
    score += 2 if pmid_present else 0
    score += 1 if author_present else 0
    score += 1 if year_present else 0
    score -= 3 if obvious_unrelated_title else 0

    return {
        "score": score,
        "doi_present": doi_present,
        "pmid_present": pmid_present,
        "title_token_overlap": round(title_overlap, 3),
        "first_author_surname_present": author_present,
        "publication_year_present": year_present,
        "obvious_unrelated_title_detected": obvious_unrelated_title,
        "candidate_pdf_title_line": best_line[:300],
    }


def classify(pdf_path: str, resolved_path: str, text: str, error: str, checks: Dict[str, Any]) -> str:
    if not pdf_path:
        return "missing_pdf"
    if error:
        return "unreadable_pdf"
    if not resolved_path and pdf_path.startswith(("http://", "https://")):
        return "manual_review"
    if resolved_path.startswith(("http://", "https://")):
        return "manual_review"
    if not resolved_path:
        return "missing_pdf"
    if checks.get("obvious_unrelated_title_detected"):
        return "likely_mismatch"
    if checks.get("score", 0) >= 4 or checks.get("title_token_overlap", 0) >= 0.65:
        return "ok"
    if checks.get("score", 0) <= 1 and checks.get("title_token_overlap", 0) < 0.35:
        return "likely_mismatch"
    return "weak_match"


def paper_row(paper: Any, resolver: PDFResolver, pages: int, check_r2: bool = False) -> Dict[str, Any]:
    pdf_path = str(getattr(paper, "pdf_path", "") or "")
    resolved_path = ""
    text = ""
    error = ""
    url_status = ""

    if pdf_path.startswith(("http://", "https://")):
        ok, status = maybe_check_url(pdf_path)
        url_status = status
        error = "" if ok else f"url_head_{status}"
    elif pdf_path:
        resolved = resolver.resolve(pdf_path)
        resolved_path = resolved or ""
        if resolved_path:
            text, error = extract_pdf_text(resolved_path, pages)
        elif check_r2:
            for r2_url in r2_urls_for_internal_path(resolver, pdf_path):
                ok, status = maybe_check_url(r2_url)
                url_status = status
                if ok:
                    resolved_path = r2_url
                    break

    checks = score_pdf_text(paper, text) if text else {
        "score": 0,
        "doi_present": False,
        "pmid_present": False,
        "title_token_overlap": 0.0,
        "first_author_surname_present": False,
        "publication_year_present": False,
        "obvious_unrelated_title_detected": False,
        "candidate_pdf_title_line": "",
    }
    classification = classify(pdf_path, resolved_path, text, error, checks)

    return {
        "classification": classification,
        "paper_key": canonical_paper_key(paper),
        "paper_id": getattr(paper, "id", ""),
        "title": getattr(paper, "title", ""),
        "doi": getattr(paper, "doi", ""),
        "pmid": getattr(paper, "pmid", ""),
        "year": getattr(paper, "year", ""),
        "first_author": first_author_surname(paper),
        "pdf_path": pdf_path,
        "resolved_pdf_path": resolved_path,
        "url_status": url_status,
        "error": error,
        **checks,
    }


def write_reports(rows: List[Dict[str, Any]], report_dir: Path, date_tag: str) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = report_dir / f"pdf_link_audit_{date_tag}.jsonl"
    csv_path = report_dir / f"pdf_link_audit_{date_tag}_summary.csv"

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    fieldnames = [
        "classification", "paper_key", "title", "doi", "pmid", "year",
        "first_author", "pdf_path", "resolved_pdf_path", "score",
        "title_token_overlap", "doi_present", "pmid_present",
        "first_author_surname_present", "publication_year_present",
        "obvious_unrelated_title_detected", "candidate_pdf_title_line", "error",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return jsonl_path, csv_path


def update_overrides_for_mismatches(rows: List[Dict[str, Any]]) -> int:
    data = load_pdf_overrides()
    existing = set(str(p) for p in data.get("bad_pdf_paths", []) if str(p))
    added = 0
    for row in rows:
        if row["classification"] != "likely_mismatch":
            continue
        pdf_path = row.get("pdf_path") or ""
        if not pdf_path or pdf_path in existing:
            continue
        existing.add(pdf_path)
        added += 1
    if added:
        data["bad_pdf_paths"] = sorted(existing)
        save_pdf_overrides(data)
    return added


def suppressed_row(paper: Any) -> Dict[str, Any]:
    """Emit a minimal row for a paper whose PDF was suppressed by bad_pdf_paths."""
    return {
        "classification": "suppressed_by_override",
        "paper_key": canonical_paper_key(paper),
        "paper_id": getattr(paper, "id", ""),
        "title": getattr(paper, "title", ""),
        "doi": getattr(paper, "doi", ""),
        "pmid": getattr(paper, "pmid", ""),
        "year": getattr(paper, "year", ""),
        "first_author": first_author_surname(paper),
        "pdf_path": getattr(paper, "_original_pdf_path", ""),
        "resolved_pdf_path": "",
        "url_status": "",
        "error": "",
        "score": 0,
        "doi_present": False,
        "pmid_present": False,
        "title_token_overlap": 0.0,
        "first_author_surname_present": False,
        "publication_year_present": False,
        "obvious_unrelated_title_detected": False,
        "candidate_pdf_title_line": "",
    }


def replaced_row(paper: Any, new_pdf_path: str) -> Dict[str, Any]:
    """Emit a minimal row for a paper whose PDF was replaced via paper_pdf_overrides."""
    return {
        "classification": "replaced_by_override",
        "paper_key": canonical_paper_key(paper),
        "paper_id": getattr(paper, "id", ""),
        "title": getattr(paper, "title", ""),
        "doi": getattr(paper, "doi", ""),
        "pmid": getattr(paper, "pmid", ""),
        "year": getattr(paper, "year", ""),
        "first_author": first_author_surname(paper),
        "pdf_path": new_pdf_path,
        "resolved_pdf_path": "",
        "url_status": "",
        "error": "",
        "score": 0,
        "doi_present": False,
        "pmid_present": False,
        "title_token_overlap": 0.0,
        "first_author_surname_present": False,
        "publication_year_present": False,
        "obvious_unrelated_title_detected": False,
        "candidate_pdf_title_line": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit visualizer PDF links.")
    parser.add_argument("--pages", type=int, default=3, help="First pages to extract with pdftotext, max 3.")
    parser.add_argument("--limit", type=int, default=0, help="Debug limit after applying website loading rules.")
    parser.add_argument("--check-r2", action="store_true", help="Also HEAD-check R2 URLs for locally unresolved internal-pdf links. Slower.")
    parser.add_argument("--update-overrides", action="store_true", help="Add likely_mismatch pdf_path values to pdf_overrides.json.")
    parser.add_argument(
        "--output-tag",
        help=(
            "Report filename tag. Defaults to a timestamp "
            "(YYYY_MM_DD_HHMMSS) so smoke tests do not overwrite full audits."
        ),
    )
    args = parser.parse_args()

    resolved_queries = get_queries_with_ris_files()
    calculator = OverlapCalculator(resolved_queries)
    calculator.load_papers_from_queries()

    # Capture original pdf_path values and override sets before mutating papers
    overrides_data = load_pdf_overrides()
    bad_paths: Set[str] = {str(p) for p in overrides_data.get("bad_pdf_paths", []) if p}
    paper_overrides_map: Dict[str, str] = {
        str(k): "" if v is None else str(v)
        for k, v in overrides_data.get("paper_pdf_overrides", {}).items()
    }
    for paper in calculator.all_papers:
        paper._original_pdf_path = str(getattr(paper, "pdf_path", "") or "")  # type: ignore[attr-defined]

    changed = apply_pdf_overrides(calculator.all_papers)
    if changed:
        print(f"Applied {changed} existing PDF override/suppression rule(s)")

    all_papers = calculator.all_papers[: args.limit] if args.limit else calculator.all_papers
    resolver = PDFResolver()
    rows: List[Dict[str, Any]] = []
    for paper in all_papers:
        orig = getattr(paper, "_original_pdf_path", "")
        key = canonical_paper_key(paper)
        if orig and orig in bad_paths:
            rows.append(suppressed_row(paper))
        elif key in paper_overrides_map and str(getattr(paper, "pdf_path", "") or "") != orig:
            rows.append(replaced_row(paper, str(getattr(paper, "pdf_path", "") or "")))
        else:
            rows.append(paper_row(paper, resolver, args.pages, check_r2=args.check_r2))

    if args.update_overrides:
        added = update_overrides_for_mismatches(rows)
        print(f"Added {added} likely_mismatch suppression(s) to pdf_overrides.json")

    date_tag = args.output_tag or datetime.now().strftime("%Y_%m_%d_%H%M%S")
    jsonl_path, csv_path = write_reports(rows, VISUALIZER_DIR / "audit_reports", date_tag)
    counts = Counter(row["classification"] for row in rows)
    print(f"Wrote {jsonl_path}")
    print(f"Wrote {csv_path}")
    print("Classifications:")
    for key in (
        "ok", "missing_pdf", "unreadable_pdf", "weak_match",
        "likely_mismatch", "manual_review",
        "suppressed_by_override", "replaced_by_override",
    ):
        print(f"  {key}: {counts.get(key, 0)}")
    if R2_BUCKET_NAME and not args.check_r2:
        print("Skipped R2 HEAD checks. Re-run with --check-r2 for targeted/cloud availability checks.")
    elif not R2_BUCKET_NAME:
        print("R2 bucket is not configured; URL checks were limited to direct http(s) pdf_path values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
