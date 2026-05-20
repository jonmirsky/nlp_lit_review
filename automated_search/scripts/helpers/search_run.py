#!/usr/bin/env python3
"""
SearchRun dataclass, run-folder bootstrap, metadata I/O, Entrez fetch, progress log.

Inputs:
- CLI arguments / function kwargs from automated_search/scripts/auto_search_wrapper.py:
  search query, slug, RN label, source database, optional input RIS or found RIS,
  dry-run flag.
- NCBI_EMAIL / NCBI_API_KEY environment variables (Entrez fetch path).
- LIT_REVIEW_PDF_REMOTE environment variable (recorded in metadata.json; defaults to gdrive:nlp_lit_review_1_papers/pdfs).

Outputs (per run, under automated_search/searches/<run_id>/):
- metadata.json          (atomic-write; schema described in automated_search/SCHEMA.md)
- input.ris              (fetched from Entrez or copied from --input-ris)
- found/found.ris        (created later by V4 / wrapper steps; this module only mkdir's the parents)
- found/pdfs/            (symlinks; populated by V4)
- missing/still_missing.ris (created by V4)
- progress.jsonl         (line-appended by V4 via append_progress)
- errors.jsonl           (line-appended by V4 on failures)
- log.txt                (created/appended by V4's logging handler)
- summary.md             (rendered by wrapper Step 3 tail)

Naming convention:
- run_id = "YYYY_MM_DD_HHMMSS__<slug>", UTC, second precision. Auto-suffixed
  with "-2", "-3", ... when the folder already exists (up to "-99").
- Slug normalization: lowercase, [^a-z0-9_] -> "_", strip leading/trailing "_".
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Literal, Optional


SCHEMA_VERSION = 2
GENERATOR_PATH = "automated_search/scripts/auto_search_wrapper.py"

REPO_ROOT = Path(__file__).resolve().parents[3]
SEARCHES_DIR = REPO_ROOT / "automated_search" / "searches"


QuerySource = Literal["entrez", "manual_export", "byo_found_ris"]


# --------------------------------------------------------------------------- #
# SearchRun dataclass
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SearchRun:
    root: Path
    run_id: str
    metadata_path: Path
    input_all_ris: Path
    input_ris: Path
    found_dir: Path
    found_ris: Path
    pdfs_dir: Path
    missing_dir: Path
    missing_ris: Path
    progress_path: Path
    errors_path: Path
    log_path: Path
    summary_path: Path

    @classmethod
    def for_root(cls, root: Path) -> "SearchRun":
        """Construct a SearchRun pointing at an existing run-folder."""
        return cls(
            root=root,
            run_id=root.name,
            metadata_path=root / "metadata.json",
            input_all_ris=root / "input_all.ris",
            input_ris=root / "input.ris",
            found_dir=root / "found",
            found_ris=root / "found" / "found.ris",
            pdfs_dir=root / "found" / "pdfs",
            missing_dir=root / "missing",
            missing_ris=root / "missing" / "still_missing.ris",
            progress_path=root / "progress.jsonl",
            errors_path=root / "errors.jsonl",
            log_path=root / "log.txt",
            summary_path=root / "summary.md",
        )


# --------------------------------------------------------------------------- #
# Slug + timestamp helpers
# --------------------------------------------------------------------------- #

_SLUG_VALID = re.compile(r"[^a-z0-9_]")


def normalize_slug(raw: str) -> str:
    """Lowercase, collapse non-alphanumerics to `_`, strip ends.

    Raises ValueError on empty results.
    """
    if not raw or not raw.strip():
        raise ValueError("Slug must be non-empty")
    slug = raw.strip().lower()
    slug = _SLUG_VALID.sub("_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        raise ValueError(f"Slug normalized to empty: {raw!r}")
    return slug


def utc_timestamp() -> str:
    """Return a second-precision UTC timestamp 'YYYY_MM_DD_HHMMSS'."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S")


