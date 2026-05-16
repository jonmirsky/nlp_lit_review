#!/usr/bin/env python3
"""
AI Agent script to download papers from RIS file.
Uses existing download functions to handle browser sessions properly.
"""

import re
import sys
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Import download functions
sys.path.insert(0, str(Path(__file__).parent))
from debug_second_pdf_scrape_v2 import (
    setup_driver,
    download_via_pubmed_selenium,
    download_from_pmc_url,
    download_via_url_selenium,
    download_via_doi_selenium,
    detect_publisher_type
)


def parse_ris_papers(filepath: str, limit: int = None):
    """Parse RIS file and extract papers with label IDs."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    papers = []
    
    for entry in entries:
        if limit and len(papers) >= limit:
            break
            
        entry = entry.strip()
        if not entry:
            continue
        
        label_id = None
        url = None
        title = None
        pmid = None
        pmc_id = None
        doi = None
        
        for line in entry.split('\n'):
            line = line.strip()
            if line.startswith('LB  - '):
                label_id = line[6:].strip()
            elif line.startswith('UR  - '):
                url = line[6:].strip()
            elif line.startswith('TI  - '):
                title = line[6:].strip()
            elif line.startswith('AN  - '):
                pmid = line[6:].strip()
            elif line.startswith('C2  - '):
                pmc_text = line[6:].strip()
                pmc_match = re.search(r'PMC?(\d+)', pmc_text, re.IGNORECASE)
                if pmc_match:
                    pmc_id = pmc_match.group(1)
            elif line.startswith('DO  - '):
                doi = line[6:].strip()
                doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
                doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
                doi = doi.strip()
        
        if label_id and (url or pmid or doi):
            papers.append({
                'label_id': label_id,
                'url': url,
                'title': title or 'Unknown',
                'pmid': pmid,
                'pmc_id': pmc_id,
                'doi': doi
            })
    
    return papers


def download_paper(ref, output_dir: Path, driver: webdriver.Chrome):
    """Download one paper and return status."""
    label_id = ref['label_id']
    output_path = output_dir / f"{label_id}.pdf"
    
    # Check if already exists
    if output_path.exists() and output_path.stat().st_size > 1024:
        return {'status': 'success', 'filename': f"{label_id}.pdf", 'error': None}
    
    error = None
    
    try:
        # Priority 1: Direct URL
        if ref.get('url'):
            url = ref['url']
            publisher_type = detect_publisher_type(url)
            
            if publisher_type == 'pubmed':
                pmid_match = re.search(r'/pubmed/(\d+)', url)
                if pmid_match:
                    error = download_via_pubmed_selenium(driver, pmid_match.group(1), output_path, use_library=False)
            elif publisher_type == 'pmc':
                error = download_from_pmc_url(driver, url, output_path)
            else:
                error = download_via_url_selenium(driver, url, output_path, use_library=False, doi=ref.get('doi'))
            
            if error is None and output_path.exists() and output_path.stat().st_size > 1024:
                return {'status': 'success', 'filename': f"{label_id}.pdf", 'error': None}
        
        # Priority 2: PMID
        if ref.get('pmid') and error:
            error = download_via_pubmed_selenium(driver, ref['pmid'], output_path, use_library=False)
            if error is None and output_path.exists() and output_path.stat().st_size > 1024:
                return {'status': 'success', 'filename': f"{label_id}.pdf", 'error': None}
        
        # Priority 3: PMC ID
        if ref.get('pmc_id') and error:
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{ref['pmc_id']}/"
            error = download_from_pmc_url(driver, pmc_url, output_path)
            if error is None and output_path.exists() and output_path.stat().st_size > 1024:
                return {'status': 'success', 'filename': f"{label_id}.pdf", 'error': None}
        
        # Priority 4: DOI
        if ref.get('doi') and error:
            doi_result = download_via_doi_selenium(driver, ref['doi'], output_path, use_library=False)
            if doi_result and doi_result.isdigit():
                error = download_via_pubmed_selenium(driver, doi_result, output_path, use_library=False)
            else:
                error = doi_result
            if error is None and output_path.exists() and output_path.stat().st_size > 1024:
                return {'status': 'success', 'filename': f"{label_id}.pdf", 'error': None}
        
        return {'status': 'failed', 'filename': '', 'error': error or 'no_pdf_found'}
        
    except Exception as e:
        return {'status': 'failed', 'filename': '', 'error': str(e)}


def main():
    ris_file = Path('missing_papers/still_missing/missing_after_second_scrape.txt')
    output_dir = Path('found_papers/downloaded_papers/third_scrape_AI_agent')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    mapping_file = output_dir / 'label_to_filename.txt'
    
    # Parse papers (start with 20 for testing)
    print("Parsing RIS file...")
    papers = parse_ris_papers(str(ris_file), limit=20)
    print(f"Found {len(papers)} papers to process\n")
    
    # Setup driver
    print("Setting up browser...")
    driver = setup_driver(headless=False, download_dir=str(output_dir))
    
    # Open mapping file
    mapping_fp = open(mapping_file, 'w', encoding='utf-8')
    mapping_fp.write("# label_id|filename|title|status|error_reason\n")
    
    try:
        for i, paper in enumerate(papers, 1):
            label_id = paper['label_id']
            title = paper['title'][:60] + '...' if len(paper['title']) > 60 else paper['title']
            
            print(f"[{i}/{len(papers)}] Label {label_id}: {title}")
            
            result = download_paper(paper, output_dir, driver)
            
            # Write to mapping
            filename = result['filename'] or ''
            status = result['status']
            error = result['error'] or ''
            mapping_fp.write(f"{label_id}|{filename}|{paper['title']}|{status}|{error}\n")
            mapping_fp.flush()
            
            if result['status'] == 'success':
                print(f"  ✓ Downloaded: {result['filename']}\n")
            else:
                error_msg = error or "can't get file"
                print(f"  ✗ Failed: {error_msg}\n")
    
    finally:
        mapping_fp.close()
        driver.quit()
        print(f"\nCompleted. Mapping saved to: {mapping_file}")


if __name__ == '__main__':
    main()
