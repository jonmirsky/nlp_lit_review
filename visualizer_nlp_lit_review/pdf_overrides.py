"""
Manual PDF override/suppression registry for the visualizer.

The registry is intentionally small and explicit.  Paper identity is based on
PMID, then DOI, then a normalized title hash; EndNote folder IDs and filenames
are treated only as locator strings, never identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Set

from config import MANUAL_GROUPINGS_FOLDER


PDF_OVERRIDES_FILENAME = "pdf_overrides.json"


def normalize_doi(doi: str) -> str:
    value = (doi or "").strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip()


def normalize_title(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def title_hash(title: str) -> str:
    normalized = normalize_title(title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def canonical_paper_key(paper: Any) -> str:
    pmid = str(getattr(paper, "pmid", "") or "").strip()
    if pmid:
        return f"pmid:{pmid}"

    doi = normalize_doi(str(getattr(paper, "doi", "") or ""))
    if doi:
        return f"doi:{doi}"

    return f"title:{title_hash(str(getattr(paper, 'title', '') or ''))}"


def default_overrides_path() -> Path:
    return Path(MANUAL_GROUPINGS_FOLDER) / PDF_OVERRIDES_FILENAME


def load_pdf_overrides(path: Path | None = None) -> Dict[str, Any]:
    registry_path = path or default_overrides_path()
    if not registry_path.is_file():
        return {"bad_pdf_paths": [], "paper_pdf_overrides": {}}

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"Warning: could not load PDF override registry {registry_path}: {exc}")
        return {"bad_pdf_paths": [], "paper_pdf_overrides": {}}

    if not isinstance(data, dict):
        return {"bad_pdf_paths": [], "paper_pdf_overrides": {}}

    bad_pdf_paths = data.get("bad_pdf_paths", [])
    paper_pdf_overrides = data.get("paper_pdf_overrides", {})
    return {
        "bad_pdf_paths": bad_pdf_paths if isinstance(bad_pdf_paths, list) else [],
        "paper_pdf_overrides": paper_pdf_overrides if isinstance(paper_pdf_overrides, dict) else {},
    }


def bad_pdf_paths(path: Path | None = None) -> Set[str]:
    return {str(p) for p in load_pdf_overrides(path).get("bad_pdf_paths", []) if str(p)}


def apply_pdf_overrides(papers: Iterable[Any], path: Path | None = None) -> int:
    overrides = load_pdf_overrides(path)
    known_bad = {str(p) for p in overrides["bad_pdf_paths"] if str(p)}
    paper_overrides = {
        str(key): "" if value is None else str(value)
        for key, value in overrides["paper_pdf_overrides"].items()
    }

    changed = 0
    for paper in papers:
        current_path = str(getattr(paper, "pdf_path", "") or "")
        new_path = current_path

        if current_path in known_bad:
            new_path = ""

        paper_key = canonical_paper_key(paper)
        if paper_key in paper_overrides:
            new_path = paper_overrides[paper_key]

        if new_path != current_path:
            setattr(paper, "pdf_path", new_path)
            changed += 1

    return changed


def save_pdf_overrides(data: Dict[str, Any], path: Path | None = None) -> None:
    registry_path = path or default_overrides_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    bad_paths = sorted({str(p) for p in data.get("bad_pdf_paths", []) if str(p)})
    paper_overrides = {
        str(k): "" if v is None else str(v)
        for k, v in sorted(data.get("paper_pdf_overrides", {}).items())
    }
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "bad_pdf_paths": bad_paths,
                "paper_pdf_overrides": paper_overrides,
            },
            f,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")
