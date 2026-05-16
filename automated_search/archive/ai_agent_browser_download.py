#!/usr/bin/env python3
"""
AI Agent browser-based download - uses browser to navigate and click download buttons.
Downloads PDFs and saves them with label IDs from RIS file.
"""

import re
import time
import shutil
import os
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Try to get ChromeDriver
try:
    from webdriver_manager.chrome import ChromeDriverManager
    def get_chromedriver():
        return Service(ChromeDriverManager().install())
except:
    import subprocess
    def get_chromedriver():
        result = subprocess.run(['which', 'chromedriver'], capture_output=True, text=True)
        if result.returncode == 0:
            return Service(result.stdout.strip())
        raise Exception("ChromeDriver not found")


def parse_ris_papers(filepath: str, limit: int = None):
    """Parse RIS file and extract papers with label IDs and record numbers."""
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
        record_number = None
        url = None
        title = None
        pmid = None
        pmc_id = None
        doi = None
        
        for line in entry.split('\n'):
            line = line.strip()
            if line.startswith('LB  - '):
                label_id = line[6:].strip()
            elif line.startswith('ID  - '):
                # EndNote Record Number
                record_number = line[6:].strip()
            elif line.startswith('UR  - '):
                url = line[6:].strip()
            elif line.startswith('TI  - '):
                title = line[6:].strip()
            elif line.startswith('AN  - '):
                pmid = line[6:].strip()
            elif line.startswith('DO  - '):
                # Extract DOI
                doi = line[6:].strip()
                # Clean up DOI (remove "doi:" prefix if present, handle URLs)
                doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
                doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
                doi = doi.strip()
            elif line.startswith('C2  - '):
                pmc_text = line[6:].strip()
                pmc_match = re.search(r'PMC?(\d+)', pmc_text, re.IGNORECASE)
                if pmc_match:
                    pmc_id = pmc_match.group(1)
        
        # Include papers with label_id and at least one identifier (URL, PMID, or DOI)
        if label_id and (url or pmid or doi):
            papers.append({
                'label_id': label_id,
                'record_number': record_number or label_id,  # Use label_id as fallback if ID field missing
                'url': url,
                'title': title or 'Unknown',
                'pmid': pmid,
                'pmc_id': pmc_id,
                'doi': doi
            })
    
    return papers


def setup_driver(download_dir: Path):
    """Setup Chrome driver with download preferences."""
    chrome_options = Options()
    prefs = {
        'download.default_directory': str(download_dir.absolute()),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True,
        'plugins.always_open_pdf_externally': True,
        'profile.default_content_setting_values.automatic_downloads': 1,
        'profile.content_settings.exceptions.automatic_downloads.*.setting': 1
    }
    chrome_options.add_experimental_option('prefs', prefs)
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    
    service = get_chromedriver()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_window_size(1200, 800)
    
    return driver


def handle_cookie_popup(driver):
    """Dismiss cookie/consent popups that might block clicks."""
    cookie_selectors = [
        "//button[contains(text(), 'Accept')]",
        "//button[contains(text(), 'I Accept')]",
        "//button[contains(text(), 'Agree')]",
        "//button[contains(text(), 'OK')]",
        "//button[contains(text(), 'Close')]",
        "//button[contains(@id, 'accept')]",
        "//button[contains(@class, 'accept')]",
        "//*[@id='onetrust-accept-btn-handler']",
        "//*[@id='onetrust-close-btn-container']//button",
    ]
    for selector in cookie_selectors:
        try:
            buttons = driver.find_elements(By.XPATH, selector)
            for btn in buttons[:2]:
                try:
                    btn.click()
                    time.sleep(0.5)
                except:
                    pass
        except:
            pass


def download_pmc_pdf(driver, pmc_id: str, output_path: Path, timeout: int = 30):
    """Navigate to PMC article, click Download PDF, then click browser download button."""
    article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"
    
    # Step 1: Navigate to article page
    driver.get(article_url)
    time.sleep(4)
    
    # Handle any cookie popups first
    handle_cookie_popup(driver)
    time.sleep(1)
    
    # Step 2: Find and click "Download PDF" button on article page
    try:
        download_buttons = driver.find_elements(By.XPATH,
            "//button[contains(text(), 'Download PDF')] | "
            "//a[contains(text(), 'Download PDF')] | "
            "//a[contains(text(), 'PDF')] | "
            "//button[contains(@aria-label, 'Download PDF')] | "
            "//a[contains(@aria-label, 'Download PDF')]")
        
        if download_buttons:
            btn = download_buttons[0]
            # Scroll into view and use JavaScript click for reliability
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            time.sleep(0.5)
            try:
                btn.click()
            except:
                # Fallback to JavaScript click
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(5)  # Wait for PDF to load in viewer
            
            # Step 3: PDF should now be open in Chrome PDF viewer
            # Click the download button in top-right of PDF viewer
            try:
                window_size = driver.get_window_size()
                width = window_size['width']
                
                # Click in top-right area (where Chrome PDF viewer download button is)
                actions = ActionChains(driver)
                actions.move_by_offset(width - 80, 40).click().perform()
                time.sleep(3)
                
                # Also try JavaScript to find and click download button
                driver.execute_script('''
                    var buttons = document.querySelectorAll('button, a, [role="button"]');
                    for (var i = 0; i < buttons.length; i++) {
                        var btn = buttons[i];
                        var text = (btn.textContent || btn.getAttribute('aria-label') || btn.getAttribute('title') || '').toLowerCase();
                        if (text.includes('download') || text.includes('save')) {
                            btn.click();
                            break;
                        }
                    }
                ''')
                time.sleep(3)
                
            except Exception as e:
                print(f"    Warning: Could not click PDF viewer download button: {e}")
            
            # Step 4: Wait for download and rename file
            time.sleep(5)
            return True
        else:
            print(f"    Could not find Download PDF button on article page")
            return False
            
    except Exception as e:
        print(f"    Error navigating to PMC article: {e}")
        return False


