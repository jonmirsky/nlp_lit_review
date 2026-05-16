#!/usr/bin/env python3
"""
Archive duplicate papers from main downloaded_papers folder.

This script finds any PDF files in downloaded_papers/ that also exist in
first_scrape/ or second_scrape/ folders, and moves those duplicates to an
archive folder.
"""

from pathlib import Path
from typing import Set


def get_pdf_filenames(directory: Path) -> Set[str]:
    """
    Get set of all PDF filenames in a directory.
    
    Args:
        directory: Path to directory to scan
        
    Returns:
        Set of PDF filenames (just the filename, not full path)
    """
    if not directory.exists():
        return set()
    
    pdf_files = {f.name for f in directory.iterdir() 
                 if f.is_file() and f.suffix.lower() == '.pdf'}
    return pdf_files


def main():
    """Main execution function."""
    # Define paths
    base_dir = Path(__file__).parent
    downloaded_papers_dir = base_dir / "found_papers" / "downloaded_papers"
    first_scrape_dir = downloaded_papers_dir / "first_scrape"
    second_scrape_dir = downloaded_papers_dir / "second_scrape"
    archive_dir = downloaded_papers_dir / "archive"
    
    print("="*60)
    print("ARCHIVING DUPLICATE PAPERS")
    print("="*60)
    print()
    
    # Get all PDF filenames from each folder
    print("Scanning folders for PDF files...")
    main_folder_pdfs = get_pdf_filenames(downloaded_papers_dir)
    first_scrape_pdfs = get_pdf_filenames(first_scrape_dir)
    second_scrape_pdfs = get_pdf_filenames(second_scrape_dir)
    
    print(f"  Main folder (downloaded_papers/): {len(main_folder_pdfs)} PDFs")
    print(f"  first_scrape/: {len(first_scrape_pdfs)} PDFs")
    print(f"  second_scrape/: {len(second_scrape_pdfs)} PDFs")
    print()
    
    # Find duplicates
    # Files in main folder that also exist in first_scrape or second_scrape
    all_scrape_pdfs = first_scrape_pdfs | second_scrape_pdfs
    duplicates = main_folder_pdfs & all_scrape_pdfs
    
    print(f"Found {len(duplicates)} duplicate files")
    print()
    
    if not duplicates:
        print("No duplicates found. Nothing to archive.")
        print("="*60)
        return
    
    # Create archive folder
    print("Creating archive folder...")
    archive_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Created: {archive_dir}")
    print()
    
    # Move duplicates
    print("Moving duplicates to archive...")
    archived_files = []
    
    for pdf_filename in sorted(duplicates):
        source_path = downloaded_papers_dir / pdf_filename
        target_path = archive_dir / pdf_filename
        
        if source_path.exists():
            source_path.rename(target_path)
            archived_files.append(pdf_filename)
            print(f"  {pdf_filename} ? archive/")
    
    print()
    
    # Print summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  Total duplicates found: {len(duplicates)}")
    print(f"  Files moved to archive: {len(archived_files)}")
    
    if archived_files:
        print()
        print("  Archived files:")
        for filename in sorted(archived_files):
            print(f"    - {filename}")
    
    print("="*60)


if __name__ == "__main__":
    main()
