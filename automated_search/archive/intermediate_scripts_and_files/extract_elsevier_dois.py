#!/usr/bin/env python3
"""
Extract DOIs from Elsevier papers in missing_after_second_scrape.txt
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
    base_dir = Path(__file__).parent
    ris_file = base_dir / "missing_papers" / "still_missing" / "missing_after_second_scrape.txt"
    output_file = base_dir / "elsevier_dois.txt"
    
    if not ris_file.exists():
        print(f"ERROR: RIS file not found: {ris_file}")
        return
    
    print("Extracting DOIs from Elsevier papers...")
    
    # Read and parse RIS file
    with open(ris_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    elsevier_dois = []
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        if identify_elsevier(entry):
            doi = extract_doi(entry)
            if doi:
                elsevier_dois.append(doi)
    
    # Write DOIs to file
    with open(output_file, 'w', encoding='utf-8') as f:
        for doi in elsevier_dois:
            f.write(doi + '\n')
    
    print(f"Found {len(elsevier_dois)} Elsevier papers with DOIs")
    print(f"DOIs written to: {output_file}")
    
    if len(elsevier_dois) < 196:
        print(f"Note: Expected 196 Elsevier papers, but found {len(elsevier_dois)} with DOIs")
        print("Some papers may not have DOIs in the RIS file.")


if __name__ == "__main__":
    main()
