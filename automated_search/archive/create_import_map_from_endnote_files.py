#!/usr/bin/env python3
"""
Create import map from EndNote files folder structure.

This script scans an EndNote "files" folder (containing numbered subdirectories with PDFs)
and creates an import map file in the same format as other import maps in import_IDs.

The script:
1. Finds the newest folder in search_term_results (default)
2. Looks for a "files" subdirectory
3. Scans numbered subdirectories for PDF files
4. Creates import map: record_number\tabsolute_path_to_pdf
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Tuple


def find_newest_search_term_folder(search_term_results_dir: Path) -> Optional[Path]:
    """
    Find the newest (most recently modified) folder in search_term_results directory.
    """
    if not search_term_results_dir.exists():
        return None
    
    folders = []
    for item in search_term_results_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            stat = item.stat()
            mtime = stat.st_mtime
            folders.append((mtime, item))
    
    if not folders:
        return None
    
    # Sort by modification time (most recent first)
    folders.sort(key=lambda x: x[0], reverse=True)
    return folders[0][1]


def find_files_folder(base_dir: Path) -> Optional[Path]:
    """
    Look for a "files" subdirectory in the given directory.
    """
    files_dir = base_dir / "files"
    if files_dir.exists() and files_dir.is_dir():
        return files_dir
    return None


def scan_files_folder_for_pdfs(files_dir: Path) -> List[Tuple[str, Path]]:
    """
    Scan the files folder for numbered subdirectories containing PDF files.
    Returns list of (record_number, pdf_path) tuples.
    """
    pdf_mappings = []
    
    if not files_dir.exists():
        return pdf_mappings
    
    # Pattern to match numbered folder names (e.g., "14605", "14861")
    number_pattern = re.compile(r'^\d+$')
    
    for item in files_dir.iterdir():
        if not item.is_dir():
            continue
        
        # Check if folder name is a number (record number)
        if number_pattern.match(item.name):
            record_number = item.name
            
            # Look for PDF files in this folder
            pdf_files = list(item.glob("*.pdf"))
            
            if pdf_files:
                # Use the first PDF found (typically there's only one)
                pdf_path = pdf_files[0]
                pdf_mappings.append((record_number, pdf_path))
            else:
                print(f"  WARNING: No PDF found in folder {item.name}")
    
    return pdf_mappings


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


def find_ris_file_in_directory(base_dir: Path) -> Optional[Path]:
    """
    Find RIS file in the given directory (looks for .ris files).
    """
    ris_files = list(base_dir.glob("*.ris"))
    if ris_files:
        # Return the first one found (or could return most recent)
        return ris_files[0]
    return None


def get_import_map_filename(found_pdfs: int, total_refs: int, base_dir_name: str, import_ids_dir: Path) -> str:
    """
    Generate import map filename in format similar to existing ones.
    Format: import_{found_pdfs}_of_{total_refs}_of_{total_refs}_{base_dir_name}.txt
    """
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    # Clean base_dir_name for filename (remove special characters)
    clean_name = re.sub(r'[^\w\-_]', '_', base_dir_name)
    return f"import_{found_pdfs}_of_{total_refs}_of_{total_refs}_{clean_name}.txt"


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent
    
    print("="*70)
    print("CREATE IMPORT MAP FROM ENDNOTE FILES FOLDER")
    print("="*70)
    print()
    
    # Default: search_term_results directory - now in OneDrive
    search_term_results_dir = Path("/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/search_term_results")
    
    # Find newest folder in search_term_results
    default_folder = find_newest_search_term_folder(search_term_results_dir)
    
    if default_folder:
        print(f"Default folder (newest in search_term_results): {default_folder.name}")
        print(f"  Path: {default_folder}")
        print()
        
        use_default = input("Use default folder? (y/n): ").strip().lower()
        if use_default == 'y':
            target_dir = default_folder
        else:
            user_input = input("Enter path to directory containing 'files' folder: ").strip()
            if not user_input:
                print("ERROR: No directory specified")
                return
            # Remove quotes if user included them (common when copy-pasting paths)
            user_input = user_input.strip("'\"")
            target_dir = Path(user_input)
    else:
        print("No default folder found in search_term_results")
        user_input = input("Enter path to directory containing 'files' folder: ").strip()
        if not user_input:
            print("ERROR: No directory specified")
            return
        # Remove quotes if user included them (common when copy-pasting paths)
        user_input = user_input.strip("'\"")
        target_dir = Path(user_input)
    
    if not target_dir.exists():
        print(f"ERROR: Directory not found: {target_dir}")
        return
    
    print(f"Using directory: {target_dir}")
    print()
    
    # Look for "files" subdirectory
    files_dir = find_files_folder(target_dir)
    if not files_dir:
        print(f"ERROR: 'files' folder not found in: {target_dir}")
        print("  Expected structure: <directory>/files/")
        return
    
    print(f"Found 'files' folder: {files_dir}")
    print()
    
    # Scan for PDFs
    print("Scanning for PDF files in numbered folders...")
    pdf_mappings = scan_files_folder_for_pdfs(files_dir)
    
    if not pdf_mappings:
        print("ERROR: No PDF files found in numbered folders")
        return
    
    print(f"Found {len(pdf_mappings)} PDF files")
    print()
    
    # Try to find RIS file to get total reference count
    ris_file = find_ris_file_in_directory(target_dir)
    total_refs = len(pdf_mappings)  # Default to number of PDFs found
    if ris_file:
        total_refs = count_ris_references(ris_file)
        print(f"Found RIS file: {ris_file.name}")
        print(f"  Total references in RIS: {total_refs}")
        print()
    
    # Generate import map filename
    base_dir_name = target_dir.name
    import_ids_dir = base_dir / "found_papers" / "import_IDs"
    import_map_filename = get_import_map_filename(len(pdf_mappings), total_refs, base_dir_name, import_ids_dir)
    import_map_path = import_ids_dir / import_map_filename
    
    # Write import map file (tab-delimited, no header)
    print(f"Writing import map to: {import_map_path}")
    with open(import_map_path, 'w', encoding='utf-8') as f:
        for record_number, pdf_path in sorted(pdf_mappings, key=lambda x: int(x[0])):
            absolute_path = os.path.abspath(pdf_path)
            f.write(f"{record_number}\t{absolute_path}\n")
    
    print()
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Source directory: {target_dir}")
    print(f"  Files folder: {files_dir}")
    print(f"  PDF files found: {len(pdf_mappings)}")
    if ris_file:
        print(f"  Total references in RIS: {total_refs}")
    print(f"  Import map file: {import_map_path.name}")
    print(f"  Full path: {import_map_path}")
    print()
    print("Import map format: record_number\\tabsolute_path_to_pdf")
    print("="*70)


if __name__ == '__main__':
    main()
