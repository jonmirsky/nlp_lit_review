#!/usr/bin/env python3
"""
Analyze failed papers to identify publisher/journal trends.

This script parses missing_after_second_scrape.txt and counts papers by publisher/journal.
"""

import re
from pathlib import Path
from collections import Counter
from typing import Dict, List, Optional


def extract_publisher_info(entry: str) -> Dict[str, Optional[str]]:
    """
    Extract publisher, journal, and URL information from a RIS entry.
    Returns a dict with 'publisher', 'journal', 'url', 'doi' keys.
    """
    publisher = None
    journal = None
    url = None
    doi = None
    
    lines = entry.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('PB  - '):
            publisher = line[6:].strip()
        elif line.startswith('T2  - '):
            journal = line[6:].strip()
        elif line.startswith('UR  - '):
            url = line[6:].strip()
        elif line.startswith('DO  - '):
            doi = line[6:].strip()
    
    return {
        'publisher': publisher,
        'journal': journal,
        'url': url,
        'doi': doi
    }


def identify_publisher_from_url(url: str) -> Optional[str]:
    """Identify publisher from URL patterns."""
    if not url:
        return None
    
    url_lower = url.lower()
    
    # Major publishers
    if 'elsevier' in url_lower or 'sciencedirect' in url_lower:
        return 'Elsevier'
    elif 'nature.com' in url_lower or 'springernature' in url_lower:
        return 'Nature/Springer Nature'
    elif 'springer.com' in url_lower or 'springerlink' in url_lower:
        return 'Springer'
    elif 'wiley.com' in url_lower or 'onlinelibrary.wiley' in url_lower:
        return 'Wiley'
    elif 'jama' in url_lower or 'jamanetwork' in url_lower:
        return 'JAMA'
    elif 'nejm.org' in url_lower:
        return 'New England Journal of Medicine'
    elif 'bmj.com' in url_lower:
        return 'BMJ'
    elif 'thelancet.com' in url_lower:
        return 'Lancet'
    elif 'ieee.org' in url_lower or 'ieeexplore' in url_lower:
        return 'IEEE'
    elif 'acm.org' in url_lower:
        return 'ACM'
    elif 'pubmed' in url_lower or 'ncbi.nlm.nih' in url_lower:
        return 'PubMed/NCBI'
    elif 'plos.org' in url_lower or 'plosone' in url_lower:
        return 'PLOS'
    elif 'frontiersin.org' in url_lower:
        return 'Frontiers'
    elif 'hindawi.com' in url_lower:
        return 'Hindawi'
    elif 'tandfonline.com' in url_lower or 'taylorandfrancis' in url_lower:
        return 'Taylor & Francis'
    elif 'sagepub.com' in url_lower or 'sage' in url_lower:
        return 'SAGE'
    elif 'oup.com' in url_lower or 'oxfordjournals' in url_lower:
        return 'Oxford University Press'
    elif 'cambridge.org' in url_lower:
        return 'Cambridge University Press'
    elif 'journals.asm.org' in url_lower:
        return 'American Society for Microbiology'
    elif 'ahajournals.org' in url_lower:
        return 'American Heart Association'
    elif 'aacrjournals.org' in url_lower:
        return 'American Association for Cancer Research'
    elif 'ascopubs.org' in url_lower:
        return 'American Society of Clinical Oncology'
    elif 'ashpublications.org' in url_lower:
        return 'American Society of Hematology'
    elif 'cell.com' in url_lower:
        return 'Cell Press'
    elif 'science.org' in url_lower or 'sciencemag.org' in url_lower:
        return 'Science'
    elif 'pnas.org' in url_lower:
        return 'PNAS'
    elif 'biomedcentral.com' in url_lower or 'bmc' in url_lower:
        return 'BioMed Central'
    elif 'mdpi.com' in url_lower:
        return 'MDPI'
    elif 'journals.lww.com' in url_lower:
        return 'Lippincott Williams & Wilkins'
    elif 'onlinelibrary.wiley' in url_lower:
        return 'Wiley'
    
    return None


def identify_publisher_from_doi(doi: str) -> Optional[str]:
    """Identify publisher from DOI prefix patterns."""
    if not doi:
        return None
    
    doi_lower = doi.lower()
    
    # Common DOI prefixes by publisher
    if '10.1016' in doi_lower or '10.1017' in doi_lower:
        return 'Elsevier'
    elif '10.1038' in doi_lower or '10.1039' in doi_lower:
        return 'Nature/Springer Nature'
    elif '10.1007' in doi_lower or '10.1002' in doi_lower:
        return 'Springer/Wiley'
    elif '10.1001' in doi_lower:
        return 'JAMA'
    elif '10.1056' in doi_lower:
        return 'New England Journal of Medicine'
    elif '10.1136' in doi_lower:
        return 'BMJ'
    elif '10.1016/s0140' in doi_lower:
        return 'Lancet'
    elif '10.1109' in doi_lower or '10.1103' in doi_lower:
        return 'IEEE'
    elif '10.1145' in doi_lower:
        return 'ACM'
    elif '10.1371' in doi_lower:
        return 'PLOS'
    elif '10.3389' in doi_lower:
        return 'Frontiers'
    elif '10.1080' in doi_lower or '10.1081' in doi_lower:
        return 'Taylor & Francis'
    elif '10.1177' in doi_lower:
        return 'SAGE'
    elif '10.1093' in doi_lower:
        return 'Oxford University Press'
    elif '10.1128' in doi_lower:
        return 'American Society for Microbiology'
    elif '10.1161' in doi_lower:
        return 'American Heart Association'
    elif '10.1158' in doi_lower:
        return 'American Association for Cancer Research'
    elif '10.1200' in doi_lower:
        return 'American Society of Clinical Oncology'
    elif '10.1182' in doi_lower:
        return 'American Society of Hematology'
    elif '10.1016/j.cell' in doi_lower:
        return 'Cell Press'
    elif '10.1126' in doi_lower:
        return 'Science'
    elif '10.1073' in doi_lower:
        return 'PNAS'
    elif '10.1186' in doi_lower:
        return 'BioMed Central'
    elif '10.3390' in doi_lower:
        return 'MDPI'
    
    return None


