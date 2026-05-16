#!/usr/bin/env python3
"""
Analyze unmatched PDF files to determine their source.

This script checks:
1. If filenames match PMIDs in RIS files
2. If filenames match record numbers in RIS files
3. If files appear in import map files
4. Pattern analysis of filenames
"""

import re
from pathlib import Path
from typing import Set, Dict, List


def extract_pmids_from_ris(ris_file_path: Path) -> Set[str]:
    """Extract all PMID values from a RIS file."""
    pmids = set()
    
    if not ris_file_path.exists():
        return pmids
    
    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all AN fields (PMID): "AN  - <value>"
    pattern = re.compile(r'^AN\s+-\s+(.+)$', re.MULTILINE)
    matches = pattern.findall(content)
    
    for match in matches:
        pmid = match.strip()
        if pmid and pmid.isdigit():
            pmids.add(pmid)
    
    return pmids


def extract_record_numbers_from_ris(ris_file_path: Path) -> Set[str]:
    """Extract all record number (ID) values from a RIS file."""
    ids = set()
    
    if not ris_file_path.exists():
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


def get_import_map_record_numbers() -> Set[str]:
    """Get all record numbers from import map files."""
    record_numbers = set()
    import_ids_dir = Path("found_papers/import_IDs")
    
    if not import_ids_dir.exists():
        return record_numbers
    
    # Check all import_map*.txt files
    for import_map_file in import_ids_dir.glob("import_map*.txt"):
        with open(import_map_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '\t' in line:
                    record_number = line.split('\t')[0]
                    if record_number:
                        record_numbers.add(record_number)
    
    return record_numbers


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent
    
    # Define paths
    downloaded_papers_dir = base_dir / "found_papers" / "downloaded_papers"
    archive_dir = base_dir / "missing_papers" / "still_missing" / "archive"
    
    first_scrape_ris = archive_dir / "missing_papers.txt"
    second_scrape_ris = archive_dir / "missing_papers2.txt"
    no_doi_ris = base_dir / "missing_papers" / "still_missing" / "no_DOI_missing_post_selenium" / "missing_papers.txt"
    
    print("="*60)
    print("ANALYZING UNMATCHED PDF FILES")
    print("="*60)
    print()
    
    # Get unmatched files (PDFs in main folder, not in subfolders)
    print("Scanning for unmatched PDF files...")
    unmatched_files = []
    for pdf_file in downloaded_papers_dir.iterdir():
        if pdf_file.is_file() and pdf_file.suffix.lower() == '.pdf':
            unmatched_files.append(pdf_file.stem)  # filename without .pdf
    
    print(f"  Found {len(unmatched_files)} unmatched PDF files")
    print()
    
    # Extract IDs from RIS files
    print("Extracting IDs from RIS files...")
    first_scrape_pmids = extract_pmids_from_ris(first_scrape_ris)
    first_scrape_record_numbers = extract_record_numbers_from_ris(first_scrape_ris)
    print(f"  {first_scrape_ris.name}: {len(first_scrape_pmids)} PMIDs, {len(first_scrape_record_numbers)} record numbers")
    
    second_scrape_pmids = extract_pmids_from_ris(second_scrape_ris)
    second_scrape_record_numbers = extract_record_numbers_from_ris(second_scrape_ris)
    print(f"  {second_scrape_ris.name}: {len(second_scrape_pmids)} PMIDs, {len(second_scrape_record_numbers)} record numbers")
    
    no_doi_pmids = extract_pmids_from_ris(no_doi_ris)
    no_doi_record_numbers = extract_record_numbers_from_ris(no_doi_ris)
    print(f"  {no_doi_ris.name}: {len(no_doi_pmids)} PMIDs, {len(no_doi_record_numbers)} record numbers")
    
    all_pmids = first_scrape_pmids | second_scrape_pmids | no_doi_pmids
    all_record_numbers = first_scrape_record_numbers | second_scrape_record_numbers | no_doi_record_numbers
    
    # Get record numbers from import maps
    print()
    print("Checking import map files...")
    import_map_record_numbers = get_import_map_record_numbers()
    print(f"  Found {len(import_map_record_numbers)} record numbers in import map files")
    print()
    
    # Analyze unmatched files
    print("Analyzing unmatched files...")
    print()
    
    matched_as_pmid = []
    matched_as_record_number = []
    matched_in_import_map = []
    unmatched_completely = []
    
    for filename in unmatched_files:
        matched = False
        
        # Check if it's a PMID
        if filename in all_pmids:
            matched_as_pmid.append(filename)
            matched = True
        
        # Check if it's a record number
        if filename in all_record_numbers:
            matched_as_record_number.append(filename)
            matched = True
        
        # Check if it's in import maps
        if filename in import_map_record_numbers:
            matched_in_import_map.append(filename)
            matched = True
        
        if not matched:
            unmatched_completely.append(filename)
    
    # Print results
    print("="*60)
    print("RESULTS")
    print("="*60)
    print(f"  Total unmatched files: {len(unmatched_files)}")
    print()
    
    if matched_as_pmid:
        print(f"  Matched as PMIDs: {len(matched_as_pmid)}")
        print("    These files are named with PMIDs (not record numbers):")
        for f in sorted(matched_as_pmid, key=lambda x: (len(x), x))[:20]:
            print(f"      - {f}.pdf")
        if len(matched_as_pmid) > 20:
            print(f"      ... and {len(matched_as_pmid) - 20} more")
        print()
    
    if matched_as_record_number:
        print(f"  Matched as record numbers: {len(matched_as_record_number)}")
        print("    These files ARE in RIS files but weren't moved (possible bug):")
        for f in sorted(matched_as_record_number):
            print(f"      - {f}.pdf")
        print()
    
    if matched_in_import_map:
        print(f"  Found in import maps: {len(matched_in_import_map)}")
        print("    These files were downloaded by your scripts:")
        for f in sorted(matched_in_import_map)[:20]:
            print(f"      - {f}.pdf")
        if len(matched_in_import_map) > 20:
            print(f"      ... and {len(matched_in_import_map) - 20} more")
        print()
    
    if unmatched_completely:
        print(f"  Completely unmatched: {len(unmatched_completely)}")
        print("    These files don't match any IDs in RIS files or import maps:")
        for f in sorted(unmatched_completely, key=lambda x: (len(x), x))[:20]:
            print(f"      - {f}.pdf")
        if len(unmatched_completely) > 20:
            print(f"      ... and {len(unmatched_completely) - 20} more")
        print()
    
    # Pattern analysis
    print("="*60)
    print("PATTERN ANALYSIS")
    print("="*60)
    
    # Count by length
    length_counts = {}
    for filename in unmatched_files:
        length = len(filename)
        length_counts[length] = length_counts.get(length, 0) + 1
    
    print("  Filename length distribution:")
    for length in sorted(length_counts.keys()):
        count = length_counts[length]
        print(f"    {length} digits: {count} files")
    
    print()
    print("  Files that look like PMIDs (7 digits):")
    pmid_like = [f for f in unmatched_files if re.match(r'^\d{7}$', f)]
    print(f"    {len(pmid_like)} files")
    if pmid_like:
        print(f"    Examples: {', '.join(pmid_like[:5])}")
    
    print()
    print("  Files that look like record numbers (1-4 digits):")
    record_like = [f for f in unmatched_files if re.match(r'^\d{1,4}$', f)]
    print(f"    {len(record_like)} files")
    if record_like:
        print(f"    Examples: {', '.join(record_like[:10])}")
    
    print("="*60)


if __name__ == "__main__":
    main()
