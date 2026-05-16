#!/usr/bin/env python3
"""
Remove common references between missing_after_second_scrape.txt and missing_elsevier_papers.txt
from missing_after_second_scrape.txt
"""

import re
from pathlib import Path
from typing import List, Set, Tuple


def parse_ris_file(ris_file_path: Path) -> List[Tuple[str, str]]:
    """
    Parse RIS file and return list of (id, ris_text) tuples.
    """
    references = []

    if not ris_file_path.exists():
        print(f"ERROR: RIS file not found: {ris_file_path}")
        return references

    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        record_id = None
        lines = entry.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ID  - '):
                record_id = line[6:].strip()
                break

        ris_text = entry + '\nER  - \n'

        if record_id:
            references.append((record_id, ris_text))
        else:
            # If no ID, use the full entry as identifier (less ideal but handles edge cases)
            references.append((None, ris_text))

    return references


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent.parent
    
    missing_after_second_scrape_path = base_dir / "missing_papers" / "still_missing" / "missing_after_second_scrape.txt"
    missing_elsevier_path = base_dir / "missing_papers" / "still_missing" / "missing_elsevier_papers.txt"
    
    print("="*70)
    print("REMOVING ELSEVIER REFERENCES FROM MISSING_AFTER_SECOND_SCRAPE.TXT")
    print("="*70)
    print()
    
    # Parse both files
    print("Parsing missing_after_second_scrape.txt...")
    missing_after_second_scrape_refs = parse_ris_file(missing_after_second_scrape_path)
    print(f"  Found {len(missing_after_second_scrape_refs)} references")
    print()
    
    print("Parsing missing_elsevier_papers.txt...")
    missing_elsevier_refs = parse_ris_file(missing_elsevier_path)
    print(f"  Found {len(missing_elsevier_refs)} references")
    print()
    
    # Create set of IDs from Elsevier file for fast lookup
    elsevier_ids = set()
    for record_id, _ in missing_elsevier_refs:
        if record_id:
            elsevier_ids.add(record_id)
    
    print(f"  Found {len(elsevier_ids)} unique IDs in Elsevier file")
    print()
    
    # Find common references
    print("Finding common references...")
    common_count = 0
    remaining_refs = []
    
    for record_id, ris_text in missing_after_second_scrape_refs:
        if record_id and record_id in elsevier_ids:
            common_count += 1
        else:
            remaining_refs.append(ris_text)
    
    print(f"  Found {common_count} common references")
    print(f"  Remaining references: {len(remaining_refs)}")
    print()
    
    # Write updated file
    print("Writing updated missing_after_second_scrape.txt...")
    with open(missing_after_second_scrape_path, 'w', encoding='utf-8') as f:
        for ris_text in remaining_refs:
            f.write(ris_text)
    
    print(f"  Updated file: {missing_after_second_scrape_path}")
    print()
    
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Original references in missing_after_second_scrape.txt: {len(missing_after_second_scrape_refs)}")
    print(f"  References in missing_elsevier_papers.txt: {len(missing_elsevier_refs)}")
    print(f"  Common references removed: {common_count}")
    print(f"  Remaining references in missing_after_second_scrape.txt: {len(remaining_refs)}")
    print("="*70)


if __name__ == "__main__":
    main()

