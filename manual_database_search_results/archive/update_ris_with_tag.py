#!/usr/bin/env python3
"""
Update RIS file by adding tag to RN field for references that match NBIB file.
Then create a filtered RIS file with only tagged references.

Inputs:
- NBIB file in nbib_files.
- RIS source file in visualizer_nlp_lit_review/RIS_source_files.

Outputs:
- Tagged/filtered RIS files in the external OneDrive Endnote/intermediate_ris_files directory.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]

# Import functions from compare_nbib_ris
sys.path.insert(0, str(Path(__file__).parent))
from compare_nbib_ris import (
    parse_nbib_file, parse_ris_file, find_matches,
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
    # Use a more careful pattern to split records
    records = re.split(r'^ER\s+-\s*$\n?', content, flags=re.MULTILINE)
    
    for record in records:
        if not record.strip():
            continue
        
        # Store raw record (without ER line)
        raw_records.append(record.strip())
        
        ref = {
            'doi': '',
            'title': '',
            'first_author': '',
            'rn': ''
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
                    elif current_field == 'RN':
                        ref['rn'] = value
                
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
            elif current_field == 'RN':
                ref['rn'] = value
        
        references.append(ref)
    
    return references, raw_records


def update_ris_record_rn(record: str, tag: str) -> str:
    """
    Update RN field in RIS record. Add tag if not already present.
    Returns updated record string.
    """
    lines = record.split('\n')
    updated_lines = []
    rn_found = False
    rn_index = -1
    rn_value = None
    
    # Find RN field
    for i, line in enumerate(lines):
        if re.match(r'^RN\s+-\s+', line):
            rn_found = True
            rn_index = i
            match = re.match(r'^RN\s+-\s+(.+)$', line)
            if match:
                rn_value = match.group(1).strip()
            break
    
    # Check if tag already present (case-insensitive)
    tag_present = False
    if rn_found and rn_value:
        tag_present = tag.lower() in rn_value.lower()
    
    # If tag already present, return record unchanged
    if tag_present:
        return record
    
    # Build updated record
    for i, line in enumerate(lines):
        if i == rn_index:
            # Update existing RN field
            if rn_value:
                new_rn = f'{rn_value}, {tag}'
            else:
                new_rn = tag
            updated_lines.append(f'RN  - {new_rn}')
        else:
            updated_lines.append(line)
    
    # If no RN field found, add it before the end (before any ER line if present)
    if not rn_found:
        # Find insertion point (before ER or at end)
        insert_index = len(updated_lines)
        for i, line in enumerate(updated_lines):
            if line.strip() == 'ER  -':
                insert_index = i
                break
        
        # Insert RN field
        updated_lines.insert(insert_index, f'RN  - {tag}')
    
    return '\n'.join(updated_lines)


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
    tag = 'neurocritical_OR_"critical_care"_OR_triage_OR_emergency'
    # Endnote folder is now in OneDrive
    output_dir = Path('/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/intermediate_ris_files')
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Parsing NBIB file...")
    nbib_refs = parse_nbib_file(nbib_path)
    print(f"Found {len(nbib_refs)} references in NBIB file")
    
    print("\nParsing RIS file...")
    ris_refs, raw_ris_records = parse_ris_file_with_structure(ris_path)
    print(f"Found {len(ris_refs)} references in RIS file")
    
    print("\nFinding matches...")
    matched_ris_indices = find_ris_matches(nbib_refs, ris_refs)
    print(f"Found {len(matched_ris_indices)} matching references")
    
    # Update RIS records
    print("\nUpdating RIS file...")
    updated_records = []
    tagged_count = 0
    already_tagged_count = 0
    
    for i, record in enumerate(raw_ris_records):
        if i in matched_ris_indices:
            # Check if already has tag
            if tag.lower() in record.lower():
                already_tagged_count += 1
                updated_records.append(record)
            else:
                updated_record = update_ris_record_rn(record, tag)
                updated_records.append(updated_record)
                tagged_count += 1
        else:
            updated_records.append(record)
    
    # Write updated RIS file
    print(f"\nWriting updated RIS file...")
    with open(ris_path, 'w', encoding='utf-8') as f:
        for i, record in enumerate(updated_records):
            f.write(record)
            if not record.endswith('\n'):
                f.write('\n')
            f.write('ER  -\n')
            # Add blank line between records (except for last one)
            if i < len(updated_records) - 1:
                f.write('\n')
    
    print(f"Updated {tagged_count} references with the tag")
    print(f"Skipped {already_tagged_count} references that already had the tag")
    
    # Create filtered RIS file
    print("\nCreating filtered RIS file...")
    filtered_records = []
    for record in updated_records:
        # Check if record has the tag in RN field (case-insensitive)
        if tag.lower() in record.lower():
            # Double-check it's actually in an RN field
            lines = record.split('\n')
            for line in lines:
                if re.match(r'^RN\s+-\s+', line) and tag.lower() in line.lower():
                    filtered_records.append(record)
                    break
    
    filtered_ris_path = output_dir / 'pubmed_NLP_v4_12_17_25_1114am_neurocritical_filtered.ris'
    with open(filtered_ris_path, 'w', encoding='utf-8') as f:
        for i, record in enumerate(filtered_records):
            f.write(record)
            if not record.endswith('\n'):
                f.write('\n')
            f.write('ER  -\n')
            # Add blank line between records (except for last one)
            if i < len(filtered_records) - 1:
                f.write('\n')
    
    print(f"Created filtered RIS file with {len(filtered_records)} references")
    print(f"Filtered file saved to: {filtered_ris_path}")


if __name__ == '__main__':
    main()












