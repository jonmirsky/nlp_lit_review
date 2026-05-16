#!/usr/bin/env python3
"""
Remove duplicate references from a RIS file.

Inputs:
- Local manual grouping RIS file in visualizer_nlp_lit_review/RIS_source_files/manual_groupings.

Outputs:
- Cleaned local manual grouping RIS file at the original path.
- Original file renamed next to it with a _with_duplicates suffix.
"""

import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


REPO_ROOT = Path(__file__).resolve().parents[1]

# Import functions from compare_nbib_ris
sys.path.insert(0, str(Path(__file__).parent))
from compare_nbib_ris import (
    normalize_doi, normalize_title, normalize_author
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


def find_duplicates(references: List[Dict]) -> Set[int]:
    """
    Find duplicate references based on DOI, title, and author.
    Returns set of indices to remove (keeping first occurrence).
    """
    seen_keys = {}
    indices_to_remove = set()
    
    for idx, ref in enumerate(references):
        # Create key: prefer DOI, fallback to title+author
        if ref['doi']:
            key = ('doi', ref['doi'])
        elif ref['title'] and ref['first_author']:
            key = ('title_author', ref['title'], ref['first_author'])
        elif ref['title']:
            key = ('title_only', ref['title'])
        else:
            # No good identifier, skip duplicate detection for this one
            continue
        
        if key in seen_keys:
            # This is a duplicate, mark for removal
            indices_to_remove.add(idx)
        else:
            # First occurrence, keep it
            seen_keys[key] = idx
    
    return indices_to_remove


def main():
    ris_path = str(REPO_ROOT / 'visualizer_nlp_lit_review/RIS_source_files/manual_groupings/most_cited_or_of_interest.txt')
    ris_path_with_duplicates = ris_path.replace('.txt', '_with_duplicates.txt')
    
    print("Parsing RIS file...")
    references, raw_records = parse_ris_file_with_structure(ris_path)
    print(f"Found {len(references)} references in file")
    
    print("\nFinding duplicates...")
    indices_to_remove = find_duplicates(references)
    print(f"Found {len(indices_to_remove)} duplicate references to remove")
    
    if indices_to_remove:
        print("\nDuplicates found:")
        for idx in sorted(indices_to_remove):
            ref = references[idx]
            title = ref['title'][:60] + "..." if len(ref['title']) > 60 else ref['title']
            print(f"  [{idx}] {title}")
            if ref['doi']:
                print(f"      DOI: {ref['doi']}")
    
    # Rename original file
    print(f"\nRenaming original file to: {ris_path_with_duplicates}")
    shutil.move(ris_path, ris_path_with_duplicates)
    print("File renamed successfully")
    
    # Create cleaned file without duplicates
    print("\nCreating cleaned file without duplicates...")
    filtered_records = []
    for i, record in enumerate(raw_records):
        if i not in indices_to_remove:
            filtered_records.append(record)
    
    # Write cleaned RIS file
    print(f"Writing cleaned RIS file...")
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
    print(f"Original references: {len(references)}")
    print(f"Duplicates removed: {len(indices_to_remove)}")
    print(f"Remaining references: {len(filtered_records)}")
    print(f"{'='*60}")
    print(f"\nCleaned file saved to: {ris_path}")
    print(f"Original file (with duplicates) saved to: {ris_path_with_duplicates}")


if __name__ == '__main__':
    main()