def normalize_publisher_name(publisher: str) -> str:
    """Normalize publisher names to common formats."""
    if not publisher:
        return "Unknown"
    
    publisher_lower = publisher.lower()
    
    # Normalize common variations
    if 'elsevier' in publisher_lower:
        return 'Elsevier'
    elif 'nature' in publisher_lower or 'springer nature' in publisher_lower:
        return 'Nature/Springer Nature'
    elif 'springer' in publisher_lower:
        return 'Springer'
    elif 'wiley' in publisher_lower:
        return 'Wiley'
    elif 'jama' in publisher_lower:
        return 'JAMA'
    elif 'nejm' in publisher_lower or 'new england' in publisher_lower:
        return 'New England Journal of Medicine'
    elif 'bmj' in publisher_lower:
        return 'BMJ'
    elif 'lancet' in publisher_lower:
        return 'Lancet'
    elif 'ieee' in publisher_lower:
        return 'IEEE'
    elif 'acm' in publisher_lower:
        return 'ACM'
    elif 'taylor' in publisher_lower or 'francis' in publisher_lower:
        return 'Taylor & Francis'
    elif 'sage' in publisher_lower:
        return 'SAGE'
    elif 'oxford' in publisher_lower:
        return 'Oxford University Press'
    elif 'cambridge' in publisher_lower:
        return 'Cambridge University Press'
    elif 'cell' in publisher_lower and 'press' in publisher_lower:
        return 'Cell Press'
    elif 'science' in publisher_lower:
        return 'Science'
    elif 'pnas' in publisher_lower:
        return 'PNAS'
    elif 'biomed central' in publisher_lower or 'bmc' in publisher_lower:
        return 'BioMed Central'
    elif 'mdpi' in publisher_lower:
        return 'MDPI'
    elif 'lippincott' in publisher_lower:
        return 'Lippincott Williams & Wilkins'
    
    return publisher  # Return as-is if no match


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent
    ris_file = base_dir / "missing_papers" / "still_missing" / "missing_after_second_scrape.txt"
    
    if not ris_file.exists():
        print(f"ERROR: RIS file not found: {ris_file}")
        return
    
    print("="*70)
    print("ANALYZING FAILED PAPERS BY PUBLISHER/JOURNAL")
    print("="*70)
    print()
    
    # Read and parse RIS file
    with open(ris_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    print(f"Found {len(entries)} references in RIS file")
    print()
    
    # Count by publisher
    publisher_counts = Counter()
    journal_counts = Counter()
    url_publisher_counts = Counter()
    doi_publisher_counts = Counter()
    final_publisher_counts = Counter()
    
    unknown_count = 0
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        info = extract_publisher_info(entry)
        
        # Try to identify publisher from multiple sources
        identified_publisher = None
        
        # Priority 1: URL
        if info['url']:
            identified_publisher = identify_publisher_from_url(info['url'])
            if identified_publisher:
                url_publisher_counts[identified_publisher] += 1
        
        # Priority 2: DOI
        if not identified_publisher and info['doi']:
            identified_publisher = identify_publisher_from_doi(info['doi'])
            if identified_publisher:
                doi_publisher_counts[identified_publisher] += 1
        
        # Priority 3: Publisher field
        if not identified_publisher and info['publisher']:
            identified_publisher = normalize_publisher_name(info['publisher'])
            publisher_counts[identified_publisher] += 1
        
        # Final assignment
        if identified_publisher:
            final_publisher_counts[identified_publisher] += 1
        else:
            final_publisher_counts["Unknown"] += 1
            unknown_count += 1
        
        # Also count journals
        if info['journal']:
            journal_counts[info['journal']] += 1
    
    # Print results
    print("="*70)
    print("PUBLISHER BREAKDOWN (by final identification)")
    print("="*70)
    print()
    
    # Sort by count, descending
    sorted_publishers = sorted(final_publisher_counts.items(), key=lambda x: x[1], reverse=True)
    
    for publisher, count in sorted_publishers:
        percentage = (count / len(entries)) * 100
        print(f"{publisher:40s}: {count:4d} papers ({percentage:5.1f}%)")
    
    print()
    print("="*70)
    print("TOP 20 JOURNALS")
    print("="*70)
    print()
    
    sorted_journals = sorted(journal_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    
    for journal, count in sorted_journals:
        percentage = (count / len(entries)) * 100
        print(f"{journal:60s}: {count:4d} papers ({percentage:5.1f}%)")
    
    print()
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total references analyzed: {len(entries)}")
    print(f"Publishers identified: {len(final_publisher_counts)}")
    print(f"Unknown publishers: {unknown_count}")
    print(f"Journals found: {len(journal_counts)}")
    print("="*70)


if __name__ == "__main__":
    main()
