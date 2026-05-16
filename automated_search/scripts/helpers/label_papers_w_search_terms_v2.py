#!/usr/bin/env python3
"""
Create composite RIS file with Research Notes (RN) fields from multiple RIS files.

This script:
1. Lists query folders in the default or user-provided zotero_pass directory
2. Lets user select a folder
3. Recursively finds all RIS files in subfolders of the selected folder
4. Extracts search terms from RIS filenames
5. Adds RN fields to each entry with the search term from its source filename
6. Combines all RIS files into one composite RIS file
7. Deduplicates entries (by PMID, DOI, ISSN, or Title) and combines RN values

Inputs:
- RIS files under the ZOTERO_PASS_DIR environment variable, or under find_pubmed_full_texts/zotero_pass
  relative to this repository when that folder exists.

Outputs:
- Composite RIS files written into the selected query folder.

Version 2: Supports both original pubmed_*.ris files and new format with identifier
prefixes (e.g., a0pubmed-...ris) in subdirectories.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict


# Script now lives under automated_search/scripts/helpers.
REPO_ROOT = Path(__file__).resolve().parents[3]


def get_default_ris_dir() -> Path:
    """Return the default zotero_pass directory without hardcoding the repository path."""
    env_dir = os.environ.get("ZOTERO_PASS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return REPO_ROOT / "find_pubmed_full_texts" / "zotero_pass"


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


def transform_underscores_for_rn(text: str) -> str:
    """
    Transform underscores for RN field display:
    - Delete underscores directly adjacent to '(' or ')' characters
    - Replace all other underscores with spaces
    
    Examples:
    '(_CT_report_)' -> '( CT report )'
    'test_word' -> 'test word'
    """
    # Delete underscores directly adjacent to parentheses
    # Pattern: underscore followed by ')' or preceded by '('
    text = re.sub(r'_\)', ')', text)
    text = re.sub(r'\(_', '(', text)
    # Replace remaining underscores with spaces
    text = text.replace('_', ' ')
    return text


def extract_search_term_from_filename(filename: str) -> str:
    """
    Extract search term from .ris filename.
    
    Supports two patterns:
    1. Original: 'pubmed_' prefix, extract everything after 'pubmed_' up to first digit.
       Example: 'pubmed_clinical.ris' -> 'clinical'
       Example: 'pubmed_CT_extraction_12_15_1220pm.ris' -> 'CT_extraction'
    
    2. New: Optional identifier prefix + 'pubmed' or 'pubmed-', extract everything after.
       Apply underscore transformation for RN display.
       Example: 'a0pubmed-(_CT_report_OR_MRI_report_).ris' -> '( CT report OR MRI report )'
       Example: 'a1pubmed-(_clinical_NLP_OR_clinical_text_).ris' -> '( clinical NLP OR clinical text )'
    """
    # Remove extension
    name = Path(filename).stem
    
    # Pattern 1: Original format - starts with 'pubmed_'
    if name.startswith('pubmed_'):
        # Extract everything after 'pubmed_' up to first digit
        match = re.search(r'^pubmed_(.+?)(?=\d|$)', name)
        if match:
            # Strip trailing underscores
            keyword = match.group(1).rstrip('_')
            return keyword
    
    # Pattern 2: New format - identifier prefix + 'pubmed' or 'pubmed-'
    # Match: optional alphanumeric prefix, then 'pubmed' or 'pubmed-', then rest
    match = re.search(r'^[a-zA-Z0-9]+pubmed[-]?(.+)$', name)
    if match:
        search_term = match.group(1)
        # Apply underscore transformation for RN field
        return transform_underscores_for_rn(search_term)
    
    return ""


def parse_ris_file(ris_path: Path, search_term: str) -> Dict[str, Dict[str, str]]:
    """
    Parse .ris file and extract papers with their identifiers.
    
    Args:
        ris_path: Path to .ris file
        search_term: Search term associated with this file
    
    Returns:
        Dictionary with keys: 'pmid', 'doi', 'title', 'issn' -> each maps to dict of 
        identifier -> set of search terms
    """
    papers = {
        'pmid': {},
        'doi': {},
        'title': {},
        'issn': {}
    }
    
    if not ris_path.exists():
        print(f"WARNING: .ris file not found: {ris_path}")
        return papers
    
    with open(ris_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Parse RIS entries (separated by ER  - lines)
    current_entry = []
    pmid = None
    doi = None
    title = None
    issn_list = []
    current_field_tag = None
    
    for line in lines:
        line_stripped = line.rstrip()
        
        # Check if this is the end of a record
        if line_stripped == 'ER  -' or line_stripped == 'ER -':
            # Process the completed entry
            if pmid or doi or title or issn_list:
                # Add to lookup dictionaries
                if pmid:
                    if pmid not in papers['pmid']:
                        papers['pmid'][pmid] = set()
                    papers['pmid'][pmid].add(search_term)
                
                if doi:
                    normalized_doi = normalize_doi(doi)
                    if normalized_doi:
                        if normalized_doi not in papers['doi']:
                            papers['doi'][normalized_doi] = set()
                        papers['doi'][normalized_doi].add(search_term)
                
                if title:
                    normalized_title = normalize_title(title)
                    if normalized_title:
                        if normalized_title not in papers['title']:
                            papers['title'][normalized_title] = set()
                        papers['title'][normalized_title].add(search_term)
                
                # Add ISSN/ISBN to lookup
                for issn in issn_list:
                    # Normalize ISSN/ISBN: remove hyphens and spaces, convert to uppercase
                    normalized_issn = re.sub(r'[-\s]', '', issn).upper()
                    if normalized_issn:
                        if normalized_issn not in papers['issn']:
                            papers['issn'][normalized_issn] = set()
                        papers['issn'][normalized_issn].add(search_term)
            
            # Reset for next entry
            current_entry = []
            pmid = None
            doi = None
            title = None
            issn_list = []
            current_field_tag = None
            continue
        
        # Check if line starts with a RIS tag (2 letters, 2 spaces, hyphen)
        if re.match(r'^[A-Z]{2}\s+-', line_stripped):
            tag = line_stripped[0:2]
            value = line_stripped[6:].strip()
            
            # Track fields
            if tag == 'AN':
                pmid = value
                current_field_tag = 'AN'
            elif tag == 'DO':
                doi = value
                current_field_tag = 'DO'
            elif tag == 'TI':
                title = value
                current_field_tag = 'TI'
            elif tag == 'SN':
                # SN field may contain multiple ISSNs/ISBNs separated by spaces
                sn_value = value
                # Remove parenthetical text like "(Electronic)", "(Linking)", "(Print)"
                sn_value = re.sub(r'\s*\([^)]+\)', '', sn_value)
                # Split by space to handle multiple ISSNs
                for issn in sn_value.split():
                    issn = issn.strip()
                    if issn:  # Only add non-empty values
                        issn_list.append(issn)
                current_field_tag = 'SN'
            else:
                current_field_tag = None
        else:
            # Continuation of previous field
            if current_field_tag == 'TI' and title is not None:
                title += ' ' + line_stripped.strip()
            current_field_tag = None
        
        current_entry.append(line)
    
    return papers


def parse_ris_entries(ris_path: Path) -> List[Dict[str, any]]:
    """
    Parse .ris file and return full entry structures.
    
    Args:
        ris_path: Path to .ris file
    
    Returns:
        List of dictionaries, each containing:
        - 'lines': List of raw RIS lines for the entry
        - 'pmid': AN field value (or None)
        - 'doi': DO field value (or None)
        - 'title': TI field value (or None)
        - 'issn_list': List of SN field values
    """
    entries = []
    
    if not ris_path.exists():
        print(f"WARNING: .ris file not found: {ris_path}")
        return entries
    
    with open(ris_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    current_entry_lines = []
    pmid = None
    doi = None
    title = None
    issn_list = []
    current_field_tag = None
    
    for line in lines:
        line_stripped = line.rstrip()
        
        # Check if this is the end of a record
        if line_stripped == 'ER  -' or line_stripped == 'ER -':
            # Save the completed entry
            if current_entry_lines:
                entries.append({
                    'lines': current_entry_lines + [line],  # Include ER line
                    'pmid': pmid,
                    'doi': doi,
                    'title': title,
                    'issn_list': issn_list.copy()
                })
            
            # Reset for next entry
            current_entry_lines = []
            pmid = None
            doi = None
            title = None
            issn_list = []
            current_field_tag = None
            continue
        
        # Check if line starts with a RIS tag (2 letters, 2 spaces, hyphen)
        if re.match(r'^[A-Z]{2}\s+-', line_stripped):
            tag = line_stripped[0:2]
            value = line_stripped[6:].strip()
            
            # Track fields
            if tag == 'AN':
                pmid = value
                current_field_tag = 'AN'
            elif tag == 'DO':
                doi = value
                current_field_tag = 'DO'
            elif tag == 'TI':
                title = value
                current_field_tag = 'TI'
            elif tag == 'SN':
                # SN field may contain multiple ISSNs/ISBNs separated by spaces
                sn_value = value
                # Remove parenthetical text like "(Electronic)", "(Linking)", "(Print)"
                sn_value = re.sub(r'\s*\([^)]+\)', '', sn_value)
                # Split by space to handle multiple ISSNs
                for issn in sn_value.split():
                    issn = issn.strip()
                    if issn:  # Only add non-empty values
                        issn_list.append(issn)
                current_field_tag = 'SN'
            else:
                current_field_tag = None
        else:
            # Continuation of previous field
            if current_field_tag == 'TI' and title is not None:
                title += ' ' + line_stripped.strip()
            current_field_tag = None
        
        current_entry_lines.append(line)
    
    return entries


def load_all_ris_files(ris_dir: Path) -> Dict[str, Dict[str, Set[str]]]:
    """
    Load all .ris files and build unified lookup dictionaries.
    
    Searches both top-level directory (for original pubmed_*.ris files) and
    recursively in subdirectories (for new format with identifier prefixes).
    
    Args:
        ris_dir: Directory containing .ris files (searches top-level and recursively in subdirectories)
    
    Returns:
        Dictionary with keys: 'pmid', 'doi', 'title', 'issn' -> each maps to dict of 
        identifier -> set of search terms
    """
    all_papers = {
        'pmid': defaultdict(set),
        'doi': defaultdict(set),
        'title': defaultdict(set),
        'issn': defaultdict(set)
    }
    
    # Find all .ris files - both original format and new format
    # Original: top-level pubmed_*.ris files
    original_ris_files = list(ris_dir.glob('pubmed_*.ris'))
    original_names_set = {f.name for f in original_ris_files}
    
    # New: recursive search for *.ris files (excluding those already found in top-level)
    # rglob includes top-level, so we need to filter out files that match original pattern
    all_ris_files = list(ris_dir.rglob('*.ris'))
    new_ris_files = [f for f in all_ris_files 
                     if f.parent != ris_dir or f.name not in original_names_set]
    
    # Combine both lists
    ris_files = original_ris_files + new_ris_files
    
    if not ris_files:
        print(f"WARNING: No .ris files found in {ris_dir}")
        return {
            'pmid': dict(all_papers['pmid']),
            'doi': dict(all_papers['doi']),
            'title': dict(all_papers['title']),
            'issn': dict(all_papers['issn'])
        }
    
    for ris_file in ris_files:
        search_term = extract_search_term_from_filename(ris_file.name)
        if not search_term:
            print(f"WARNING: Could not extract search term from {ris_file.name}")
            continue
        
        # Show relative path if in subdirectory
        display_path = ris_file.relative_to(ris_dir) if ris_file.parent != ris_dir else ris_file.name
        print(f"Parsing {display_path} (search term: {search_term})")
        papers = parse_ris_file(ris_file, search_term)
        
        # Merge into unified dictionaries
        for identifier_type in ['pmid', 'doi', 'title', 'issn']:
            for identifier, terms in papers[identifier_type].items():
                all_papers[identifier_type][identifier].update(terms)
    
    # Convert defaultdict to regular dict for cleaner output
    return {
        'pmid': dict(all_papers['pmid']),
        'doi': dict(all_papers['doi']),
        'title': dict(all_papers['title']),
        'issn': dict(all_papers['issn'])
    }


def convert_file_paths_to_absolute(entry_lines: List[str], ris_file_path: Path) -> tuple[List[str], bool]:
    """
    Convert relative file paths in L1/L2/L3/L4 fields to absolute paths.
    
    Args:
        entry_lines: List of RIS entry lines
        ris_file_path: Path to the source RIS file (used to resolve relative paths)
    
    Returns:
        Tuple of (modified list of lines with absolute paths, has_valid_full_text)
        has_valid_full_text: True if entry has an L1-L4 field with a valid file path
    """
    ris_file_dir = ris_file_path.parent
    modified_lines = []
    has_full_text_field = False
    has_valid_path = False
    
    for line in entry_lines:
        line_stripped = line.rstrip()
        
        # Check if this is a file attachment field (L1, L2, L3, or L4)
        if re.match(r'^(L[1-4])\s+-', line_stripped):
            has_full_text_field = True
            tag = line_stripped[0:2]
            value = line_stripped[6:].strip()
            
            # Check if it's a relative path (doesn't start with /)
            if value and not value.startswith('/') and not value.startswith('http://') and not value.startswith('https://'):
                # Resolve relative path against RIS file's directory
                relative_path = Path(value)
                absolute_path = (ris_file_dir / relative_path).resolve()
                
                # Only convert if the absolute path exists
                if absolute_path.exists() and absolute_path.is_file():
                    has_valid_path = True
                    new_value = str(absolute_path)
                    # Reconstruct line with absolute path
                    new_line = f'{tag}  - {new_value}\n'
                    modified_lines.append(new_line)
                else:
                    # Path doesn't exist, keep original
                    modified_lines.append(line)
            else:
                # Already absolute or URL
                if value.startswith('/'):
                    # Check if absolute path exists
                    abs_path = Path(value)
                    if abs_path.exists() and abs_path.is_file():
                        has_valid_path = True
                elif value.startswith('http://') or value.startswith('https://'):
                    # URL - consider valid
                    has_valid_path = True
                modified_lines.append(line)
        else:
            modified_lines.append(line)
    
    # Entry has valid full text if it has an L1-L4 field AND the path is valid
    has_valid_full_text = has_full_text_field and has_valid_path
    return modified_lines, has_valid_full_text


def get_entry_identifier(entry: Dict[str, any]) -> tuple:
    """
    Get identifier tuple for an entry for deduplication.
    Priority: PMID > DOI > ISSN > Title
    
    Returns:
        Tuple of (identifier_type, identifier_value) or None if no identifier found
    """
    if entry.get('pmid'):
        return ('pmid', entry['pmid'].strip())
    
    if entry.get('doi'):
        normalized_doi = normalize_doi(entry['doi'])
        if normalized_doi:
            return ('doi', normalized_doi)
    
    if entry.get('issn_list'):
        for issn in entry['issn_list']:
            normalized_issn = re.sub(r'[-\s]', '', issn).upper()
            if normalized_issn:
                return ('issn', normalized_issn)
    
    if entry.get('title'):
        normalized_title = normalize_title(entry['title'])
        if normalized_title:
            return ('title', normalized_title)
    
    return None


def add_rn_field_to_entry_lines(entry_lines: List[str], rn_term: str) -> List[str]:
    """
    Add or replace RN field in RIS entry lines.
    
    Args:
        entry_lines: List of RIS entry lines (without ER line)
        rn_term: Search term to add to RN field
    
    Returns:
        Modified list of lines with RN field added/replaced
    """
    rn_line = f'RN  - {rn_term}\n'
    rn_index = None
    output_lines = []
    
    # Find existing RN field
    for i, line in enumerate(entry_lines):
        line_stripped = line.rstrip()
        if re.match(r'^RN\s+-', line_stripped):
            rn_index = i
            break
        output_lines.append(line)
    
    # Add or replace RN field
    if rn_index is not None:
        # Replace existing RN field
        output_lines = entry_lines[:rn_index] + [rn_line] + entry_lines[rn_index + 1:]
    else:
        # Add RN field before ER (ER will be added separately)
        output_lines = entry_lines + [rn_line]
    
    return output_lines


def combine_ris_files_with_rn(ris_files: List[Path]) -> List[Dict[str, any]]:
    """
    Combine RIS files and add RN fields based on filenames.
    
    Args:
        ris_files: List of RIS file paths
    
    Returns:
        List of entry dictionaries with RN fields added
    """
    all_entries = []
    
    for ris_file in ris_files:
        # Extract search term from filename
        search_term = extract_search_term_from_filename(ris_file.name)
        if not search_term:
            print(f"WARNING: Could not extract search term from {ris_file.name}, skipping")
            continue
        
        # Parse RIS entries
        entries = parse_ris_entries(ris_file)
        
        # Add RN field to each entry and convert relative paths to absolute
        for entry in entries:
            # Convert relative file paths to absolute paths
            entry_lines_with_absolute_paths, has_valid_full_text = convert_file_paths_to_absolute(entry['lines'], ris_file)
            
            # Add RN field to entry lines (excluding ER line)
            entry_lines_without_er = entry_lines_with_absolute_paths[:-1]  # All lines except ER
            entry_lines_with_rn = add_rn_field_to_entry_lines(entry_lines_without_er, search_term)
            
            # Reconstruct entry with RN field and absolute paths
            entry_with_rn = entry.copy()
            entry_with_rn['lines'] = entry_lines_with_rn + [entry_lines_with_absolute_paths[-1]]  # Add ER back
            entry_with_rn['rn_term'] = search_term
            entry_with_rn['has_valid_full_text'] = has_valid_full_text
            all_entries.append(entry_with_rn)
        
        print(f"Processed {ris_file.name}: {len(entries)} entries (search term: {search_term})")
    
    return all_entries


def deduplicate_and_combine_ris_entries(entries: List[Dict[str, any]]) -> List[Dict[str, any]]:
    """
    Deduplicate RIS entries by identifier and combine RN fields.
    
    Args:
        entries: List of entry dictionaries with 'lines', 'pmid', 'doi', 'title', 'issn_list', 'rn_term'
    
    Returns:
        List of deduplicated entries with combined RN fields
    """
    # Group entries by identifier
    identifier_map = {}  # identifier -> list of entry indices
    
    for idx, entry in enumerate(entries):
        identifier = get_entry_identifier(entry)
        if identifier:
            id_type, id_value = identifier
            if id_value not in identifier_map:
                identifier_map[id_value] = []
            identifier_map[id_value].append(idx)
    
    # Process duplicates
    seen_indices = set()
    combined_entries = []
    
    for id_value, indices in identifier_map.items():
        if len(indices) > 1:
            # Duplicate found - combine them
            # Prefer entry with full text as base entry (Option 1 fix)
            base_idx = indices[0]
            for idx in indices:
                if entries[idx].get('has_valid_full_text', False):
                    base_idx = idx
                    break  # Use first entry with full text as base
            
            base_entry = entries[base_idx].copy()
            base_rn_term = base_entry.get('rn_term', '')
            base_has_full_text = base_entry.get('has_valid_full_text', False)
            
            # Collect all RN terms from duplicates
            # Also track if any duplicate has valid full text (if one has it, consider it valid)
            rn_terms_set = set()
            has_any_full_text = base_has_full_text
            
            if base_rn_term:
                rn_terms_set.add(base_rn_term)
            
            for idx in indices:
                if idx == base_idx:
                    continue  # Skip base entry (already processed)
                seen_indices.add(idx)
                if entries[idx].get('rn_term'):
                    rn_terms_set.add(entries[idx]['rn_term'])
                # If any duplicate has valid full text, mark the combined entry as having it
                if entries[idx].get('has_valid_full_text', False):
                    has_any_full_text = True
            
            # Combine RN terms (comma-separated, sorted)
            if rn_terms_set:
                combined_rn = ', '.join(sorted(rn_terms_set))
                base_entry['rn_term'] = combined_rn
                # Update RN field in lines
                entry_lines_without_er = base_entry['lines'][:-1]  # All lines except ER
                entry_lines_with_rn = add_rn_field_to_entry_lines(entry_lines_without_er, combined_rn)
                base_entry['lines'] = entry_lines_with_rn + [base_entry['lines'][-1]]  # Add ER back
            
            # Set has_valid_full_text flag
            base_entry['has_valid_full_text'] = has_any_full_text
            
            combined_entries.append(base_entry)
            seen_indices.add(base_idx)
        else:
            # No duplicate, keep as is
            idx = indices[0]
            if idx not in seen_indices:
                combined_entries.append(entries[idx])
                seen_indices.add(idx)
    
    # Add entries that had no identifier (keep them all)
    for idx, entry in enumerate(entries):
        if idx not in seen_indices:
            combined_entries.append(entry)
    
    return combined_entries


def match_paper_to_search_terms(an_field: str, doi_field: str, title_field: str, sn_field: str,
                                lookups: Dict[str, Dict[str, Set[str]]]) -> Set[str]:
    """
    Match a paper to search terms using multiple strategies.
    
    Args:
        an_field: AN field value (PubMed ID)
        doi_field: DO field value (DOI)
        title_field: TI field value (Title)
        sn_field: SN field value (ISSN/ISBN)
        lookups: Lookup dictionaries from .ris files
    
    Returns:
        Set of search terms that match this paper
    """
    matched_terms = set()
    
    # Strategy 1: Match by PMID (AN field)
    if an_field:
        an_field = an_field.strip()
        if an_field in lookups['pmid']:
            matched_terms.update(lookups['pmid'][an_field])
            return matched_terms  # PMID is most reliable, return immediately
    
    # Strategy 2: Match by DOI
    if doi_field:
        normalized_doi = normalize_doi(doi_field)
        if normalized_doi and normalized_doi in lookups['doi']:
            matched_terms.update(lookups['doi'][normalized_doi])
            return matched_terms  # DOI is reliable, return immediately
    
    # Strategy 3: Match by ISSN/ISBN
    if sn_field:
        # Normalize and split SN field (may contain multiple ISSNs/ISBNs)
        sn_values = sn_field.split()
        for sn in sn_values:
            # Normalize: remove hyphens and spaces, convert to uppercase
            normalized_sn = re.sub(r'[-\s]', '', sn).upper()
            if normalized_sn and normalized_sn in lookups['issn']:
                matched_terms.update(lookups['issn'][normalized_sn])
                return matched_terms  # ISSN/ISBN is reliable, return immediately
    
    # Strategy 4: Match by Title (fallback)
    if title_field:
        normalized_title = normalize_title(title_field)
        if normalized_title and normalized_title in lookups['title']:
            matched_terms.update(lookups['title'][normalized_title])
    
    return matched_terms


def add_research_notes_to_ris_with_explicit_label(
    input_ris_path: Path,
    output_ris_path: Path,
    label: str,
) -> None:
    """Stamp every entry in `input_ris_path` with `RN  - <label>`; write to `output_ris_path`.

    Used by the new SearchRun-aware pipeline: the wrapper passes
    `metadata.search_term_label` directly, which means we don't need to
    parse the historical Endnote/search_term_results tree at all (the legacy
    `load_all_ris_files` path remains for --legacy callers).

    Inputs:
        input_ris_path: RIS file produced by Step 1 (absolute L1 paths).
        output_ris_path: target path for the RN-tagged RIS.
        label: literal string written into the RN field (e.g. "( NLP extraction )").

    Outputs:
        output_ris_path with one RN field per entry containing `label`.
        Existing RN fields are replaced.

    The file is opened, scanned line by line, and rewritten with the RN field
    inserted/replaced before each ER terminator. No lookup tables are loaded.
    """
    if not label:
        raise ValueError("explicit label must be non-empty")

    with open(input_ris_path, "r", encoding="utf-8") as f_in:
        lines = f_in.readlines()

    output_lines: List[str] = [
        "; generated by automated_search/scripts/helpers/label_papers_w_search_terms_v2.py::add_research_notes_to_ris_with_explicit_label\n",
        f"; explicit_label: {label}\n",
        "\n",
    ]
    current_entry: List[str] = []
    rn_index = None
    rn_line = f"RN  - {label}\n"

    for line in lines:
        line_stripped = line.rstrip()
        if line_stripped == "ER  -" or line_stripped == "ER -":
            if rn_index is not None:
                current_entry[rn_index] = rn_line
            else:
                current_entry.append(rn_line)
            output_lines.extend(current_entry)
            output_lines.append(line)
            current_entry = []
            rn_index = None
            continue
        if re.match(r"^RN\s+-", line_stripped):
            rn_index = len(current_entry)
        current_entry.append(line)

    if current_entry:
        output_lines.extend(current_entry)

    with open(output_ris_path, "w", encoding="utf-8") as f_out:
        f_out.writelines(output_lines)


def add_research_notes_to_ris(input_ris_path: Path, output_ris_path: Path,
                               lookups: Dict[str, Dict[str, Set[str]]]) -> None:
    """
    Add RN (Research Notes) fields to RIS file based on .ris lookups.
    
    Args:
        input_ris_path: Path to input RIS file
        output_ris_path: Path to output RIS file
        lookups: Lookup dictionaries from .ris files
    """
    with open(input_ris_path, 'r', encoding='utf-8') as f_in:
        lines = f_in.readlines()
    
    output_lines = []
    current_entry = []
    an_field = None
    doi_field = None
    title_field = None
    sn_field = None
    rn_index = None
    current_field_tag = None
    
    for line in lines:
        line_stripped = line.rstrip()
        
        # Check if this is the end of a record
        if line_stripped == 'ER  -' or line_stripped == 'ER -':
            # End of record - add RN field if we have matching search terms
            matched_terms = match_paper_to_search_terms(
                an_field, doi_field, title_field, sn_field, lookups
            )
            
            if matched_terms:
                # Format search terms as comma-separated string
                terms_text = ', '.join(sorted(matched_terms))
                rn_line = f'RN  - {terms_text}\n'
                
                if rn_index is not None:
                    # Replace existing RN field
                    current_entry[rn_index] = rn_line
                else:
                    # Add RN field before ER
                    current_entry.append(rn_line)
            
            # Add all entry lines including ER
            output_lines.extend(current_entry)
            output_lines.append(line)  # ER line
            
            # Reset for next entry
            current_entry = []
            an_field = None
            doi_field = None
            title_field = None
            sn_field = None
            rn_index = None
            current_field_tag = None
            continue
        
        # Check if line starts with a RIS tag (2 letters, 2 spaces, hyphen)
        if re.match(r'^[A-Z]{2}\s+-', line_stripped):
            tag = line_stripped[0:2]
            value = line_stripped[6:].strip()
            
            # Track fields
            if tag == 'AN':
                an_field = value
                current_field_tag = 'AN'
            elif tag == 'DO':
                doi_field = value
                current_field_tag = 'DO'
            elif tag == 'TI':
                title_field = value
                current_field_tag = 'TI'
            elif tag == 'SN':
                sn_field = value
                current_field_tag = 'SN'
            elif tag == 'RN':
                rn_index = len(current_entry)
                current_field_tag = 'RN'
            else:
                current_field_tag = None
        else:
            # Continuation of previous field
            if current_field_tag == 'TI' and title_field is not None:
                title_field += ' ' + line_stripped.strip()
            current_field_tag = None
        
        # Add line to current entry
        current_entry.append(line)
    
    # Write output file
    with open(output_ris_path, 'w', encoding='utf-8') as f_out:
        f_out.writelines(output_lines)


def main():
    """Main function."""
    # Default directory
    default_ris_dir = get_default_ris_dir()
    
    print("="*70)
    print("CREATE COMPOSITE RIS FILE WITH SEARCH TERMS (v2)")
    print("="*70)
    print()
    
    # Verify default directory exists
    if not default_ris_dir.exists():
        print(f"Default directory not found: {default_ris_dir}")
        user_input = input("Enter zotero_pass directory: ").strip().strip("'\"")
        if not user_input:
            print("ERROR: No directory specified")
            return
        default_ris_dir = Path(user_input).expanduser().resolve()
        if not default_ris_dir.exists():
            print(f"ERROR: Directory not found: {default_ris_dir}")
            return
    
    # List subfolders
    subfolders = [f for f in default_ris_dir.iterdir() if f.is_dir()]
    subfolders.sort()  # Sort alphabetically
    
    if not subfolders:
        print(f"ERROR: No subfolders found in {default_ris_dir}")
        return
    
    # Display folder selection
    print("Which query folder?")
    print()
    for idx, folder in enumerate(subfolders, 1):
        print(f" ({idx}) {folder.name}")
    print()
    
    # Get user selection
    while True:
        try:
            selection = input("Enter folder number: ").strip()
            folder_idx = int(selection) - 1
            if 0 <= folder_idx < len(subfolders):
                selected_folder = subfolders[folder_idx]
                break
            else:
                print(f"Invalid selection. Please enter a number between 1 and {len(subfolders)}")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return
    
    print()
    print(f"Selected folder: {selected_folder.name}")
    print()
    
    # Find all RIS files recursively in subfolders of selected folder
    ris_files = list(selected_folder.rglob('*.ris'))
    
    if not ris_files:
        print(f"WARNING: No .ris files found in {selected_folder}")
        return
    
    print(f"Found {len(ris_files)} RIS file(s) in subfolders")
    print()
    
    # Combine RIS files with RN fields
    print("Processing RIS files and adding search terms...")
    all_entries = combine_ris_files_with_rn(ris_files)
    
    print()
    print(f"Total entries before deduplication: {len(all_entries)}")
    
    # Deduplicate entries
    print("Deduplicating entries...")
    deduplicated_entries = deduplicate_and_combine_ris_entries(all_entries)
    
    print(f"Total entries after deduplication: {len(deduplicated_entries)}")
    print()
    
    # Split entries into three groups: all, with full text, without full text
    entries_with_full_text = []
    entries_without_full_text = []
    
    for entry in deduplicated_entries:
        if entry.get('has_valid_full_text', False):
            entries_with_full_text.append(entry)
        else:
            entries_without_full_text.append(entry)
    
    # Generate output filenames
    base_name = selected_folder.name
    composite_filename = f"{base_name}_composite.ris"
    full_text_filename = f"{base_name}_composite_only_full_text.ris"
    no_full_text_filename = f"{base_name}_composite_no_full_text.ris"
    
    composite_path = selected_folder / composite_filename
    full_text_path = selected_folder / full_text_filename
    no_full_text_path = selected_folder / no_full_text_filename
    
    # Write main composite RIS file (all entries)
    print(f"Writing composite RIS file: {composite_filename}")
    with open(composite_path, 'w', encoding='utf-8') as f_out:
        for entry in deduplicated_entries:
            f_out.writelines(entry['lines'])
    
    # Write "only_full_text" RIS file (entries with valid full text)
    if entries_with_full_text:
        print(f"Writing full text only RIS file: {full_text_filename}")
        with open(full_text_path, 'w', encoding='utf-8') as f_out:
            for entry in entries_with_full_text:
                f_out.writelines(entry['lines'])
    
    # Write "no_full_text" RIS file (entries without valid full text)
    if entries_without_full_text:
        print(f"Writing no full text RIS file: {no_full_text_filename}")
        with open(no_full_text_path, 'w', encoding='utf-8') as f_out:
            for entry in entries_without_full_text:
                f_out.writelines(entry['lines'])
    
    print()
    print("="*70)
    print("COMPLETE")
    print("="*70)
    print(f"Successfully created composite RIS files:")
    print(f"  Main composite: {composite_filename} ({len(deduplicated_entries)} entries)")
    if entries_with_full_text:
        print(f"  Full text only: {full_text_filename} ({len(entries_with_full_text)} entries)")
    if entries_without_full_text:
        print(f"  No full text: {no_full_text_filename} ({len(entries_without_full_text)} entries)")
    print(f"Output location: {selected_folder}")
    print("="*70)


if __name__ == "__main__":
    main()
