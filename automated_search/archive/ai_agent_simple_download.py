#!/usr/bin/env python3
"""
Simplified AI Agent download script - uses requests with browser-like headers
"""

import re
import requests
from pathlib import Path
from urllib.parse import urlparse

def parse_ris_papers(filepath: str, limit: int = None):
    """Parse RIS file and extract papers."""
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
        
        if label_id and (url or pmid):
            papers.append({
                'label_id': label_id,
                'url': url,
                'title': title or 'Unknown',
                'pmid': pmid,
                'pmc_id': pmc_id
            })
    
    return papers


def download_pmc_pdf(pmc_id: str, output_path: Path) -> bool:
    """Try to download PMC PDF directly."""
    # Try common PMC PDF URL patterns
    pdf_urls = [
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/nihms-{pmc_id}.pdf",
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/pdf,application/octet-stream,*/*',
        'Referer': f'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/'
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    for pdf_url in pdf_urls:
        try:
            response = session.get(pdf_url, timeout=30, stream=True, allow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/pdf' in content_type or response.content[:4] == b'%PDF':
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        return True
        except:
            continue
    
    return False


def main():
    ris_file = Path('missing_papers/still_missing/missing_after_second_scrape.txt')
    output_dir = Path('found_papers/downloaded_papers/third_scrape_AI_agent')
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_file = output_dir / 'label_to_filename.txt'
    
    print("Parsing RIS file...")
    papers = parse_ris_papers(str(ris_file), limit=20)
    print(f"Found {len(papers)} papers\n")
    
    mapping_fp = open(mapping_file, 'w', encoding='utf-8')
    mapping_fp.write("# label_id|filename|title|status|error_reason\n")
    
    for i, paper in enumerate(papers, 1):
        label_id = paper['label_id']
        title = paper['title'][:60] + '...' if len(paper['title']) > 60 else paper['title']
        output_path = output_dir / f"{label_id}.pdf"
        
        print(f"[{i}/{len(papers)}] Label {label_id}: {title}")
        
        if output_path.exists() and output_path.stat().st_size > 1024:
            print(f"  ✓ Already exists\n")
            mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success|already_exists\n")
            continue
        
        success = False
        error = "can't get file"
        
        # Try PMC download if available
        if paper.get('pmc_id'):
            print(f"  Trying PMC download (PMC{paper['pmc_id']})...")
            success = download_pmc_pdf(paper['pmc_id'], output_path)
            if success:
                print(f"  ✓ Downloaded via PMC\n")
                mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success|\n")
                mapping_fp.flush()
                continue
        
        if not success:
            print(f"  ✗ Failed: {error}\n")
            mapping_fp.write(f"{label_id}||{paper['title']}|failed|{error}\n")
            mapping_fp.flush()
    
    mapping_fp.close()
    print(f"\nCompleted. Mapping saved to: {mapping_file}")


if __name__ == '__main__':
    main()
