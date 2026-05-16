#!/usr/bin/env python3
"""
Merge RIS file with master RIS file in visualizer_nlp_lit_review/RIS_source_files.

This script:
1. Finds the newest RIS file in RIS_source_files (by modification time, pattern: pubmed_*.txt)
2. Reads both the input RIS and master RIS files
3. Deduplicates references using DOI, PMID, or normalized title
4. Creates a NEW file (does NOT modify existing files) with:
   - All references from master RIS
   - Existing master references updated with any new RN search labels
   - All new unique references from input RIS
5. Saves to RIS_source_files with timestamped filename

Inputs:
- Input RIS file path to merge (CLI prompt in standalone mode, or function argument).
- Master RIS directory: visualizer_nlp_lit_review/RIS_source_files under repository root.

Outputs:
- A new merged master RIS text file in RIS_source_files, named pubmed_NLP_v4_<timestamp>.txt
  unless an explicit output path is provided.
"""

import json
import re
import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple


CACHE_DIR_NAME = ".cache"
MASTER_LOOKUP_CACHE_FILE = "master_lookup.json"


def normalize_doi(doi: str) -> str:
    """Normalize DOI for matching: lowercase, remove whitespace and brackets."""
    if not doi:
        return ""
    # Extract DOI from formats like "10.xxx [doi]" or just "10.xxx"
    doi = re.sub(r'\[doi\]', '', doi, flags=re.IGNORECASE)
    doi = doi.strip()
    return doi.lower().replace(" ", "")


def normalize_title(title: str) -> str:
    """Normalize title for matching: lowercase, remove extra whitespace, strip punctuation."""
    if not title:
        return ""
    # Convert to lowercase
    title = title.lower()
    # Remove extra whitespace
    title = " ".join(title.split())
    # Remove common punctuation (keep alphanumeric and spaces)
    title = re.sub(r'[^\w\s]', '', title)
    return title.strip()


