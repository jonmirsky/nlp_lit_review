#!/usr/bin/env python3
"""
Download PDFs using Selenium browser automation - V2
This version includes:
- Fixed download detection (checks download directory for new files)
- DOI support (tries DOI first, then falls back to PMID/PMC)
- Better success/failure reporting

Requirements:
    pip install selenium webdriver-manager
    Also need Chrome browser installed.
"""

import re
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


def parse_ris_file(filepath: str) -> List[Dict[str, str]]:
    """Parse RIS file into list of reference dictionaries, including DOIs and Record Numbers."""
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
        
        if pmid or doi:  # Accept if we have either PMID or DOI
            references.append({
                'pmid': pmid,
                'title': title or 'Unknown Title',
                'pmc_id': pmc_id,
                'doi': doi,
                'record_number': record_number,  # EndNote Record Number
                'ris_text': entry + '\nER  - \n'
            })
    
    return references


def get_next_import_map_filename(import_ids_dir: Path) -> str:
    """
    Get the next import_map filename with intelligent numbering.
    Checks existing files and returns the next number.
    Example: if import_map3.txt and import_map12.txt exist, returns 'import_map13.txt'
    """
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    
    # Pattern to match import_map#.txt files
    pattern = re.compile(r'^import_map(\d+)\.txt$')
    
    max_number = 0
    
    # Check all files in the directory
    for file_path in import_ids_dir.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                number = int(match.group(1))
                max_number = max(max_number, number)
    
    # Return next number
    next_number = max_number + 1
    return f"import_map{next_number}.txt"


def get_downloaded_files(directory: Path) -> Set[str]:
    """Get set of all PDF files currently in download directory."""
    return {f.name for f in directory.glob('*.pdf')}


def get_most_recent_downloads_file(downloads_dir: Path) -> Optional[tuple[str, float]]:
    """
    Get the most recent PDF file in Downloads folder.
    
    Returns:
        Tuple of (filename, modification_time) of most recent PDF, or None if no PDFs found
    """
    pdf_files = list(downloads_dir.glob('*.pdf'))
    if not pdf_files:
        return None
    
    # Find the most recent file by modification time
    most_recent = max(pdf_files, key=lambda f: f.stat().st_mtime)
    return (most_recent.name, most_recent.stat().st_mtime)


def wait_for_download(directory: Path, initial_files: Set[str], expected_filename: str = None, timeout: int = 15) -> Optional[Path]:
    """
    Wait for a new PDF file to appear in the download directory.
    
    Args:
        directory: Directory to watch for downloads
        initial_files: Set of filenames that existed before download started
        expected_filename: Optional expected filename to look for specifically
        timeout: Maximum time to wait in seconds
    
    Returns:
        Path to the downloaded file if found, None otherwise
    """
    start_time = time.time()
    
    # If we have an expected filename, check if it already exists
    if expected_filename:
        expected_path = directory / expected_filename
        if expected_path.exists() and expected_path.stat().st_size > 1024:
            # File already exists and has content, return it
            return expected_path
    
    while time.time() - start_time < timeout:
        current_files = get_downloaded_files(directory)
        new_files = current_files - initial_files
        
        if new_files:
            # If we have an expected filename, prioritize it
            if expected_filename and expected_filename in new_files:
                file_path = directory / expected_filename
            else:
                # Return the most recent new file
                new_file = sorted(new_files)[-1]
                file_path = directory / new_file
            
            # Wait a bit more to ensure download is complete
            time.sleep(1)
            
            # Check file size is stable (download complete)
            if file_path.exists():
                initial_size = file_path.stat().st_size
                time.sleep(0.5)
                if file_path.stat().st_size == initial_size and initial_size > 1024:
                    return file_path
        
        # Also check if expected file appeared (in case it was created between checks)
        if expected_filename:
            expected_path = directory / expected_filename
            if expected_path.exists() and expected_path.stat().st_size > 1024:
                return expected_path
        
        time.sleep(0.5)
    
    # Final check: maybe the file was downloaded but we missed it
    if expected_filename:
        expected_path = directory / expected_filename
        if expected_path.exists() and expected_path.stat().st_size > 1024:
            return expected_path
    
    return None


