"""
Script to create folder structure mirroring the flowchart organization.
Organizes papers into folders: Database ? Query ? Branch Terms ? Green Nodes
Also creates orange (Most cited aggregate) and red (Most relevant) folders.

Inputs:
- RIS source and manual grouping files configured by visualizer_nlp_lit_review/config.py.
- PDF files resolved from the external EndNote data folders configured by the visualizer.

Outputs:
- Organized paper folders in the --output-dir location, or the default OneDrive organized_papers directory.
- Debug log entries in .cursor/debug.log under the current repository.
"""

import os
import sys
import shutil
import argparse
import json
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime
import subprocess

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from overlap_calculator import OverlapCalculator
from config import get_queries_with_ris_files, RIS_SOURCE_FOLDER
from pdf_resolver import PDFResolver


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_available_disk_space(path: Path) -> int:
    """
    Get available disk space in bytes for the given path.
    
    Args:
        path: Path to check disk space for
        
    Returns:
        Available space in bytes, or -1 if unable to determine
    """
    try:
        stat = shutil.disk_usage(path)
        return stat.free
    except (OSError, AttributeError):
        # Fallback for older Python versions or if path doesn't exist
        try:
            result = subprocess.run(
                ['df', '-k', str(path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        # Available space in KB, convert to bytes
                        return int(parts[3]) * 1024
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError, IndexError):
            pass
    return -1


def check_disk_space(output_dir: Path, min_gb: float = 1.0) -> bool:
    """
    Check if there's sufficient disk space available.
    With symlinks, we only need minimal space, but still good to check.
    
    Args:
        output_dir: Directory where files will be created
        min_gb: Minimum required space in GB (default 1GB for safety)
        
    Returns:
        True if sufficient space, False otherwise
    """
    available_bytes = get_available_disk_space(output_dir)
    if available_bytes < 0:
        print(f"⚠️  Warning: Could not determine available disk space for {output_dir}")
        return True  # Proceed anyway if we can't check
    
    available_gb = available_bytes / (1024 ** 3)
    min_bytes = min_gb * (1024 ** 3)
    
    if available_bytes < min_bytes:
        print(f"\n❌ ERROR: Insufficient disk space!")
        print(f"   Available: {available_gb:.2f} GB")
        print(f"   Required: {min_gb:.2f} GB minimum")
        print(f"   Location: {output_dir}")
        print(f"\n   Please free up disk space or choose a different output location.")
        return False
    
    if available_gb < 5.0:
        print(f"⚠️  Warning: Low disk space ({available_gb:.2f} GB available)")
        print(f"   Proceeding with symlinks (uses minimal space)...")
    
    return True


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


def log_debug(log_path: str, location: str, message: str, data: dict, hypothesis_id: str = None):
    """Log debug information to file"""
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "timestamp": int(datetime.now().timestamp() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "sessionId": "pdf-verification",
            "runId": "run1",
            "hypothesisId": hypothesis_id or "A"
        }
        with open(log_path, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception:
        pass  # Don't fail if logging fails


def copy_pdf_to_folder(pdf_resolver: PDFResolver, paper, target_folder: Path, copied_files: Set[str], log_path: str = None, stats: dict = None) -> bool:
    """
    Create symlink to PDF file in target folder if it exists.
    Uses symlinks instead of copying to save disk space (same PDF can appear in multiple folders).
    Only checks for duplicates within the same target folder, allowing the same PDF to be
    symlinked in multiple folders (e.g., branch term folder AND orange node folder).
    
    Args:
        pdf_resolver: PDFResolver instance
        paper: Paper object with pdf_path attribute
        target_folder: Destination folder path
        copied_files: Set of unique PDF paths (for statistics only, not used to skip symlinks)
        log_path: Path to log file for debugging
        stats: Dictionary to track statistics
        
    Returns:
        True if PDF was symlinked or already exists in this folder, False otherwise
    """
    # #region agent log
    if log_path:
        log_debug(log_path, "copy_pdf_to_folder:entry", "Checking paper for PDF", {
            "paper_id": getattr(paper, 'id', None),
            "paper_title": getattr(paper, 'title', '')[:100] if hasattr(paper, 'title') else '',
            "has_pdf_path": bool(paper.pdf_path),
            "pdf_path": paper.pdf_path if hasattr(paper, 'pdf_path') else None
        }, "A")
    # #endregion
    
    if not paper.pdf_path:
        if stats:
            stats['no_pdf_path'] = stats.get('no_pdf_path', 0) + 1
        if log_path:
            log_debug(log_path, "copy_pdf_to_folder:no_path", "Paper has no pdf_path", {
                "paper_id": getattr(paper, 'id', None),
                "paper_title": getattr(paper, 'title', '')[:100] if hasattr(paper, 'title') else ''
            }, "B")
        return False
    
    # Resolve PDF path
    pdf_path = pdf_resolver.resolve(paper.pdf_path)
    
    # #region agent log
    if log_path:
        log_debug(log_path, "copy_pdf_to_folder:resolved", "PDF resolver result", {
            "paper_id": getattr(paper, 'id', None),
            "internal_path": paper.pdf_path,
            "resolved_path": pdf_path,
            "resolved_exists": bool(pdf_path and Path(pdf_path).exists()) if pdf_path else False
        }, "C")
    # #endregion
    
    if not pdf_path:
        if stats:
            stats['pdf_not_resolved'] = stats.get('pdf_not_resolved', 0) + 1
        if log_path:
            log_debug(log_path, "copy_pdf_to_folder:not_resolved", "PDF resolver returned None", {
                "paper_id": getattr(paper, 'id', None),
                "internal_path": paper.pdf_path,
                "paper_title": getattr(paper, 'title', '')[:100] if hasattr(paper, 'title') else ''
            }, "D")
        return False
    
    if not Path(pdf_path).exists():
        if stats:
            stats['pdf_not_found'] = stats.get('pdf_not_found', 0) + 1
        if log_path:
            log_debug(log_path, "copy_pdf_to_folder:not_exists", "Resolved PDF path does not exist", {
                "paper_id": getattr(paper, 'id', None),
                "internal_path": paper.pdf_path,
                "resolved_path": pdf_path,
                "paper_title": getattr(paper, 'title', '')[:100] if hasattr(paper, 'title') else ''
            }, "E")
        return False
    
    # Create target folder if it doesn't exist
    target_folder.mkdir(parents=True, exist_ok=True)
    
    # Generate target filename
    source_filename = Path(pdf_path).name
    sanitized_filename = sanitize_pdf_filename(source_filename)
    target_path = target_folder / sanitized_filename
    
    # Handle filename conflicts (in case same PDF name appears multiple times in same folder)
    counter = 1
    original_target = target_path
    while target_path.exists():
        stem = original_target.stem
        ext = original_target.suffix
        target_path = target_folder / f"{stem}_{counter}{ext}"
        counter += 1
    
    # Check if symlink already exists in THIS folder (avoid duplicates within same folder)
    if target_path.exists():
        if stats:
            stats['already_copied'] = stats.get('already_copied', 0) + 1
        if log_path:
            log_debug(log_path, "copy_pdf_to_folder:duplicate", "Symlink already exists in this folder", {
                "paper_id": getattr(paper, 'id', None),
                "target_path": str(target_path)
            }, "F")
        return True
    
    try:
        # Copy file (OneDrive-compatible, works with sharing)
        shutil.copy2(pdf_path, target_path)
        
        # Track unique PDFs for statistics
        pdf_abs_path = str(Path(pdf_path).absolute())
        copied_files.add(pdf_abs_path)
        if stats:
            stats['copied'] = stats.get('copied', 0) + 1
        # #region agent log
        if log_path:
            log_debug(log_path, "copy_pdf_to_folder:success", "PDF copied successfully", {
                "paper_id": getattr(paper, 'id', None),
                "source": pdf_path,
                "target": str(target_path)
            }, "G")
        # #endregion
        return True
    except Exception as e:
        if stats:
            stats['copy_failed'] = stats.get('copy_failed', 0) + 1
        if log_path:
            log_debug(log_path, "copy_pdf_to_folder:exception", "Exception during copy", {
                "paper_id": getattr(paper, 'id', None),
                "source": pdf_path,
                "target": str(target_path),
                "error": str(e)
            }, "H")
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
    
    # Statistics tracking
    stats = {
        'total_papers': len(calculator.all_papers),
        'no_pdf_path': 0,
        'pdf_not_resolved': 0,
        'pdf_not_found': 0,
        'already_copied': 0,
        'copied': 0,
        'copy_failed': 0
    }
    
    # Log file path
    log_path = str(PROJECT_ROOT / ".cursor" / "debug.log")
    
    # Process each database
    for database_name, queries in hierarchy.items():
        # Sanitize database name
        db_folder_name = sanitize_folder_name(database_name.lower())
        db_folder = output_dir / db_folder_name
        db_folder.mkdir(parents=True, exist_ok=True)
        print(f"\nProcessing database: {database_name} -> {db_folder_name}/")
        
        # Collect papers for orange and red nodes at DATABASE level (across all queries)
        # This matches the visualization logic
        all_most_cited_papers_for_db = []  # Collect all most-cited papers from all queries
        all_most_relevant_papers_for_db = []  # Collect all most-relevant papers from all queries
        all_uncategorized_papers_for_db = []  # Collect all uncategorized papers from all queries
        
        # Process each query
        for query_name, branch_terms in queries.items():
            # Sanitize query name
            query_folder_name = sanitize_folder_name(query_name)
            query_folder = db_folder / query_folder_name
            query_folder.mkdir(parents=True, exist_ok=True)
            print(f"  Processing query: {query_name} -> {query_folder_name}/")
            
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
                    copy_pdf_to_folder(pdf_resolver, paper, branch_folder, copied_files, log_path, stats)
                
                # Check for green node (most cited for this branch term)
                most_cited_papers = calculator.most_cited_by_query_and_branch.get(query_name, {}).get(branch_term, [])
                if most_cited_papers:
                    green_folder = branch_folder / "Most_cited_or_of_interest"
                    green_folder.mkdir(parents=True, exist_ok=True)
                    print(f"      Creating green node: Most_cited_or_of_interest/")
                    
                    # Copy PDFs to green node folder and add to database-level aggregate
                    for paper in most_cited_papers:
                        copy_pdf_to_folder(pdf_resolver, paper, green_folder, copied_files, log_path, stats)
                        # Add to database-level aggregate (duplicates OK per user request)
                        all_most_cited_papers_for_db.append(paper)
                
                # Check for most relevant papers for this branch term
                most_relevant_papers = calculator.most_relevant_by_query_and_branch.get(query_name, {}).get(branch_term, [])
                if most_relevant_papers:
                    # Add to database-level aggregate (duplicates OK per user request)
                    all_most_relevant_papers_for_db.extend(most_relevant_papers)
            
            # Collect uncategorized papers for this query
            uncategorized_papers = calculator.papers_by_query_and_branch.get(query_name, {}).get("uncategorized", [])
            if uncategorized_papers:
                all_uncategorized_papers_for_db.extend(uncategorized_papers)
        
        # Create orange and red nodes at DATABASE level (after processing all queries)
        # This matches the visualization logic exactly
        
        # Orange node: all papers from green nodes + all uncategorized papers
        # Note: Visualization deduplicates, but user said duplicates are OK, so we include all
        if all_most_cited_papers_for_db or all_uncategorized_papers_for_db:
            # Create orange folder at database level (or query level if only one query)
            if len(queries) == 1:
                # Single query: create at query level
                query_name = list(queries.keys())[0]
                query_folder_name = sanitize_folder_name(query_name)
                query_folder = db_folder / query_folder_name
                orange_folder = query_folder / "Most_cited_or_of_interest"
            else:
                # Multiple queries: create at database level
                orange_folder = db_folder / "Most_cited_or_of_interest"
            
            orange_folder.mkdir(parents=True, exist_ok=True)
            print(f"\n  Creating orange node (database level): Most_cited_or_of_interest/")
            
            # Copy PDFs from green nodes to orange node folder
            for paper in all_most_cited_papers_for_db:
                copy_pdf_to_folder(pdf_resolver, paper, orange_folder, copied_files, log_path, stats)
            
            # Add uncategorized papers to orange node (as per visualization logic)
            for paper in all_uncategorized_papers_for_db:
                copy_pdf_to_folder(pdf_resolver, paper, orange_folder, copied_files, log_path, stats)
            
            # Create red node (Most relevant) inside orange node
            # Red node includes: all papers from most_relevant_by_query_and_branch (NO uncategorized)
            if all_most_relevant_papers_for_db:
                red_folder = orange_folder / "Most_relevant"
                red_folder.mkdir(parents=True, exist_ok=True)
                print(f"    Creating red node: Most_relevant/")
                
                # Copy PDFs to red node folder
                for paper in all_most_relevant_papers_for_db:
                    copy_pdf_to_folder(pdf_resolver, paper, red_folder, copied_files, log_path, stats)
    
    print(f"\n✓ Folder structure created successfully in {output_dir}")
    print(f"  Total unique PDFs copied: {len(copied_files)}")
    print(f"\n📊 PDF Copy Statistics:")
    print(f"  Total papers processed: {stats['total_papers']}")
    print(f"  Papers with no pdf_path: {stats['no_pdf_path']}")
    print(f"  PDFs that couldn't be resolved: {stats['pdf_not_resolved']}")
    print(f"  PDFs resolved but file not found: {stats['pdf_not_found']}")
    print(f"  PDFs already copied (duplicates in same folder): {stats['already_copied']}")
    print(f"  PDFs successfully copied: {stats['copied']}")
    print(f"  PDFs that failed to copy: {stats['copy_failed']}")
    print(f"\n  Summary: {stats['copied']} total PDF copies made ({len(copied_files)} unique PDFs) out of {stats['total_papers']} total papers")
    print(f"           (Same PDF can appear in multiple folders: branch term, green node, orange node, red node)")
    print(f"  Missing PDFs: {stats['no_pdf_path'] + stats['pdf_not_resolved'] + stats['pdf_not_found']} papers")
    
    # Log final stats
    if log_path:
        log_debug(log_path, "create_folder_structure:complete", "Process complete", stats, "I")


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
    
    # Check disk space before proceeding
    print(f"📁 Output directory: {output_dir}")
    # Note: With copying, we need more space. Estimate ~6GB for all PDFs with duplicates
    if not check_disk_space(output_dir, min_gb=8.0):
        print("\n❌ Aborting due to insufficient disk space.")
        print("   Note: Copying files requires more space than symlinks.")
        print("   Consider freeing up space or using a different location.")
        sys.exit(1)
    
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









