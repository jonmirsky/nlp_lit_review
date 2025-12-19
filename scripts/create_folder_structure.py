"""
Script to create folder structure mirroring the flowchart organization.
Organizes papers into folders: Database ? Query ? Branch Terms ? Green Nodes
Also creates orange (Most cited aggregate) and red (Most relevant) folders.
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from typing import Dict, List, Set

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from overlap_calculator import OverlapCalculator
from config import get_queries_with_ris_files, RIS_SOURCE_FOLDER
from pdf_resolver import PDFResolver


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize folder name to be filesystem-safe.
    Removes invalid characters and trims whitespace.
    
    Args:
        name: Original folder name
        
    Returns:
        Sanitized folder name safe for filesystem
    """
    if not name:
        return "unnamed"
    
    # Remove "AND " prefix if present
    name = name.strip()
    if name.upper().startswith("AND "):
        name = name[4:].strip()
    
    # Replace invalid filesystem characters with underscore
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    
    # Remove leading/trailing dots and spaces
    name = name.strip('. ')
    
    # Collapse multiple underscores/spaces
    while '__' in name:
        name = name.replace('__', '_')
    while '  ' in name:
        name = name.replace('  ', ' ')
    
    # Replace spaces with underscores for folder names
    name = name.replace(' ', '_')
    
    # Ensure not empty
    if not name:
        return "unnamed"
    
    # Limit length
    if len(name) > 100:
        name = name[:100]
    
    return name