def download_pubmed_paper(driver, pmid: str, output_path: Path):
    """Navigate to PubMed page, find PMC link, then download."""
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    driver.get(url)
    time.sleep(3)
    
    # Look for "Free PMC article" link
    try:
        pmc_links = driver.find_elements(By.XPATH,
            "//a[contains(text(), 'Free PMC article')] | "
            "//a[contains(@href, '/pmc/articles/')]")
        
        if pmc_links:
            pmc_href = pmc_links[0].get_attribute('href')
            pmc_match = re.search(r'/pmc/articles/(PMC\d+)', pmc_href)
            if pmc_match:
                pmc_id = pmc_match.group(1).replace('PMC', '')
                return download_pmc_pdf(driver, pmc_id, output_path)
    except Exception as e:
        print(f"    Error finding PMC link: {e}")
    
    return False


def download_via_doi(driver, doi: str, output_path: Path):
    """Navigate to DOI resolver and try to download PDF from publisher page."""
    doi_url = f"https://dx.doi.org/{doi}"
    driver.get(doi_url)
    time.sleep(5)  # Wait for redirect to publisher page
    
    # Handle cookie popups first
    handle_cookie_popup(driver)
    time.sleep(1)
    
    # Try to find PDF download links/buttons
    try:
        pdf_links = driver.find_elements(By.XPATH,
            "//a[contains(@href, '.pdf')] | "
            "//a[contains(@href, '/pdf/')] | "
            "//a[contains(text(), 'PDF')] | "
            "//a[contains(text(), 'Download PDF')] | "
            "//button[contains(text(), 'PDF')] | "
            "//button[contains(text(), 'Download PDF')]")
        
        if pdf_links:
            # Try clicking the first PDF link with better handling
            link = pdf_links[0]
            driver.execute_script("arguments[0].scrollIntoView(true);", link)
            time.sleep(0.5)
            try:
                link.click()
            except:
                # Fallback to JavaScript click
                driver.execute_script("arguments[0].click();", link)
            time.sleep(5)
            
            # If PDF opened in viewer, try to click download button
            try:
                window_size = driver.get_window_size()
                width = window_size['width']
                actions = ActionChains(driver)
                actions.move_by_offset(width - 80, 40).click().perform()
                time.sleep(3)
            except:
                pass
            
            return True
    except Exception as e:
        print(f"    Error downloading via DOI: {e}")
    
    return False


