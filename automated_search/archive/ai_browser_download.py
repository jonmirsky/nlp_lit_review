#!/usr/bin/env python3
"""
AI Agent browser-based download script.
Uses browser automation to download papers and save with label IDs.
"""

import re
import sys
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import requests

# Try to use existing ChromeDriver or install via webdriver_manager
try:
    from webdriver_manager.chrome import ChromeDriverManager
    driver_path = ChromeDriverManager().install()
except:
    # Fallback: try to find chromedriver in common locations
    import subprocess
    result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
    if result.returncode == 0:
        driver_path = result.stdout.strip()
    else:
        print("ERROR: ChromeDriver not found. Please install it or ensure it's in PATH.")
        sys.exit(1)


def setup_driver(download_dir: str):
    """Setup Chrome driver with download preferences."""
    chrome_options = Options()
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_settings.popups": 0,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
        "plugins.plugins_list": [{"enabled": False, "name": "Chrome PDF Viewer"}],
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver


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


def download_pmc_paper(driver, pmc_id: str, output_path: Path):
    """Download PMC paper using browser session."""
    article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"
    driver.get(article_url)
    time.sleep(4)
    
    # Find and click Download PDF button
    try:
        download_buttons = driver.find_elements(By.XPATH,
            "//button[contains(text(), 'Download PDF')] | "
            "//a[contains(text(), 'Download PDF')]")
        
        if download_buttons:
            download_buttons[0].click()
            time.sleep(5)
            
            # Get current URL (should be PDF URL now)
            current_url = driver.current_url
            if '/pdf/' in current_url and '.pdf' in current_url:
                # Extract cookies and download with requests
                cookies = driver.get_cookies()
                session = requests.Session()
                for cookie in cookies:
                    session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''))
                
                # Download PDF
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Referer': article_url
                }
                response = session.get(current_url, headers=headers, timeout=60, stream=True)
                
                if response.status_code == 200:
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        return True
    except Exception as e:
        print(f"    Error: {e}")
    
    return False


def download_pubmed_paper(driver, pmid: str, output_path: Path):
    """Download PubMed paper - navigate to PMC if available."""
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    driver.get(url)
    time.sleep(3)
    
    # Look for Free PMC article link
    try:
        pmc_links = driver.find_elements(By.XPATH,
            "//a[contains(text(), 'Free PMC article')] | "
            "//a[contains(@href, '/pmc/articles/')]")
        
        if pmc_links:
            pmc_href = pmc_links[0].get_attribute('href')
            pmc_match = re.search(r'/pmc/articles/(PMC\d+)', pmc_href)
            if pmc_match:
                pmc_id = pmc_match.group(1).replace('PMC', '')
                return download_pmc_paper(driver, pmc_id, output_path)
    except:
        pass
    
    return False


def main():
    ris_file = Path('missing_papers/still_missing/missing_after_second_scrape.txt')
    output_dir = Path('found_papers/downloaded_papers/third_scrape_AI_agent')
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_file = output_dir / 'label_to_filename.txt'
    
    print("Parsing RIS file...")
    papers = parse_ris_papers(str(ris_file), limit=5)  # Start with 5
    print(f"Found {len(papers)} papers to process\n")
    
    print("Setting up browser...")
    driver = setup_driver(str(output_dir))
    
    mapping_fp = open(mapping_file, 'w', encoding='utf-8')
    mapping_fp.write("# label_id|filename|title|status|error_reason\n")
    
    try:
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
            
            # Try PubMed -> PMC path
            if paper.get('pmid'):
                success = download_pubmed_paper(driver, paper['pmid'], output_path)
            
            # Try direct PMC
            if not success and paper.get('pmc_id'):
                success = download_pmc_paper(driver, paper['pmc_id'], output_path)
            
            if success:
                print(f"  ✓ Downloaded: {label_id}.pdf\n")
                mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success|\n")
            else:
                print(f"  ✗ Failed: {error}\n")
                mapping_fp.write(f"{label_id}||{paper['title']}|failed|{error}\n")
            
            mapping_fp.flush()
            time.sleep(2)
    
    finally:
        mapping_fp.close()
        driver.quit()
        print(f"\nCompleted. Mapping saved to: {mapping_file}")


if __name__ == '__main__':
    main()
