#!/usr/bin/env python3
"""
Extract DOIs from a RIS file and save to a text file, one DOI per line.
"""

import re
from pathlib import Path
from typing import List, Optional


def extract_doi(entry: str) -> Optional[str]:
    """Extract DOI from RIS entry."""
    lines = entry.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('DO  - '):
            doi = line[6:].strip()
            # Clean up DOI (remove "doi:" prefix if present, handle URLs)
            doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
            doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
            return doi.strip()
    return None


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent.parent
    
    input_file = base_dir / "missing_papers" / "still_missing" / "missing_after_second_scrape.txt"
    output_file = base_dir / "missing_papers" / "still_missing" / "DOI_missing_after_second_scrape.txt"
    
    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        return
    
    print("Extracting DOIs from RIS file...")
    
    # Read and parse RIS file
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    dois = []
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        doi = extract_doi(entry)
        if doi:
            dois.append(doi)
    
    # Write DOIs to output file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        for doi in dois:
            f.write(doi + '\n')
    
    print(f"Found {len(dois)} DOIs")
    print(f"DOIs written to: {output_file}")
    
    if len(dois) < len(entries):
        print(f"Note: {len(entries)} references found, but only {len(dois)} have DOIs")


if __name__ == "__main__":
    main()
