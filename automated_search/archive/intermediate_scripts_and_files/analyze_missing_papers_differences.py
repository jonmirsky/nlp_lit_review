#!/usr/bin/env python3
"""
Comprehensive analysis of differences between original 1033 missing papers 
and remaining 379 missing papers.

Identifies:
- Paywalled papers (quick categorization)
- Papers with unknown/technical failure reasons (focus area)
- Patterns in missing papers
- Potentially fixable issues
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, Counter


def parse_ris_file(filepath: str) -> List[Dict[str, str]]:
    """Parse RIS file into list of reference dictionaries, including label_id."""
    references = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
            
        pmid = None
        title = None
        pmc_id = None
        doi = None
        record_number = None  # EndNote Record Number from ID field
        label_id = None  # LB field - label ID used in mapping files
        url = None  # UR field - direct URL to paper
        pii = None  # PII identifier extracted from ScienceDirect URLs
        journal = None  # T2 field - journal name
        issn = None  # SN field - ISSN
        publisher = None  # PB field - publisher
        start_page = None  # SP field
        end_page = None  # EP field
        volume = None  # VL field
        year = None  # PY field
        first_author = None  # AU field - first author
        
        lines = entry.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('AN  - '):
                pmid = line[6:].strip()
            elif line.startswith('TI  - '):
                title = line[6:].strip()
            elif line.startswith('C2  - '):
                pmc_text = line[6:].strip()
                pmc_match = re.search(r'PMC?(\d+)', pmc_text, re.IGNORECASE)
                if pmc_match:
                    pmc_id = pmc_match.group(1)
            elif line.startswith('DO  - '):
                # DOI field in RIS format
                doi = line[6:].strip()
                # Clean up DOI (remove "doi:" prefix if present, handle URLs)
                doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
                doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
                doi = doi.strip()
            elif line.startswith('ID  - '):
                # EndNote Record Number
                record_number = line[6:].strip()
            elif line.startswith('LB  - '):
                # Label ID (used in mapping files)
                label_id = line[6:].strip()
            elif line.startswith('UR  - '):
                # URL field - direct link to paper
                url = line[6:].strip()
                # Extract PII from ScienceDirect URLs (e.g., /pii/S1532046424001345)
                if url and 'sciencedirect.com' in url.lower():
                    pii_match = re.search(r'/pii/([A-Z0-9]+)', url, re.IGNORECASE)
                    if pii_match:
                        pii = pii_match.group(1)
            elif line.startswith('T2  - '):
                # Secondary title (journal name)
                journal = line[6:].strip()
            elif line.startswith('SN  - '):
                # ISSN
                issn_text = line[6:].strip()
                # Extract first ISSN if multiple (format: "1234-5678 9876-5432")
                issn_match = re.search(r'(\d{4}[- ]?\d{3,4}[\dXx]?)', issn_text)
                if issn_match:
                    issn = issn_match.group(1).replace(' ', '-')
            elif line.startswith('PB  - '):
                # Publisher
                publisher = line[6:].strip()
            elif line.startswith('SP  - '):
                # Start page
                start_page = line[6:].strip()
            elif line.startswith('EP  - '):
                # End page
                end_page = line[6:].strip()
            elif line.startswith('VL  - '):
                # Volume
                volume = line[6:].strip()
            elif line.startswith('PY  - '):
                # Publication year
                year_text = line[6:].strip()
                # Extract year if it's a date string
                year_match = re.search(r'(\d{4})', year_text)
                if year_match:
                    year = year_match.group(1)
            elif line.startswith('AU  - ') and first_author is None:
                # First author (take first one)
                first_author = line[6:].strip()
        
        # Extract publisher from URL or DOI if not found in PB field
        if not publisher:
            publisher = extract_publisher_from_url_or_doi(url, doi, journal)
        
        # Accept if we have any identifier or metadata
        if pmid or doi or url or title:
            references.append({
                'pmid': pmid,
                'title': title or 'Unknown Title',
                'pmc_id': pmc_id,
                'doi': doi,
                'record_number': record_number,
                'label_id': label_id,
                'url': url,
                'pii': pii,
                'journal': journal,
                'issn': issn,
                'publisher': publisher or 'Unknown',
                'start_page': start_page,
                'end_page': end_page,
                'volume': volume,
                'year': year,
                'first_author': first_author,
                'ris_text': entry + '\nER  - \n'
            })
    
    return references


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
        # DOI prefixes indicate publishers
        if doi.startswith('10.1016'):
            return 'Elsevier'
        elif doi.startswith('10.1007'):
            return 'Springer'
        elif doi.startswith('10.1002') or doi.startswith('10.1111'):
            return 'Wiley'
        elif doi.startswith('10.1109') or doi.startswith('10.1109'):
            return 'IEEE'
        elif doi.startswith('10.1038'):
            return 'Nature Publishing'
        elif doi.startswith('10.1136'):
            return 'BMJ'
        elif doi.startswith('10.1080') or doi.startswith('10.1177'):
            return 'Taylor & Francis'
        elif doi.startswith('10.1177'):
            return 'Sage Publications'
        elif doi.startswith('10.1093'):
            return 'Oxford University Press'
        elif doi.startswith('10.1017'):
            return 'Cambridge University Press'
        elif doi.startswith('10.1148') or doi.startswith('10.2214'):
            return 'Radiological Society of North America'
        elif doi.startswith('10.1089'):
            return 'Mary Ann Liebert'
        elif doi.startswith('10.3233'):
            return 'IOS Press'
        elif doi.startswith('10.2196'):
            return 'JMIR Publications'
    
    # Try to infer from journal name
    if journal:
        journal_lower = journal.lower()
        if 'radiology' in journal_lower and 'rsna' not in journal_lower:
            return 'Radiological Society of North America'
        elif 'ieee' in journal_lower:
            return 'IEEE'
        elif 'nature' in journal_lower:
            return 'Nature Publishing'
    
    return None


def load_error_reasons(mapping_file: str) -> Dict[str, Dict[str, str]]:
    """
    Load error reasons from label_to_filename.txt.
    Returns dict mapping label_id to {status, error_reason, title}
    """
    error_map = {}
    
    if not Path(mapping_file).exists():
        print(f"Warning: Error mapping file not found: {mapping_file}")
        return error_map
    
    with open(mapping_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('|')
            if len(parts) >= 4:
                label_id = parts[0].strip()
                status = parts[3].strip() if len(parts) > 3 else ''
                error_reason = parts[4].strip() if len(parts) > 4 else ''
                title = parts[2].strip() if len(parts) > 2 else ''
                
                error_map[label_id] = {
                    'status': status,
                    'error_reason': error_reason,
                    'title': title
                }
    
    return error_map


def detect_paywall_indicators(paper: Dict[str, str]) -> bool:
    """
    Quick paywall detection based on publisher and URL patterns.
    Returns True if likely paywalled, False otherwise.
    """
    publisher = (paper.get('publisher') or '').lower()
    url = (paper.get('url') or '').lower()
    journal = (paper.get('journal') or '').lower()
    
    # Known paywall-heavy publishers (but some may have open access)
    paywall_publishers = [
        'elsevier', 'springer', 'wiley', 'taylor & francis', 'tandfonline',
        'sage', 'sage publications', 'oxford university press', 'oup',
        'cambridge university press', 'acm', 'ieee', 'nature publishing',
        'bmj', 'lancet', 'cell press', 'american medical association',
        'ama', 'radiological society', 'rsna'
    ]
    
    # Check publisher
    for paywall_pub in paywall_publishers:
        if paywall_pub in publisher:
            # But check for open access indicators
            if 'open access' in publisher or 'openaccess' in publisher:
                return False
            # Many Elsevier/Springer/Wiley papers are paywalled, but not all
            # We'll mark as "possibly paywalled" but not definitive
            return True
    
    # Check URL patterns
    paywall_url_patterns = [
        'subscription', 'paywall', 'purchase', 'buy article',
        'members only', 'society member'
    ]
    
    for pattern in paywall_url_patterns:
        if pattern in url:
            return True
    
    return False


def categorize_paper(paper: Dict[str, str], error_map: Dict[str, Dict[str, str]]) -> str:
    """
    Categorize paper failure reason.
    Returns: 'paywall', 'unknown', 'technical', 'no_identifier', or 'other'
    """
    label_id = paper.get('label_id')
    record_number = paper.get('record_number')
    
    # Check error map first
    error_info = None
    if label_id and label_id in error_map:
        error_info = error_map[label_id]
    elif record_number and record_number in error_map:
        error_info = error_map[record_number]
    
    if error_info:
        error_reason = error_info.get('error_reason', '').lower()
        status = error_info.get('status', '').lower()
        
        # If already successful, shouldn't be in missing list
        if status == 'success':
            return 'other'
        
        # Check error reason
        if 'paywall' in error_reason or 'subscription' in error_reason:
            return 'paywall'
        elif 'timeout' in error_reason:
            return 'technical'
        elif 'not found' in error_reason or '404' in error_reason:
            return 'technical'
        elif 'download failed' in error_reason:
            return 'technical'
        elif 'can\'t get file' in error_reason or "can't get file" in error_reason:
            return 'unknown'  # Generic failure - focus area
    
    # Check for paywall indicators
    if detect_paywall_indicators(paper):
        return 'paywall'
    
    # Check identifier completeness
    has_doi = bool(paper.get('doi'))
    has_url = bool(paper.get('url'))
    has_pmid = bool(paper.get('pmid'))
    has_pmc = bool(paper.get('pmc_id'))
    
    if not (has_doi or has_url or has_pmid or has_pmc):
        return 'no_identifier'
    
    # Has identifiers but unknown failure
    return 'unknown'


def analyze_identifiers(papers: List[Dict[str, str]]) -> Dict[str, int]:
    """Analyze identifier completeness across papers."""
    stats = {
        'total': len(papers),
        'with_doi': 0,
        'with_url': 0,
        'with_pmid': 0,
        'with_pmc': 0,
        'with_all': 0,
        'with_none': 0,
        'with_doi_and_url': 0,
        'with_doi_and_pmid': 0,
    }
    
    for paper in papers:
        has_doi = bool(paper.get('doi'))
        has_url = bool(paper.get('url'))
        has_pmid = bool(paper.get('pmid'))
        has_pmc = bool(paper.get('pmc_id'))
        
        if has_doi:
            stats['with_doi'] += 1
        if has_url:
            stats['with_url'] += 1
        if has_pmid:
            stats['with_pmid'] += 1
        if has_pmc:
            stats['with_pmc'] += 1
        
        if has_doi and has_url and has_pmid:
            stats['with_all'] += 1
        if has_doi and has_url:
            stats['with_doi_and_url'] += 1
        if has_doi and has_pmid:
            stats['with_doi_and_pmid'] += 1
        
        if not (has_doi or has_url or has_pmid or has_pmc):
            stats['with_none'] += 1
    
    return stats


def compare_ris_files(original_file: str, remaining_file: str) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Compare two RIS files to find:
    1. Papers that were successfully downloaded (in original but not in remaining)
    2. Papers that remain missing (in remaining file)
    3. All original papers
    
    Returns: (successful_papers, remaining_papers, all_original_papers)
    """
    print("Parsing original RIS file...")
    original_papers = parse_ris_file(original_file)
    print(f"  Found {len(original_papers)} papers in original file")
    
    print("Parsing remaining RIS file...")
    remaining_papers = parse_ris_file(remaining_file)
    print(f"  Found {len(remaining_papers)} papers in remaining file")
    
    # Create lookup sets - use multiple identifiers for matching
    def create_paper_key(paper: Dict[str, str]) -> Set[str]:
        """Create set of identifiers that can be used for matching."""
        keys = set()
        if paper.get('record_number'):
            keys.add(f"id:{paper['record_number']}")
        if paper.get('label_id'):
            keys.add(f"lb:{paper['label_id']}")
        if paper.get('doi'):
            keys.add(f"doi:{paper['doi'].lower()}")
        if paper.get('pmid'):
            keys.add(f"pmid:{paper['pmid']}")
        if paper.get('url'):
            # Normalize URL for matching
            url = paper['url'].lower().rstrip('/')
            keys.add(f"url:{url}")
        return keys
    
    # Build lookup for remaining papers
    remaining_keys = {}
    for paper in remaining_papers:
        keys = create_paper_key(paper)
        for key in keys:
            remaining_keys[key] = paper
    
    # Find successful papers (in original but not in remaining)
    successful_papers = []
    remaining_papers_set = set()
    
    for paper in original_papers:
        keys = create_paper_key(paper)
        found_in_remaining = False
        
        for key in keys:
            if key in remaining_keys:
                remaining_papers_set.add(id(remaining_keys[key]))
                found_in_remaining = True
                break
        
        if not found_in_remaining:
            successful_papers.append(paper)
    
    # Get actual remaining papers list (deduplicated)
    remaining_papers_list = []
    seen_ids = set()
    for paper in remaining_papers:
        paper_id = id(paper)
        if paper_id in remaining_papers_set and paper_id not in seen_ids:
            remaining_papers_list.append(paper)
            seen_ids.add(paper_id)
    
    print(f"\nComparison results:")
    print(f"  Original papers: {len(original_papers)}")
    print(f"  Successfully downloaded: {len(successful_papers)}")
    print(f"  Still missing: {len(remaining_papers_list)}")
    
    return successful_papers, remaining_papers_list, original_papers


