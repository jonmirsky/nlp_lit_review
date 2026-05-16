#!/usr/bin/env python3
"""
Create missing_after_first_scrape.txt RIS file.

This script:
1. Parses missing_papers2.txt to get all references
2. Gets all PDF filenames from first_scrape/ and second_scrape/ folders
3. Filters out references whose ID matches downloaded PDFs
4. Writes remaining references to missing_after_first_scrape.txt
"""

import re
from pathlib import Path
from typing import List, Set, Tuple


def parse_ris_file(ris_file_path: Path) -> List[Tuple[str, str]]:
    """
    Parse RIS file and return list of (id, ris_text) tuples.
    
    Args:
        ris_file_path: Path to RIS file
        
    Returns:
        List of tuples: (record_id, full_ris_text)
    """
    references = []
    
    if not ris_file_path.exists():
        print(f"ERROR: RIS file not found: {ris_file_path}")
        return references
    
    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by ER  - (end of record)
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        # Extract ID field
        record_id = None
        lines = entry.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ID  - '):
                record_id = line[6:].strip()
                break
        
        # Store full RIS text (add back ER  - at the end)
        ris_text = entry + '\nER  - \n'
        
        if record_id:
            references.append((record_id, ris_text))
        else:
            # If no ID found, still include it but with None as ID
            references.append((None, ris_text))
    
    return references


def get_downloaded_pdf_ids(first_scrape_dir: Path, second_scrape_dir: Path) -> Set[str]:
    """
    Get set of all PDF IDs (filenames without .pdf extension) from both folders.
    
    Args:
        first_scrape_dir: Path to first_scrape folder
        second_scrape_dir: Path to second_scrape folder
        
    Returns:
        Set of ID strings (PDF filenames without .pdf extension)
    """
    downloaded_ids = set()
    
    # Get IDs from first_scrape folder
    if first_scrape_dir.exists():
        for pdf_file in first_scrape_dir.glob('*.pdf'):
            if pdf_file.is_file():
                downloaded_ids.add(pdf_file.stem)  # filename without .pdf
    
    # Get IDs from second_scrape folder
    if second_scrape_dir.exists():
        for pdf_file in second_scrape_dir.glob('*.pdf'):
            if pdf_file.is_file():
                downloaded_ids.add(pdf_file.stem)  # filename without .pdf
    
    return downloaded_ids


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent
    
    # Define paths
    missing_papers2_path = base_dir / "missing_papers" / "still_missing" / "archive" / "missing_papers2.txt"
    first_scrape_dir = base_dir / "found_papers" / "downloaded_papers" / "first_scrape"
    second_scrape_dir = base_dir / "found_papers" / "downloaded_papers" / "second_scrape"
    output_path = base_dir / "missing_papers" / "still_missing" / "missing_after_first_scrape.txt"
    
    print("="*60)
    print("CREATING MISSING_AFTER_FIRST_SCRAPE.TXT")
    print("="*60)
    print()
    
    # Parse missing_papers2.txt
    print("Parsing missing_papers2.txt...")
    all_references = parse_ris_file(missing_papers2_path)
    print(f"  Found {len(all_references)} references in missing_papers2.txt")
    print()
    
    # Get downloaded PDF IDs
    print("Scanning downloaded PDFs...")
    downloaded_ids = get_downloaded_pdf_ids(first_scrape_dir, second_scrape_dir)
    print(f"  Found {len(downloaded_ids)} unique PDF files in first_scrape/ and second_scrape/")
    print()
    
    # Filter references
    print("Filtering references...")
    missing_references = []
    excluded_count = 0
    
    for record_id, ris_text in all_references:
        if record_id and record_id in downloaded_ids:
            # This reference has a downloaded PDF - exclude it
            excluded_count += 1
        else:
            # This reference doesn't have a downloaded PDF - keep it
            missing_references.append(ris_text)
    
    print(f"  Excluded {excluded_count} references (have downloaded PDFs)")
    print(f"  Kept {len(missing_references)} references (still missing)")
    print()
    
    # Write output file
    print("Writing output file...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for ris_text in missing_references:
            f.write(ris_text)
            f.write('\n')  # Extra blank line between references
    
    print(f"  Written to: {output_path}")
    print()
    
    # Print summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  Total references in missing_papers2.txt: {len(all_references)}")
    print(f"  References with downloaded PDFs (excluded): {excluded_count}")
    print(f"  References still missing (included in output): {len(missing_references)}")
    print(f"  Output file: {output_path}")
    print("="*60)


if __name__ == "__main__":
    main()