def utc_iso_now() -> str:
    """Return ISO-8601 UTC timestamp ending in 'Z'."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def allocate_run_dir(
    slug: str,
    *,
    searches_dir: Path = SEARCHES_DIR,
    timestamp: Optional[str] = None,
) -> tuple[Path, Optional[int]]:
    """Pick a non-colliding `<ts>__<slug>[-N]/` folder and create it.

    Returns:
        (run_dir, collision_suffix). `collision_suffix` is None when no
        collision occurred, else the integer suffix that was applied.
    """
    ts = timestamp or utc_timestamp()
    base_name = f"{ts}__{slug}"
    candidate = searches_dir / base_name
    if not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate, None

    for n in range(2, 100):
        suffixed = searches_dir / f"{base_name}-{n}"
        if not suffixed.exists():
            suffixed.mkdir(parents=True, exist_ok=False)
            return suffixed, n

    raise RuntimeError(
        f"Could not allocate a non-colliding run folder under {searches_dir} "
        f"for {base_name!r} (tried -2 through -99)."
    )


# --------------------------------------------------------------------------- #
# Atomic metadata.json + minimal validator
# --------------------------------------------------------------------------- #

_REQUIRED_METADATA_KEYS = {
    "_generated_by",
    "schema_version",
    "run_id",
    "slug",
    "base_query",
    "query_hash",
    "collision_suffix",
    "search_query",
    "search_term_label",
    "source_db",
    "query_source",
    "started_at",
    "finished_at",
    "incremental_refresh",
    "refresh_anchor_run_id",
    "refresh_anchor_started_at",
    "pubmed_datetype",
    "pubmed_mindate",
    "input_count",
    "candidate_count_before_skip",
    "known_success_skip_count",
    "known_failure_skip_count",
    "candidate_count_after_skip",
    "download_success",
    "download_fail",
    "download_skipped_existing",
    "pdf_store_root",
    "pipeline_version",
    "merged_from",
    "error_summary",
    "r2_synced_at",
    "notes",
}

_VALID_SOURCE_DB = {"pubmed", "manual", "byo"}
_VALID_QUERY_SOURCE = {"entrez", "manual_export", "byo_found_ris"}
_RUN_ID_RE = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{6}__[a-z0-9_]+(-\d+)?$")
_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _validate_metadata(meta: Dict[str, Any]) -> None:
    """Schema v2 validator. Locks the contract documented in automated_search/SCHEMA.md.

    Raises ValueError with a concrete field name on violation.
    """
    if not isinstance(meta, dict):
        raise ValueError(f"metadata must be a dict; got {type(meta).__name__}")

    missing = _REQUIRED_METADATA_KEYS - meta.keys()
    if missing:
        raise ValueError(f"metadata.json missing required keys: {sorted(missing)}")

    extra = meta.keys() - _REQUIRED_METADATA_KEYS
    if extra:
        raise ValueError(f"metadata.json contains unknown keys (schema v2): {sorted(extra)}")

    if meta["_generated_by"] != GENERATOR_PATH:
        raise ValueError(f"_generated_by must be {GENERATOR_PATH!r}; got {meta['_generated_by']!r}")
    if meta["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}; got {meta['schema_version']!r}")
    if not isinstance(meta["run_id"], str) or not _RUN_ID_RE.match(meta["run_id"]):
        raise ValueError(f"run_id has invalid shape: {meta['run_id']!r}")

    if meta["collision_suffix"] is not None:
        if not isinstance(meta["collision_suffix"], int) or meta["collision_suffix"] < 2:
            raise ValueError(f"collision_suffix must be null or int>=2; got {meta['collision_suffix']!r}")

    for k in ("slug", "base_query", "query_hash", "search_query", "search_term_label", "pdf_store_root", "pipeline_version"):
        if not isinstance(meta[k], str):
            raise ValueError(f"{k} must be a string; got {type(meta[k]).__name__}")
    if meta["slug"].strip() == "":
        raise ValueError("slug must be non-empty")
    if meta["base_query"].strip() == "":
        raise ValueError("base_query must be non-empty")
    if not re.fullmatch(r"[a-f0-9]{16}", meta["query_hash"]):
        raise ValueError(f"query_hash must be 16 lowercase hex chars; got {meta['query_hash']!r}")
    if meta["search_query"].strip() == "":
        raise ValueError("search_query must be non-empty")
    if meta["search_term_label"].strip() == "":
        raise ValueError("search_term_label must be non-empty")
    if len(meta["pipeline_version"]) > 40:
        raise ValueError(f"pipeline_version must be <=40 chars; got {len(meta['pipeline_version'])}")

    if meta["source_db"] not in _VALID_SOURCE_DB:
        raise ValueError(f"source_db must be one of {sorted(_VALID_SOURCE_DB)}; got {meta['source_db']!r}")
    if meta["query_source"] not in _VALID_QUERY_SOURCE:
        raise ValueError(f"query_source must be one of {sorted(_VALID_QUERY_SOURCE)}; got {meta['query_source']!r}")

    if not isinstance(meta["incremental_refresh"], bool):
        raise ValueError("incremental_refresh must be a bool")
    for opt_str in ("refresh_anchor_run_id", "refresh_anchor_started_at", "pubmed_datetype", "pubmed_mindate"):
        if meta[opt_str] is not None and not isinstance(meta[opt_str], str):
            raise ValueError(f"{opt_str} must be null or string; got {type(meta[opt_str]).__name__}")

    for ts_key in ("started_at", "finished_at", "refresh_anchor_started_at", "r2_synced_at"):
        val = meta[ts_key]
        if val is None:
            continue
        if not isinstance(val, str) or not _ISO_UTC_RE.match(val):
            raise ValueError(
                f"{ts_key} must be ISO-8601 UTC ending in 'Z' (e.g. '2026-05-14T19:47:32Z'); "
                f"got {val!r}"
            )

    for k in (
        "input_count",
        "candidate_count_before_skip",
        "known_success_skip_count",
        "known_failure_skip_count",
        "candidate_count_after_skip",
        "download_success",
        "download_fail",
        "download_skipped_existing",
    ):
        if not isinstance(meta[k], int) or meta[k] < 0:
            raise ValueError(f"{k} must be a non-negative int; got {meta[k]!r}")

    if not isinstance(meta["merged_from"], list) or not all(isinstance(x, str) for x in meta["merged_from"]):
        raise ValueError("merged_from must be a list of strings")

    if not isinstance(meta["error_summary"], dict):
        raise ValueError("error_summary must be a dict")
    for reason, count in meta["error_summary"].items():
        if not isinstance(reason, str):
            raise ValueError(f"error_summary keys must be strings; got {type(reason).__name__}")
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"error_summary[{reason!r}] must be non-negative int; got {count!r}")

    if not isinstance(meta["notes"], str):
        raise ValueError(f"notes must be a string; got {type(meta['notes']).__name__}")


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    ) as tf:
        json.dump(data, tf, indent=2, sort_keys=False)
        tf.write("\n")
        tmp_path = Path(tf.name)
    os.replace(tmp_path, path)


def read_metadata(run: SearchRun) -> Dict[str, Any]:
    with open(run.metadata_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_metadata(run: SearchRun, **updates: Any) -> Dict[str, Any]:
    """Load current metadata.json (or initialize), apply updates, validate, atomic-write.

    Callers should pass only the fields they intend to change. The full document
    is round-tripped on disk.
    """
    if run.metadata_path.exists():
        meta = read_metadata(run)
    else:
        meta = _empty_metadata(run.run_id)

    meta.update(updates)
    if not meta.get("slug") and "__" in run.run_id:
        meta["slug"] = run.run_id.split("__", 1)[1].removesuffix("-2")
        meta["slug"] = re.sub(r"-\d+$", "", meta["slug"])
    if not meta.get("base_query") and meta.get("search_query"):
        meta["base_query"] = normalize_query_text(str(meta["search_query"]))
    if not meta.get("query_hash") and meta.get("base_query"):
        meta["query_hash"] = query_hash_for_text(str(meta["base_query"]))
    _validate_metadata(meta)
    _atomic_write_json(run.metadata_path, meta)
    return meta


def _empty_metadata(run_id: str) -> Dict[str, Any]:
    return {
        "_generated_by": GENERATOR_PATH,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "slug": "",
        "base_query": "",
        "query_hash": "",
        "collision_suffix": None,
        "search_query": "",
        "search_term_label": "",
        "source_db": "pubmed",
        "query_source": "entrez",
        "started_at": utc_iso_now(),
        "finished_at": None,
        "incremental_refresh": False,
        "refresh_anchor_run_id": None,
        "refresh_anchor_started_at": None,
        "pubmed_datetype": None,
        "pubmed_mindate": None,
        "input_count": 0,
        "candidate_count_before_skip": 0,
        "known_success_skip_count": 0,
        "known_failure_skip_count": 0,
        "candidate_count_after_skip": 0,
        "download_success": 0,
        "download_fail": 0,
        "download_skipped_existing": 0,
        "pdf_store_root": os.environ.get("LIT_REVIEW_PDF_REMOTE", "gdrive:nlp_lit_review_1_papers/pdfs"),
        "pipeline_version": _detect_pipeline_version(),
        "merged_from": [],
        "error_summary": {},
        "r2_synced_at": None,
        "notes": "",
    }


def _detect_pipeline_version() -> str:
    """Best-effort short git SHA; falls back to 'unknown'."""
    try:
        head = REPO_ROOT / ".git" / "HEAD"
        if head.exists():
            ref = head.read_text(encoding="utf-8").strip()
            if ref.startswith("ref: "):
                ref_path = REPO_ROOT / ".git" / ref[5:]
                if ref_path.exists():
                    return ref_path.read_text(encoding="utf-8").strip()[:12]
            return ref[:12]
    except OSError:
        pass
    return "unknown"


# --------------------------------------------------------------------------- #
# progress.jsonl / errors.jsonl appenders
# --------------------------------------------------------------------------- #

def append_progress(
    run: SearchRun,
    *,
    record_number: Optional[str],
    identifier_used: Optional[str],
    outcome: Literal["success", "fail", "skipped_existing"],
    paper_key: Optional[str] = None,
    error_reason: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
) -> None:
    """Append a single line to progress.jsonl. Used by V4 inside the per-ref loop."""
    line = {
        "record_number": record_number,
        "identifier_used": identifier_used,
        "paper_key": paper_key,
        "outcome": outcome,
        "error_reason": error_reason,
        "attempted_at": utc_iso_now(),
        "elapsed_ms": elapsed_ms,
    }
    _append_jsonl(run.progress_path, line)


def append_error(
    run: SearchRun,
    *,
    record_number: Optional[str],
    identifier_used: Optional[str],
    error_reason: str,
    traceback: Optional[str] = None,
    selenium_url: Optional[str] = None,
) -> None:
    """Append a single line to errors.jsonl with optional traceback / last URL."""
    line = {
        "record_number": record_number,
        "identifier_used": identifier_used,
        "outcome": "fail",
        "error_reason": error_reason,
        "attempted_at": utc_iso_now(),
        "traceback": traceback,
        "selenium_url": selenium_url,
    }
    _append_jsonl(run.errors_path, line)


def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, sort_keys=False) + "\n")


def read_progress(run: SearchRun) -> list[Dict[str, Any]]:
    """Read progress.jsonl into a list of dicts. Empty list if file absent."""
    if not run.progress_path.exists():
        return []
    out: list[Dict[str, Any]] = []
    with open(run.progress_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def terminal_outcomes_for_resume() -> set[str]:
    """Record-level outcomes that --resume should skip on rerun."""
    return {"success", "skipped_existing"}


def terminal_error_reasons_for_resume() -> set[str]:
    """V4 error_reason values that --resume should skip on rerun (won't change on retry)."""
    return {"not_found", "paywall_detected", "no_identifier"}


# --------------------------------------------------------------------------- #
# Entrez (PubMed) fetch
# --------------------------------------------------------------------------- #

def fetch_pubmed_via_entrez(
    query: str,
    out_path: Path,
    *,
    email: Optional[str] = None,
    api_key: Optional[str] = None,
    retmax: int = 10_000,
    datetype: Optional[str] = None,
    mindate: Optional[str] = None,
) -> int:
    """Fetch a PubMed query as RIS, written to `out_path`. Returns reference count.

    Uses Bio.Entrez (biopython). Imported lazily so this module stays importable
    even before biopython is installed; callers that select the Entrez path get
    a clear error pointing at the right `pip install`.

    Args:
        query: PubMed query string (the same syntax accepted by the web UI).
        out_path: Where to write the resulting RIS file.
        email: NCBI requires a contact email per its API ToS. Falls back to
            $NCBI_EMAIL env var; raises if neither is set.
        api_key: Optional NCBI API key for higher rate limits. Falls back to
            $NCBI_API_KEY env var.
        retmax: Maximum number of records to fetch (default 10k).
    """
    try:
        from Bio import Entrez, Medline  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Entrez fetch requires biopython. Install with `pip install biopython`."
        ) from exc

    contact_email = email or os.environ.get("NCBI_EMAIL")
    if not contact_email:
        raise RuntimeError(
            "NCBI requires an email address. Set $NCBI_EMAIL or pass email= explicitly."
        )
    Entrez.email = contact_email
    if api_key is None:
        api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        Entrez.api_key = api_key

    from entrez_ssl import apply_entrez_ssl_settings, ssl_error_hint  # type: ignore[import-not-found]

    apply_entrez_ssl_settings()

    try:
        search_kwargs: Dict[str, Any] = {"db": "pubmed", "term": query, "retmax": retmax}
        if datetype:
            search_kwargs["datetype"] = datetype
        if mindate:
            search_kwargs["mindate"] = mindate
        handle = Entrez.esearch(**search_kwargs)
    except Exception as exc:
        err_text = str(exc).lower()
        if "certificate" in err_text or "ssl" in err_text:
            raise RuntimeError(ssl_error_hint(exc)) from exc
        raise
    search = Entrez.read(handle)
    handle.close()
    pmids = list(search.get("IdList", []))
    if not pmids:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")
        return 0

    try:
        handle = Entrez.efetch(db="pubmed", id=",".join(pmids), rettype="medline", retmode="text")
        records = list(Medline.parse(handle))
        handle.close()
    except Exception as exc:
        err_text = str(exc).lower()
        if "certificate" in err_text or "ssl" in err_text:
            raise RuntimeError(ssl_error_hint(exc)) from exc
        raise

    ris_text = _medline_records_to_ris(records, query=query)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ris_text, encoding="utf-8")
    return len(records)


