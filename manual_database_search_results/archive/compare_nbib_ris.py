#!/usr/bin/env python3
"""
Compare references in NBIB file with references in RIS file.
Match by DOI first, then by title + first author if no DOI.

Inputs:
- NBIB file in nbib_files.
- RIS source file in visualizer_nlp_lit_review/RIS_source_files.

Outputs:
- Console comparison report only; no files are written.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]


def normalize_doi(doi: str) -> str:
    """Normalize DOI for comparison"""
    if not doi:
        return ""
    # Remove common prefixes and whitespace
    doi = doi.strip()
    # Remove [doi] suffix if present
    doi = re.sub(r'\s*\[doi\]\s*$', '', doi, flags=re.IGNORECASE)
    # Remove any leading "doi:" or "DOI:"
    doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE)
    # Remove any whitespace
    doi = doi.strip()
    return doi.lower()


def normalize_title(title: str) -> str:
    """Normalize title for comparison"""
    if not title:
        return ""
    # Remove extra whitespace, convert to lowercase
    title = ' '.join(title.split())
    return title.lower().strip()


def normalize_author(author: str) -> str:
    """Normalize author name for comparison"""
    if not author:
        return ""
    # Remove extra whitespace
    author = ' '.join(author.split())
    # Extract last name (first part before comma, or first word if no comma)
    if ',' in author:
        last_name = author.split(',')[0].strip()
    else:
        # If no comma, take first word as last name
        parts = author.split()
        last_name = parts[0] if parts else ""
    return last_name.lower().strip()


def parse_nbib_file(nbib_path: str) -> List[Dict]:
    """Parse NBIB file and extract references"""
    references = []
    
    with open(nbib_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Split by PMID- (new record marker)
    records = re.split(r'^PMID-\s+', content, flags=re.MULTILINE)
    
    for record in records:
        if not record.strip():
            continue
        
        ref = {
            'doi': '',
            'title': '',
            'first_author': '',
            'pmid': ''
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
                    _set_nbib_field(ref, current_field, value)
                
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
            _set_nbib_field(ref, current_field, value)
        
        # Only add if we have at least a title
        if ref['title']:
            references.append(ref)
    
    return references


def _set_nbib_field(ref: Dict, field_tag: str, value: str):
    """Set NBIB field value"""
    if field_tag == 'LID' or field_tag == 'AID':
        # Extract DOI from LID or AID field (format: "10.xxxxx [doi]")
        doi_match = re.search(r'10\.\d+/[^\s\[\]]+', value)
        if doi_match:
            ref['doi'] = normalize_doi(doi_match.group())
    elif field_tag == 'TI':
        ref['title'] = normalize_title(value)
    elif field_tag == 'FAU':
        # First author (FAU field)
        if not ref['first_author']:
            ref['first_author'] = normalize_author(value)
    elif field_tag == 'PMID':
        ref['pmid'] = value.strip()


def parse_ris_file(ris_path: str) -> List[Dict]:
    """Parse RIS file and extract references"""
    references = []
    
    with open(ris_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Split by record terminator (ER  -)
    records = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for record in records:
        if not record.strip():
            continue
        
        ref = {
            'doi': '',
            'title': '',
            'first_author': ''
        }
        
        lines = record.strip().split('\n')
        current_field = None
        current_value = []
        
        for line in lines:
            line = line.rstrip()
            if not line:
                continue
            
            # Check if line starts with a field tag (2-3 letters, space, dash)
            match = re.match(r'^([A-Z0-9]{2,3})\s+-\s+(.+)$', line)
            if match:
                # Save previous field
                if current_field:
                    value = '\n'.join(current_value).strip()
                    _set_ris_field(ref, current_field, value)
                
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
            _set_ris_field(ref, current_field, value)
        
        # Only add if we have at least a title
        if ref['title']:
            references.append(ref)
    
    return references


def _set_ris_field(ref: Dict, field_tag: str, value: str):
    """Set RIS field value"""
    if field_tag == 'DO':
        ref['doi'] = normalize_doi(value)
    elif field_tag == 'TI':
        ref['title'] = normalize_title(value)
    elif field_tag == 'AU':
        # First author (first AU field)
        if not ref['first_author']:
            ref['first_author'] = normalize_author(value)


def find_matches(nbib_refs: List[Dict], ris_refs: List[Dict]) -> Tuple[Set[int], Set[int]]:
    """
    Find matches between NBIB and RIS references.
    Returns: (matched_indices, unmatched_indices)
    """
    # Build lookup sets from RIS references
    ris_by_doi: Dict[str, bool] = {}
    ris_by_title_author: Dict[Tuple[str, str], bool] = {}
    
    for ris_ref in ris_refs:
        if ris_ref['doi']:
            ris_by_doi[ris_ref['doi']] = True
        if ris_ref['title'] and ris_ref['first_author']:
            ris_by_title_author[(ris_ref['title'], ris_ref['first_author'])] = True
    
    matched_indices = set()
    unmatched_indices = set()
    
    for idx, nbib_ref in enumerate(nbib_refs):
        matched = False
        
        # Try DOI match first
        if nbib_ref['doi'] and nbib_ref['doi'] in ris_by_doi:
            matched = True
            matched_indices.add(idx)
        # Try title + first author match
        elif nbib_ref['title'] and nbib_ref['first_author']:
            key = (nbib_ref['title'], nbib_ref['first_author'])
            if key in ris_by_title_author:
                matched = True
                matched_indices.add(idx)
        
        if not matched:
            unmatched_indices.add(idx)
    
    return matched_indices, unmatched_indices


def main():
    nbib_path = str(REPO_ROOT / 'nbib_files/pubmed_neurocritical_"critical_care"_emergency_triage.nbib')
    ris_path = str(REPO_ROOT / 'visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_12_17_25_1114am.txt')
    
    print("Parsing NBIB file...")
    nbib_refs = parse_nbib_file(nbib_path)
    print(f"Found {len(nbib_refs)} references in NBIB file")
    
    print("\nParsing RIS file...")
    ris_refs = parse_ris_file(ris_path)
    print(f"Found {len(ris_refs)} references in RIS file")
    
    print("\nComparing references...")
    matched_indices, unmatched_indices = find_matches(nbib_refs, ris_refs)
    
    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"{'='*60}")
    print(f"Total references in NBIB file: {len(nbib_refs)}")
    print(f"Total references in RIS file: {len(ris_refs)}")
    print(f"Matched references: {len(matched_indices)}")
    print(f"Unmatched references (in NBIB but not in RIS): {len(unmatched_indices)}")
    print(f"{'='*60}")
    
    # Show some statistics
    nbib_with_doi = sum(1 for r in nbib_refs if r['doi'])
    nbib_with_title_author = sum(1 for r in nbib_refs if r['title'] and r['first_author'])
    ris_with_doi = sum(1 for r in ris_refs if r['doi'])
    ris_with_title_author = sum(1 for r in ris_refs if r['title'] and r['first_author'])
    
    print(f"\nStatistics:")
    print(f"NBIB references with DOI: {nbib_with_doi}")
    print(f"NBIB references with title+author: {nbib_with_title_author}")
    print(f"RIS references with DOI: {ris_with_doi}")
    print(f"RIS references with title+author: {ris_with_title_author}")
    
    # Show some examples of unmatched references
    if unmatched_indices:
        print(f"\nFirst 10 unmatched references (examples):")
        for i, idx in enumerate(sorted(unmatched_indices)[:10]):
            ref = nbib_refs[idx]
            print(f"\n{i+1}. PMID: {ref.get('pmid', 'N/A')}")
            print(f"   Title: {ref['title'][:80]}..." if len(ref['title']) > 80 else f"   Title: {ref['title']}")
            print(f"   First Author: {ref['first_author']}")
            print(f"   DOI: {ref['doi'] if ref['doi'] else 'N/A'}")


if __name__ == '__main__':
    main()











