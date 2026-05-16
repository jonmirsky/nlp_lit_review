#!/usr/bin/env python3
"""
Extract Elsevier papers from missing_after_second_scrape.txt and save to missing_elsevier_papers.txt
"""

import re
from pathlib import Path
from typing import Optional


def identify_elsevier(entry: str) -> bool:
    """Check if an entry is from Elsevier."""
    url = None
    doi = None
    publisher = None
    
    lines = entry.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('UR  - '):
            url = line[6:].strip().lower()
        elif line.startswith('DO  - '):
            doi = line[6:].strip().lower()
        elif line.startswith('PB  - '):
            publisher = line[6:].strip().lower()
    
    # Check URL
    if url and ('elsevier' in url or 'sciencedirect' in url):
        return True
    
    # Check DOI (Elsevier DOIs typically start with 10.1016)
    if doi and '10.1016' in doi:
        return True
    
    # Check publisher field
    if publisher and 'elsevier' in publisher:
        return True
    
    return False


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent
    input_file = base_dir / "missing_papers" / "still_missing" / "missing_after_second_scrape.txt"
    output_file = base_dir / "missing_papers" / "still_missing" / "missing_elsevier_papers.txt"
    
    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        return
    
    print("Extracting Elsevier papers from RIS file...")
    
    # Read and parse RIS file
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    elsevier_entries = []
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        if identify_elsevier(entry):
            # Add the ER  -  terminator back
            elsevier_entries.append(entry + '\nER  - \n')
    
    # Write to output file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for entry in elsevier_entries:
            f.write(entry)
    
    print(f"Found {len(elsevier_entries)} Elsevier papers")
    print(f"Written to: {output_file}")


if __name__ == "__main__":
    main()