def parse_ris_file(ris_path: Path) -> List[Tuple[str, str]]:
    """
    Parse RIS file and return list of (reference_text, identifier) tuples.
    
    Args:
        ris_path: Path to RIS file
    
    Returns:
        List of tuples: (full_ris_text, identifier_string)
        identifier_string format: "doi:{doi}|pmid:{pmid}|title:{normalized_title}"
    """
    references = []
    
    if not ris_path.exists():
        print(f"ERROR: RIS file not found: {ris_path}")
        return references
    
    with open(ris_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by record terminator
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        # Parse fields to extract identifiers
        lines = entry.split('\n')
        doi = None
        pmid = None
        title = None
        
        for line in lines:
            line_stripped = line.rstrip()
            if re.match(r'^[A-Z]{2}\s+-', line_stripped):
                tag = line_stripped[0:2]
                value = line_stripped[6:].strip()
                
                if tag == 'DO':
                    doi = value
                elif tag == 'AN':
                    pmid = value
                elif tag == 'TI':
                    title = value
            elif title is not None and line_stripped:
                # Continuation of title field
                title += ' ' + line_stripped.strip()
        
        # Create identifier string
        identifier_parts = []
        if doi:
            identifier_parts.append(f"doi:{normalize_doi(doi)}")
        if pmid:
            identifier_parts.append(f"pmid:{pmid.strip()}")
        if title:
            identifier_parts.append(f"title:{normalize_title(title)}")
        
        if identifier_parts:
            identifier = "|".join(identifier_parts)
            # Add ER marker back to entry
            full_entry = entry + '\nER  -\n'
            references.append((full_entry, identifier))
    
    return references


def find_newest_master_ris(ris_source_dir: Path) -> Optional[Path]:
    """
    Find the newest RIS file in RIS_source_files directory.
    
    Args:
        ris_source_dir: Path to RIS_source_files directory
    
    Returns:
        Path to newest RIS file, or None if not found
    """
    if not ris_source_dir.exists():
        return None
    
    # Find all files matching pubmed_*.txt pattern
    matching_files = []
    for file_path in ris_source_dir.glob("pubmed_*.txt"):
        if file_path.is_file() and not file_path.name.endswith('.bak') and not file_path.name.endswith('.bak2'):
            stat = file_path.stat()
            mtime = stat.st_mtime
            matching_files.append((mtime, file_path))
    
    if not matching_files:
        return None
    
    # Sort by modification time (most recent first)
    matching_files.sort(key=lambda x: x[0], reverse=True)
    return matching_files[0][1]


def create_identifier_set(identifier_string: str) -> Set[str]:
    """
    Create a set of identifiers from identifier string for matching.
    
    Args:
        identifier_string: Format "doi:{doi}|pmid:{pmid}|title:{title}"
    
    Returns:
        Set of identifier strings for matching
    """
    identifiers = set()
    parts = identifier_string.split('|')
    for part in parts:
        if part:
            identifiers.add(part)
            # Also add just the value (without prefix) for flexible matching
            if ':' in part:
                value = part.split(':', 1)[1]
                if value:
                    identifiers.add(value)
    return identifiers


def references_match(ref1_id: str, ref2_id: str) -> bool:
    """
    Check if two references match based on their identifiers.
    
    Matching priority:
    1. DOI match (most reliable)
    2. PMID match (very reliable)
    3. Title match (fallback)
    
    Args:
        ref1_id: Identifier string for reference 1
        ref2_id: Identifier string for reference 2
    
    Returns:
        True if references match, False otherwise
    """
    set1 = create_identifier_set(ref1_id)
    set2 = create_identifier_set(ref2_id)
    
    # Check for DOI match first
    doi1 = {v for v in set1 if v.startswith('doi:') or (':' not in v and '10.' in v)}
    doi2 = {v for v in set2 if v.startswith('doi:') or (':' not in v and '10.' in v)}
    if doi1 and doi2 and doi1.intersection(doi2):
        return True
    
    # Check for PMID match
    pmid1 = {v for v in set1 if v.startswith('pmid:')}
    pmid2 = {v for v in set2 if v.startswith('pmid:')}
    if pmid1 and pmid2 and pmid1.intersection(pmid2):
        return True
    
    # Check for title match (fallback)
    title1 = {v for v in set1 if v.startswith('title:')}
    title2 = {v for v in set2 if v.startswith('title:')}
    if title1 and title2 and title1.intersection(title2):
        return True
    
    return False


def _identifier_keys(identifier_string: str) -> List[str]:
    """Return the individual prefixed identifier tokens (doi:..., pmid:..., title:...) in a string."""
    return [part for part in identifier_string.split("|") if part]


def _extract_rn_labels(ref_text: str) -> List[str]:
    labels = []
    for line in ref_text.splitlines():
        if line.startswith("RN  -"):
            label = line[6:].strip()
            if label and label not in labels:
                labels.append(label)
    return labels


def _merge_rn_labels(master_ref_text: str, input_ref_text: str) -> Tuple[str, bool]:
    """Add missing RN labels from input reference to master reference text."""
    master_labels = _extract_rn_labels(master_ref_text)
    input_labels = _extract_rn_labels(input_ref_text)
    missing = [label for label in input_labels if label not in master_labels]
    if not missing:
        return master_ref_text, False

    lines = master_ref_text.splitlines()
    rn_lines = [f"RN  - {label}" for label in missing]
    for idx, line in enumerate(lines):
        if re.match(r"^ER\s+-\s*$", line):
            lines[idx:idx] = rn_lines
            return "\n".join(lines) + "\n", True

    lines.extend(rn_lines)
    lines.append("ER  -")
    return "\n".join(lines) + "\n", True


def _load_master_lookup(master_path: Path, *, cache_dir: Optional[Path] = None) -> Tuple[Dict[str, int], List[Tuple[str, str]]]:
    """Parse master RIS into (identifier_index, master_refs).

    `identifier_index` maps each individual prefixed identifier (doi:..., pmid:...,
    title:...) to the index of that reference in `master_refs`.

    Uses an mtime-keyed cache at <cache_dir>/master_lookup.json when provided.
    """
    if cache_dir is not None:
        cache_path = cache_dir / MASTER_LOOKUP_CACHE_FILE
        try:
            if cache_path.exists():
                with open(cache_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                cached_mtime = payload.get("master_mtime")
                cached_master = payload.get("master_path")
                if (
                    cached_master == str(master_path)
                    and cached_mtime == master_path.stat().st_mtime
                    and payload.get("schema_version") == 2
                    and "identifier_index" in payload
                    and "refs" in payload
                ):
                    master_refs_cached = [(item["text"], item["identifier"]) for item in payload["refs"]]
                    return payload["identifier_index"], master_refs_cached
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    master_refs = parse_ris_file(master_path)
    identifier_index: Dict[str, int] = {}
    for idx, (ref_text, identifier) in enumerate(master_refs):
        for key in _identifier_keys(identifier):
            identifier_index[key] = idx

    if cache_dir is not None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / MASTER_LOOKUP_CACHE_FILE
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "_generated_by": "automated_search/scripts/helpers/merge_ris_to_master.py",
                        "schema_version": 2,
                        "master_path": str(master_path),
                        "master_mtime": master_path.stat().st_mtime,
                        "identifier_index": identifier_index,
                        "refs": [{"text": t, "identifier": i} for (t, i) in master_refs],
                    },
                    f,
                )
        except OSError:
            pass

    return identifier_index, master_refs