def generate_reports(remaining_papers: List[Dict[str, str]], 
                     original_papers: List[Dict[str, str]],
                     error_map: Dict[str, Dict[str, str]],
                     output_dir: Path):
    """Generate all analysis reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Categorize papers
    print("\nCategorizing papers...")
    categorized = defaultdict(list)
    for paper in remaining_papers:
        category = categorize_paper(paper, error_map)
        categorized[category].append(paper)
    
    # Analyze identifiers
    print("Analyzing identifiers...")
    identifier_stats = analyze_identifiers(remaining_papers)
    
    # Publisher analysis
    print("Analyzing publishers...")
    publisher_counts = Counter()
    publisher_by_category = defaultdict(lambda: defaultdict(int))
    
    for paper in remaining_papers:
        publisher = paper.get('publisher') or 'Unknown'
        category = categorize_paper(paper, error_map)
        publisher_counts[publisher] += 1
        publisher_by_category[publisher][category] += 1
    
    # Generate Summary Report
    print("Generating summary report...")
    with open(output_dir / 'missing_papers_analysis_summary.txt', 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("MISSING PAPERS ANALYSIS SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Original missing papers: {len(original_papers)}\n")
        f.write(f"Still missing papers: {len(remaining_papers)}\n")
        f.write(f"Successfully downloaded: {len(original_papers) - len(remaining_papers)}\n")
        f.write(f"Success rate: {((len(original_papers) - len(remaining_papers)) / len(original_papers) * 100):.1f}%\n\n")
        
        f.write("BREAKDOWN BY CATEGORY:\n")
        f.write("-" * 80 + "\n")
        for category, papers in sorted(categorized.items(), key=lambda x: len(x[1]), reverse=True):
            f.write(f"  {category.upper()}: {len(papers)} ({len(papers)/len(remaining_papers)*100:.1f}%)\n")
        f.write("\n")
        
        f.write("IDENTIFIER AVAILABILITY:\n")
        f.write("-" * 80 + "\n")
        f.write(f"  Total papers: {identifier_stats['total']}\n")
        f.write(f"  With DOI: {identifier_stats['with_doi']} ({identifier_stats['with_doi']/identifier_stats['total']*100:.1f}%)\n")
        f.write(f"  With URL: {identifier_stats['with_url']} ({identifier_stats['with_url']/identifier_stats['total']*100:.1f}%)\n")
        f.write(f"  With PMID: {identifier_stats['with_pmid']} ({identifier_stats['with_pmid']/identifier_stats['total']*100:.1f}%)\n")
        f.write(f"  With PMC ID: {identifier_stats['with_pmc']} ({identifier_stats['with_pmc']/identifier_stats['total']*100:.1f}%)\n")
        f.write(f"  With all (DOI+URL+PMID): {identifier_stats['with_all']} ({identifier_stats['with_all']/identifier_stats['total']*100:.1f}%)\n")
        f.write(f"  With DOI and URL: {identifier_stats['with_doi_and_url']} ({identifier_stats['with_doi_and_url']/identifier_stats['total']*100:.1f}%)\n")
        f.write(f"  With DOI and PMID: {identifier_stats['with_doi_and_pmid']} ({identifier_stats['with_doi_and_pmid']/identifier_stats['total']*100:.1f}%)\n")
        f.write(f"  With no identifiers: {identifier_stats['with_none']} ({identifier_stats['with_none']/identifier_stats['total']*100:.1f}%)\n")
        f.write("\n")
        
        f.write("TOP 20 PUBLISHERS IN MISSING PAPERS:\n")
        f.write("-" * 80 + "\n")
        for publisher, count in publisher_counts.most_common(20):
            f.write(f"  {publisher}: {count} papers\n")
        f.write("\n")
    
    # Generate Detailed Analysis
    print("Generating detailed analysis...")
    with open(output_dir / 'missing_papers_detailed_analysis.txt', 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("DETAILED ANALYSIS BY CATEGORY\n")
        f.write("=" * 80 + "\n\n")
        
        for category in ['paywall', 'unknown', 'technical', 'no_identifier', 'other']:
            if category not in categorized:
                continue
            
            papers = categorized[category]
            f.write(f"\n{'=' * 80}\n")
            f.write(f"{category.upper()} - {len(papers)} papers\n")
            f.write(f"{'=' * 80}\n\n")
            
            for i, paper in enumerate(papers, 1):
                label_id = paper.get('label_id') or 'N/A'
                record_number = paper.get('record_number') or 'N/A'
                title = paper.get('title', 'Unknown')[:80]
                doi = paper.get('doi') or 'N/A'
                url = paper.get('url') or 'N/A'
                if url != 'N/A' and len(url) > 60:
                    url = url[:57] + '...'
                publisher = paper.get('publisher') or 'N/A'
                pmid = paper.get('pmid') or 'N/A'
                pmc = paper.get('pmc_id') or 'N/A'
                
                # Get error reason if available
                error_reason = 'N/A'
                if label_id and label_id in error_map:
                    error_reason = error_map[label_id].get('error_reason', 'N/A')
                elif record_number and record_number in error_map:
                    error_reason = error_map[record_number].get('error_reason', 'N/A')
                
                f.write(f"{i}. [{label_id}/{record_number}] {title}\n")
                f.write(f"   Publisher: {publisher}\n")
                f.write(f"   DOI: {doi}\n")
                f.write(f"   URL: {url}\n")
                f.write(f"   PMID: {pmid} | PMC: {pmc}\n")
                f.write(f"   Error: {error_reason}\n")
                f.write("\n")
    
    # Generate Potentially Fixable Papers
    print("Generating potentially fixable papers list...")
    fixable_papers = []
    
    # Focus on unknown failures with good identifiers
    for paper in categorized.get('unknown', []):
        has_doi = bool(paper.get('doi'))
        has_url = bool(paper.get('url'))
        has_pmid = bool(paper.get('pmid'))
        publisher = (paper.get('publisher') or '').lower()
        
        # Supported publishers
        supported_publishers = ['elsevier', 'springer', 'wiley', 'ieee', 'sciencedirect',
                              'nature', 'bmj', 'tandfonline', 'taylor', 'francis']
        
        is_supported = any(sp in publisher for sp in supported_publishers)
        
        # Consider fixable if:
        # 1. Has good identifiers (DOI+URL or DOI+PMID)
        # 2. From supported publisher OR has library proxy-accessible URL
        if (has_doi and (has_url or has_pmid)) and (is_supported or 'ncbi.nlm.nih.gov' in (paper.get('url') or '').lower()):
            fixable_papers.append(paper)
    
    # Also include technical failures with good identifiers
    for paper in categorized.get('technical', []):
        has_doi = bool(paper.get('doi'))
        has_url = bool(paper.get('url'))
        has_pmid = bool(paper.get('pmid'))
        
        if has_doi and (has_url or has_pmid):
            fixable_papers.append(paper)
    
    with open(output_dir / 'potentially_fixable_papers.txt', 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("POTENTIALLY FIXABLE PAPERS\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total potentially fixable papers: {len(fixable_papers)}\n")
        f.write("\nThese papers have:\n")
        f.write("  - Valid identifiers (DOI + URL or DOI + PMID)\n")
        f.write("  - From supported publishers OR library proxy-accessible URLs\n")
        f.write("  - Unknown or technical failure reasons (not paywall)\n")
        f.write("\n" + "=" * 80 + "\n\n")
        
        for i, paper in enumerate(fixable_papers, 1):
            label_id = paper.get('label_id') or 'N/A'
            record_number = paper.get('record_number') or 'N/A'
            title = paper.get('title', 'Unknown')
            doi = paper.get('doi') or 'N/A'
            url = paper.get('url') or 'N/A'
            publisher = paper.get('publisher') or 'N/A'
            pmid = paper.get('pmid') or 'N/A'
            
            error_reason = 'N/A'
            if label_id and label_id in error_map:
                error_reason = error_map[label_id].get('error_reason', 'N/A')
            elif record_number and record_number in error_map:
                error_reason = error_map[record_number].get('error_reason', 'N/A')
            
            f.write(f"{i}. [{label_id}/{record_number}] {title}\n")
            f.write(f"   Publisher: {publisher}\n")
            f.write(f"   DOI: {doi}\n")
            f.write(f"   URL: {url}\n")
            f.write(f"   PMID: {pmid}\n")
            f.write(f"   Error: {error_reason}\n")
            f.write("\n")
    
    # Generate RIS file for potentially fixable papers
    with open(output_dir / 'unknown_failures_ris.txt', 'w', encoding='utf-8') as f:
        for paper in fixable_papers:
            f.write(paper['ris_text'])
    
    # Generate Publisher Breakdown
    print("Generating publisher breakdown...")
    with open(output_dir / 'publisher_breakdown.txt', 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("PUBLISHER BREAKDOWN\n")
        f.write("=" * 80 + "\n\n")
        
        # Count original papers by publisher
        original_publisher_counts = Counter()
        for paper in original_papers:
            publisher = paper.get('publisher') or 'Unknown'
            original_publisher_counts[publisher] += 1
        
        f.write("Publisher | Original | Remaining | % Remaining | Breakdown by Category\n")
        f.write("-" * 80 + "\n")
        
        for publisher, remaining_count in publisher_counts.most_common():
            original_count = original_publisher_counts.get(publisher, 0)
            pct_remaining = (remaining_count / original_count * 100) if original_count > 0 else 0
            
            f.write(f"\n{publisher}\n")
            f.write(f"  Original: {original_count} | Remaining: {remaining_count} | {pct_remaining:.1f}% remaining\n")
            
            if publisher in publisher_by_category:
                f.write("  Category breakdown:\n")
                for category, count in sorted(publisher_by_category[publisher].items(), key=lambda x: x[1], reverse=True):
                    f.write(f"    {category}: {count}\n")
    
    print(f"\nAll reports generated in: {output_dir}")


def main():
    """Main execution function."""
    # File paths
    original_file = Path("missing_papers/still_missing/missing_papers_original_1033.txt")
    remaining_file = Path("missing_papers/still_missing/379_missing_texts.txt")
    error_mapping_file = Path("found_papers/downloaded_papers/third_scrape_AI_agent/label_to_filename.txt")
    output_dir = Path("missing_papers/analysis")
    
    # Check files exist
    if not original_file.exists():
        print(f"ERROR: Original file not found: {original_file}")
        return
    
    if not remaining_file.exists():
        print(f"ERROR: Remaining file not found: {remaining_file}")
        return
    
    print("=" * 80)
    print("MISSING PAPERS DEEP ANALYSIS")
    print("=" * 80)
    print()
    
    # Load error reasons
    print("Loading error reasons from mapping file...")
    error_map = load_error_reasons(str(error_mapping_file))
    print(f"  Loaded {len(error_map)} error mappings")
    
    # Compare files
    successful_papers, remaining_papers, original_papers = compare_ris_files(
        str(original_file), str(remaining_file)
    )
    
    # Generate reports
    generate_reports(remaining_papers, original_papers, error_map, output_dir)
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"\nReports saved to: {output_dir}")
    print("\nGenerated files:")
    print("  - missing_papers_analysis_summary.txt")
    print("  - missing_papers_detailed_analysis.txt")
    print("  - potentially_fixable_papers.txt")
    print("  - publisher_breakdown.txt")
    print("  - unknown_failures_ris.txt (RIS file for re-processing)")


if __name__ == "__main__":
    main()
