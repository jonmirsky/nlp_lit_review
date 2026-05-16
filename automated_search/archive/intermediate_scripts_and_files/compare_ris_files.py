#!/usr/bin/env python3
"""
Compare two RIS files to find common references.
"""

import re
from pathlib import Path
from typing import Set


def extract_record_ids(ris_file_path: Path) -> Set[str]:
    """
    Extract all record IDs from a RIS file.
    Returns a set of record IDs.
    """
    record_ids = set()
    
    if not ris_file_path.exists():
        print(f"ERROR: RIS file not found: {ris_file_path}")
        return record_ids
    
    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        lines = entry.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ID  - '):
                record_id = line[6:].strip()
                if record_id:
                    record_ids.add(record_id)
                break
    
    return record_ids


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent.parent
    
    file1_path = base_dir / "missing_papers" / "still_missing" / "no_DOI_missing_post_selenium" / "missing_papers.txt"
    file2_path = base_dir / "missing_papers" / "still_missing" / "missing_after_second_scrape.txt"
    
    print("="*70)
    print("COMPARING RIS FILES")
    print("="*70)
    print()
    
    print(f"File 1: {file1_path.name}")
    print(f"  Path: {file1_path}")
    ids1 = extract_record_ids(file1_path)
    print(f"  Found {len(ids1)} references")
    print()
    
    print(f"File 2: {file2_path.name}")
    print(f"  Path: {file2_path}")
    ids2 = extract_record_ids(file2_path)
    print(f"  Found {len(ids2)} references")
    print()
    
    # Find common IDs
    common_ids = ids1.intersection(ids2)
    only_in_file1 = ids1 - ids2
    only_in_file2 = ids2 - ids1
    
    print("="*70)
    print("COMPARISON RESULTS")
    print("="*70)
    print(f"  Common references: {len(common_ids)}")
    print(f"  Only in {file1_path.name}: {len(only_in_file1)}")
    print(f"  Only in {file2_path.name}: {len(only_in_file2)}")
    print()
    
    if len(common_ids) == len(ids1):
        print("  RESULT: ALL references from file 1 are also in file 2")
    elif len(common_ids) == 0:
        print("  RESULT: NONE of the references from file 1 are in file 2")
    else:
        print(f"  RESULT: SOME references from file 1 are in file 2 ({len(common_ids)} out of {len(ids1)})")
    
    if common_ids:
        print()
        print(f"  Common record IDs (first 20): {sorted(list(common_ids))[:20]}")
        if len(common_ids) > 20:
            print(f"  ... and {len(common_ids) - 20} more")
    
    print("="*70)


if __name__ == "__main__":
    main()

