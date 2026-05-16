#!/usr/bin/env python3
"""
Download PDFs using Selenium browser automation.
This can handle library authentication and bypass some download restrictions.

Requirements:
    pip install selenium webdriver-manager
    Also need Chrome browser installed.
"""

import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


def parse_ris_file(filepath: str) -> List[Dict[str, str]]:
    """Parse RIS file into list of reference dictionaries."""
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
        
        if pmid:
            references.append({
                'pmid': pmid,
                'title': title or 'Unknown Title',
                'pmc_id': pmc_id,
                'ris_text': entry + '\nER  - \n'
            })
    
    return references


def sanitize_filename(title: str, max_length: int = 40) -> str:
    """Sanitize title for use as filename."""
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, '', title)
    filename = re.sub(r'\s+', ' ', filename).strip()
    
    if len(filename) > max_length:
        filename = filename[:max_length].rstrip()
    
    if not filename:
        filename = "untitled"
    
    if not filename.endswith('.pdf'):
        filename += '.pdf'
    
    return filename


def ensure_unique_filename(directory: Path, base_filename: str) -> Path:
    """Ensure filename is unique in directory."""
    output_path = directory / base_filename
    
    if not output_path.exists():
        return output_path
    
    name_part = base_filename[:-4]
    counter = 1
    
    while output_path.exists():
        new_name = f"{name_part}_{counter}.pdf"
        output_path = directory / new_name
        counter += 1
    
    return output_path


def setup_driver(headless: bool = False, download_dir: str = None) -> webdriver.Chrome:
    """Set up Chrome driver with download preferences."""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument('--headless')
    
    # Set download preferences
    prefs = {
        "download.default_directory": str(download_dir) if download_dir else str(Path.cwd() / "found_papers"),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True  # Download PDFs instead of viewing
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver


def download_via_pmc_selenium(driver: webdriver.Chrome, pmc_id: str, output_path: Path) -> bool:
    """Download PDF from PMC using Selenium."""
    try:
        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
        driver.get(url)
        time.sleep(3)  # Wait for page load
        
        # Check if we got a PDF (status 200) or error page
        current_url = driver.current_url
        page_source = driver.page_source.lower()
        
        # If redirected to error page or access denied
        if 'access denied' in page_source or '403' in page_source or 'not available' in page_source:
            return False
        
        # Try to find and click download link if present
        try:
            download_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf') or contains(text(), 'Download') or contains(text(), 'PDF')]")
            for link in download_links[:3]:  # Try first few links
                try:
                    link.click()
                    time.sleep(2)
                    # Check if download started
                    break
                except:
                    continue
        except:
            pass
        
        # Check if file was downloaded
        time.sleep(2)
        return output_path.exists() and output_path.stat().st_size > 1024
        
    except Exception as e:
        print(f"      Error: {str(e)[:50]}")
        return False


def download_via_pubmed_selenium(driver: webdriver.Chrome, pmid: str, output_path: Path, use_library: bool = False) -> bool:
    """Download PDF via PubMed page using Selenium."""
    try:
        if use_library:
            # Access through library proxy
            url = f"https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/pubmed/{pmid}/"
        else:
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        
        driver.get(url)
        time.sleep(3)
        
        # Look for full-text links
        fulltext_selectors = [
            "//a[contains(text(), 'Full text')]",
            "//a[contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download')]",
            "//a[contains(@href, 'fulltext')]",
            "//a[contains(@href, '.pdf')]",
            "//a[contains(@href, 'publisher')]",
        ]
        
        for selector in fulltext_selectors:
            try:
                links = driver.find_elements(By.XPATH, selector)
                for link in links[:5]:  # Try first few
                    try:
                        href = link.get_attribute('href')
                        if href and ('.pdf' in href.lower() or 'fulltext' in href.lower() or 'publisher' in href.lower()):
                            # Open in new tab
                            driver.execute_script("window.open(arguments[0], '_blank');", href)
                            driver.switch_to.window(driver.window_handles[-1])
                            time.sleep(4)
                            
                            # Look for PDF download on publisher page
                            pdf_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf') or contains(text(), 'PDF') or contains(text(), 'Download PDF')]")
                            for pdf_link in pdf_links[:3]:
                                try:
                                    pdf_href = pdf_link.get_attribute('href')
                                    if pdf_href:
                                        driver.get(pdf_href)
                                        time.sleep(3)
                                        
                                        # Check if PDF downloaded
                                        if output_path.exists() and output_path.stat().st_size > 1024:
                                            driver.close()
                                            driver.switch_to.window(driver.window_handles[0])
                                            return True
                                except:
                                    continue
                            
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                    except:
                        continue
            except:
                continue
        
        return False
        
    except Exception as e:
        print(f"      Error: {str(e)[:50]}")
        return False


def main():
    """Main execution function."""
    ris_file = Path("missing_papers_12_9_2025.txt")
    output_dir = Path("found_papers")
    output_dir.mkdir(exist_ok=True)
    
    print("="*60)
    print("PDF DOWNLOADER - Selenium Browser Automation")
    print("="*60)
    print("\nThis script will open a Chrome browser window.")
    print("You may need to:")
    print("1. Log into HSHSL library if prompted")
    print("2. Allow downloads in the browser")
    print("3. Let the script run (it will control the browser)")
    print("\nPress Enter to start...")
    input()
    
    use_library = input("\nUse HSHSL library access? (y/n, default=y): ").strip().lower()
    use_library = use_library != 'n'
    
    print(f"\nParsing RIS file: {ris_file}")
    references = parse_ris_file(str(ris_file))
    print(f"Found {len(references)} references\n")
    
    # Setup driver
    print("Setting up Chrome browser...")
    driver = setup_driver(headless=False, download_dir=str(output_dir))
    
    successful = []
    failed = []
    
    try:
        for i, ref in enumerate(references, 1):
            pmid = ref['pmid']
            title = ref['title']
            pmc_id = ref.get('pmc_id')
            
            print(f"[{i}/{len(references)}] PMID {pmid}: {title[:50]}...", end=' ')
            
            filename = sanitize_filename(title, max_length=40)
            output_path = ensure_unique_filename(output_dir, filename)
            
            # Try PMC first if available
            download_success = False
            if pmc_id:
                download_success = download_via_pmc_selenium(driver, pmc_id, output_path)
                if download_success:
                    print(f"DOWNLOADED (PMC)")
                    successful.append(ref)
                    time.sleep(1)
            
            # Try PubMed/library access if PMC failed
            if not download_success:
                download_success = download_via_pubmed_selenium(driver, pmid, output_path, use_library)
                if download_success:
                    print(f"DOWNLOADED (Library/Pubmed)")
                    successful.append(ref)
                    time.sleep(1)
            
            if not download_success:
                print("FAILED")
                failed.append(ref)
                time.sleep(0.5)
    
    finally:
        print("\nClosing browser...")
        driver.quit()
    
    # Write failed references
    if failed:
        still_missing_path = output_dir / "still_missing.txt"
        with open(still_missing_path, 'w', encoding='utf-8') as f:
            for ref in failed:
                f.write(ref['ris_text'])
                f.write('\n')
        print(f"\nFailed downloads written to: {still_missing_path}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  Total references: {len(references)}")
    print(f"  Successfully downloaded: {len(successful)}")
    print(f"  Failed: {len(failed)}")
    if len(references) > 0:
        print(f"  Success rate: {len(successful)/len(references)*100:.1f}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