def count_ris_references(ris_file_path: Path) -> int:
    """
    Count the number of references in a RIS file.
    """
    if not ris_file_path.exists():
        return 0
    
    try:
        with open(ris_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by ER  -  markers
        entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
        # Filter out empty entries
        return len([e for e in entries if e.strip()])
    except:
        return 0


def find_original_ris_file() -> Optional[Path]:
    """
    Find the original RIS file (the one the first scrape script would have read).
    Looks for missing_papers*.txt files in missing_papers/still_missing/ directory.
    """
    still_missing_dir = Path("missing_papers/still_missing")
    if not still_missing_dir.exists():
        return None
    
    # Pattern to match missing_papers*.txt files
    pattern = re.compile(r'^missing_papers(\d*)\.txt$')
    
    # Check for base file first
    base_file = still_missing_dir / "missing_papers.txt"
    if base_file.exists():
        return base_file
    
    # Find all numbered files
    numbered_files = []
    for file_path in still_missing_dir.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                number_str = match.group(1)
                number = int(number_str) if number_str else 0
                numbered_files.append((number, file_path))
    
    if numbered_files:
        # Return highest numbered file
        numbered_files.sort(key=lambda x: x[0], reverse=True)
        return numbered_files[0][1]
    
    return None


def get_import_map_filename(downloads: int, input_refs: int, original_refs: int, import_ids_dir: Path) -> str:
    """
    Generate import map filename in format: import_{downloads}_of_{input_refs}_of_{original_refs}_third_scrape.txt
    """
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    return f"import_{downloads}_of_{input_refs}_of_{original_refs}_third_scrape.txt"


def rename_downloaded_file(download_dir: Path, label_id: str, timeout: int = 10):
    """Wait for download to complete and rename to label_id.pdf"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Look for recently downloaded PDF files
        pdf_files = list(download_dir.glob('*.pdf'))
        for pdf_file in pdf_files:
            # Check if file was modified recently (within last 10 seconds)
            if time.time() - pdf_file.stat().st_mtime < 10:
                # Rename to label_id.pdf
                target_path = download_dir / f"{label_id}.pdf"
                if target_path.exists() and target_path != pdf_file:
                    # Already have the correct file
                    if pdf_file != target_path:
                        pdf_file.unlink()  # Delete duplicate
                    return True
                else:
                    shutil.move(str(pdf_file), str(target_path))
                    return True
        time.sleep(1)
    
    return False


def main():
    ris_file = Path('missing_papers/still_missing/missing_after_second_scrape.txt')
    output_dir = Path('found_papers/downloaded_papers/third_scrape_AI_agent')
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_file = output_dir / 'label_to_filename.txt'
    
    # Import map directory
    import_ids_dir = Path("found_papers/import_IDs")
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    
    # Use temporary filename during execution, will rename at end with final counts
    import_map_temp_path = import_ids_dir / "import_map_temp.txt"
    import_map_path = import_map_temp_path  # Will be updated at end
    
    # Initialize import map file (no header)
    with open(import_map_path, 'w', encoding='utf-8') as f:
        pass  # File will be created, entries appended later
    
    print("Parsing RIS file...")
    papers = parse_ris_papers(str(ris_file), limit=None)  # Process all papers
    print(f"Found {len(papers)} papers to process\n")
    
    # Get counts for final import map filename
    input_refs = len(papers)  # Papers in current RIS file
    original_ris_file = find_original_ris_file()
    if original_ris_file:
        original_refs = count_ris_references(original_ris_file)
    else:
        original_refs = input_refs  # Fallback: use input_refs if original not found
    
    print("Setting up browser...")
    driver = setup_driver(output_dir)
    
    mapping_fp = open(mapping_file, 'w', encoding='utf-8')
    mapping_fp.write("# label_id|filename|title|status|error_reason\n")
    
    successful = []  # Track successful downloads for import map
    
    try:
        for i, paper in enumerate(papers, 1):
            label_id = paper['label_id']
            record_number = paper['record_number']
            title = paper['title'][:60] + '...' if len(paper['title']) > 60 else paper['title']
            output_path = output_dir / f"{label_id}.pdf"
            
            print(f"[{i}/{len(papers)}] Label {label_id}: {title}")
            
            # Check if already exists
            if output_path.exists() and output_path.stat().st_size > 1024:
                print(f"  ✓ Already exists\n")
                mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success|already_exists\n")
                mapping_fp.flush()
                successful.append((record_number, output_path))
                continue
            
            success = False
            error = "can't get file"
            
            # Try PubMed -> PMC path
            if paper.get('pmid'):
                print(f"  Trying PubMed (PMID: {paper['pmid']})...")
                success = download_pubmed_paper(driver, paper['pmid'], output_path)
            
            # Try direct PMC
            if not success and paper.get('pmc_id'):
                print(f"  Trying PMC (PMC{paper['pmc_id']})...")
                success = download_pmc_pdf(driver, paper['pmc_id'], output_path)
            
            # Try DOI-based download
            if not success and paper.get('doi'):
                print(f"  Trying DOI ({paper['doi']})...")
                success = download_via_doi(driver, paper['doi'], output_path)
            
            # Rename downloaded file if download succeeded
            if success:
                if rename_downloaded_file(output_dir, label_id):
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        print(f"  ✓ Downloaded: {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                        mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success|\n")
                        successful.append((record_number, output_path))
                        success = True
                    else:
                        success = False
                        error = "download failed - file not found or too small"
                else:
                    success = False
                    error = "download failed - could not rename file"
            
            if not success:
                print(f"  ✗ Failed: {error}\n")
                mapping_fp.write(f"{label_id}||{paper['title']}|failed|{error}\n")
            
            mapping_fp.flush()
            time.sleep(2)  # Small delay between papers
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    finally:
        mapping_fp.close()
        driver.quit()
        print(f"\nCompleted. Mapping saved to: {mapping_file}")
        
        # Write import map entries for successful downloads
        downloads_count = len(successful)
        if downloads_count > 0:
            with open(import_map_path, 'a', encoding='utf-8') as f:
                for record_number, output_path in successful:
                    absolute_path = os.path.abspath(output_path)
                    f.write(f"{record_number}\t{absolute_path}\n")
        
        # Rename import map file with final counts
        final_import_map_filename = get_import_map_filename(downloads_count, input_refs, original_refs, import_ids_dir)
        final_import_map_path = import_ids_dir / final_import_map_filename
        
        if import_map_path.exists() and downloads_count > 0:
            import_map_path.rename(final_import_map_path)
            import_map_path = final_import_map_path
            print(f"\nImport map file: {import_map_path}")
            print(f"({downloads_count} entries written to import map)")
        elif import_map_path.exists():
            # No successful downloads, delete temp file
            import_map_path.unlink()


if __name__ == '__main__':
    main()
