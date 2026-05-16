#!/usr/bin/env python3
"""
Reorganize downloaded papers by scrape source.

This script:
1. Extracts IDs from missing_papers.txt (first scrape source)
2. Extracts IDs from missing_papers2.txt (second scrape source)
3. Moves PDF files to first_scrape/ or second_scrape/ folders based on ID matches
"""

import re
from pathlib import Path
from typing import Set


def extract_ids_from_ris(ris_file_path: Path) -> Set[str]:
    """
    Extract all ID values from a RIS file.
    
    Args:
        ris_file_path: Path to the RIS file
        
    Returns:
        Set of ID strings found in the RIS file
    """
    ids = set()
    
    if not ris_file_path.exists():
        print(f"Warning: RIS file not found: {ris_file_path}")
        return ids
    
    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all ID fields: "ID  - <value>"
    pattern = re.compile(r'^ID\s+-\s+(.+)$', re.MULTILINE)
    matches = pattern.findall(content)
    
    for match in matches:
        id_value = match.strip()
        if id_value:
            ids.add(id_value)
    
    return ids


def main():
    """Main execution function."""
    # Define paths
    base_dir = Path(__file__).parent
    archive_dir = base_dir / "missing_papers" / "still_missing" / "archive"
    downloaded_papers_dir = base_dir / "found_papers" / "downloaded_papers"
    
    # RIS files
    first_scrape_ris = archive_dir / "missing_papers.txt"
    second_scrape_ris = archive_dir / "missing_papers2.txt"
    
    # Output folders
    first_scrape_dir = downloaded_papers_dir / "first_scrape"
    second_scrape_dir = downloaded_papers_dir / "second_scrape"
    
    print("="*60)
    print("REORGANIZING DOWNLOADED PAPERS BY SCRAPE SOURCE")
    print("="*60)
    print()
    
    # Extract IDs from RIS files
    print("Extracting IDs from RIS files...")
    first_scrape_ids = extract_ids_from_ris(first_scrape_ris)
    print(f"  Found {len(first_scrape_ids)} IDs in {first_scrape_ris.name}")
    
    second_scrape_ids = extract_ids_from_ris(second_scrape_ris)
    print(f"  Found {len(second_scrape_ids)} IDs in {second_scrape_ris.name}")
    print()
    
    # Create output folders
    print("Creating output folders...")
    first_scrape_dir.mkdir(parents=True, exist_ok=True)
    second_scrape_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Created: {first_scrape_dir}")
    print(f"  Created: {second_scrape_dir}")
    print()
    
    # Get all PDF files
    print("Scanning for PDF files...")
    pdf_files = [f for f in downloaded_papers_dir.iterdir() 
                 if f.is_file() and f.suffix.lower() == '.pdf']
    print(f"  Found {len(pdf_files)} PDF files")
    print()
    
    # Track results
    moved_to_first = []
    moved_to_second = []
    unmatched = []
    
    # Process each PDF file
    print("Processing PDF files...")
    for pdf_file in pdf_files:
        # Extract ID from filename (remove .pdf extension)
        file_id = pdf_file.stem  # Gets filename without extension
        
        # Check if ID matches first scrape
        if file_id in first_scrape_ids:
            target_path = first_scrape_dir / pdf_file.name
            pdf_file.rename(target_path)
            moved_to_first.append(file_id)
            print(f"  {pdf_file.name} ? first_scrape/")
        
        # Check if ID matches second scrape
        elif file_id in second_scrape_ids:
            target_path = second_scrape_dir / pdf_file.name
            pdf_file.rename(target_path)
            moved_to_second.append(file_id)
            print(f"  {pdf_file.name} ? second_scrape/")
        
        # Unmatched
        else:
            unmatched.append(file_id)
            print(f"  {pdf_file.name} ? UNMATCHED (staying in downloaded_papers/)")
    
    print()
    
    # Print summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  Total PDFs processed: {len(pdf_files)}")
    print(f"  Moved to first_scrape/: {len(moved_to_first)}")
    print(f"  Moved to second_scrape/: {len(moved_to_second)}")
    print(f"  Unmatched (remaining in downloaded_papers/): {len(unmatched)}")
    
    if unmatched:
        print()
        print("  Unmatched files:")
        for file_id in sorted(unmatched, key=lambda x: (len(x), x)):
            print(f"    - {file_id}.pdf")
    
    print("="*60)


if __name__ == "__main__":
    main()
