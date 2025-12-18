#!/usr/bin/env python3
"""
Flatten PDF folder structure for GitHub Release upload.
Creates copies of PDFs with predictable, URL-safe filenames.

Usage:
    python scripts/prepare_pdfs_for_github.py

Output:
    Creates a 'pdfs_for_github' directory with flattened PDF copies.
    Upload these files to a GitHub Release.
"""
import os
import re
import shutil
from pathlib import Path


def sanitize_filename(filename: str) -> str:
    """
    Make filename URL-safe.
    
    Args:
        filename: Original filename (e.g., "Deep Learning for NLP.pdf")
        
    Returns:
        URL-safe filename (e.g., "Deep_Learning_for_NLP.pdf")
    """
    # Remove extension, sanitize, re-add extension
    name = Path(filename).stem
    ext = Path(filename).suffix
    # Replace special chars with underscore
    safe = re.sub(r'[^\w\-]', '_', name)
    # Collapse multiple underscores
    safe = re.sub(r'_+', '_', safe)
    # Trim underscores from ends
    safe = safe.strip('_')
    # Limit length to avoid issues
    if len(safe) > 100:
        safe = safe[:100]
    return f"{safe}{ext}"


def flatten_pdfs(source_folders: list, output_dir: str):
    """
    Copy PDFs with flattened filenames.
    
    Args:
        source_folders: List of (path, prefix) tuples
        output_dir: Directory to copy flattened PDFs to
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    copied = 0
    skipped = 0
    errors = 0
    
    # Track filenames to detect collisions
    used_names = set()
    
    for source_path, prefix in source_folders:
        source = Path(source_path)
        if not source.exists():
            print(f"Warning: {source} does not exist, skipping")
            continue
        
        print(f"\nProcessing: {source} (prefix: {prefix})")
        
        # Look for PDF subfolders (numbered folders like 0352406214)
        pdf_base = source / "PDF" if (source / "PDF").exists() else source
        
        if not pdf_base.exists():
            print(f"  Warning: {pdf_base} does not exist")
            continue
        
        for folder in sorted(pdf_base.iterdir()):
            if folder.is_dir() and folder.name.isdigit():
                folder_id = folder.name
                for pdf_file in folder.glob("*.pdf"):
                    try:
                        safe_name = sanitize_filename(pdf_file.name)
                        new_name = f"{prefix}_{folder_id}_{safe_name}"
                        
                        # Handle potential name collisions
                        if new_name in used_names:
                            # Add a suffix to make unique
                            base, ext = new_name.rsplit('.', 1)
                            counter = 2
                            while f"{base}_{counter}.{ext}" in used_names:
                                counter += 1
                            new_name = f"{base}_{counter}.{ext}"
                        
                        used_names.add(new_name)
                        dest = output_path / new_name
                        
                        if dest.exists():
                            print(f"  Skip (exists): {new_name}")
                            skipped += 1
                            continue
                        
                        shutil.copy2(pdf_file, dest)
                        print(f"  Copied: {new_name}")
                        copied += 1
                        
                    except Exception as e:
                        print(f"  Error copying {pdf_file}: {e}")
                        errors += 1
    
    print(f"\n{'='*60}")
    print(f"Done!")
    print(f"  Copied: {copied}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Output directory: {output_path.absolute()}")
    
    # Calculate total size
    total_size = sum(f.stat().st_size for f in output_path.glob("*.pdf"))
    print(f"  Total size: {total_size / (1024*1024):.1f} MB")
    
    print(f"\n{'='*60}")
    print("Next steps:")
    print("1. Go to: https://github.com/jonmirsky/nlp_lit_review/releases")
    print("2. Click 'Create a new release'")
    print("3. Tag: pdfs-v1")
    print("4. Title: PDF Assets v1")
    print(f"5. Upload all files from: {output_path.absolute()}")
    print("6. Publish release")


def main():
    """Main entry point."""
    # Configure source folders
    # These are the two Endnote library locations containing PDFs
    sources = [
        ("/Users/jon/Documents/badjatia_hu/Endnote/NLP_v4.Data", "NLP_v4"),
        ("/Users/jon/Documents/badjatia_hu/Endnote/from_zotero_v3.Data", "zotero_v3"),
    ]
    
    # Output directory (in the project folder)
    output = "/Users/jon/Documents/badjatia_hu/visualizer_nlp_lit_review/pdfs_for_github"
    
    print("PDF Flattening Script for GitHub Release")
    print("="*60)
    print(f"Source folders:")
    for path, prefix in sources:
        exists = "?" if Path(path).exists() else "?"
        print(f"  [{exists}] {path} -> prefix: {prefix}")
    print(f"Output: {output}")
    print("="*60)
    
    flatten_pdfs(sources, output)


if __name__ == "__main__":
    main()