_MEDLINE_TO_RIS_TY = {
    "Journal Article": "JOUR",
    "Review": "JOUR",
    "Letter": "JOUR",
    "Editorial": "JOUR",
    "Comment": "JOUR",
    "Comparative Study": "JOUR",
}


def _medline_records_to_ris(records: list, *, query: str) -> str:
    """Convert biopython Medline records to RIS text V4 can parse.

    The resulting RIS is intentionally minimal: TY/AU/TI/JO/PY/SN/DO/AN/AB/UR/RN/ER.
    AN is set to PMID (matches the rest of the pipeline's convention).
    """
    lines: list[str] = [
        f"; generated by automated_search/scripts/helpers/search_run.py::fetch_pubmed_via_entrez",
        f"; pubmed_query: {query}",
        "",
    ]
    for rec in records:
        pmid = rec.get("PMID", "")
        title = rec.get("TI", "")
        abstract = rec.get("AB", "")
        journal = rec.get("JT") or rec.get("TA") or ""
        year = ""
        dp = rec.get("DP", "")
        if dp:
            year = dp.split(" ")[0]
        issn = rec.get("IS", "") or rec.get("SN", "")
        doi = ""
        for aid in rec.get("AID", []):
            if isinstance(aid, str) and aid.lower().endswith("[doi]"):
                doi = aid.split(" ")[0]
                break
        authors = rec.get("FAU") or rec.get("AU") or []
        pub_types = rec.get("PT") or []
        ty = "JOUR"
        for pt in pub_types:
            if pt in _MEDLINE_TO_RIS_TY:
                ty = _MEDLINE_TO_RIS_TY[pt]
                break

        lines.append(f"TY  - {ty}")
        for au in authors:
            lines.append(f"AU  - {au}")
        if title:
            lines.append(f"TI  - {title}")
        if journal:
            lines.append(f"JO  - {journal}")
        if year:
            lines.append(f"PY  - {year}")
        if issn:
            lines.append(f"SN  - {issn}")
        if doi:
            lines.append(f"DO  - {doi}")
        if pmid:
            lines.append(f"AN  - {pmid}")
        if abstract:
            lines.append(f"AB  - {abstract}")
        if pmid:
            lines.append(f"UR  - https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        lines.append("ER  - ")
        lines.append("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Query identity, schema-v2 run discovery, anchors, and global skip filtering
# --------------------------------------------------------------------------- #

def normalize_query_text(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip())


def query_hash_for_text(query: str) -> str:
    normalized = normalize_query_text(query)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def is_schema_v2_metadata(meta: Dict[str, Any]) -> bool:
    return meta.get("schema_version") == SCHEMA_VERSION


def is_completed_schema_v2_run(run: SearchRun, meta: Optional[Dict[str, Any]] = None) -> bool:
    meta = meta if meta is not None else read_metadata(run)
    merged_from = meta.get("merged_from") or []
    return is_schema_v2_metadata(meta) and bool(meta.get("finished_at")) and run.run_id in merged_from


def iter_schema_v2_runs(searches_dir: Path = SEARCHES_DIR) -> list[tuple[SearchRun, Dict[str, Any]]]:
    if not searches_dir.exists():
        return []
    out: list[tuple[SearchRun, Dict[str, Any]]] = []
    for child in searches_dir.iterdir():
        if not child.is_dir() or not (child / "metadata.json").is_file():
            continue
        run = SearchRun.for_root(child)
        try:
            meta = read_metadata(run)
        except (OSError, json.JSONDecodeError):
            continue
        if is_schema_v2_metadata(meta):
            out.append((run, meta))
    return out


def find_completed_anchor(
    *,
    slug: str,
    query_hash: str,
    searches_dir: Path = SEARCHES_DIR,
) -> Optional[tuple[SearchRun, Dict[str, Any]]]:
    slug_n = normalize_slug(slug)
    matches = [
        (run, meta)
        for run, meta in iter_schema_v2_runs(searches_dir)
        if meta.get("slug") == slug_n
        and meta.get("query_hash") == query_hash
        and is_completed_schema_v2_run(run, meta)
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: item[1].get("started_at") or item[0].run_id)


def edat_mindate_from_started_at(started_at: str) -> str:
    dt = _dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    return dt.strftime("%Y/%m/%d")


def _split_ris_entries(text: str) -> tuple[str, list[str]]:
    parts = re.split(r"(?m)^ER\s+-\s*$", text)
    entries: list[str] = []
    header = parts[0] if parts and "TY  -" not in parts[0] else ""
    for part in parts:
        if "TY  -" not in part:
            continue
        entry = part.strip()
        if entry:
            entries.append(entry + "\nER  -\n")
    return header, entries


def _reference_from_ris_entry(entry: str) -> Dict[str, object]:
    ref: Dict[str, object] = {}
    title_lines: list[str] = []
    for raw in entry.splitlines():
        line = raw.rstrip()
        if line.startswith("AN  - "):
            ref["pmid"] = line[6:].strip()
        elif line.startswith("DO  - "):
            ref["doi"] = line[6:].strip()
        elif line.startswith("TI  - "):
            title_lines.append(line[6:].strip())
        elif title_lines and not re.match(r"^[A-Z0-9]{2}\s+-\s+", line):
            title_lines.append(line.strip())
    if title_lines:
        ref["title"] = " ".join(x for x in title_lines if x)
    return ref


def _paper_key_for_entry(entry: str) -> Optional[str]:
    from ensure_pdf_store import cas_key_for_reference  # type: ignore[import-not-found]

    return cas_key_for_reference(_reference_from_ris_entry(entry))


def count_ris_references(path: Path) -> int:
    return _count_ris_references(path)


def filter_ris_by_known_papers(
    input_all_ris: Path,
    filtered_ris: Path,
    *,
    known_success_keys: set[str],
    known_failure_keys: set[str],
) -> Dict[str, int]:
    text = input_all_ris.read_text(encoding="utf-8") if input_all_ris.exists() else ""
    header, entries = _split_ris_entries(text)
    kept: list[str] = []
    success_skips = 0
    failure_skips = 0
    for entry in entries:
        key = _paper_key_for_entry(entry)
        if key and key in known_success_keys:
            success_skips += 1
            continue
        if key and key in known_failure_keys:
            failure_skips += 1
            continue
        kept.append(entry)

    filtered_ris.parent.mkdir(parents=True, exist_ok=True)
    prefix = header.strip()
    body = "\n".join(e.rstrip() for e in kept)
    if prefix and body:
        filtered_ris.write_text(prefix + "\n\n" + body + "\n", encoding="utf-8")
    elif body:
        filtered_ris.write_text(body + "\n", encoding="utf-8")
    else:
        filtered_ris.write_text(prefix + ("\n" if prefix else ""), encoding="utf-8")

    return {
        "candidate_count_before_skip": len(entries),
        "known_success_skip_count": success_skips,
        "known_failure_skip_count": failure_skips,
        "candidate_count_after_skip": len(kept),
    }


def build_known_paper_skip_sets(searches_dir: Path = SEARCHES_DIR) -> tuple[set[str], set[str]]:
    successes: set[str] = set()
    failures: set[str] = set()
    for run, _meta in iter_schema_v2_runs(searches_dir):
        for entry in read_progress(run):
            key = entry.get("paper_key")
            if not key:
                continue
            outcome = entry.get("outcome")
            if outcome in {"success", "skipped_existing"}:
                successes.add(str(key))
            elif outcome == "fail":
                failures.add(str(key))
    return successes, failures


# --------------------------------------------------------------------------- #
# Bootstrap: create a run folder, populate input.ris, write initial metadata.
# --------------------------------------------------------------------------- #

def bootstrap_search_run(
    *,
    slug: str,
    search_query: str,
    search_term_label: str,
    source_db: str = "pubmed",
    query_source: QuerySource = "entrez",
    input_ris: Optional[Path] = None,
    found_ris: Optional[Path] = None,
    searches_dir: Path = SEARCHES_DIR,
    dry_run: bool = False,
    entrez_email: Optional[str] = None,
    entrez_api_key: Optional[str] = None,
    incremental_refresh: bool = False,
    refresh_anchor_run_id: Optional[str] = None,
    refresh_anchor_started_at: Optional[str] = None,
    pubmed_datetype: Optional[str] = None,
    pubmed_mindate: Optional[str] = None,
) -> SearchRun:
    """Create a `<ts>__<slug>/` folder, populate input.ris, write initial metadata.

    The `query_source` arg controls how `input.ris` is populated:
      - "entrez": call NCBI E-utilities with `search_query`.
      - "manual_export": copy `input_ris` (caller-provided path) in.
      - "byo_found_ris": skip V4; copy `found_ris` into `<run>/found/found.ris`.

    `dry_run=True` creates the folder + metadata and returns the SearchRun
    *without* fetching from Entrez or copying any RIS, so the user can preview
    what would happen.

    Returns:
        SearchRun pointing at the new folder.
    """
    slug_n = normalize_slug(slug)
    base_query = normalize_query_text(search_query)
    query_hash = query_hash_for_text(base_query)
    if not search_query.strip():
        raise ValueError("search_query must be non-empty")
    if not search_term_label.strip():
        raise ValueError("search_term_label must be non-empty")
    if query_source == "manual_export" and not input_ris:
        raise ValueError("query_source='manual_export' requires input_ris=<Path>")
    if query_source == "byo_found_ris" and not found_ris:
        raise ValueError("query_source='byo_found_ris' requires found_ris=<Path>")

    run_dir, collision_suffix = allocate_run_dir(slug_n, searches_dir=searches_dir)
    run = SearchRun.for_root(run_dir)

    run.found_dir.mkdir(parents=True, exist_ok=True)
    run.missing_dir.mkdir(parents=True, exist_ok=True)
    run.pdfs_dir.mkdir(parents=True, exist_ok=True)

    save_metadata(
        run,
        run_id=run.run_id,
        slug=slug_n,
        base_query=base_query,
        query_hash=query_hash,
        collision_suffix=collision_suffix,
        search_query=base_query,
        search_term_label=search_term_label,
        source_db=source_db,
        query_source=query_source,
        started_at=utc_iso_now(),
        incremental_refresh=incremental_refresh,
        refresh_anchor_run_id=refresh_anchor_run_id,
        refresh_anchor_started_at=refresh_anchor_started_at,
        pubmed_datetype=pubmed_datetype,
        pubmed_mindate=pubmed_mindate,
    )

    if dry_run:
        run.input_all_ris.touch(exist_ok=True)
        run.input_ris.touch(exist_ok=True)
        return run

    input_count = 0
    if query_source == "entrez":
        fetch_pubmed_via_entrez(
            base_query,
            run.input_all_ris,
            email=entrez_email,
            api_key=entrez_api_key,
            datetype=pubmed_datetype,
            mindate=pubmed_mindate,
        )
        success_keys, failure_keys = build_known_paper_skip_sets(searches_dir)
        skip_counts = filter_ris_by_known_papers(
            run.input_all_ris,
            run.input_ris,
            known_success_keys=success_keys,
            known_failure_keys=failure_keys,
        )
        input_count = skip_counts["candidate_count_after_skip"]
        save_metadata(run, **skip_counts)
    elif query_source == "manual_export":
        assert input_ris is not None
        shutil.copy2(input_ris, run.input_all_ris)
        shutil.copy2(input_ris, run.input_ris)
        input_count = _count_ris_references(run.input_ris)
        save_metadata(
            run,
            candidate_count_before_skip=input_count,
            candidate_count_after_skip=input_count,
        )
    elif query_source == "byo_found_ris":
        assert found_ris is not None
        run.input_all_ris.touch(exist_ok=True)
        run.input_ris.touch(exist_ok=True)
        shutil.copy2(found_ris, run.found_ris)
        input_count = _count_ris_references(run.found_ris)
        save_metadata(
            run,
            candidate_count_before_skip=input_count,
            candidate_count_after_skip=input_count,
        )
    else:
        raise ValueError(f"Unknown query_source: {query_source!r}")

    save_metadata(run, input_count=input_count)
    return run


def _count_ris_references(path: Path) -> int:
    """Cheap reference counter: counts ER- terminators."""
    if not path.exists():
        return 0
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.rstrip()
            if s == "ER  -" or s == "ER -":
                n += 1
    return n


# --------------------------------------------------------------------------- #
# summary.md rendering
# --------------------------------------------------------------------------- #

def render_summary_md(run: SearchRun) -> str:
    """Render a human-readable run summary from metadata.json + progress.jsonl.

    Returns the markdown string (does not write).
    """
    meta = read_metadata(run) if run.metadata_path.exists() else _empty_metadata(run.run_id)

    n_input = meta.get("input_count", 0)
    n_success = meta.get("download_success", 0)
    n_fail = meta.get("download_fail", 0)
    n_skipped = meta.get("download_skipped_existing", 0)
    started_at = meta.get("started_at") or "?"
    finished_at = meta.get("finished_at") or "?"

    duration = ""
    try:
        start = _dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = _dt.datetime.fromisoformat(finished_at.replace("Z", "+00:00")) if finished_at != "?" else None
        if end is not None:
            duration = str(end - start)
    except (ValueError, AttributeError):
        pass

    error_summary = meta.get("error_summary") or {}
    top_errors = sorted(error_summary.items(), key=lambda kv: kv[1], reverse=True)[:3]
    r2 = meta.get("r2_synced_at")

    success_rate = ""
    denom = max(1, n_input)
    if n_input:
        success_rate = f"{(n_success + n_skipped) * 100.0 / denom:.1f}%"

    error_table_rows = "\n".join([f"| `{reason}` | {count} |" for reason, count in top_errors]) or "| _none_ | _0_ |"

    lines = [
        "<!-- generated by automated_search/scripts/auto_search_wrapper.py -->",
        "",
        f"# Search Run Summary — `{meta.get('run_id', run.run_id)}`",
        "",
        f"- **Query:** `{meta.get('search_query','')}`",
        f"- **Label:** `{meta.get('search_term_label','')}`",
        f"- **Source:** `{meta.get('source_db','')}` via `{meta.get('query_source','')}`",
        f"- **Started / Finished:** `{started_at}` → `{finished_at}` ({duration or 'running'})",
        f"- **Counts:** input={n_input}, success={n_success}, fail={n_fail}, skipped_existing={n_skipped}",
        f"- **Success rate:** {success_rate or 'n/a'}",
        f"- **R2 sync:** {('ok @ ' + r2) if r2 else 'not yet synced'}",
        "",
        "## Top error reasons",
        "",
        "| reason | count |",
        "|---|---|",
        error_table_rows,
        "",
        "## Artifacts",
        "",
        f"- Full log: `log.txt`",
        f"- Progress journal: `progress.jsonl`",
        f"- Errors: `errors.jsonl`",
        f"- Found RIS: `found/found.ris`",
        f"- Missing RIS: `missing/still_missing.ris`",
        f"- PDFs (symlinks): `found/pdfs/`",
        "",
    ]
    return "\n".join(lines)


def write_summary_md(run: SearchRun) -> Path:
    """Render and atomically write `<run>/summary.md`. Returns the path."""
    content = render_summary_md(run)
    tmp = run.summary_path.with_suffix(run.summary_path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, run.summary_path)
    return run.summary_path
