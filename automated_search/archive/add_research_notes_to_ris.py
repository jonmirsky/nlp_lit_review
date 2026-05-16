#!/usr/bin/env python3
"""
Add Research Notes (N1) fields to RIS file based on cross-reference CSV.

This script reads the cross-reference CSV and adds N1 fields to each reference
in the RIS file containing comma-separated search term categories.
"""

import csv
import re
from pathlib import Path
from typing import Dict, List


def load_csv_mapping(csv_path: Path) -> Dict[str, List[str]]:
    """
    Load CSV file and create mapping from paper labels to categories.
    
    Args:
        csv_path: Path to cross-reference CSV file
    
    Returns:
        Dictionary mapping paper label (string) to list of category names
    """
    mapping = {}
    categories = ['brain', 'clinical', 'neurology', 'neuroscience', 'pathology', 'radiology', 'stroke']
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            paper_label = row['Paper Label'].strip()
            matched_categories = []
            
            for category in categories:
                if row.get(category, '').strip().lower() == 'x':
                    matched_categories.append(category)
            
            mapping[paper_label] = matched_categories
    
    return mapping


def add_research_notes_to_ris(input_ris_path: Path, output_ris_path: Path, 
                               csv_mapping: Dict[str, List[str]]) -> None:
    """
    Add N1 (Research Notes) fields to RIS file based on CSV mapping.
    
    Args:
        input_ris_path: Path to input RIS file
        output_ris_path: Path to output RIS file
        csv_mapping: Dictionary mapping paper labels to categories
    """
    with open(input_ris_path, 'r', encoding='utf-8') as f_in:
        lines = f_in.readlines()
    
    output_lines = []
    current_entry = []
    paper_label = None
    n1_index = None
    
    for line in lines:
        line_stripped = line.rstrip()
        
        # Check if this is the end of a record
        if line_stripped == 'ER  -' or line_stripped == 'ER -':
            # End of record - add N1 field if we have categories
            if paper_label and paper_label in csv_mapping:
                categories = csv_mapping[paper_label]
                if categories:
                    # Format categories as comma-separated string
                    notes_text = ', '.join(categories)
                    n1_line = f'N1  - {notes_text}\n'
                    
                    if n1_index is not None:
                        # Replace existing N1 field
                        current_entry[n1_index] = n1_line
                    else:
                        # Add N1 field before ER
                        current_entry.append(n1_line)
            
            # Add all entry lines including ER
            output_lines.extend(current_entry)
            output_lines.append(line)  # ER line
            
            # Reset for next entry
            current_entry = []
            paper_label = None
            n1_index = None
            continue
        
        # Track LB field (paper label)
        if line_stripped.startswith('LB  -'):
            paper_label = line_stripped[6:].strip()
        
        # Track N1 field if it exists
        if line_stripped.startswith('N1  -'):
            n1_index = len(current_entry)
        
        # Add line to current entry
        current_entry.append(line)
    
    # Write output file
    with open(output_ris_path, 'w', encoding='utf-8') as f_out:
        f_out.writelines(output_lines)


def main():
    """Main function."""
    base_dir = Path(__file__).parent
    input_ris_file = base_dir / "found_papers" / "RIS_files" / "import_to_endnote" / "1033_papers_ris_with_attachments.txt"
    csv_file = base_dir / "found_papers" / "RIS_files" / "import_to_endnote" / "cross_reference_results.csv"
    output_ris_file = base_dir / "found_papers" / "RIS_files" / "import_to_endnote" / "1033_papers_ris_with_attachments_with_notes.txt"
    
    # Verify input files exist
    if not input_ris_file.exists():
        print(f"ERROR: Input RIS file not found: {input_ris_file}")
        return
    
    if not csv_file.exists():
        print(f"ERROR: CSV file not found: {csv_file}")
        return
    
    # Load CSV mapping
    print(f"Loading CSV mapping from: {csv_file.name}")
    csv_mapping = load_csv_mapping(csv_file)
    print(f"Loaded {len(csv_mapping)} paper labels from CSV")
    
    # Count papers with categories
    papers_with_categories = sum(1 for cats in csv_mapping.values() if cats)
    print(f"Found {papers_with_categories} papers with matching categories")
    
    # Process RIS file
    print(f"\nProcessing RIS file: {input_ris_file.name}")
    add_research_notes_to_ris(input_ris_file, output_ris_file, csv_mapping)
    
    print(f"\nSuccessfully created output file: {output_ris_file.name}")
    print(f"Output location: {output_ris_file}")


if __name__ == "__main__":
    main()
