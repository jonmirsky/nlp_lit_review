#!/usr/bin/env python3
"""
Create import map for existing PDFs in third_scrape_AI_agent folder.
Reads label_to_filename.txt and generates import map in the same format as debug_second_pdf_scrape_v2.py
"""

import re
import os
from pathlib import Path
from typing import Optional


def count_ris_references(ris_file_path: Path) -> int:
    """
    Count the number of references in a RIS file.
    """
    if not ris_file_path.exists():
        return 0
    
    try:
        with open(ris_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by ER  -  markers
        entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
        # Filter out empty entries
        return len([e for e in entries if e.strip()])
    except:
        return 0


def find_original_ris_file() -> Optional[Path]:
    """
    Find the original RIS file (the one the first scrape script would have read).
    Looks for missing_papers*.txt files in missing_papers/still_missing/ directory.
    """
    still_missing_dir = Path("missing_papers/still_missing")
    if not still_missing_dir.exists():
        return None
    
    # Pattern to match missing_papers*.txt files
    pattern = re.compile(r'^missing_papers(\d*)\.txt$')
    
    # Check for base file first
    base_file = still_missing_dir / "missing_papers.txt"
    if base_file.exists():
        return base_file
    
    # Find all numbered files
    numbered_files = []
    for file_path in still_missing_dir.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                number_str = match.group(1)
                number = int(number_str) if number_str else 0
                numbered_files.append((number, file_path))
    
    if numbered_files:
        # Return highest numbered file
        numbered_files.sort(key=lambda x: x[0], reverse=True)
        return numbered_files[0][1]
    
    return None


def get_import_map_filename(downloads: int, input_refs: int, original_refs: int, import_ids_dir: Path) -> str:
    """
    Generate import map filename in format: import_{downloads}_of_{input_refs}_of_{original_refs}_third_scrape.txt
    """
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    return f"import_{downloads}_of_{input_refs}_of_{original_refs}_third_scrape.txt"


def main():
    # Paths
    label_to_filename_file = Path('found_papers/downloaded_papers/third_scrape_AI_agent/label_to_filename.txt')
    pdf_dir = Path('found_papers/downloaded_papers/third_scrape_AI_agent')
    import_ids_dir = Path('found_papers/import_IDs')
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    
    if not label_to_filename_file.exists():
        print(f"ERROR: label_to_filename.txt not found at {label_to_filename_file}")
        return
    
    print(f"Reading {label_to_filename_file}...")
    
    # Read label_to_filename.txt
    successful_entries = []
    total_entries = 0
    
    with open(label_to_filename_file, 'r', encoding='utf-8') as f:
        # Skip header line
        header = f.readline()
        if not header.startswith('#'):
            f.seek(0)  # No header, start from beginning
        
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            total_entries += 1
            parts = line.split('|')
            if len(parts) >= 4:
                label_id = parts[0].strip()
                filename = parts[1].strip()
                status = parts[3].strip() if len(parts) > 3 else ''
                
                # Only process successful entries with a filename
                if status == 'success' and filename:
                    pdf_path = pdf_dir / filename
                    if pdf_path.exists() and pdf_path.stat().st_size > 1024:
                        # label_id equals record_number based on RIS file format
                        record_number = label_id
                        successful_entries.append((record_number, pdf_path))
    
    print(f"Found {len(successful_entries)} successful downloads with existing PDF files")
    print(f"Total entries in label_to_filename.txt: {total_entries}")
    
    if len(successful_entries) == 0:
        print("No successful entries found. Exiting.")
        return
    
    # Calculate counts
    downloads = len(successful_entries)
    input_refs = total_entries
    original_ris_file = find_original_ris_file()
    if original_ris_file:
        original_refs = count_ris_references(original_ris_file)
        print(f"Found original RIS file: {original_ris_file}")
        print(f"Original references: {original_refs}")
    else:
        original_refs = input_refs  # Fallback: use input_refs if original not found
        print(f"Original RIS file not found, using input_refs: {original_refs}")
    
    # Generate import map filename
    import_map_filename = get_import_map_filename(downloads, input_refs, original_refs, import_ids_dir)
    import_map_path = import_ids_dir / import_map_filename
    
    # Write import map file (tab-delimited, no header)
    print(f"\nWriting import map to: {import_map_path}")
    with open(import_map_path, 'w', encoding='utf-8') as f:
        for record_number, pdf_path in successful_entries:
            absolute_path = os.path.abspath(pdf_path)
            f.write(f"{record_number}\t{absolute_path}\n")
    
    print(f"Import map created successfully!")
    print(f"  File: {import_map_path}")
    print(f"  Entries: {downloads}")
    print(f"  Format: record_number\\tabsolute_path")


if __name__ == '__main__':
    main()
