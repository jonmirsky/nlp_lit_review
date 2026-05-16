#!/usr/bin/env python3
"""
Convert RIS file L1 (file attachment) paths from relative to absolute.

This script reads a RIS file with relative L1 paths like:
    L1  - files/14861/filename.pdf

And converts them to absolute paths like:
    L1  - /Users/jon/.../files/14861/filename.pdf

The absolute path is based on the RIS file's location.
"""

import re
from pathlib import Path
from typing import Optional


def find_newest_ris_file(search_term_results_dir: Path) -> Optional[Path]:
    """
    Find the newest (most recently modified) folder in search_term_results directory
    and return the RIS file within it.
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
    newest_folder = folders[0][1]
    
    # Look for RIS file in this folder
    ris_files = list(newest_folder.glob("*.ris"))
    if ris_files:
        return ris_files[0]
    return None


def convert_ris_to_absolute_paths(input_ris_path: Path, output_ris_path: Optional[Path] = None) -> Path:
    """
    Convert relative L1 paths in a RIS file to absolute paths.
    
    Args:
        input_ris_path: Path to the input RIS file
        output_ris_path: Optional path for output file. If None, creates a new file
                        with "_absolute_paths" suffix in the same directory.
    
    Returns:
        Path to the output RIS file
    """
    if not input_ris_path.exists():
        raise FileNotFoundError(f"RIS file not found: {input_ris_path}")
    
    # Base directory for resolving relative paths
    base_dir = input_ris_path.parent
    
    # Read the RIS file
    with open(input_ris_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match L1 fields with relative paths
    # Matches: L1  - files/... or L1  - ./files/... etc.
    l1_pattern = re.compile(r'^(L1\s+-\s+)(?!/)(files/.+)$', re.MULTILINE)
    
    converted_count = 0
    already_absolute_count = 0
    
    def replace_l1_path(match):
        nonlocal converted_count
        prefix = match.group(1)
        relative_path = match.group(2)
        
        # Convert to absolute path
        absolute_path = (base_dir / relative_path).resolve()
        
        if absolute_path.exists():
            converted_count += 1
            return f"{prefix}{absolute_path}"
        else:
            # File doesn't exist, keep original but warn
            print(f"  WARNING: File not found: {absolute_path}")
            converted_count += 1
            return f"{prefix}{absolute_path}"
    
    # Also handle paths that might already start with /
    def check_absolute(match):
        nonlocal already_absolute_count
        already_absolute_count += 1
        return match.group(0)
    
    # First, count already absolute paths
    absolute_pattern = re.compile(r'^L1\s+-\s+/.+$', re.MULTILINE)
    already_absolute_count = len(absolute_pattern.findall(content))
    
    # Convert relative paths to absolute
    new_content = l1_pattern.sub(replace_l1_path, content)
    
    # Determine output path
    if output_ris_path is None:
        output_ris_path = base_dir / f"{input_ris_path.stem}_absolute_paths.ris"
    
    # Write the output file
    with open(output_ris_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  Converted {converted_count} relative L1 paths to absolute")
    if already_absolute_count > 0:
        print(f"  {already_absolute_count} L1 paths were already absolute")
    
    return output_ris_path


def main():
    """Main execution function."""
    print("="*70)
    print("CONVERT RIS L1 PATHS TO ABSOLUTE")
    print("="*70)
    print()
    
    # Default: search_term_results directory - now in OneDrive
    search_term_results_dir = Path("/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/search_term_results")
    
    # Find newest RIS file
    default_ris_file = find_newest_ris_file(search_term_results_dir)
    
    if default_ris_file:
        print(f"Default RIS file (newest in search_term_results):")
        print(f"  {default_ris_file}")
        print()
        
        use_default = input("Use default RIS file? (y/n): ").strip().lower()
        if use_default == 'y':
            input_ris_path = default_ris_file
        else:
            user_input = input("Enter path to RIS file: ").strip()
            if not user_input:
                print("ERROR: No file specified")
                return
            user_input = user_input.strip("'\"")
            input_ris_path = Path(user_input)
    else:
        print("No default RIS file found in search_term_results")
        user_input = input("Enter path to RIS file: ").strip()
        if not user_input:
            print("ERROR: No file specified")
            return
        user_input = user_input.strip("'\"")
        input_ris_path = Path(user_input)
    
    if not input_ris_path.exists():
        print(f"ERROR: RIS file not found: {input_ris_path}")
        return
    
    print()
    print(f"Processing: {input_ris_path}")
    print()
    
    # Convert paths
    output_ris_path = convert_ris_to_absolute_paths(input_ris_path)
    
    print()
    print("="*70)
    print("COMPLETE")
    print("="*70)
    print(f"  Input:  {input_ris_path.name}")
    print(f"  Output: {output_ris_path.name}")
    print(f"  Location: {output_ris_path.parent}")
    print()
    print("Next steps:")
    print("  1. Open EndNote")
    print("  2. Go to File > Import > File...")
    print(f"  3. Select: {output_ris_path.name}")
    print("  4. Set Import Option to: Reference Manager (RIS)")
    print("  5. Click Import")
    print("  6. Attachments should now work with absolute paths")
    print("="*70)


if __name__ == '__main__':
    main()














