#!/usr/bin/env python3
"""
Filter RIS file to exclude papers from specific publishers.

Excludes papers from:
- Springer
- Taylor & Francis
- IEEE
- BMJ
- Wiley
- JAMA Network
"""

import re
from pathlib import Path
from typing import Optional, Dict, List
from collections import Counter


def extract_publisher_from_url_or_doi(url: Optional[str], doi: Optional[str], journal: Optional[str]) -> Optional[str]:
    """Extract publisher name from URL, DOI, or journal."""
    if url:
        url_lower = url.lower()
        # Publisher patterns in URLs
        if 'sciencedirect.com' in url_lower or 'elsevier.com' in url_lower:
            return 'Elsevier'
        elif 'springer.com' in url_lower or 'link.springer.com' in url_lower:
            return 'Springer'
        elif 'wiley.com' in url_lower or 'onlinelibrary.wiley.com' in url_lower:
            return 'Wiley'
        elif 'ieeexplore.ieee.org' in url_lower:
            return 'IEEE'
        elif 'nature.com' in url_lower:
            return 'Nature Publishing'
        elif 'bmj.com' in url_lower:
            return 'BMJ'
        elif 'tandfonline.com' in url_lower:
            return 'Taylor & Francis'
        elif 'jamanetwork.com' in url_lower:
            return 'JAMA Network'
        elif 'journals.sagepub.com' in url_lower or 'sagepub.com' in url_lower:
            return 'Sage Publications'
        elif 'oup.com' in url_lower or 'academic.oup.com' in url_lower:
            return 'Oxford University Press'
        elif 'cambridge.org' in url_lower:
            return 'Cambridge University Press'
        elif 'pmc.ncbi.nlm.nih.gov' in url_lower or 'pubmed.ncbi.nlm.nih.gov' in url_lower:
            return 'PubMed/PMC'
        elif 'journals.lww.com' in url_lower:
            return 'Lippincott Williams & Wilkins'
        elif 'liebertpub.com' in url_lower:
            return 'Mary Ann Liebert'
        elif 'acm.org' in url_lower:
            return 'ACM'
        elif 'rsna.org' in url_lower or 'pubs.rsna.org' in url_lower:
            return 'Radiological Society of North America'
    
    if doi:
        doi_lower = doi.lower()
        # Clean up DOI (remove "doi:" prefix if present, handle URLs)
        doi_clean = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi_lower, flags=re.IGNORECASE)
        doi_clean = re.sub(r'^doi:', '', doi_clean, flags=re.IGNORECASE)
        doi_clean = doi_clean.strip()
        
        # DOI prefixes indicate publishers
        if doi_clean.startswith('10.1016'):
            return 'Elsevier'
        elif doi_clean.startswith('10.1007'):
            return 'Springer'
        elif doi_clean.startswith('10.1002') or doi_clean.startswith('10.1111'):
            return 'Wiley'
        elif doi_clean.startswith('10.1109'):
            return 'IEEE'
        elif doi_clean.startswith('10.1038'):
            return 'Nature Publishing'
        elif doi_clean.startswith('10.1136'):
            return 'BMJ'
        elif doi_clean.startswith('10.1080') or doi_clean.startswith('10.1177'):
            return 'Taylor & Francis'
        elif doi_clean.startswith('10.1001'):
            return 'JAMA Network'
        elif doi_clean.startswith('10.1093'):
            return 'Oxford University Press'
        elif doi_clean.startswith('10.1017'):
            return 'Cambridge University Press'
        elif doi_clean.startswith('10.1148') or doi_clean.startswith('10.2214'):
            return 'Radiological Society of North America'
        elif doi_clean.startswith('10.1089'):
            return 'Mary Ann Liebert'
        elif doi_clean.startswith('10.3233'):
            return 'IOS Press'
        elif doi_clean.startswith('10.2196'):
            return 'JMIR Publications'
    
    # Try to infer from journal name
    if journal:
        journal_lower = journal.lower()
        if 'jama' in journal_lower:
            return 'JAMA Network'
        elif 'radiology' in journal_lower and 'rsna' not in journal_lower:
            return 'Radiological Society of North America'
        elif 'ieee' in journal_lower:
            return 'IEEE'
        elif 'nature' in journal_lower:
            return 'Nature Publishing'
    
    return None


