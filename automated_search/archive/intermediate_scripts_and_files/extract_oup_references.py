#!/usr/bin/env python3
"""
Extract OUP references from a RIS file.
Creates a new RIS file containing only references with OUP URLs.
"""

import re
from pathlib import Path


def is_oup_url(url: str) -> bool:
    """Check if URL is an Oxford University Press (OUP) URL."""
    if not url:
        return False
    url_lower = url.lower()
    return 'academic.oup.com' in url_lower or 'oup.com' in url_lower


def extract_oup_references(input_file: Path, output_file: Path):
    """Extract only OUP references from input RIS file and write to output file."""
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split entries by ER  - 
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    oup_entries = []
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        # Check if this entry has an OUP URL
        lines = entry.split('\n')
        has_oup_url = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('UR  - '):
                url = line[6:].strip()
                if is_oup_url(url):
                    has_oup_url = True
                    break
        
        if has_oup_url:
            # Add the ER  - terminator back
            oup_entries.append(entry + '\nER  - \n')
    
    # Write to output file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(''.join(oup_entries))
    
    print(f"Extracted {len(oup_entries)} OUP references from {input_file.name}")
    print(f"Saved to: {output_file}")


def main():
    """Main execution function."""
    input_file = Path("missing_papers/still_missing/379_missing_texts_filtered.txt")
    output_file = Path("missing_papers/still_missing/379_missing_texts_filtered_oup_only.txt")
    
    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        return
    
    extract_oup_references(input_file, output_file)


if __name__ == '__main__':
    main()
