#!/usr/bin/env python3
"""
Convert NBIB references to RIS format and update existing RIS file.
- Extract all unmatched references from NBIB and create new RIS file
- Update existing RIS file to add search term to matched references' RN fields

Inputs:
- NBIB file in nbib_files.
- Existing RIS source file in visualizer_nlp_lit_review/RIS_source_files.

Outputs:
- Unmatched references RIS file in the external OneDrive Endnote/search_term_results directory.
- Updated local RIS source file with matched search terms added to RN fields.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]


def normalize_doi(doi: str) -> str:
    """Normalize DOI for comparison"""
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r'\s*\[doi\]\s*$', '', doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE)
    return doi.strip().lower()


def normalize_title(title: str) -> str:
    """Normalize title for comparison"""
    if not title:
        return ""
    title = ' '.join(title.split())
    return title.lower().strip()


def normalize_author(author: str) -> str:
    """Normalize author name for comparison"""
    if not author:
        return ""
    author = ' '.join(author.split())
    if ',' in author:
        last_name = author.split(',')[0].strip()
    else:
        parts = author.split()
        last_name = parts[0] if parts else ""
    return last_name.lower().strip()


def parse_nbib_file_full(nbib_path: str) -> List[Dict]:
    """Parse NBIB file and extract all fields"""
    references = []
    
    with open(nbib_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Split by PMID- (new record marker)
    records = re.split(r'^PMID-\s+', content, flags=re.MULTILINE)
    
    for record in records:
        if not record.strip():
            continue
        
        ref = {
            'pmid': '',
            'title': '',
            'abstract': '',
            'authors': [],  # All authors
            'first_author': '',
            'doi': '',
            'year': '',
            'date': '',
            'journal': '',
            'journal_full': '',
            'volume': '',
            'issue': '',
            'pages': '',
            'issn': '',
            'language': '',
            'keywords': [],
            'url': '',
            'publication_type': '',
            'citation': ''
        }
        
        lines = record.split('\n')
        current_field = None
        current_value = []
        
        for line in lines:
            line = line.rstrip()
            if not line:
                continue
            
            # Check if line starts with a field tag
            match = re.match(r'^([A-Z0-9]+)\s*-\s*(.+)$', line)
            if match:
                # Save previous field
                if current_field:
                    value = '\n'.join(current_value).strip()
                    _set_nbib_field_full(ref, current_field, value)
                
                # Start new field
                current_field = match.group(1)
                current_value = [match.group(2)]
            else:
                # Continuation of previous field
                if current_field:
                    current_value.append(line)
        
        # Save last field
        if current_field:
            value = '\n'.join(current_value).strip()
            _set_nbib_field_full(ref, current_field, value)
        
        # Only add if we have at least a title
        if ref['title']:
            references.append(ref)
    
    return references


def _set_nbib_field_full(ref: Dict, field_tag: str, value: str):
    """Set NBIB field value with full extraction"""
    if field_tag == 'PMID':
        ref['pmid'] = value.strip()
    elif field_tag == 'TI':
        ref['title'] = value.strip()
    elif field_tag == 'AB':
        ref['abstract'] = value.strip()
    elif field_tag == 'FAU':
        # Full author name (Last, First)
        ref['authors'].append(value.strip())
        if not ref['first_author']:
            ref['first_author'] = normalize_author(value)
    elif field_tag == 'AU':
        # Abbreviated author name
        if not ref['authors']:
            # If no FAU, use AU
            ref['authors'].append(value.strip())
            if not ref['first_author']:
                ref['first_author'] = normalize_author(value)
    elif field_tag == 'LID' or field_tag == 'AID':
        # Extract DOI
        doi_match = re.search(r'10\.\d+/[^\s\[\]]+', value)
        if doi_match:
            ref['doi'] = doi_match.group().strip()
    elif field_tag == 'DP':
        # Date published - extract year
        ref['date'] = value.strip()
        year_match = re.search(r'\b(19|20)\d{2}\b', value)
        if year_match:
            ref['year'] = year_match.group()
    elif field_tag == 'TA':
        ref['journal'] = value.strip()
    elif field_tag == 'JT':
        ref['journal_full'] = value.strip()
    elif field_tag == 'VI':
        ref['volume'] = value.strip()
    elif field_tag == 'IP':
        ref['issue'] = value.strip()
    elif field_tag == 'PG':
        ref['pages'] = value.strip()
    elif field_tag == 'IS':
        # ISSN
        issn_match = re.search(r'\d{4}-\d{3}[\dX]', value)
        if issn_match:
            ref['issn'] = issn_match.group()
    elif field_tag == 'LA':
        ref['language'] = value.strip()
    elif field_tag == 'OT':
        # Keywords/MeSH terms
        ref['keywords'].append(value.strip())
    elif field_tag == 'SO':
        ref['citation'] = value.strip()
        # Try to extract URL from citation if available
        url_match = re.search(r'https?://[^\s]+', value)
        if url_match:
            ref['url'] = url_match.group()
    elif field_tag == 'PT':
        ref['publication_type'] = value.strip()


def nbib_to_ris(nbib_ref: Dict, search_term: str) -> str:
    """Convert a single NBIB reference to RIS format"""
    lines = []
    
    # Type (default to JOUR for journal articles)
    lines.append("TY  - JOUR")
    
    # Title
    if nbib_ref['title']:
        lines.append(f"TI  - {nbib_ref['title']}")
    
    # Abstract
    if nbib_ref['abstract']:
        # Handle multi-line abstracts
        abstract_lines = nbib_ref['abstract'].split('\n')
        lines.append(f"AB  - {abstract_lines[0]}")
        for line in abstract_lines[1:]:
            lines.append(f"     {line}")
    
    # Authors
    if nbib_ref['authors']:
        for author in nbib_ref['authors']:
            lines.append(f"AU  - {author}")
    
    # DOI
    if nbib_ref['doi']:
        lines.append(f"DO  - {nbib_ref['doi']}")
    
    # Year
    if nbib_ref['year']:
        lines.append(f"PY  - {nbib_ref['year']}")
    
    # Date
    if nbib_ref['date']:
        lines.append(f"DA  - {nbib_ref['date']}")
    
    # Journal
    if nbib_ref['journal']:
        lines.append(f"T2  - {nbib_ref['journal']}")
    elif nbib_ref['journal_full']:
        lines.append(f"T2  - {nbib_ref['journal_full']}")
    
    # Volume
    if nbib_ref['volume']:
        lines.append(f"VL  - {nbib_ref['volume']}")
    
    # Issue
    if nbib_ref['issue']:
        lines.append(f"IS  - {nbib_ref['issue']}")
    
    # Pages
    if nbib_ref['pages']:
        lines.append(f"SP  - {nbib_ref['pages']}")
    
    # ISSN
    if nbib_ref['issn']:
        lines.append(f"SN  - {nbib_ref['issn']}")
    
    # Language
    if nbib_ref['language']:
        lines.append(f"LA  - {nbib_ref['language']}")
    
    # Keywords
    if nbib_ref['keywords']:
        for kw in nbib_ref['keywords']:
            lines.append(f"KW  - {kw}")
    
    # URL
    if nbib_ref['url']:
        lines.append(f"UR  - {nbib_ref['url']}")
    elif nbib_ref['doi']:
        # Construct URL from DOI
        lines.append(f"UR  - https://doi.org/{nbib_ref['doi']}")
    
    # Research Notes (search term)
    lines.append(f"RN  - {search_term}")
    
    # ID and Label (PMID)
    if nbib_ref['pmid']:
        lines.append(f"ID  - {nbib_ref['pmid']}")
        lines.append(f"LB  - {nbib_ref['pmid']}")
    
    # End of record
    lines.append("ER  -")
    lines.append("")
    
    return "\n".join(lines)


def parse_ris_file_full(ris_path: str) -> List[Tuple[Dict, List[str]]]:
    """
    Parse RIS file and return list of (reference_dict, original_record_lines)
    This preserves the original formatting for updating
    """
    references = []
    
    with open(ris_path, 'r', encoding='utf-8', errors='ignore') as f:
        all_lines = f.readlines()
    
    current_record_lines = []
    ref = {
        'doi': '',
        'title': '',
        'first_author': '',
        'rn': ''  # Store original RN value
    }
    
    current_field = None
    current_value = []
    
    for line in all_lines:
        current_record_lines.append(line)
        line_stripped = line.rstrip()
        
        if not line_stripped:
            continue
        
        # Check if line starts with a field tag
        match = re.match(r'^([A-Z0-9]{2,3})\s+-\s+(.+)$', line_stripped)
        if match:
            # Save previous field
            if current_field:
                value = '\n'.join(current_value).strip()
                _set_ris_field_full(ref, current_field, value)
            
            # Start new field
            current_field = match.group(1)
            current_value = [match.group(2)]
        elif line_stripped.startswith('ER'):
            # End of record
            # Save last field
            if current_field:
                value = '\n'.join(current_value).strip()
                _set_ris_field_full(ref, current_field, value)
            
            # Only add if we have at least a title
            if ref['title']:
                references.append((ref.copy(), current_record_lines.copy()))
            
            # Reset for next record
            current_record_lines = []
            ref = {
                'doi': '',
                'title': '',
                'first_author': '',
                'rn': ''
            }
            current_field = None
            current_value = []
        else:
            # Continuation of previous field
            if current_field:
                current_value.append(line_stripped)
    
    return references


def _set_ris_field_full(ref: Dict, field_tag: str, value: str):
    """Set RIS field value"""
    if field_tag == 'DO':
        ref['doi'] = normalize_doi(value)
    elif field_tag == 'TI':
        ref['title'] = normalize_title(value)
    elif field_tag == 'AU':
        # First author (first AU field)
        if not ref['first_author']:
            ref['first_author'] = normalize_author(value)
    elif field_tag == 'RN':
        ref['rn'] = value.strip()


def find_matches(nbib_refs: List[Dict], ris_refs: List[Tuple[Dict, List[str]]]) -> Tuple[Set[int], Set[int], Dict[int, int]]:
    """
    Find matches between NBIB and RIS references.
    Returns: (matched_nbib_indices, unmatched_nbib_indices, nbib_to_ris_index_map)
    """
    # Build lookup from RIS references
    ris_by_doi: Dict[str, int] = {}  # DOI -> RIS index
    ris_by_title_author: Dict[Tuple[str, str], int] = {}  # (title, author) -> RIS index
    
    for ris_idx, (ris_ref, _) in enumerate(ris_refs):
        if ris_ref['doi']:
            ris_by_doi[ris_ref['doi']] = ris_idx
        if ris_ref['title'] and ris_ref['first_author']:
            key = (ris_ref['title'], ris_ref['first_author'])
            ris_by_title_author[key] = ris_idx
    
    matched_nbib_indices = set()
    unmatched_nbib_indices = set()
    nbib_to_ris_map = {}  # nbib_index -> ris_index
    
    for nbib_idx, nbib_ref in enumerate(nbib_refs):
        matched = False
        ris_idx = None
        
        # Try DOI match first
        if nbib_ref['doi']:
            normalized_doi = normalize_doi(nbib_ref['doi'])
            if normalized_doi in ris_by_doi:
                matched = True
                ris_idx = ris_by_doi[normalized_doi]
                matched_nbib_indices.add(nbib_idx)
                nbib_to_ris_map[nbib_idx] = ris_idx
        # Try title + first author match
        if not matched and nbib_ref['title'] and nbib_ref['first_author']:
            key = (normalize_title(nbib_ref['title']), normalize_author(nbib_ref['first_author']))
            if key in ris_by_title_author:
                matched = True
                ris_idx = ris_by_title_author[key]
                matched_nbib_indices.add(nbib_idx)
                nbib_to_ris_map[nbib_idx] = ris_idx
        
        if not matched:
            unmatched_nbib_indices.add(nbib_idx)
    
    return matched_nbib_indices, unmatched_nbib_indices, nbib_to_ris_map


def update_ris_rn_field(record_lines: List[str], new_term: str) -> List[str]:
    """Update RN field in RIS record lines, appending new term if not already present"""
    updated_lines = []
    rn_found = False
    rn_index = -1
    
    # Find RN field
    for i, line in enumerate(record_lines):
        line_stripped = line.rstrip()
        if re.match(r'^RN\s+-\s+', line_stripped):
            rn_found = True
            rn_index = i
            # Get value after "RN  - " (accounting for variable spacing)
            match = re.match(r'^RN\s+-\s+(.+)$', line_stripped)
            if match:
                current_rn = match.group(1).strip()
                
                # Check if term already exists
                if new_term not in current_rn:
                    # Append new term
                    updated_rn = f"{current_rn}, {new_term}"
                    # Preserve original line ending (newline or not)
                    if line.endswith('\n'):
                        updated_lines.append(f"RN  - {updated_rn}\n")
                    else:
                        updated_lines.append(f"RN  - {updated_rn}")
                else:
                    # Keep as is
                    updated_lines.append(line)
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)
    
    # If no RN field found, add it before ER
    if not rn_found:
        # Find ER line
        er_index = -1
        for i, line in enumerate(updated_lines):
            if line.rstrip().startswith('ER'):
                er_index = i
                break
        
        if er_index > 0:
            # Insert RN before ER, preserving line ending style
            if updated_lines[er_index].endswith('\n'):
                updated_lines.insert(er_index, f"RN  - {new_term}\n")
            else:
                updated_lines.insert(er_index, f"RN  - {new_term}")
        else:
            # Append before ER if not found
            updated_lines.append(f"RN  - {new_term}\n")
    
    return updated_lines


def main():
    nbib_path = str(REPO_ROOT / 'nbib_files/pubmed_neurocritical_"critical_care"_emergency_triage.nbib')
    ris_path = str(REPO_ROOT / 'visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_12_16_25_1226pm.txt')
    # Endnote folder is now in OneDrive
    output_ris_path = '/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/search_term_results/unmatched_neurocritical_critical_care_emergency_triage.ris'
    search_term = 'neurocritical_OR_"critical_care"_OR_triage_OR_emergency'
    
    print("Parsing NBIB file with full field extraction...")
    nbib_refs = parse_nbib_file_full(nbib_path)
    print(f"Found {len(nbib_refs)} references in NBIB file")
    
    print("\nParsing RIS file...")
    ris_refs = parse_ris_file_full(ris_path)
    print(f"Found {len(ris_refs)} references in RIS file")
    
    print("\nFinding matches...")
    matched_nbib_indices, unmatched_nbib_indices, nbib_to_ris_map = find_matches(nbib_refs, ris_refs)
    
    print(f"\nMatched: {len(matched_nbib_indices)}")
    print(f"Unmatched: {len(unmatched_nbib_indices)}")
    
    # Create new RIS file with unmatched references
    print(f"\nCreating new RIS file with {len(unmatched_nbib_indices)} unmatched references...")
    with open(output_ris_path, 'w', encoding='utf-8') as f:
        for idx in sorted(unmatched_nbib_indices):
            nbib_ref = nbib_refs[idx]
            ris_text = nbib_to_ris(nbib_ref, search_term)
            f.write(ris_text)
    
    print(f"Saved to: {output_ris_path}")
    
    # Update existing RIS file
    print(f"\nUpdating existing RIS file to add search term to {len(matched_nbib_indices)} matched references...")
    
    # Track which RIS records need updating
    ris_needs_update = set(nbib_to_ris_map.values())
    
    # Reconstruct file with updates
    updated_lines = []
    for ris_idx, (ref_dict, record_lines) in enumerate(ris_refs):
        if ris_idx in ris_needs_update:
            # Update this record's RN field
            updated_record_lines = update_ris_rn_field(record_lines, search_term)
            updated_lines.extend(updated_record_lines)
        else:
            # Keep as is
            updated_lines.extend(record_lines)
    
    # Write updated RIS file
    with open(ris_path, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)
    
    print(f"Updated RIS file: {ris_path}")
    print("\nDone!")


if __name__ == '__main__':
    main()