def extract_publisher_from_entry(entry_text: str) -> Optional[str]:
    """Extract publisher from a single RIS entry."""
    url = None
    doi = None
    journal = None
    
    lines = entry_text.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('UR  - '):
            url = line[6:].strip()
        elif line.startswith('DO  - '):
            doi = line[6:].strip()
        elif line.startswith('T2  - '):
            journal = line[6:].strip()
    
    return extract_publisher_from_url_or_doi(url, doi, journal)


def should_exclude_publisher(publisher: Optional[str]) -> bool:
    """Check if publisher should be excluded."""
    if not publisher:
        return False
    
    publisher_lower = publisher.lower()
    
    # Publishers to exclude
    exclude_publishers = [
        'springer',
        'taylor & francis',
        'taylor and francis',
        'ieee',
        'bmj',
        'wiley',
        'jama network',
        'jama'
    ]
    
    for exclude_pub in exclude_publishers:
        if exclude_pub in publisher_lower:
            return True
    
    return False


def filter_ris_file(input_path: Path, output_path: Path) -> Dict[str, int]:
    """Filter RIS file by excluding specified publishers."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # Read input file
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split entries by ER  -  markers
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    # Filter entries
    filtered_entries = []
    excluded_entries = []
    excluded_by_publisher = Counter()
    unknown_publisher_count = 0
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        # Extract publisher
        publisher = extract_publisher_from_entry(entry)
        
        if should_exclude_publisher(publisher):
            excluded_entries.append(entry)
            if publisher:
                excluded_by_publisher[publisher] += 1
            else:
                unknown_publisher_count += 1
        else:
            # Include this entry
            filtered_entries.append(entry)
    
    # Write filtered RIS file
    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in filtered_entries:
            f.write(entry)
            f.write('\nER  - \n')
    
    # Calculate statistics
    total_entries = len(filtered_entries) + len(excluded_entries)
    excluded_count = len(excluded_entries)
    remaining_count = len(filtered_entries)
    
    stats = {
        'total': total_entries,
        'excluded': excluded_count,
        'remaining': remaining_count,
        'excluded_by_publisher': dict(excluded_by_publisher),
        'unknown_publisher_excluded': unknown_publisher_count
    }
    
    return stats


def main():
    """Main execution function."""
    input_file = Path('missing_papers/still_missing/379_missing_texts.txt')
    output_file = Path('missing_papers/still_missing/379_missing_texts_filtered.txt')
    
    print("="*60)
    print("RIS File Publisher Filter")
    print("="*60)
    print(f"\nInput file: {input_file}")
    print(f"Output file: {output_file}")
    print("\nExcluding papers from:")
    print("  - Springer")
    print("  - Taylor & Francis")
    print("  - IEEE")
    print("  - BMJ")
    print("  - Wiley")
    print("  - JAMA Network")
    print()
    
    try:
        stats = filter_ris_file(input_file, output_file)
        
        print("="*60)
        print("FILTERING COMPLETE")
        print("="*60)
        print(f"\nTotal entries in original file: {stats['total']}")
        print(f"Entries excluded: {stats['excluded']}")
        print(f"Entries remaining: {stats['remaining']}")
        print(f"\nExcluded entries by publisher:")
        
        if stats['excluded_by_publisher']:
            for publisher, count in sorted(stats['excluded_by_publisher'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {publisher}: {count}")
        
        if stats['unknown_publisher_excluded'] > 0:
            print(f"\nNote: {stats['unknown_publisher_excluded']} entries were excluded but publisher could not be determined")
        
        print(f"\nFiltered RIS file saved to: {output_file}")
        print("="*60)
        
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
