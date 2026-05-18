#!/usr/bin/env python3
"""
Headless terminal front end for the literature review pipeline.

This mirrors the desktop GUI's main actions for SSH/VPS use:
- Search and Pull via automated_search/scripts/auto_search_wrapper.py
- Resume Latest
- Refresh Catalog
- Add papers to Jon's List

Prompts show defaults in brackets; pressing Enter accepts the default.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = REPO_ROOT / "visualizer_nlp_lit_review" / "config.py"
RIS_PARSER_PATH = REPO_ROOT / "visualizer_nlp_lit_review" / "ris_parser.py"
RIS_SOURCE_DIR = REPO_ROOT / "visualizer_nlp_lit_review" / "RIS_source_files"
MANUAL_GROUPINGS_DIR = RIS_SOURCE_DIR / "manual_groupings"
JONS_LIST_PATH = MANUAL_GROUPINGS_DIR / "jons_list.txt"
CUSTOM_QUERY_REGISTRY_PATH = MANUAL_GROUPINGS_DIR / "custom_queries.json"
HELPERS_DIR = REPO_ROOT / "automated_search" / "scripts" / "helpers"
WRAPPER_PATH = REPO_ROOT / "automated_search" / "scripts" / "auto_search_wrapper.py"
REFRESH_PATH = REPO_ROOT / "automated_search" / "scripts" / "refresh_catalog.py"

DEFAULT_PDF_REMOTE = "gdrive:nlp_lit_review_1_papers/pdfs"
MAX_JONS_LIST_MATCHES = 250


def _section(title: str, body: str = "") -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    if body:
        print(body)


def _load_catalog() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if CONFIG_PATH.is_file():
        spec = importlib.util.spec_from_file_location("viz_config", CONFIG_PATH)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                terms = getattr(mod, "COMMON_SEARCH_TERMS", {})
            except Exception:
                terms = {}
            for name, info in terms.items():
                if isinstance(info, dict) and info.get("slug") and info.get("label") and info.get("query"):
                    entries.append({
                        "name": str(name),
                        "query": str(info["query"]),
                        "slug": str(info["slug"]),
                        "label": str(info["label"]),
                        "source_db": "pubmed",
                    })

    if CUSTOM_QUERY_REGISTRY_PATH.is_file():
        try:
            registry = json.loads(CUSTOM_QUERY_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception:
            registry = {}
        for entry in registry.get("queries", []):
            if isinstance(entry, dict) and entry.get("slug") and entry.get("label") and entry.get("query"):
                entries.append({
                    "name": str(entry.get("name") or entry["slug"]),
                    "query": str(entry["query"]),
                    "slug": str(entry["slug"]),
                    "label": str(entry["label"]),
                    "source_db": str(entry.get("source_db") or "pubmed"),
                })
    return entries


def _load_ris_parser_class() -> Any | None:
    if not RIS_PARSER_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("viz_ris_parser", RIS_PARSER_PATH)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return getattr(mod, "RISParser", None)


def _find_newest_master_ris() -> Path | None:
    if not RIS_SOURCE_DIR.is_dir():
        return None
    candidates = [
        p for p in RIS_SOURCE_DIR.glob("pubmed*.txt")
        if p.is_file() and ".bak" not in p.name and not p.name.endswith(".backup")
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _normalize_lookup_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _ris_value(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _paper_lookup_key(paper: Any) -> str:
    doi = _normalize_lookup_text(getattr(paper, "doi", ""))
    if doi:
        return f"doi:{doi}"
    return f"title:{_normalize_lookup_text(getattr(paper, 'title', ''))}"


def _query_name_from_label(label: str, slug: str = "") -> str:
    raw = slug or label
    raw = raw.replace("(", " ").replace(")", " ")
    return re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_") or "Custom_Query"


def _prompt(label: str, default: str = "", *, required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        if not required:
            return ""
        print("Required.")


def _confirm(label: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{label} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def _choose(label: str, choices: list[str], default_index: int = 0, *, prompt: str | None = None) -> int:
    for idx, choice in enumerate(choices, start=1):
        marker = " (default)" if idx - 1 == default_index else ""
        print(f"{idx}. {choice} {marker}".rstrip())
    while True:
        value = input(prompt if prompt is not None else f"{label}: ").strip().lower()
        if not value:
            return default_index
        if value in {"q", "quit"}:
            return -1
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return int(value) - 1
        print("Enter a listed number, or q to cancel.")


def _shorten(value: str, width: int = 96) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= width:
        return value
    return value[: width - 3].rstrip() + "..."


def _gui_default_state() -> dict[str, str]:
    catalog = _load_catalog()
    entry = catalog[0] if catalog else None
    master_ris = _find_newest_master_ris()
    return {
        "catalog": entry["name"] if entry else "Custom",
        "database": "pubmed",
        "base_query": entry["query"] if entry else "",
        "additional_terms": "",
        "label": entry["label"] if entry else "",
        "slug": entry["slug"] if entry else "",
        "ncbi_email": os.environ.get("NCBI_EMAIL", ""),
        "pdf_remote": os.environ.get("LIT_REVIEW_PDF_REMOTE", DEFAULT_PDF_REMOTE),
        "ncbi_api_key": "set" if os.environ.get("NCBI_API_KEY") else "",
        "insecure_ssl": (
            "enabled"
            if os.environ.get("LIT_REVIEW_ENTREZ_INSECURE_SSL", "").strip().lower() in {"1", "true", "yes"}
            else "disabled"
        ),
        "jons_list": str(JONS_LIST_PATH),
        "paper_index": master_ris.name if master_ris else "No pubmed*.txt master RIS found",
    }


def _print_gui_snapshot() -> None:
    state = _gui_default_state()
    _section(
        "Lit Review Pipeline",
        "Terminal workflow for running the literature review pipeline over SSH.\n"
        "This screen shows the current default fields before you choose an action.\n"
        "Press Enter at prompts to keep the shown default.",
    )
    print("Search settings")
    print(f"  A. Catalog entry:       {state['catalog']}")
    print(f"  B. Database:            {state['database']}")
    print()
    print("Query")
    print(f"  C. Base query:          {_shorten(state['base_query']) if state['base_query'] else '(custom query required)'}")
    print(f"  D. Additional terms:    {state['additional_terms'] or '(blank)'}")
    print("                          ANDed with base as: (base) AND (extra)")
    print(f"  E. Label / node text:   {state['label'] or '(custom label required)'}")
    print("                          Exact string stamped into RN field and used as a branch node.")
    print(f"  F. Slug:                {state['slug'] or '(custom slug required)'}")
    print("                          Used for run folder name.")
    print()
    print("Environment")
    print(f"  G. NCBI_EMAIL:          {state['ncbi_email'] or '(blank)'}")
    print(f"  H. LIT_REVIEW_PDF_REMOTE: {state['pdf_remote']}")
    print(f"  I. NCBI_API_KEY:        {state['ncbi_api_key'] or '(blank, optional)'}")
    print(f"  J. Insecure SSL:        {state['insecure_ssl']}")
    print()
    print("Jon's List")
    print(f"  K. Paper index:         {state['paper_index']}")
    print(f"  L. Output file:         {state['jons_list']}")
    print()


def _parse_number_selection(value: str, max_number: int) -> list[int]:
    """Parse selections like '1', '1,3,5', or '2-4' into zero-based indexes."""
    indexes: list[int] = []
    seen: set[int] = set()
    for raw_part in value.replace(" ", "").split(","):
        if not raw_part:
            continue
        if "-" in raw_part:
            start_raw, end_raw = raw_part.split("-", 1)
            if not start_raw.isdigit() or not end_raw.isdigit():
                raise ValueError(raw_part)
            start, end = int(start_raw), int(end_raw)
            if start > end:
                start, end = end, start
            numbers = range(start, end + 1)
        else:
            if not raw_part.isdigit():
                raise ValueError(raw_part)
            numbers = [int(raw_part)]
        for number in numbers:
            if number < 1 or number > max_number:
                raise ValueError(str(number))
            idx = number - 1
            if idx not in seen:
                indexes.append(idx)
                seen.add(idx)
    return indexes


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    _section(
        "Environment",
        "These match the GUI Environment panel. Press Enter to accept each default.",
    )
    email = _prompt("G. NCBI_EMAIL", os.environ.get("NCBI_EMAIL", ""))
    if email:
        env["NCBI_EMAIL"] = email

    print("LIT_REVIEW_PDF_REMOTE points the pipeline at the canonical PDF store.")
    pdf_remote = _prompt("H. LIT_REVIEW_PDF_REMOTE", os.environ.get("LIT_REVIEW_PDF_REMOTE", DEFAULT_PDF_REMOTE))
    if pdf_remote:
        env["LIT_REVIEW_PDF_REMOTE"] = pdf_remote

    print("NCBI_API_KEY is optional but improves NCBI E-utilities rate limits when set.")
    api_key = _prompt("I. NCBI_API_KEY optional", os.environ.get("NCBI_API_KEY", ""))
    if api_key:
        env["NCBI_API_KEY"] = api_key

    print("Insecure SSL for NCBI is only for networks that intercept TLS certificates.")
    insecure_default = os.environ.get("LIT_REVIEW_ENTREZ_INSECURE_SSL", "").strip().lower() in {"1", "true", "yes"}
    if _confirm("J. Insecure SSL for NCBI", insecure_default):
        env["LIT_REVIEW_ENTREZ_INSECURE_SSL"] = "1"
    else:
        env.pop("LIT_REVIEW_ENTREZ_INSECURE_SSL", None)

    return env


def _run(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print("\n" + "-" * 60)
    print("Running:")
    print(" ".join(cmd))
    print("-" * 60)
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    print("-" * 60)
    print(f"Done (exit {proc.returncode})")
    return proc.returncode


def _register_custom_query_node(*, query: str, slug: str, label: str, source_db: str) -> None:
    MANUAL_GROUPINGS_DIR.mkdir(parents=True, exist_ok=True)
    if CUSTOM_QUERY_REGISTRY_PATH.is_file():
        try:
            registry = json.loads(CUSTOM_QUERY_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception:
            registry = {}
    else:
        registry = {}

    entries = registry.get("queries", [])
    if not isinstance(entries, list):
        entries = []

    name = _query_name_from_label(label, slug)
    new_entry = {
        "name": name,
        "query": query,
        "slug": slug,
        "label": label,
        "source_db": source_db,
    }

    for idx, entry in enumerate(entries):
        if isinstance(entry, dict) and (
            entry.get("label") == label or entry.get("slug") == slug or entry.get("name") == name
        ):
            entries[idx] = new_entry
            break
    else:
        entries.append(new_entry)

    registry["queries"] = entries
    CUSTOM_QUERY_REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"Registered custom visualizer query node: {name} ({label})")


def search_and_pull(*, dry_run: bool = False) -> None:
    catalog = _load_catalog()
    _section(
        "Search Settings",
        "Choose a saved catalog entry or choose Custom.\n"
        "Press Enter to use the default catalog entry.",
    )
    choices = [f"{entry['name']} - {entry['label']}" for entry in catalog] + ["Custom PubMed query"]
    idx = _choose("A. Catalog entry / query source", choices, 0 if catalog else len(choices) - 1)
    if idx < 0:
        return

    is_custom = idx == len(choices) - 1
    if is_custom:
        _section(
            "Query",
            "Base query is the PubMed query string.\n"
            "Label is the exact string stamped into the RN field and becomes a branch node in the visualizer.\n"
            "Slug is used for the run folder name.",
        )
        base_q = _prompt("C. Base PubMed query", required=True)
        source_db = _prompt("B. Database", "pubmed")
        label_default = ""
        slug_default = ""
    else:
        entry = catalog[idx]
        base_q = entry["query"]
        source_db = entry.get("source_db") or "pubmed"
        label_default = entry["label"]
        slug_default = entry["slug"]
        print(f"\nBase query default:\n{base_q}\n")

    print("Additional terms are ANDed with the base query as: (base) AND (extra).")
    extra = _prompt("D. Additional terms, ANDed with base", "")
    final_q = f"({base_q}) AND ({extra})" if extra else base_q
    label_auto = f"{label_default} AND {extra}" if label_default and extra else label_default
    print("Label -> visualizer node. Exact string stamped into RN field -> becomes a branch node.")
    label = _prompt("E. Label / node text", label_auto, required=True)
    print("Slug is used for run folder name.")
    slug = _prompt("F. Slug", slug_default or _query_name_from_label(label).lower(), required=True)
    source_db = _prompt("B. Database", source_db or "pubmed")

    if is_custom:
        _register_custom_query_node(query=final_q, slug=slug, label=label, source_db=source_db)

    cmd = [
        sys.executable,
        "-u",
        str(WRAPPER_PATH),
        "--query",
        final_q,
        "--slug",
        slug,
        "--label",
        label,
        "--source-db",
        source_db,
    ]
    if dry_run:
        cmd.append("--dry-run")

    env = _build_env()
    if _confirm("Run now", True):
        _run(cmd, env)


def resume_latest() -> None:
    cmd = [sys.executable, "-u", str(WRAPPER_PATH), "--resume-latest"]
    env = _build_env()
    if _confirm("Resume latest run now", True):
        _run(cmd, env)


def refresh_catalog() -> None:
    cmd = [sys.executable, "-u", str(REFRESH_PATH)]
    if _confirm("Refresh catalog now", True):
        _run(cmd, os.environ.copy())


def _existing_jons_list_keys() -> set[str]:
    parser_cls = _load_ris_parser_class()
    if parser_cls is None or not JONS_LIST_PATH.is_file():
        return set()
    try:
        papers = parser_cls(str(JONS_LIST_PATH)).parse()
    except Exception:
        return set()
    return {_paper_lookup_key(paper) for paper in papers if _paper_lookup_key(paper) != "title:"}


def _append_paper_to_jons_list(paper: Any) -> str:
    title = _ris_value(getattr(paper, "title", ""))
    doi = _ris_value(getattr(paper, "doi", ""))
    year = _ris_value(getattr(paper, "year", ""))
    paper_id = _ris_value(getattr(paper, "id", ""))

    MANUAL_GROUPINGS_DIR.mkdir(parents=True, exist_ok=True)
    needs_leading_newline = JONS_LIST_PATH.exists() and JONS_LIST_PATH.stat().st_size > 0
    lines = []
    if needs_leading_newline:
        lines.append("")
    lines.append("TY  - JOUR")
    if title:
        lines.append(f"TI  - {title}")
    if doi:
        lines.append(f"DO  - {doi}")
    if year:
        lines.append(f"PY  - {year}")
    if paper_id:
        lines.append(f"ID  - {paper_id}")
    lines.append("ER  -")

    with JONS_LIST_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return title or doi


def _search_papers_for_jons_list(papers: list[Any], query: str) -> list[Any]:
    terms = _normalize_lookup_text(query).split()
    matches = []
    for paper in papers:
        haystack = " ".join([
            _normalize_lookup_text(getattr(paper, "title", "")),
            _normalize_lookup_text(getattr(paper, "abstract", "")),
            _normalize_lookup_text(getattr(paper, "doi", "")),
            _normalize_lookup_text(" ".join(getattr(paper, "authors", []) or [])),
            _normalize_lookup_text(str(getattr(paper, "year", "") or "")),
        ])
        if all(term in haystack for term in terms):
            matches.append(paper)
        if len(matches) >= MAX_JONS_LIST_MATCHES:
            break
    return matches


def add_to_jons_list() -> None:
    parser_cls = _load_ris_parser_class()
    master_ris = _find_newest_master_ris()
    if parser_cls is None:
        print(f"RIS parser not found: {RIS_PARSER_PATH}")
        return
    if master_ris is None:
        print(f"No pubmed*.txt master RIS found in {RIS_SOURCE_DIR}")
        return

    papers = parser_cls(str(master_ris)).parse()
    _section(
        "Jon's List",
        "Find paper: enter title text, author, DOI, year, or abstract terms.\n"
        "The terminal will show numbered matching titles. Enter one number, multiple numbers\n"
        "such as 1,3,5, or a range such as 2-4 to add papers to Jon's List.\n"
        f"Loaded {len(papers)} papers from {master_ris.name}.",
    )

    while True:
        query = _prompt("Find paper", required=True)
        matches = _search_papers_for_jons_list(papers, query)

        if not matches:
            print("No matches.")
            if _confirm("Search again", True):
                continue
            return

        suffix = "showing first 250" if len(matches) == MAX_JONS_LIST_MATCHES else f"{len(matches)} found"
        print(f"\nSearch: {suffix}. Select number(s), then add to Jon's List.\n")
        for idx, paper in enumerate(matches, start=1):
            year = _ris_value(getattr(paper, "year", ""))
            title = _ris_value(getattr(paper, "title", ""))
            doi = _ris_value(getattr(paper, "doi", ""))
            authors = ", ".join((getattr(paper, "authors", []) or [])[:3])
            author_part = f" | {authors}" if authors else ""
            doi_part = f" | DOI: {doi}" if doi else ""
            year_part = f"{year} | " if year else ""
            print(f"{idx}. {year_part}{title}{author_part}{doi_part}")

        while True:
            raw_selection = input("\nAdd which number(s)? [q to cancel this search]: ").strip().lower()
            if raw_selection in {"q", "quit", ""}:
                selected_indexes = []
                break
            try:
                selected_indexes = _parse_number_selection(raw_selection, len(matches))
                if selected_indexes:
                    break
                print("Enter at least one number.")
            except ValueError:
                print("Use numbers from the list, comma-separated numbers like 1,3,5, or ranges like 2-4.")

        if selected_indexes:
            existing_keys = _existing_jons_list_keys()
            added: list[str] = []
            skipped: list[str] = []
            invalid: list[str] = []
            for selected_idx in selected_indexes:
                paper = matches[selected_idx]
                title = _ris_value(getattr(paper, "title", ""))
                doi = _ris_value(getattr(paper, "doi", ""))
                if not title and not doi:
                    invalid.append(f"{selected_idx + 1}")
                    continue
                key = _paper_lookup_key(paper)
                if key in existing_keys:
                    skipped.append(title or doi)
                    continue
                added_label = _append_paper_to_jons_list(paper)
                added.append(added_label)
                existing_keys.add(key)

            if added:
                print("\nAdded to Jon's List:")
                for item in added:
                    print(f"- {item}")
            if skipped:
                print("\nAlready in Jon's List, skipped:")
                for item in skipped:
                    print(f"- {item}")
            if invalid:
                print(f"\nSkipped invalid paper(s) with neither title nor DOI: {', '.join(invalid)}")

        if not _confirm("Add/search another paper for Jon's List", True):
            print("Finished Jon's List edits.")
            return


def main() -> int:
    actions = [
        ("Search and Pull", lambda: search_and_pull(dry_run=False)),
        ("Resume Latest", resume_latest),
        ("Refresh Catalog", refresh_catalog),
        ("Find Paper / Add to Jon's List", add_to_jons_list),
        ("Dry Run Search", lambda: search_and_pull(dry_run=True)),
        ("Quit", None),
    ]

    while True:
        _print_gui_snapshot()
        print("Actions - Pick a number")
        idx = _choose("Action", [name for name, _func in actions], 0, prompt="> ")
        if idx < 0 or actions[idx][1] is None:
            return 0
        try:
            actions[idx][1]()
        except KeyboardInterrupt:
            print("\nCanceled.")
        except Exception as exc:
            print(f"ERROR: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