def sanitize_pdf_filename(filename: str) -> str:
    """
    Sanitize PDF filename to be filesystem-safe.
    
    Args:
        filename: Original PDF filename
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed.pdf"
    
    # Get extension
    path = Path(filename)
    ext = path.suffix or '.pdf'
    stem = path.stem
    
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        stem = stem.replace(char, '_')
    
    # Remove leading/trailing dots and spaces
    stem = stem.strip('. ')
    
    # Collapse multiple underscores
    while '__' in stem:
        stem = stem.replace('__', '_')
    
    # Ensure not empty
    if not stem:
        stem = "unnamed"
    
    # Limit length
    if len(stem) > 200:
        stem = stem[:200]
    
    return f"{stem}{ext}"


def copy_pdf_to_folder(pdf_resolver: PDFResolver, paper, target_folder: Path, copied_files: Set[str]) -> bool:
    """
    Copy PDF file to target folder if it exists and hasn't been copied already.
    
    Args:
        pdf_resolver: PDFResolver instance
        paper: Paper object with pdf_path attribute
        target_folder: Destination folder path
        copied_files: Set of already copied file paths (to avoid duplicates)
        
    Returns:
        True if PDF was copied, False otherwise
    """
    if not paper.pdf_path:
        return False
    
    # Resolve PDF path
    pdf_path = pdf_resolver.resolve(paper.pdf_path)
    if not pdf_path or not Path(pdf_path).exists():
        return False
    
    # Check if already copied (avoid duplicates)
    pdf_abs_path = str(Path(pdf_path).absolute())
    if pdf_abs_path in copied_files:
        # File already copied, but we might want to create a symlink or skip
        # For now, we'll skip to avoid duplicates
        return True
    
    # Create target folder if it doesn't exist
    target_folder.mkdir(parents=True, exist_ok=True)
    
    # Generate target filename
    source_filename = Path(pdf_path).name
    sanitized_filename = sanitize_pdf_filename(source_filename)
    target_path = target_folder / sanitized_filename
    
    # Handle filename conflicts
    counter = 1
    original_target = target_path
    while target_path.exists():
        stem = original_target.stem
        ext = original_target.suffix
        target_path = target_folder / f"{stem}_{counter}{ext}"
        counter += 1
    
    try:
        # Copy file
        shutil.copy2(pdf_path, target_path)
        copied_files.add(pdf_abs_path)
        return True
    except Exception as e:
        print(f"Warning: Failed to copy PDF {pdf_path} to {target_path}: {e}")
        return False


def create_folder_structure(output_dir: Path, clean: bool = False):
    """
    Create folder structure mirroring flowchart organization.
    
    Args:
        output_dir: Base directory where folder structure will be created
        clean: If True, remove existing structure before creating new one
    """
    print(f"Creating folder structure in: {output_dir}")
    
    # Clean existing structure if requested
    if clean and output_dir.exists():
        print(f"Cleaning existing folder structure at {output_dir}...")
        shutil.rmtree(output_dir)
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get queries with RIS files
    resolved_queries = get_queries_with_ris_files()
    if not resolved_queries:
        print("Error: No queries found. Check RIS_SOURCE_FOLDER and COMMON_SEARCH_TERMS configuration.")
        return
    
    print(f"Found {len(resolved_queries)} query/queries")
    
    # Initialize PDF resolver
    pdf_resolver = PDFResolver()
    
    # Build hierarchy using OverlapCalculator
    calculator = OverlapCalculator(resolved_queries)
    query_databases = calculator.load_papers_from_queries()
    
    # Load most-cited and most-relevant papers
    calculator.load_most_cited_papers()
    calculator.load_most_relevant_papers()
    
    # Build hierarchy
    hierarchy = calculator.build_hierarchy()
    
    # Track copied files to avoid duplicates
    copied_files: Set[str] = set()
    
    # Process each database
    for database_name, queries in hierarchy.items():
        # Sanitize database name
        db_folder_name = sanitize_folder_name(database_name.lower())
        db_folder = output_dir / db_folder_name
        db_folder.mkdir(parents=True, exist_ok=True)
        print(f"\nProcessing database: {database_name} -> {db_folder_name}/")
        
        # Process each query
        for query_name, branch_terms in queries.items():
            # Sanitize query name
            query_folder_name = sanitize_folder_name(query_name)
            query_folder = db_folder / query_folder_name
            query_folder.mkdir(parents=True, exist_ok=True)
            print(f"  Processing query: {query_name} -> {query_folder_name}/")
            
            # Collect papers for orange and red nodes
            # Use sets with paper IDs to track unique papers
            all_most_cited_paper_ids = set()
            all_most_cited_papers = []  # Keep list for order
            all_most_relevant_paper_ids = set()
            all_most_relevant_papers = []  # Keep list for order
            
            # Process branch terms (blue nodes)
            for branch_term, papers in branch_terms.items():
                # Skip "uncategorized" - it's handled separately
                if branch_term == "uncategorized":
                    continue
                
                # Sanitize branch term name
                branch_folder_name = sanitize_folder_name(branch_term)
                branch_folder = query_folder / branch_folder_name
                branch_folder.mkdir(parents=True, exist_ok=True)
                print(f"    Processing branch term: {branch_term} -> {branch_folder_name}/")
                
                # Get papers for this branch term
                branch_papers = calculator.papers_by_query_and_branch.get(query_name, {}).get(branch_term, [])
                
                # Copy PDFs to branch term folder
                for paper in branch_papers:
                    copy_pdf_to_folder(pdf_resolver, paper, branch_folder, copied_files)
                
                # Check for green node (most cited for this branch term)
                most_cited_papers = calculator.most_cited_by_query_and_branch.get(query_name, {}).get(branch_term, [])
                if most_cited_papers:
                    green_folder = branch_folder / "Most_cited_or_of_interest"
                    green_folder.mkdir(parents=True, exist_ok=True)
                    print(f"      Creating green node: Most_cited_or_of_interest/")
                    
                    # Copy PDFs to green node folder and add to aggregate
                    for paper in most_cited_papers:
                        copy_pdf_to_folder(pdf_resolver, paper, green_folder, copied_files)
                        # Add to aggregate list (deduplicate by ID)
                        paper_id = paper.id if hasattr(paper, 'id') else None
                        if paper_id and paper_id not in all_most_cited_paper_ids:
                            all_most_cited_paper_ids.add(paper_id)
                            all_most_cited_papers.append(paper)
                        elif not paper_id and paper not in all_most_cited_papers:
                            all_most_cited_papers.append(paper)
                
                # Check for most relevant papers for this branch term
                most_relevant_papers = calculator.most_relevant_by_query_and_branch.get(query_name, {}).get(branch_term, [])
                if most_relevant_papers:
                    for paper in most_relevant_papers:
                        paper_id = paper.id if hasattr(paper, 'id') else None
                        if paper_id and paper_id not in all_most_relevant_paper_ids:
                            all_most_relevant_paper_ids.add(paper_id)
                            all_most_relevant_papers.append(paper)
                        elif not paper_id and paper not in all_most_relevant_papers:
                            all_most_relevant_papers.append(paper)
            
            # Get uncategorized papers
            uncategorized_papers = calculator.papers_by_query_and_branch.get(query_name, {}).get("uncategorized", [])
            
            # Create orange node (Most cited aggregate) at query level
            # Orange node includes: all papers from green nodes + all uncategorized papers
            if all_most_cited_papers or uncategorized_papers:
                orange_folder = query_folder / "Most_cited_or_of_interest"
                orange_folder.mkdir(parents=True, exist_ok=True)
                print(f"    Creating orange node: Most_cited_or_of_interest/")
                
                # Copy PDFs from green nodes to orange node folder
                for paper in all_most_cited_papers:
                    copy_pdf_to_folder(pdf_resolver, paper, orange_folder, copied_files)
                
                # Add uncategorized papers to orange node (as per visualization logic)
                for paper in uncategorized_papers:
                    paper_id = paper.id if hasattr(paper, 'id') else None
                    if paper_id and paper_id not in all_most_cited_paper_ids:
                        all_most_cited_paper_ids.add(paper_id)
                        all_most_cited_papers.append(paper)
                        copy_pdf_to_folder(pdf_resolver, paper, orange_folder, copied_files)
                    elif not paper_id and paper not in all_most_cited_papers:
                        all_most_cited_papers.append(paper)
                        copy_pdf_to_folder(pdf_resolver, paper, orange_folder, copied_files)
                
                # Create red node (Most relevant) inside orange node
                # Red node includes: all papers from most_relevant_by_query_and_branch (NO uncategorized)
                if all_most_relevant_papers:
                    red_folder = orange_folder / "Most_relevant"
                    red_folder.mkdir(parents=True, exist_ok=True)
                    print(f"      Creating red node: Most_relevant/")
                    
                    # Copy PDFs to red node folder
                    for paper in all_most_relevant_papers:
                        copy_pdf_to_folder(pdf_resolver, paper, red_folder, copied_files)
    
    print(f"\n? Folder structure created successfully in {output_dir}")
    print(f"  Total unique PDFs copied: {len(copied_files)}")


def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(
        description="Create folder structure mirroring flowchart organization"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for folder structure (defaults to OneDrive location)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing folder structure before creating new one"
    )
    
    args = parser.parse_args()
    
    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).absolute()
    else:
        # Default to OneDrive location
        output_dir = Path("/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/organized_papers")
    
    # Create folder structure
    try:
        create_folder_structure(output_dir, clean=args.clean)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