def setup_driver(headless: bool = False, download_dir: str = None) -> webdriver.Chrome:
    """Set up Chrome driver with download preferences."""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument('--headless')
    
    # Set download preferences
    # Default to found_papers/downloaded_papers if not specified
    if download_dir:
        download_path = str(download_dir)
    else:
        download_path = str(Path.cwd() / "found_papers" / "downloaded_papers")
    
    prefs = {
        "download.default_directory": download_path,
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


def download_via_doi_selenium(driver: webdriver.Chrome, doi: str, output_path: Path, use_library: bool = False) -> None:
    """
    Attempt to download PDF via DOI using Selenium.
    Success is determined by Downloads folder tracking, not by this function.
    """
    try:
        # Check if file already exists (from previous download attempt)
        if output_path.exists() and output_path.stat().st_size > 1024:
            return
        
        # Method 1: Try DOI resolver (dx.doi.org)
        if use_library:
            # Access through library proxy
            doi_url = f"https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/doi/{doi}"
        else:
            doi_url = f"https://dx.doi.org/{doi}"
        
        driver.get(doi_url)
        time.sleep(4)  # Wait for redirect to publisher
        
        # Check if we landed on a publisher page with PDF
        current_url = driver.current_url.lower()
        page_source = driver.page_source.lower()
        
        # Look for PDF download links
        pdf_selectors = [
            "//a[contains(@href, '.pdf')]",
            "//a[contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'Full Text')]",
            "//a[contains(@href, 'fulltext')]",
            "//a[contains(@href, 'download')]",
            "//button[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download')]",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:5]:  # Try first few
                    try:
                        # Try clicking the element
                        element.click()
                        time.sleep(3)
                        
                        # Download attempted - success will be detected via Downloads tracking
                        time.sleep(2)  # Give download time to start
                        return
                    except Exception:
                        # Try getting href if it's a link
                        try:
                            href = element.get_attribute('href')
                            if href:
                                driver.get(href)
                                time.sleep(2)  # Give download time to start
                                return
                        except Exception:
                            continue
            except Exception:
                continue
        
        # Download attempted - success will be detected via Downloads tracking
        time.sleep(2)  # Give download time to start
        return
        
    except Exception as e:
        # Download failed - will be detected by Downloads tracking
        return


def download_via_pmc_selenium(driver: webdriver.Chrome, pmc_id: str, output_path: Path) -> None:
    """Attempt to download PDF from PMC using Selenium. Success determined by Downloads tracking."""
    try:
        # Check if file already exists (from previous download attempt)
        if output_path.exists() and output_path.stat().st_size > 1024:
            return
        
        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
        driver.get(url)
        time.sleep(4)  # Wait for page load
        
        # Check if we got a PDF or error page
        page_source = driver.page_source.lower()
        
        # If redirected to error page or access denied
        if 'access denied' in page_source or '403' in page_source or 'not available' in page_source:
            return False
        
        # Download attempted - success will be detected via Downloads tracking
        time.sleep(2)  # Give download time to start
        
        # Try to find and click download link if present
        try:
            download_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf') or contains(text(), 'Download') or contains(text(), 'PDF')]")
            for link in download_links[:3]:
                try:
                    link.click()
                    time.sleep(2)  # Give download time to start
                    return
                except:
                    continue
        except:
            pass
        
        return
        
    except Exception as e:
        # Download failed - will be detected by Downloads tracking
        return


def download_via_pubmed_selenium(driver: webdriver.Chrome, pmid: str, output_path: Path, use_library: bool = False) -> None:
    """Attempt to download PDF via PubMed page using Selenium. Success determined by Downloads tracking."""
    try:
        # Check if file already exists (from previous download attempt)
        if output_path.exists() and output_path.stat().st_size > 1024:
            return
        
        if use_library:
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
                for link in links[:5]:
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
                                        
                                        # Download attempted - success will be detected via Downloads tracking
                                        time.sleep(2)  # Give download time to start
                                        driver.close()
                                        driver.switch_to.window(driver.window_handles[0])
                                        return
                                except:
                                    continue
                            
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                    except:
                        continue
            except:
                continue
        
        return
        
    except Exception as e:
        # Download failed - will be detected by Downloads tracking
        return


def main():
    """Main execution function."""
    # Ask user if they want to manually specify RIS file
    manual_input = input("Would you like to enter RIS file name manually? If not, I will automate. (y/n, default=n): ").strip().lower()
    
    if manual_input == 'y':
        ris_file_input = input("Enter RIS file name or path (relative to missing_papers/still_missing/): ").strip()
        # Build path - if it starts with archive/, use that, otherwise assume it's in still_missing/
        if ris_file_input.startswith('archive/'):
            ris_file = Path("missing_papers/still_missing") / ris_file_input
        else:
            ris_file = Path("missing_papers/still_missing") / ris_file_input
        
        if not ris_file.exists():
            print(f"ERROR: RIS file not found: {ris_file}")
            return
        print(f"Using RIS file: {ris_file}")
    else:
        # Default automated behavior
        ris_file = Path("missing_papers/still_missing/missing_papers.txt")
        if not ris_file.exists():
            print(f"ERROR: Default RIS file not found: {ris_file}")
            return
        print(f"Using default RIS file: {ris_file}")
    output_dir = Path("found_papers/downloaded_papers/first_scrape")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Import map directory
    import_ids_dir = Path("found_papers/import_IDs")
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    
    # Get next import map filename
    import_map_filename = get_next_import_map_filename(import_ids_dir)
    import_map_path = import_ids_dir / import_map_filename
    
    # Initialize import map file (no header)
    with open(import_map_path, 'w', encoding='utf-8') as f:
        pass  # File will be created, entries appended later
    
    print("="*60)
    print("PDF DOWNLOADER V2 - Selenium Browser Automation")
    print("="*60)
    print("\nThis script will open a Chrome browser window.")
    print("Features:")
    print("  - DOI support (tries DOI first if available)")
    print("  - Fixed download detection")
    print("  - Library proxy access support")
    print("\nYou may need to:")
    print("1. Log into HSHSL library if prompted")
    print("2. Allow downloads in the browser")
    print("3. Let the script run (it will control the browser)")
    print("\nPress Enter to start...")
    input()
    
    use_library = input("\nUse HSHSL library access? (y/n, default=y): ").strip().lower()
    use_library = use_library != 'n'
    
    print(f"\nParsing RIS file: {ris_file}")
    references = parse_ris_file(str(ris_file))
    print(f"Found {len(references)} references")
    
    # Count how many have DOIs
    refs_with_doi = sum(1 for ref in references if ref.get('doi'))
    print(f"  - {refs_with_doi} references have DOIs")
    print(f"  - {len(references) - refs_with_doi} references have only PMIDs\n")
    
    # Ask about pilot mode
    pilot_mode = input("Run in PILOT mode? (only processes test paper) (y/n, default=n): ").strip().lower()
    pilot_mode = pilot_mode == 'y'
    
    if pilot_mode:
        pilot_title = "Identification of suspected tuberculosis patients based on natural language processing of chest radiograph reports"
        print(f"\n⚠️  PILOT MODE ENABLED - Searching for test paper")
        print(f"  Looking for: {pilot_title[:60]}...")
        
        # Find the reference with the matching title
        pilot_reference = None
        for ref in references:
            if ref.get('title') == pilot_title:
                pilot_reference = ref
                break
        
        if pilot_reference:
            references = [pilot_reference]  # Only keep the pilot reference
            print(f"  ✓ Found test paper (Record {pilot_reference.get('record_number', 'N/A')})")
            print(f"  Processing 1 reference (pilot mode)\n")
        else:
            print(f"  ✗ ERROR: Test paper not found in RIS file!")
            print(f"  Please check that the title matches exactly.")
            print(f"  Exiting...\n")
            return
    else:
        print(f"\nProcessing all {len(references)} references\n")
    
    # Setup driver
    print("Setting up Chrome browser...")
    print(f"  Download directory: {output_dir.absolute()}")
    driver = setup_driver(headless=False, download_dir=str(output_dir))
    
    successful = []
    failed = []
    
    # Initialize Downloads tracking
    downloads_dir = Path.home() / "Downloads"
    last_seen_file = get_most_recent_downloads_file(downloads_dir)
    if last_seen_file:
        print(f"Initial Downloads state: Most recent file is '{last_seen_file[0]}' (timestamp: {last_seen_file[1]})")
    else:
        print("Initial Downloads state: No PDF files found")
    print()
    
    try:
        for i, ref in enumerate(references, 1):
            pmid = ref.get('pmid')
            title = ref['title']
            pmc_id = ref.get('pmc_id')
            doi = ref.get('doi')
            record_number = ref.get('record_number')
            
            # Use Record Number for filename, fallback to index if not available
            if record_number:
                filename = f"{record_number}.pdf"
            else:
                # Fallback if no record number (shouldn't happen, but handle gracefully)
                print(f"[{i}/{len(references)}] WARNING: No record number found, using index {i}")
                filename = f"record_{i}.pdf"
            
            output_path = output_dir / filename
            
            print(f"[{i}/{len(references)}] ", end='')
            if record_number:
                print(f"Record {record_number} ", end='')
            if doi:
                print(f"DOI {doi[:30]}... ", end='')
            elif pmid:
                print(f"PMID {pmid}... ", end='')
            else:
                print(f"{title[:30]}... ", end='')
            
            # Record current most recent file BEFORE download attempt
            file_before = get_most_recent_downloads_file(downloads_dir)
            
            # Attempt download (but we'll determine success by tracking Downloads folder)
            download_attempted = False
            
            # Strategy 1: Try DOI first (fastest, most direct)
            if doi:
                download_via_doi_selenium(driver, doi, output_path, use_library)
                download_attempted = True
            
            # Strategy 2: Try PMC if available
            if not download_attempted and pmc_id:
                download_via_pmc_selenium(driver, pmc_id, output_path)
                download_attempted = True
            
            # Strategy 3: Try PubMed/library access
            if not download_attempted and pmid:
                download_via_pubmed_selenium(driver, pmid, output_path, use_library)
                download_attempted = True
            
            # Wait a bit for download to complete
            time.sleep(3)
            
            # Check Downloads folder: Did a new file appear?
            file_after = get_most_recent_downloads_file(downloads_dir)
            
            download_success = False
            method_used = ""
            downloaded_file_path = None
            
            # Determine success: Is the most recent file different from before?
            if file_after and file_before:
                # Compare filename and timestamp
                if file_after[0] != file_before[0] or file_after[1] > file_before[1]:
                    # New file appeared - SUCCESS!
                    download_success = True
                    method_used = "Download detected"
                    downloaded_file_path = downloads_dir / file_after[0]
            elif file_after and not file_before:
                # No file before, but file exists now - SUCCESS!
                download_success = True
                method_used = "Download detected"
                downloaded_file_path = downloads_dir / file_after[0]
            elif not file_after and file_before:
                # File existed before but not now (unlikely) - check if it's in target location
                if output_path.exists() and output_path.stat().st_size > 1024:
                    download_success = True
                    method_used = "File in target location"
            
            # Also check if file already exists in target location (direct download worked)
            if not download_success and output_path.exists() and output_path.stat().st_size > 1024:
                download_success = True
                method_used = "File in target location"
            
            if download_success:
                # Move file from Downloads to target location if needed
                if downloaded_file_path and downloaded_file_path.exists():
                    try:
                        downloaded_file_path.rename(output_path)
                        method_used = "Moved from Downloads"
                    except Exception as e:
                        # File might already be in target location or move failed
                        if not output_path.exists():
                            print(f"  Warning: Could not move file: {e}")
                
                print(f"✓ DOWNLOADED ({method_used})")
                successful.append(ref)
                
                # Append to import map file
                if record_number:
                    absolute_path = os.path.abspath(output_path)
                    with open(import_map_path, 'a', encoding='utf-8') as f:
                        f.write(f"{record_number}\t{absolute_path}\n")
                
                # Update last_seen_file for next iteration
                last_seen_file = file_after
                time.sleep(1)
            else:
                print("✗ FAILED")
                failed.append(ref)
                # Update last_seen_file even on failure (for next iteration)
                if file_after:
                    last_seen_file = file_after
                time.sleep(0.5)
    
    finally:
        print("\nClosing browser...")
        driver.quit()
    
    # Write failed references
    if failed:
        still_missing_path = Path("missing_papers/still_missing/still_missing.txt")
        still_missing_path.parent.mkdir(parents=True, exist_ok=True)
        with open(still_missing_path, 'w', encoding='utf-8') as f:
            for ref in failed:
                f.write(ref['ris_text'])
                f.write('\n')
        print(f"\nFailed downloads written to: {still_missing_path}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    if pilot_mode:
        print(f"  ⚠️  PILOT MODE - Only processed test paper")
    print(f"  Total references processed: {len(references)}")
    print(f"  Successfully downloaded: {len(successful)}")
    print(f"  Failed: {len(failed)}")
    if len(references) > 0:
        print(f"  Success rate: {len(successful)/len(references)*100:.1f}%")
    print(f"\n  Import map file: {import_map_path}")
    print(f"  ({len(successful)} entries written to import map)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