def merge_ris_to_master(input_ris_path: Path, ris_source_dir: Path, output_path: Optional[Path] = None) -> Path:
    """
    Merge input RIS file with master RIS file.
    
    Args:
        input_ris_path: Path to input RIS file (prepared with absolute paths and search terms)
        ris_source_dir: Path to RIS_source_files directory
        output_path: Optional output path. If None, creates timestamped filename.
    
    Returns:
        Path to output RIS file

    Performance: O(N+M) instead of the prior O(N*M) nested-loop reference comparison.
    Master RIS parse is cached at <repo>/automated_search/.cache/master_lookup.json
    keyed by master-file mtime, so repeat invocations skip the parse.
    """
    print("="*70)
    print("MERGE RIS TO MASTER")
    print("="*70)
    print()
    
    # Find newest master RIS file
    print("Finding newest master RIS file...")
    master_ris_path = find_newest_master_ris(ris_source_dir)
    
    if not master_ris_path:
        raise FileNotFoundError(f"No master RIS file found in {ris_source_dir}")
    
    print(f"  Master RIS: {master_ris_path.name}")
    print(f"  Location: {master_ris_path}")
    print()
    
    # Parse both RIS files
    print("Parsing RIS files (with mtime-keyed cache for master)...")
    repo_root = Path(__file__).resolve().parents[3]
    cache_dir = repo_root / "automated_search" / CACHE_DIR_NAME
    identifier_index, master_refs = _load_master_lookup(master_ris_path, cache_dir=cache_dir)
    print(f"    Found {len(master_refs)} references in master RIS "
          f"({len(identifier_index)} indexed identifier tokens)")

    print(f"  Reading input RIS: {input_ris_path.name}")
    input_refs = parse_ris_file(input_ris_path)
    print(f"    Found {len(input_refs)} references in input RIS")
    print()

    # O(N) dedup: for each input ref, check if any of its identifier tokens is in the index.
    # If the input ref is already in the master, keep the master record but add
    # any new RN labels so the visualizer can place that paper under every
    # query that found it.
    print("Checking for duplicates (O(N+M) dict lookup)...")
    new_refs: List[Tuple[str, str]] = []
    new_identifier_index: Dict[str, int] = {}
    duplicates: List[str] = []
    rn_labels_merged = 0
    for ref_text, identifier in input_refs:
        keys = _identifier_keys(identifier)
        master_match_idx = next((identifier_index[key] for key in keys if key in identifier_index), None)
        if master_match_idx is not None:
            duplicates.append(identifier)
            merged_ref, changed = _merge_rn_labels(master_refs[master_match_idx][0], ref_text)
            if changed:
                master_refs[master_match_idx] = (merged_ref, master_refs[master_match_idx][1])
                rn_labels_merged += 1
            continue

        new_match_idx = next((new_identifier_index[key] for key in keys if key in new_identifier_index), None)
        if new_match_idx is not None:
            duplicates.append(identifier)
            merged_ref, changed = _merge_rn_labels(new_refs[new_match_idx][0], ref_text)
            if changed:
                new_refs[new_match_idx] = (merged_ref, new_refs[new_match_idx][1])
                rn_labels_merged += 1
        else:
            new_identifier_index.update({key: len(new_refs) for key in keys})
            new_refs.append((ref_text, identifier))

    print(f"  New references to add: {len(new_refs)}")
    print(f"  Duplicates skipped: {len(duplicates)}")
    print(f"  Existing references updated with new RN labels: {rn_labels_merged}")
    print()
    
    # Generate output filename if not provided
    if output_path is None:
        timestamp = datetime.datetime.now().strftime("%m_%d_%y_%I%M%p").lower()
        output_filename = f"pubmed_NLP_v4_{timestamp}.txt"
        output_path = ris_source_dir / output_filename
    
    # Write merged RIS file
    print(f"Writing merged RIS file...")
    print(f"  Output: {output_path.name}")
    print(f"  Location: {output_path}")
    print()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write all master references first
        for ref_text, identifier in master_refs:
            f.write(ref_text)
            if not ref_text.endswith('\n'):
                f.write('\n')
        
        # Write new references
        for ref_text, identifier in new_refs:
            f.write(ref_text)
            if not ref_text.endswith('\n'):
                f.write('\n')
    
    # Print summary
    total_final = len(master_refs) + len(new_refs)
    
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Master RIS: {master_ris_path.name}")
    print(f"  Input RIS: {input_ris_path.name}")
    print(f"  Total references in master: {len(master_refs)}")
    print(f"  New references added: {len(new_refs)}")
    print(f"  Duplicates skipped: {len(duplicates)}")
    print(f"  Existing references updated with new RN labels: {rn_labels_merged}")
    print(f"  Final count: {total_final}")
    print(f"  Output file: {output_path.name}")
    print(f"  Location: {output_path}")
    print("="*70)
    
    return output_path


def main():
    """Main execution function."""
    repo_root = Path(__file__).resolve().parents[3]
    ris_source_dir = repo_root / "visualizer_nlp_lit_review" / "RIS_source_files"
    
    print("="*70)
    print("MERGE RIS TO MASTER")
    print("="*70)
    print()
    
    # Get input RIS file
    user_input = input("Enter path to RIS file to merge: ").strip()
    if not user_input:
        print("ERROR: No file specified")
        return
    
    user_input = user_input.strip("'\"")
    input_ris_path = Path(user_input)
    
    if not input_ris_path.exists():
        print(f"ERROR: RIS file not found: {input_ris_path}")
        return
    
    if not input_ris_path.is_absolute():
        input_ris_path = input_ris_path.resolve()
    
    print()
    
    # Merge
    try:
        output_path = merge_ris_to_master(input_ris_path, ris_source_dir)
        print()
        print("Merge completed successfully!")
    except Exception as e:
        print(f"ERROR: {e}")
        return


if __name__ == "__main__":
    main()

