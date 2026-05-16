#!/usr/bin/env python3
"""
Filter large RIS file to remove references that don't match NBIB file.
Matching is based on core identifiers (DOI, title+author) and ignores
differences in additional metadata fields.

Inputs:
- NBIB file in nbib_files.
- Local RIS source file in visualizer_nlp_lit_review/RIS_source_files.

Outputs:
- In-place filtered local RIS source file.
- Backup file next to the local RIS source file with a .backup suffix.
"""

import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]

# Import functions from compare_nbib_ris
sys.path.insert(0, str(Path(__file__).parent))
from compare_nbib_ris import (
    parse_nbib_file, normalize_doi, normalize_title, normalize_author
)


def parse_ris_file_with_structure(ris_path: str) -> Tuple[List[Dict], List[str]]:
    """
    Parse RIS file and return both parsed references and raw record strings.
    Returns: (references, raw_records)
    """
    references = []
    raw_records = []
    
    with open(ris_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Split by record terminator (ER  - followed by blank line or end)
    records = re.split(r'^ER\s+-\s*$\n?', content, flags=re.MULTILINE)
    
    for record in records:
        if not record.strip():
            continue
        
        # Store raw record (without ER line)
        raw_records.append(record.strip())
        
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
                    if current_field == 'DO':
                        ref['doi'] = normalize_doi(value)
                    elif current_field == 'TI':
                        ref['title'] = normalize_title(value)
                    elif current_field == 'AU':
                        if not ref['first_author']:
                            ref['first_author'] = normalize_author(value)
                
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
            if current_field == 'DO':
                ref['doi'] = normalize_doi(value)
            elif current_field == 'TI':
                ref['title'] = normalize_title(value)
            elif current_field == 'AU':
                if not ref['first_author']:
                    ref['first_author'] = normalize_author(value)
        
        references.append(ref)
    
    return references, raw_records


def find_ris_matches(nbib_refs: List[Dict], ris_refs: List[Dict]) -> Set[int]:
    """
    Find which RIS references match NBIB references.
    Returns set of RIS indices that match.
    """
    # Build lookup sets from NBIB references
    nbib_by_doi: Dict[str, bool] = {}
    nbib_by_title_author: Dict[Tuple[str, str], bool] = {}
    
    for nbib_ref in nbib_refs:
        if nbib_ref.get('doi'):
            nbib_by_doi[nbib_ref['doi']] = True
        if nbib_ref.get('title') and nbib_ref.get('first_author'):
            key = (nbib_ref['title'], nbib_ref['first_author'])
            nbib_by_title_author[key] = True
    
    matched_ris_indices = set()
    
    for idx, ris_ref in enumerate(ris_refs):
        matched = False
        
        # Try DOI match first
        if ris_ref.get('doi') and ris_ref['doi'] in nbib_by_doi:
            matched = True
        # Try title + first author match
        elif ris_ref.get('title') and ris_ref.get('first_author'):
            key = (ris_ref['title'], ris_ref['first_author'])
            if key in nbib_by_title_author:
                matched = True
        
        if matched:
            matched_ris_indices.add(idx)
    
    return matched_ris_indices


def main():
    nbib_path = str(REPO_ROOT / 'nbib_files/pubmed_neurocritical_"critical_care"_emergency_triage.nbib')
    ris_path = str(REPO_ROOT / 'visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_12_17_25_1114am.txt')
    backup_path = ris_path + '.backup'
    
    print("Parsing NBIB file...")
    nbib_refs = parse_nbib_file(nbib_path)
    print(f"Found {len(nbib_refs)} references in NBIB file")
    
    print("\nParsing RIS file...")
    ris_refs, raw_ris_records = parse_ris_file_with_structure(ris_path)
    print(f"Found {len(ris_refs)} references in RIS file")
    
    print("\nFinding matches...")
    matched_ris_indices = find_ris_matches(nbib_refs, ris_refs)
    print(f"Found {len(matched_ris_indices)} matching RIS references")
    
    removed_count = len(ris_refs) - len(matched_ris_indices)
    print(f"Will remove {removed_count} unmatched RIS references")
    
    # Create backup
    print(f"\nCreating backup: {backup_path}")
    shutil.copy2(ris_path, backup_path)
    print("Backup created successfully")
    
    # Filter RIS records to keep only matched ones
    print("\nFiltering RIS file...")
    filtered_records = []
    for i, record in enumerate(raw_ris_records):
        if i in matched_ris_indices:
            filtered_records.append(record)
    
    # Write filtered RIS file
    print(f"Writing filtered RIS file...")
    with open(ris_path, 'w', encoding='utf-8') as f:
        for i, record in enumerate(filtered_records):
            f.write(record)
            if not record.endswith('\n'):
                f.write('\n')
            f.write('ER  -\n')
            # Add blank line between records (except for last one)
            if i < len(filtered_records) - 1:
                f.write('\n')
    
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"{'='*60}")
    print(f"Total RIS references: {len(ris_refs)}")
    print(f"Total NBIB references: {len(nbib_refs)}")
    print(f"Matched RIS references (kept): {len(matched_ris_indices)}")
    print(f"Removed RIS references: {removed_count}")
    print(f"{'='*60}")
    print(f"\nFiltered RIS file saved to: {ris_path}")
    print(f"Backup saved to: {backup_path}")


if __name__ == '__main__':
    main()











