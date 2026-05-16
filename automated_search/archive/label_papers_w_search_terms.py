#!/usr/bin/env python3
"""
Add Research Notes (RN) fields to RIS file based on .ris file matches.

This script parses .ris files to extract papers and their associated search terms,
then matches them to references in the RIS file and adds RN fields with 
comma-separated search terms.
"""

import re
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict


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


def extract_search_term_from_filename(filename: str) -> str:
    """
    Extract search term from .ris filename.
    Pattern: everything after 'pubmed_' up to (but not including) the first digit.
    Trailing underscores are stripped.
    Example: 'pubmed_clinical.ris' -> 'clinical'
    Example: 'pubmed_CT_extraction_12_15_1220pm_absolute_paths.ris' -> 'CT_extraction'
    Example: 'pubmed_CT_12_15_1220pm_absolute_paths_absolute_paths.ris' -> 'CT'
    """
    # Remove extension
    name = Path(filename).stem
    # Check if it starts with 'pubmed_'
    if not name.startswith('pubmed_'):
        return ""
    # Extract everything after 'pubmed_' up to first digit
    match = re.search(r'^pubmed_(.+?)(?=\d|$)', name)
    if match:
        # Strip trailing underscores
        keyword = match.group(1).rstrip('_')
        return keyword
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


def load_all_ris_files(ris_dir: Path) -> Dict[str, Dict[str, Set[str]]]:
    """
    Load all .ris files and build unified lookup dictionaries.
    
    Args:
        ris_dir: Directory containing .ris files (searches only top-level, not subdirectories)
    
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
    
    # Find all .ris files in top-level directory only (not subdirectories)
    ris_files = list(ris_dir.glob('pubmed_*.ris'))
    
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
        
        print(f"Parsing {ris_file.name} (search term: {search_term})")
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
    base_dir = Path(__file__).parent
    ris_dir = base_dir.parent / "Endnote" / "search_term_results"
    
    # Default RIS file
    default_ris_file = base_dir.parent / "Endnote" / "all_refs_12_16_25_1107am.txt"
    
    # Verify search_term_results directory exists
    if not ris_dir.exists():
        print(f"ERROR: .ris directory not found: {ris_dir}")
        return
    
    print("="*70)
    print("ADD RESEARCH NOTES TO RIS FILE")
    print("="*70)
    print()
    
    # Ask for input RIS file (with default option)
    if default_ris_file.exists():
        print(f"Default RIS file:")
        print(f"  {default_ris_file}")
        print()
        use_default = input("Use default RIS file? (y/n): ").strip().lower()
        if use_default == 'y':
            input_ris_file = default_ris_file
        else:
            user_input = input("Enter path to RIS file: ").strip()
            if not user_input:
                print("ERROR: No file specified")
                return
            user_input = user_input.strip("'\"")
            input_ris_file = Path(user_input)
    else:
        print("No default RIS file found")
        user_input = input("Enter path to RIS file: ").strip()
        if not user_input:
            print("ERROR: No file specified")
            return
        user_input = user_input.strip("'\"")
        input_ris_file = Path(user_input)
    
    if not input_ris_file.exists():
        print(f"ERROR: Input RIS file not found: {input_ris_file}")
        return
    
    # Generate output filename (add _with_rn before extension)
    input_stem = input_ris_file.stem
    input_suffix = input_ris_file.suffix
    output_ris_file = input_ris_file.parent / f"{input_stem}_with_rn{input_suffix}"
    
    print()
    print(f"Input file: {input_ris_file.name}")
    print(f"Output file: {output_ris_file.name}")
    print()
    
    # Load all .ris files
    print("Loading .ris files from search_term_results...")
    lookups = load_all_ris_files(ris_dir)
    
    # Print statistics
    print(f"\nLoaded lookup dictionaries:")
    print(f"  PMID entries: {len(lookups['pmid'])}")
    print(f"  DOI entries: {len(lookups['doi'])}")
    print(f"  Title entries: {len(lookups['title'])}")
    print(f"  ISSN/ISBN entries: {len(lookups['issn'])}")
    
    # Process RIS file
    print(f"\nProcessing RIS file: {input_ris_file.name}")
    add_research_notes_to_ris(input_ris_file, output_ris_file, lookups)
    
    print()
    print("="*70)
    print("COMPLETE")
    print("="*70)
    print(f"Successfully created output file: {output_ris_file.name}")
    print(f"Output location: {output_ris_file}")
    print("="*70)


if __name__ == "__main__":
    main()
