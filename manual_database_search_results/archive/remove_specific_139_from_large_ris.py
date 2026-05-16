#!/usr/bin/env python3
"""
Find the 139 references that were removed from the intermediate RIS file,
then remove ONLY those 139 references from the large RIS file.

Inputs:
- Intermediate RIS backup and filtered files in the external OneDrive Endnote/intermediate_ris_files directory.
- Local large RIS source file in visualizer_nlp_lit_review/RIS_source_files.

Outputs:
- In-place updated local large RIS source file.
- Backup file next to the local large RIS file with a .backup suffix.
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


def create_reference_key(ref: Dict) -> Tuple[str, str, str]:
    """
    Create a unique key for a reference based on DOI, title, and first author.
    Returns: (doi, title, first_author)
    """
    return (
        ref.get('doi', ''),
        ref.get('title', ''),
        ref.get('first_author', '')
    )


def find_removed_references(backup_refs: List[Dict], filtered_refs: List[Dict]) -> Set[Tuple[str, str, str]]:
    """
    Find references that are in backup but not in filtered.
    Returns set of reference keys (doi, title, first_author).
    """
    # Create sets of reference keys
    backup_keys = set()
    for ref in backup_refs:
        key = create_reference_key(ref)
        backup_keys.add(key)
    
    filtered_keys = set()
    for ref in filtered_refs:
        key = create_reference_key(ref)
        filtered_keys.add(key)
    
    # Find keys in backup but not in filtered
    removed_keys = backup_keys - filtered_keys
    return removed_keys


def find_references_to_remove(large_ris_refs: List[Dict], removed_keys: Set[Tuple[str, str, str]]) -> Set[int]:
    """
    Find indices in large RIS file that match the removed keys.
    Returns set of indices to remove.
    """
    indices_to_remove = set()
    
    for idx, ref in enumerate(large_ris_refs):
        key = create_reference_key(ref)
        if key in removed_keys:
            indices_to_remove.add(idx)
    
    return indices_to_remove


def main():
    # Intermediate file paths - now in OneDrive
    intermediate_backup = '/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/intermediate_ris_files/pubmed_NLP_v4_12_17_25_1114am_neurocritical_filtered.ris.backup'
    intermediate_filtered = '/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/intermediate_ris_files/pubmed_NLP_v4_12_17_25_1114am_neurocritical_filtered.ris'
    
    # Large RIS file paths
    large_ris_path = str(REPO_ROOT / 'visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_12_17_25_1114am.txt')
    large_ris_backup = large_ris_path + '.backup'
    
    print("Step 1: Parsing intermediate RIS file backup (original 373 references)...")
    intermediate_backup_refs, _ = parse_ris_file_with_structure(intermediate_backup)
    print(f"Found {len(intermediate_backup_refs)} references in intermediate backup")
    
    print("\nStep 2: Parsing filtered intermediate RIS file (234 references)...")
    intermediate_filtered_refs, _ = parse_ris_file_with_structure(intermediate_filtered)
    print(f"Found {len(intermediate_filtered_refs)} references in filtered intermediate file")
    
    print("\nStep 3: Finding the 139 references that were removed...")
    removed_keys = find_removed_references(intermediate_backup_refs, intermediate_filtered_refs)
    print(f"Found {len(removed_keys)} unique references that were removed from intermediate file")
    
    print("\nStep 4: Parsing large RIS file...")
    large_ris_refs, large_ris_records = parse_ris_file_with_structure(large_ris_path)
    print(f"Found {len(large_ris_refs)} references in large RIS file")
    
    print("\nStep 5: Finding those 139 references in the large RIS file...")
    indices_to_remove = find_references_to_remove(large_ris_refs, removed_keys)
    print(f"Found {len(indices_to_remove)} references to remove from large RIS file")
    
    if len(indices_to_remove) != len(removed_keys):
        print(f"WARNING: Expected to find {len(removed_keys)} references, but found {len(indices_to_remove)}")
        print("Some references from intermediate file may not be in large RIS file")
    
    # Create backup
    print(f"\nStep 6: Creating backup of large RIS file...")
    shutil.copy2(large_ris_path, large_ris_backup)
    print("Backup created successfully")
    
    # Filter large RIS records - remove only the 139
    print("\nStep 7: Removing the 139 references from large RIS file...")
    filtered_records = []
    for i, record in enumerate(large_ris_records):
        if i not in indices_to_remove:
            filtered_records.append(record)
    
    # Write filtered RIS file
    print(f"Writing filtered RIS file...")
    with open(large_ris_path, 'w', encoding='utf-8') as f:
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
    print(f"Original large RIS references: {len(large_ris_refs)}")
    print(f"References removed: {len(indices_to_remove)}")
    print(f"Remaining references: {len(filtered_records)}")
    print(f"Expected remaining: {len(large_ris_refs) - len(removed_keys)}")
    print(f"{'='*60}")
    print(f"\nFiltered RIS file saved to: {large_ris_path}")
    print(f"Backup saved to: {large_ris_backup}")


if __name__ == '__main__':
    main()












