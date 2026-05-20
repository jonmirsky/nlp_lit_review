#!/usr/bin/env python3
"""
Wrapper for the automated literature search pipeline.

This wrapper does one of two things:

1. NEW PATH (default): Bootstrap a self-contained run folder under
   automated_search/searches/<run_id>/, fetch RIS from PubMed via Entrez
   (or accept a manual export / BYO found.ris), drive V4 scraping, then chain
   the three source-RIS update steps and (in Phase 9) sync to Cloudflare R2.

2. LEGACY PATH (--legacy): preserves today's interactive workflow that
   reads/writes under automated_search/missing_papers/ and
   automated_search/found_papers/. Removed in Phase 7 once acceptance criteria
   pass.

Inputs:
- CLI flags (see argparse below). Most useful: --query, --slug, --label.
- $LIT_REVIEW_PDF_STORE: absolute path to the canonical PDF store
  (an rclone-mounted Google Drive folder).
- $NCBI_EMAIL (required for Entrez) and $NCBI_API_KEY (optional).
- Search-term RIS directory (legacy only):
  /Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/search_term_results
- Master RIS source directory: visualizer_nlp_lit_review/RIS_source_files

Outputs (new path):
- automated_search/searches/<run_id>/ populated per automated_search/SCHEMA.md
- Updated source RIS in visualizer_nlp_lit_review/RIS_source_files
- PDFs in $LIT_REVIEW_PDF_STORE/pdfs/ (content-addressable, mirrored to R2)

Outputs (legacy path):
- automated_search/found_papers/RIS_files/import_to_endnote/*_post_scrape.txt
- Intermediate RIS files alongside the input
- Final merged source RIS in RIS_source_files

Usage examples:
    # Recommended: drive PubMed via Entrez and run end-to-end
    python3 -m automated_search.scripts.auto_search_wrapper \\
        --query '("Large Language Models"[tiab]) AND ("Extraction"[tiab])' \\
        --slug nlp_extraction \\
        --label '( NLP extraction )'

    # Accept a manually-exported RIS instead of using Entrez
    python3 -m automated_search.scripts.auto_search_wrapper \\
        --input-ris ~/Downloads/pubmed_export.ris \\
        --slug nlp_extraction \\
        --label '( NLP extraction )'

    # Skip V4 entirely (you already have a scraped found.ris)
    python3 -m automated_search.scripts.auto_search_wrapper \\
        --found-ris path/to/found.ris \\
        --slug nlp_extraction \\
        --label '( NLP extraction )'

    # Old interactive workflow (will be removed in Phase 7)
    python3 -m automated_search.scripts.auto_search_wrapper --legacy
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

HELPERS_DIR = Path(__file__).resolve().parent / "helpers"
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))

from full_text_scrape_V4 import run_full_text_scrape  # type: ignore[import-not-found]
from convert_composite_ris_paths_to_absolute import convert_ris_to_absolute_paths  # type: ignore[import-not-found]
from label_papers_w_search_terms_v2 import load_all_ris_files, add_research_notes_to_ris  # type: ignore[import-not-found]
from merge_ris_to_master import merge_ris_to_master  # type: ignore[import-not-found]
from search_run import (  # type: ignore[import-not-found]
    SearchRun,
    bootstrap_search_run,
    build_known_paper_skip_sets,
    edat_mindate_from_started_at,
    fetch_pubmed_via_entrez,
    filter_ris_by_known_papers,
    find_completed_anchor,
    normalize_query_text,
    query_hash_for_text,
    read_metadata,
    save_metadata,
    utc_iso_now,
    write_summary_md,
)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="auto_search_wrapper",
        description="Bootstrap and run an end-to-end literature search pipeline.",
    )
    p.add_argument("--query", help="PubMed query string; default path uses NCBI E-utilities.")
    p.add_argument("--input-ris", type=Path, help="Manually-exported RIS file (skips Entrez fetch).")
    p.add_argument("--found-ris", type=Path, help="Pre-scraped found.ris file (skips V4 entirely).")
    p.add_argument("--slug", help="Short slug for the run folder (will be normalized).")
    p.add_argument("--label", help="Search term label written verbatim into RN fields.")
    p.add_argument("--source-db", default="pubmed", choices=["pubmed", "manual", "byo"],
                   help="Source database tag for metadata.json (default: pubmed).")
    p.add_argument("--dry-run", action="store_true",
                   help="Create the run folder + metadata then exit before any network call.")
    p.add_argument("--incremental-refresh", action="store_true",
                   help="Use PubMed EDAT since the latest completed matching schema-v2 anchor, or create a full baseline if none exists.")
    p.add_argument("--check-only", action="store_true",
                   help="Call Entrez and compute known-paper skip counts; do not create a run folder or launch Selenium.")
    p.add_argument("--resume", type=Path,
                   help="Resume a prior run folder. Skips already-attempted records (see SCHEMA.md).")
    p.add_argument("--resume-latest", action="store_true",
                   help="Resume the most recent run only if it is incomplete; no-op when latest is complete.")
    p.add_argument("--legacy", action="store_true",
                   help="Use the old interactive workflow (removed in Phase 7).")
    p.add_argument("--fast-baseline", action="store_true",
                   help="Cap per-paper wall-clock time, disable captcha waits, and skip deep publisher "
                        "Selenium fallbacks. Deferred papers written to missing/slow_retry_candidates.ris. "
                        "Sets LIT_REVIEW_FAST_BASELINE=1.")
    p.add_argument("--max-paper-seconds", type=int, default=None, metavar="N",
                   help="Per-paper wall-clock budget in seconds. Default 30 in fast mode, unlimited otherwise.")
    p.add_argument("--captcha-timeout", type=int, default=None, metavar="N",
                   help="Max seconds to wait for captcha completion. 0 disables (default in fast mode).")
    p.add_argument("--skip-deep-publisher-fallbacks", action="store_true",
                   help="Skip DOI Selenium and metadata-search Selenium routes; record as deferred_deep_publisher.")
    return p


def _apply_fast_baseline_env(args: argparse.Namespace) -> None:
    """Translate --fast-baseline and related CLI flags into env vars for the scraper."""
    if args.fast_baseline:
        os.environ.setdefault("LIT_REVIEW_FAST_BASELINE", "1")
    if args.max_paper_seconds is not None:
        os.environ["LIT_REVIEW_MAX_PAPER_SECONDS"] = str(args.max_paper_seconds)
    if args.captcha_timeout is not None:
        os.environ["LIT_REVIEW_CAPTCHA_TIMEOUT"] = str(args.captcha_timeout)
    if args.skip_deep_publisher_fallbacks:
        os.environ.setdefault("LIT_REVIEW_SKIP_DEEP_PUBLISHER", "1")


def _incremental_params(slug: str, base_query: str) -> tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    qh = query_hash_for_text(base_query)
    anchor = find_completed_anchor(slug=slug, query_hash=qh)
    if anchor is None:
        print("No completed matching schema-v2 anchor found; creating a full baseline run.")
        return False, None, None, None, None
    anchor_run, anchor_meta = anchor
    anchor_started_at = anchor_meta["started_at"]
    mindate = edat_mindate_from_started_at(anchor_started_at)
    print(
        f"Using incremental PubMed EDAT refresh from anchor {anchor_run.run_id} "
        f"(mindate={mindate})."
    )
    return True, anchor_run.run_id, anchor_started_at, "edat", mindate


def _check_only(*, query: str, slug: str, incremental_refresh: bool) -> int:
    base_query = normalize_query_text(query)
    inc, anchor_run_id, _anchor_started_at, datetype, mindate = (
        _incremental_params(slug, base_query) if incremental_refresh else (False, None, None, None, None)
    )
    with tempfile.TemporaryDirectory(prefix="lit_review_check_") as td:
        input_all = Path(td) / "input_all.ris"
        input_filtered = Path(td) / "input.ris"
        fetch_pubmed_via_entrez(base_query, input_all, datetype=datetype, mindate=mindate)
        success_keys, failure_keys = build_known_paper_skip_sets()
        counts = filter_ris_by_known_papers(
            input_all,
            input_filtered,
            known_success_keys=success_keys,
            known_failure_keys=failure_keys,
        )
    mode = "incremental" if inc else "full"
    if incremental_refresh and not anchor_run_id:
        mode = "full baseline"
    print(
        "CHECK-ONLY: "
        f"mode={mode}, before_skip={counts['candidate_count_before_skip']}, "
        f"known_success_skips={counts['known_success_skip_count']}, "
        f"known_failure_skips={counts['known_failure_skip_count']}, "
        f"after_skip={counts['candidate_count_after_skip']}"
    )
    return 0


def _interactive_legacy_main() -> None:
    """Verbatim re-implementation of the pre-refactor interactive flow.

    Preserved while the new path is feature-flagged. Deleted in Phase 7.
    """
    base_dir = Path(__file__).parent
    ris_source_dir = base_dir.parent.parent / "visualizer_nlp_lit_review" / "RIS_source_files"
    ris_dir = Path(
        "/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine"
        "/NLP_lit_review/Endnote/search_term_results"
    )

    print("=" * 70)
    print("PREPARE AND MERGE RIS TO SOURCE RIS (LEGACY)")
    print("=" * 70)

    run_scraper = input("Run full_text_scrape_V4.py first? (y/n) [default: n]: ").strip().lower() == "y"

    if run_scraper:
        scraper_output = run_full_text_scrape()
        if not scraper_output:
            print("ERROR: Scraper did not produce an output RIS file.")
            return
        input_ris_path = scraper_output
    elif len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        input_ris_path = Path(sys.argv[1])
    else:
        user_input = input("Enter path to RIS file: ").strip().strip("'\"")
        if not user_input:
            print("ERROR: No file specified")
            return
        input_ris_path = Path(user_input)

    if not input_ris_path.exists():
        print(f"ERROR: RIS file not found: {input_ris_path}")
        return
    input_ris_path = input_ris_path.resolve()

    intermediate_files: list[Path] = []
    try:
        step1_output, _no_ft, _only_ft = convert_ris_to_absolute_paths(input_ris_path)
        intermediate_files.append(step1_output)

        if not ris_dir.exists():
            step2_output = step1_output
        else:
            lookups = load_all_ris_files(ris_dir)
            step2_output = step1_output.parent / f"{step1_output.stem}_with_rn{step1_output.suffix}"
            add_research_notes_to_ris(step1_output, step2_output, lookups)
            intermediate_files.append(step2_output)

        merge_ris_to_master(step2_output, ris_source_dir)
    except Exception as e:
        print(f"ERROR: {e}")
        raise


def _resolve_query_source(args: argparse.Namespace) -> str:
    if args.found_ris:
        return "byo_found_ris"
    if args.input_ris:
        return "manual_export"
    if args.query:
        return "entrez"
    raise SystemExit(
        "ERROR: One of --query (Entrez), --input-ris (manual export), or --found-ris "
        "(skip V4) must be provided. Use --legacy for the old interactive workflow."
    )


def _run_post_scrape_chain(run: SearchRun) -> None:
    """Steps 1, 2, 3 wired against a SearchRun.

    Phase 3 keeps the existing helpers; Phases 5/6 will swap in the
    metadata-driven label and the O(N) merge. This function is the seam.
    """
    base_dir = Path(__file__).parent
    ris_source_dir = base_dir.parent.parent / "visualizer_nlp_lit_review" / "RIS_source_files"

    print("=" * 70)
    print("STEP 1: Converting L1 paths to absolute (run folder)")
    print("=" * 70)
    step1_output, _no_ft, _only_ft = convert_ris_to_absolute_paths(run.found_ris)

    print("=" * 70)
    print("STEP 2: Adding RN field from metadata.search_term_label")
    print("=" * 70)
    from label_papers_w_search_terms_v2 import (  # type: ignore[import-not-found]
        add_research_notes_to_ris_with_explicit_label,
    )
    meta = read_metadata(run)
    label = meta.get("search_term_label", "")
    if not label:
        print("WARNING: metadata.search_term_label is empty; falling back to legacy historical-tree lookup.")
        ris_dir = Path(
            "/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine"
            "/NLP_lit_review/Endnote/search_term_results"
        )
        if ris_dir.exists():
            lookups = load_all_ris_files(ris_dir)
            step2_output = step1_output.parent / f"{step1_output.stem}_with_rn{step1_output.suffix}"
            add_research_notes_to_ris(step1_output, step2_output, lookups)
        else:
            step2_output = step1_output
    else:
        step2_output = step1_output.parent / f"{step1_output.stem}_with_rn{step1_output.suffix}"
        add_research_notes_to_ris_with_explicit_label(step1_output, step2_output, label)

    print("=" * 70)
    print("STEP 3: Merging with master RIS file (O(N) dict lookup)")
    print("=" * 70)
    final_output = merge_ris_to_master(step2_output, ris_source_dir)

    existing_merged_from = read_metadata(run).get("merged_from", [])
    if run.run_id not in existing_merged_from:
        existing_merged_from.append(run.run_id)
    save_metadata(
        run,
        finished_at=utc_iso_now(),
        merged_from=existing_merged_from,
    )

    summary_path = write_summary_md(run)
    print(f"\nFinal merged source RIS: {final_output}")
    print(f"Run summary: {summary_path}")

    if os.environ.get("LIT_REVIEW_AUTO_R2_SYNC", "1") != "0":
        try:
            from sync_pdfs_to_r2 import sync_run_to_r2  # type: ignore[import-not-found]
            sync_run_to_r2(run)
        except ImportError:
            print("NOTE: sync_pdfs_to_r2 not yet available; skipping R2 sync. "
                  "Run `python3 automated_search/scripts/sync_pdfs_to_r2.py --run <run>` to sync.")
        except Exception as exc:
            print(f"WARNING: R2 sync failed: {exc}. Re-run sync_pdfs_to_r2.py to retry.")


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    _apply_fast_baseline_env(args)

    if args.legacy:
        _interactive_legacy_main()
        return 0

    if args.resume_latest:
        from resume_latest import latest_resume_decision  # type: ignore[import-not-found]

        decision = latest_resume_decision()
        print(decision.reason)
        if not decision.can_resume:
            return 0
        run = decision.run
        assert run is not None
        print(f"Resuming latest run: {run.run_id}")
        run_full_text_scrape(run=run, resume=True)
        _run_post_scrape_chain(run)
        return 0

    if args.resume:
        run = SearchRun.for_root(Path(args.resume).resolve())
        if not run.metadata_path.exists():
            print(f"ERROR: no metadata.json at {run.metadata_path}")
            return 1
        print(f"Resuming run: {run.run_id}")
        run_full_text_scrape(run=run, resume=True)
        _run_post_scrape_chain(run)
        return 0

    if not args.slug:
        raise SystemExit("ERROR: --slug is required (will be normalized; e.g. 'nlp_extraction').")
    if not args.label:
        raise SystemExit("ERROR: --label is required (verbatim string for RN fields).")

    query_source = _resolve_query_source(args)
    query_for_metadata = args.query or (str(args.input_ris) if args.input_ris else str(args.found_ris))
    base_query = normalize_query_text(query_for_metadata)

    if args.check_only:
        if query_source != "entrez":
            raise SystemExit("ERROR: --check-only requires --query (Entrez mode).")
        return _check_only(query=base_query, slug=args.slug, incremental_refresh=args.incremental_refresh)

    incremental_refresh = False
    anchor_run_id = None
    anchor_started_at = None
    pubmed_datetype = None
    pubmed_mindate = None
    if args.incremental_refresh and query_source == "entrez":
        (
            incremental_refresh,
            anchor_run_id,
            anchor_started_at,
            pubmed_datetype,
            pubmed_mindate,
        ) = _incremental_params(args.slug, base_query)

    run = bootstrap_search_run(
        slug=args.slug,
        search_query=base_query,
        search_term_label=args.label,
        source_db=args.source_db,
        query_source=query_source,
        input_ris=args.input_ris,
        found_ris=args.found_ris,
        dry_run=args.dry_run,
        incremental_refresh=incremental_refresh,
        refresh_anchor_run_id=anchor_run_id,
        refresh_anchor_started_at=anchor_started_at,
        pubmed_datetype=pubmed_datetype,
        pubmed_mindate=pubmed_mindate,
    )
    print(f"Bootstrapped run: {run.root}")

    if args.dry_run:
        print("Dry run: stopping before V4 / post-scrape chain.")
        return 0

    if query_source != "byo_found_ris":
        try:
            run_full_text_scrape(run=run)
        except TypeError:
            print("NOTE: V4 doesn't accept run= yet (Phase 4 wires this in). "
                  "Falling back to interactive V4; you may need to point it at "
                  f"{run.input_ris} manually.")
            run_full_text_scrape()

    _run_post_scrape_chain(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
