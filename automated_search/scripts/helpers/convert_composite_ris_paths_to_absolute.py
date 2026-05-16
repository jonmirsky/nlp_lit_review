#!/usr/bin/env python3
"""
Convert L1 (file attachment) paths in composite RIS file from relative to absolute.

This script reads a composite RIS file and converts relative L1 paths to absolute paths.
Since a composite RIS file may contain entries from multiple source RIS files in different
subdirectories, this script searches for the actual files and uses their absolute paths.

Usage:
    python convert_composite_ris_paths_to_absolute.py [input_ris_file] [base_search_dir]
    
If no input file is provided, script will prompt for it.
If no base_search_dir is provided, uses the parent directory of the RIS file.

Inputs:
- Composite RIS file containing relative L1/L2/L3/L4 attachment paths.
- Optional base_search_dir containing the attachment files referenced by those paths.

Outputs:
- New RIS files next to the input RIS file with absolute path/full-text suffixes.
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional, List


REPO_ROOT = Path(__file__).resolve().parents[2]


def get_default_base_dir() -> Path:
    """Return the default composite RIS directory without hardcoding the repository path."""
    env_dir = os.environ.get("COMPOSITE_RIS_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return REPO_ROOT / "find_pubmed_full_texts" / "zotero_pass" / "pubmed_prompt_engineering_queries_1_15_25"


def find_file_in_directory(file_path: Path, search_dir: Path) -> Optional[Path]:
    """
    Search for a file in a directory structure.
    
    Since composite RIS files come from subdirectories, relative paths like
    "files/18363/..." should be resolved relative to those subdirectories.
    
    Args:
        file_path: Path object (relative path like "files/18363/file.pdf")
        search_dir: Base directory containing subdirectories
    
    Returns:
        Absolute path to the file if found, None otherwise
    """
    if not search_dir.exists():
        return None
    
    # First, try to resolve as relative path directly from search_dir
    resolved_path = (search_dir / file_path).resolve()
    if resolved_path.exists() and resolved_path.is_file():
        return resolved_path
    
    # If path starts with "files/", try resolving from subdirectories
    # The structure is: subdirectory/files/18363/file.pdf
    if file_path.parts and file_path.parts[0] == 'files':
        # Find all "files" directories in subdirectories
        for item in search_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Try resolving from this subdirectory
                subdir_resolved = (item / file_path).resolve()
                if subdir_resolved.exists() and subdir_resolved.is_file():
                    return subdir_resolved
        
        # Also try finding "files" directories more directly
        for files_dir in search_dir.rglob('files'):
            if files_dir.is_dir():
                # Try resolving the relative path from this files directory's parent
                # file_path is like "files/18363/file.pdf", so we need the parent
                parent_dir = files_dir.parent
                parent_resolved = (parent_dir / file_path).resolve()
                if parent_resolved.exists() and parent_resolved.is_file():
                    return parent_resolved
    
    return None


def wrap_long_ris_line(line: str, max_length: int = 1000) -> List[str]:
    """
    Wrap a long RIS line into multiple continuation lines.
    
    RIS format allows continuation lines by having content without a tag.
    Long lines are wrapped at max_length characters to prevent EndNote crashes.
    
    Args:
        line: RIS line to wrap (e.g., "AB  - long abstract text...")
        max_length: Maximum line length before wrapping (default 1000)
    
    Returns:
        List of lines (first has tag, subsequent are continuation lines)
    """
    line_stripped = line.rstrip()
    
    # Check if this is a RIS tag line (2 letters, 2 spaces, hyphen)
    tag_match = re.match(r'^([A-Z]{2})\s+-\s+(.+)$', line_stripped)
    if not tag_match:
        # Not a tagged line, return as is
        return [line]
    
    tag = tag_match.group(1)
    value = tag_match.group(2)
    
    # If line is short enough, return as is
    if len(line_stripped) <= max_length:
        return [line]
    
    # Split into multiple lines
    wrapped_lines = []
    # First line with tag
    wrapped_lines.append(f'{tag}  - {value[:max_length-6]}\n')
    
    # Continue with remaining content (without tag)
    remaining = value[max_length-6:]
    while remaining:
        if len(remaining) <= max_length:
            wrapped_lines.append(f'{remaining}\n')
            break
        else:
            # Wrap at word boundary if possible (within reasonable range)
            wrap_pos = max_length
            # Try to find a space within last 100 chars
            last_space = remaining.rfind(' ', max_length - 100, max_length)
            if last_space > max_length - 200:
                wrap_pos = last_space + 1
            wrapped_lines.append(f'{remaining[:wrap_pos]}\n')
            remaining = remaining[wrap_pos:]
    
    return wrapped_lines


def convert_ris_to_absolute_paths(input_ris_path: Path, base_search_dir: Optional[Path] = None, wrap_long_lines: bool = True, remove_attachments: bool = False) -> tuple[Path, Optional[Path], Optional[Path]]:
    """
    Convert relative L1 paths in a RIS file to absolute paths.
    
    Args:
        input_ris_path: Path to the input RIS file
        base_search_dir: Base directory to search for files. If None, uses input_ris_path.parent
    
    Returns:
        Path to the output RIS file
    """
    if not input_ris_path.exists():
        raise FileNotFoundError(f"RIS file not found: {input_ris_path}")
    
    # Determine base search directory
    if base_search_dir is None:
        base_search_dir = input_ris_path.parent
    else:
        base_search_dir = Path(base_search_dir).resolve()
    
    # Read the RIS file
    with open(input_ris_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    converted_count = 0
    already_absolute_count = 0
    not_found_count = 0
    wrapped_count = 0
    
    output_lines = []
    no_full_text_lines = []
    only_full_text_lines = []
    
    # Track current entry for detecting entries with/without full text
    current_entry_start_idx = 0
    current_entry_has_full_text = False
    entry_has_valid_path = False
    
    for line in lines:
        line_stripped = line.rstrip()
        
        # Check if this is an L1 field (file attachment)
        # RIS format: L1  - path
        if re.match(r'^(L[1-4])\s+-', line_stripped):
            # If removing attachments, skip this line
            if remove_attachments:
                continue
            tag_match = re.match(r'^(L[1-4])\s+-\s+(.+)$', line_stripped)
            if tag_match:
                tag = tag_match.group(1)
                path_value = tag_match.group(2).strip()
                
                # Track that this entry has an L1 field
                current_entry_has_full_text = True
                
                # Check if path is already absolute or is a URL
                if path_value.startswith('/') or path_value.startswith('http://') or path_value.startswith('https://'):
                    # Already absolute or URL - check if file exists
                    if path_value.startswith('/'):
                        abs_path = Path(path_value)
                        entry_has_valid_path = abs_path.exists() and abs_path.is_file()
                    else:
                        # URL - consider valid
                        entry_has_valid_path = True
                    already_absolute_count += 1
                    output_lines.append(line)
                else:
                    # Relative path - need to find the actual file
                    relative_path = Path(path_value)
                    absolute_path = find_file_in_directory(relative_path, base_search_dir)
                    
                    if absolute_path and absolute_path.exists():
                        # File found - use absolute path
                        entry_has_valid_path = True
                        new_line = f'{tag}  - {absolute_path}\n'
                        # Wrap if needed (L1 lines can be very long with absolute paths)
                        if wrap_long_lines and len(new_line) > 1000:
                            wrapped = wrap_long_ris_line(new_line)
                            output_lines.extend(wrapped)
                            if len(wrapped) > 1:
                                wrapped_count += 1
                        else:
                            output_lines.append(new_line)
                        converted_count += 1
                    else:
                        # File not found - try resolving relative to input file's directory
                        try_resolve = (input_ris_path.parent / relative_path).resolve()
                        if try_resolve.exists():
                            # File found - use resolved path
                            entry_has_valid_path = True
                            new_line = f'{tag}  - {try_resolve}\n'
                            # Wrap if needed
                            if wrap_long_lines and len(new_line) > 1000:
                                wrapped = wrap_long_ris_line(new_line)
                                output_lines.extend(wrapped)
                                if len(wrapped) > 1:
                                    wrapped_count += 1
                            else:
                                output_lines.append(new_line)
                            converted_count += 1
                        else:
                            # Still not found - keep original but warn
                            print(f"  WARNING: File not found: {path_value}")
                            # Wrap if long even if not found (might help EndNote)
                            if wrap_long_lines and len(line) > 1000:
                                wrapped = wrap_long_ris_line(line)
                                output_lines.extend(wrapped)
                                if len(wrapped) > 1:
                                    wrapped_count += 1
                            else:
                                output_lines.append(line)
                            # File not found - mark entry as having no valid path
                            entry_has_valid_path = False
                            not_found_count += 1
            else:
                # Malformed L1-L4 line, but still try to wrap if long
                if wrap_long_lines and len(line_stripped) > 1000:
                    wrapped = wrap_long_ris_line(line)
                    output_lines.extend(wrapped)
                    if len(wrapped) > 1:
                        wrapped_count += 1
                else:
                    output_lines.append(line)
        else:
            # Check if this is a RIS tag line (for wrapping long AB fields, etc.)
            if re.match(r'^[A-Z]{2}\s+-', line_stripped):
                # This is a tagged line - wrap if long
                if wrap_long_lines and len(line_stripped) > 1000:
                    wrapped = wrap_long_ris_line(line)
                    output_lines.extend(wrapped)
                    if len(wrapped) > 1:
                        wrapped_count += 1
                else:
                    output_lines.append(line)
            else:
                # Continuation line or empty line - keep as is (continuation lines are usually short)
                output_lines.append(line)
        
        # Check if this is the end of an entry (ER line)
        if line_stripped == 'ER  -' or line_stripped == 'ER -':
            # Ensure ER line is in output
            if not output_lines or output_lines[-1] != line:
                output_lines.append(line)
            
            # Entry is complete - check if it should go in no_full_text or only_full_text file
            entry_end_idx = len(output_lines)
            entry_lines = output_lines[current_entry_start_idx:entry_end_idx]
            
            # Entry goes in no_full_text if it has no L1 field OR the path is invalid
            if not current_entry_has_full_text or not entry_has_valid_path:
                no_full_text_lines.extend(entry_lines)
            else:
                # Entry has valid full text - goes in only_full_text
                only_full_text_lines.extend(entry_lines)
            
            # Reset for next entry
            current_entry_start_idx = len(output_lines)
            current_entry_has_full_text = False
            entry_has_valid_path = False
    
    # Determine output paths
    if remove_attachments:
        output_ris_path = input_ris_path.parent / f"{input_ris_path.stem}_no_attachments{input_ris_path.suffix}"
    else:
        output_ris_path = input_ris_path.parent / f"{input_ris_path.stem}_absolute_paths{input_ris_path.suffix}"
    
    # Write the main output file (all entries with absolute paths)
    with open(output_ris_path, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)
    
    # Write the no_full_text file (only entries without valid full text)
    no_full_text_path = None
    if no_full_text_lines:
        no_full_text_path = input_ris_path.parent / f"{input_ris_path.stem}_no_full_text{input_ris_path.suffix}"
        with open(no_full_text_path, 'w', encoding='utf-8') as f:
            f.writelines(no_full_text_lines)
    
    # Write the only_full_text file (only entries with valid full text)
    only_full_text_path = None
    if only_full_text_lines:
        only_full_text_path = input_ris_path.parent / f"{input_ris_path.stem}_only_full_text{input_ris_path.suffix}"
        with open(only_full_text_path, 'w', encoding='utf-8') as f:
            f.writelines(only_full_text_lines)
    
    if remove_attachments:
        print(f"  Removed all L1/L2/L3/L4 attachment fields (for testing)")
    else:
        print(f"  Converted {converted_count} relative L1/L2/L3/L4 paths to absolute")
    if already_absolute_count > 0:
        print(f"  {already_absolute_count} paths were already absolute or URLs")
    if not_found_count > 0:
        print(f"  {not_found_count} files could not be found (kept as relative)")
    if wrap_long_lines and wrapped_count > 0:
        print(f"  Wrapped {wrapped_count} long lines (to prevent EndNote crashes)")
    
    if no_full_text_path:
        no_full_text_count = len([l for l in no_full_text_lines if l.strip() == 'ER  -' or l.strip() == 'ER -'])
        print(f"  Created no_full_text file: {no_full_text_count} entries without valid full text paths")
    
    if only_full_text_path:
        only_full_text_count = len([l for l in only_full_text_lines if l.strip() == 'ER  -' or l.strip() == 'ER -'])
        print(f"  Created only_full_text file: {only_full_text_count} entries with valid full text paths")
    
    return output_ris_path, no_full_text_path, only_full_text_path


def main():
    """Main execution function."""
    print("="*70)
    print("CONVERT COMPOSITE RIS L1 PATHS TO ABSOLUTE")
    print("="*70)
    print()
    
    # Default composite RIS file
    # Try original composite first, then fallback to _absolute_paths version
    base_dir = get_default_base_dir()
    default_ris_file = base_dir / "pubmed_prompt_engineering_queries_1_15_25_composite.ris"
    # If original doesn't exist, try the _absolute_paths version
    if not default_ris_file.exists():
        default_ris_file = base_dir / "pubmed_prompt_engineering_queries_1_15_25_composite_absolute_paths.ris"
    
    # Get input RIS file
    if len(sys.argv) > 1:
        input_ris_path = Path(sys.argv[1])
    elif default_ris_file.exists():
        print(f"Default composite RIS file:")
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
        print("No default RIS file found")
        user_input = input("Enter path to RIS file: ").strip()
        if not user_input:
            print("ERROR: No file specified")
            return
        user_input = user_input.strip("'\"")
        input_ris_path = Path(user_input)
    
    if not input_ris_path.exists():
        print(f"ERROR: RIS file not found: {input_ris_path}")
        return
    
    # Get base search directory (where to search for files)
    if len(sys.argv) > 2:
        base_search_dir = Path(sys.argv[2])
    else:
        # Default: parent directory of RIS file (e.g., pubmed_prompt_engineering_queries_1_15_25)
        base_search_dir = input_ris_path.parent
    
    print()
    print(f"Input RIS file: {input_ris_path.name}")
    print(f"  Location: {input_ris_path}")
    print(f"Search directory: {base_search_dir}")
    print()
    
    # Convert paths
    output_ris_path, no_full_text_path, only_full_text_path = convert_ris_to_absolute_paths(input_ris_path, base_search_dir)
    
    print()
    print("="*70)
    print("COMPLETE")
    print("="*70)
    print(f"  Input:  {input_ris_path.name}")
    print(f"  Output: {output_ris_path.name}")
    print(f"  Location: {output_ris_path.parent}")
    if no_full_text_path:
        print(f"  No Full Text: {no_full_text_path.name}")
    if only_full_text_path:
        print(f"  Only Full Text: {only_full_text_path.name}")
    print("="*70)


if __name__ == '__main__':
    main()
