#!/usr/bin/env python3
"""
Batch download PDFs from RIS file with label tracking.

This script processes a RIS file, attempts to download each paper's PDF,
and maintains a mapping between label IDs (LB field) and downloaded filenames.

Usage:
    python batch_download_from_ris.py [--test] [--all]
    
    --test: Process first 20 papers only (default)
    --all: Process all papers in the RIS file
"""

import re
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.common.exceptions import TimeoutException

# Import functions from the main script
# We'll import the necessary functions at runtime
sys.path.insert(0, str(Path(__file__).parent))

# Import from debug_second_pdf_scrape_v2
from debug_second_pdf_scrape_v2 import (
    setup_driver,
    download_via_pubmed_selenium,
    download_from_pmc_url,
    download_via_url_selenium,
    download_via_doi_selenium,
    detect_publisher_type,
    ERROR_PAYWALL,
    ERROR_NO_PDF,
    ERROR_TIMEOUT,
    ERROR_DOWNLOAD_FAILED,
    ERROR_NOT_FOUND,
    ERROR_NO_IDENTIFIER,
    ERROR_PUBLISHER_ERROR,
    ERROR_UNKNOWN
)


def parse_ris_with_labels(filepath: str) -> List[Dict[str, str]]:
    """
    Parse RIS file and extract all fields including LB (label) field.
    Returns list of reference dictionaries with label_id field.
    """
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
        label_id = None  # Label from LB field
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
                # Label field - this is what we use for tracking
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
        
        # Accept if we have any identifier or metadata
        # Require label_id for tracking
        if (pmid or doi or url or title) and label_id:
            references.append({
                'label_id': label_id,
                'pmid': pmid,
                'title': title or 'Unknown Title',
                'pmc_id': pmc_id,
                'doi': doi,
                'record_number': record_number,
                'url': url,
                'pii': pii,
                'journal': journal,
                'issn': issn,
                'publisher': publisher,
                'start_page': start_page,
                'end_page': end_page,
                'volume': volume,
                'year': year,
                'first_author': first_author,
                'ris_text': entry + '\nER  - \n'
            })
    
    return references


def download_paper_with_tracking(
    reference: Dict[str, str], 
    output_dir: Path, 
    driver: webdriver.Chrome,
    use_library: bool = False
) -> Dict[str, str]:
    """
    Download one paper and return status dict.
    
    Returns:
        Dict with keys: label_id, filename, title, status, error_reason
    """
    label_id = reference['label_id']
    title = reference['title']
    output_path = output_dir / f"{label_id}.pdf"
    
    result = {
        'label_id': label_id,
        'filename': f"{label_id}.pdf" if output_path.exists() and output_path.stat().st_size > 1024 else "",
        'title': title,
        'status': 'failed',
        'error_reason': ''
    }
    
    # Check if file already exists
    if output_path.exists() and output_path.stat().st_size > 1024:
        result['status'] = 'success'
        result['filename'] = f"{label_id}.pdf"
        return result
    
    error_reason = None
    
    try:
        # Priority 1: Direct URL from RIS file
        if reference.get('url'):
            url = reference['url']
            publisher_type = detect_publisher_type(url)
            
            # Handle PubMed URLs specially
            if publisher_type == 'pubmed':
                pmid_match = re.search(r'/pubmed/(\d+)', url)
                if pmid_match:
                    pmid = pmid_match.group(1)
                    error_reason = download_via_pubmed_selenium(driver, pmid, output_path, use_library)
                    if error_reason is None:
                        if output_path.exists() and output_path.stat().st_size > 1024:
                            result['status'] = 'success'
                            result['filename'] = f"{label_id}.pdf"
                            return result
            
            # Handle PMC URLs
            elif publisher_type == 'pmc':
                error_reason = download_from_pmc_url(driver, url, output_path)
                if error_reason is None:
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        result['status'] = 'success'
                        result['filename'] = f"{label_id}.pdf"
                        return result
            
            # Try generic URL download
            else:
                error_reason = download_via_url_selenium(
                    driver, url, output_path, use_library, reference.get('doi')
                )
                if error_reason is None:
                    # Give it time to download
                    time.sleep(3)
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        result['status'] = 'success'
                        result['filename'] = f"{label_id}.pdf"
                        return result
        
        # Priority 2: PubMed/PMC download (if PMID or PMC ID available)
        if reference.get('pmid'):
            error_reason = download_via_pubmed_selenium(
                driver, reference['pmid'], output_path, use_library
            )
            if error_reason is None:
                if output_path.exists() and output_path.stat().st_size > 1024:
                    result['status'] = 'success'
                    result['filename'] = f"{label_id}.pdf"
                    return result
        
        if reference.get('pmc_id'):
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{reference['pmc_id']}/"
            error_reason = download_from_pmc_url(driver, pmc_url, output_path)
            if error_reason is None:
                if output_path.exists() and output_path.stat().st_size > 1024:
                    result['status'] = 'success'
                    result['filename'] = f"{label_id}.pdf"
                    return result
        
        # Priority 3: DOI-based download
        if reference.get('doi'):
            # Try DOI download - this may return a PMID if found via PubMed search
            doi_result = download_via_doi_selenium(
                driver, reference['doi'], output_path, use_library
            )
            
            # If DOI search found a PMID, try PubMed download
            if doi_result and doi_result.isdigit():
                error_reason = download_via_pubmed_selenium(
                    driver, doi_result, output_path, use_library
                )
                if error_reason is None:
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        result['status'] = 'success'
                        result['filename'] = f"{label_id}.pdf"
                        return result
            else:
                error_reason = doi_result
                if error_reason is None:
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        result['status'] = 'success'
                        result['filename'] = f"{label_id}.pdf"
                        return result
        
        # If we get here, download failed
        result['error_reason'] = error_reason or ERROR_NO_PDF
        
    except TimeoutException:
        result['error_reason'] = ERROR_TIMEOUT
    except Exception as e:
        result['error_reason'] = ERROR_UNKNOWN
        print(f"    Unexpected error: {str(e)}")
    
    return result


def create_mapping_entry(
    label_id: str, 
    filename: str, 
    title: str, 
    status: str, 
    error_reason: str = ""
) -> str:
    """Create a mapping file entry in TSV format."""
    # Escape pipe characters in title
    title_escaped = title.replace('|', '\\|')
    return f"{label_id}|{filename}|{title_escaped}|{status}|{error_reason}\n"


def load_existing_mapping(mapping_file: Path) -> Dict[str, Dict]:
    """Load existing mapping file to avoid re-processing."""
    existing = {}
    if mapping_file.exists():
        with open(mapping_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                if len(parts) >= 4:
                    label_id = parts[0]
                    existing[label_id] = {
                        'filename': parts[1],
                        'title': parts[2],
                        'status': parts[3],
                        'error_reason': parts[4] if len(parts) > 4 else ''
                    }
    return existing


def main():
    parser = argparse.ArgumentParser(description='Batch download PDFs from RIS file')
    parser.add_argument('--test', action='store_true', 
                       help='Process first 20 papers only (default)')
    parser.add_argument('--all', action='store_true',
                       help='Process all papers in the RIS file')
    parser.add_argument('--ris-file', type=str,
                       default='missing_papers/still_missing/missing_after_second_scrape.txt',
                       help='Path to RIS file (default: missing_papers/still_missing/missing_after_second_scrape.txt)')
    parser.add_argument('--use-library', action='store_true',
                       help='Use library proxy for downloads')
    
    args = parser.parse_args()
    
    # Determine mode
    test_mode = args.test or not args.all
    
    # Setup paths
    ris_file = Path(args.ris_file)
    if not ris_file.exists():
        print(f"ERROR: RIS file not found: {ris_file}")
        sys.exit(1)
    
    output_dir = Path("found_papers/downloaded_papers/third_scrape_AI_agent")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    mapping_file = output_dir / "label_to_filename.txt"
    
    print(f"Parsing RIS file: {ris_file}")
    references = parse_ris_with_labels(str(ris_file))
    
    if not references:
        print("ERROR: No references found in RIS file (or no LB fields found)")
        sys.exit(1)
    
    print(f"Found {len(references)} references with label IDs")
    
    # Load existing mapping to skip already processed papers
    existing_mapping = load_existing_mapping(mapping_file)
    print(f"Found {len(existing_mapping)} already processed papers")
    
    # Filter out already processed papers
    references_to_process = [
        ref for ref in references 
        if ref['label_id'] not in existing_mapping or 
           existing_mapping[ref['label_id']]['status'] != 'success'
    ]
    
    if test_mode:
        references_to_process = references_to_process[:20]
        print(f"TEST MODE: Processing first {len(references_to_process)} papers")
    else:
        print(f"Processing all {len(references_to_process)} papers")
    
    if not references_to_process:
        print("No papers to process!")
        return
    
    # Setup browser driver
    print("\nSetting up browser driver...")
    driver = setup_driver(headless=False, download_dir=str(output_dir))
    
    # Open mapping file for appending
    mapping_fp = open(mapping_file, 'a', encoding='utf-8')
    
    # Write header if file is new
    if mapping_file.stat().st_size == 0:
        mapping_fp.write("# label_id|filename|title|status|error_reason\n")
    
    try:
        for i, ref in enumerate(references_to_process, 1):
            label_id = ref['label_id']
            title = ref['title'][:80] + '...' if len(ref['title']) > 80 else ref['title']
            
            print(f"\n[{i}/{len(references_to_process)}] Processing label {label_id}: {title}")
            
            # Skip if already successfully downloaded
            if label_id in existing_mapping and existing_mapping[label_id]['status'] == 'success':
                output_path = output_dir / f"{label_id}.pdf"
                if output_path.exists() and output_path.stat().st_size > 1024:
                    print(f"  Already downloaded, skipping")
                    continue
            
            # Attempt download
            result = download_paper_with_tracking(ref, output_dir, driver, args.use_library)
            
            # Write to mapping file
            mapping_entry = create_mapping_entry(
                result['label_id'],
                result['filename'],
                result['title'],
                result['status'],
                result['error_reason']
            )
            mapping_fp.write(mapping_entry)
            mapping_fp.flush()  # Ensure it's written immediately
            
            # Print result
            if result['status'] == 'success':
                print(f"  ✓ Successfully downloaded: {result['filename']}")
            else:
                error_msg = result['error_reason'] or "can't get file"
                print(f"  ✗ Failed: {error_msg}")
            
            # Small delay between downloads
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved.")
    finally:
        mapping_fp.close()
        driver.quit()
        print(f"\n\nCompleted. Mapping file saved to: {mapping_file}")
        print(f"Downloaded papers saved to: {output_dir}")


if __name__ == '__main__':
    main()
