#!/usr/bin/env python3
"""
Download PDFs using Selenium browser automation - DOI Enhanced V2
This version includes:
- Enhanced DOI support (searches PubMed by DOI first, then tries publisher pages)
- Fixed download detection (checks download directory for new files)
- Better success/failure reporting
- Improved publisher page handling

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


def find_input_ris_file() -> Optional[Path]:
    """
    Find input RIS file in missing_papers/still_missing/ directory.
    Priority:
    1. missing_after_first_scrape*.txt files (prefers base file, then highest numbered)
    2. still_missing*.txt files (prefers base file, then highest numbered)
    
    Returns:
        Path to the file, or None if not found
    """
    still_missing_dir = Path("missing_papers/still_missing")
    if not still_missing_dir.exists():
        return None
    
    # First, try to find missing_after_first_scrape*.txt files
    first_scrape_pattern = re.compile(r'^missing_after_first_scrape(\d*)\.txt$')
    
    # Check for base file first
    base_file = still_missing_dir / "missing_after_first_scrape.txt"
    if base_file.exists():
        return base_file
    
    # Find all numbered missing_after_first_scrape files
    first_scrape_files = []
    for file_path in still_missing_dir.iterdir():
        if file_path.is_file():
            match = first_scrape_pattern.match(file_path.name)
            if match:
                number_str = match.group(1)
                number = int(number_str) if number_str else 0
                first_scrape_files.append((number, file_path))
    
    if first_scrape_files:
        # Return highest numbered file
        first_scrape_files.sort(key=lambda x: x[0], reverse=True)
        return first_scrape_files[0][1]
    
    # Fall back to still_missing*.txt files
    still_missing_pattern = re.compile(r'^still_missing(\d*)\.txt$')
    
    # Check for base file first
    base_file = still_missing_dir / "still_missing.txt"
    if base_file.exists():
        return base_file
    
    # Find all numbered files
    numbered_files = []
    for file_path in still_missing_dir.iterdir():
        if file_path.is_file():
            match = still_missing_pattern.match(file_path.name)
            if match:
                number_str = match.group(1)
                number = int(number_str) if number_str else 0
                numbered_files.append((number, file_path))
    
    if numbered_files:
        # Return highest numbered file
        numbered_files.sort(key=lambda x: x[0], reverse=True)
        return numbered_files[0][1]
    
    return None


def parse_ris_file(filepath: str) -> List[Dict[str, str]]:
    """Parse RIS file into list of reference dictionaries, including DOIs, URLs, and metadata."""
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
        url = None  # UR field - direct URL to paper
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
            elif line.startswith('UR  - '):
                # URL field - direct link to paper
                url = line[6:].strip()
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
        if pmid or doi or url or title:
            references.append({
                'pmid': pmid,
                'title': title or 'Unknown Title',
                'pmc_id': pmc_id,
                'doi': doi,
                'record_number': record_number,
                'url': url,
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


def search_pubmed_by_doi(driver: webdriver.Chrome, doi: str, use_library: bool = False) -> Optional[str]:
    """
    Search PubMed by DOI to get the PMID.
    This is more reliable than trying publisher pages directly.
    
    Returns:
        PMID if found, None otherwise
    """
    try:
        if use_library:
            search_url = f"https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/pubmed/?term={doi}"
        else:
            search_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={doi}"
        
        driver.get(search_url)
        time.sleep(3)  # Wait for search results
        
        # Check if we got a single result page or search results page
        current_url = driver.current_url.lower()
        page_source = driver.page_source.lower()
        
        # If we're on a single article page (pubmed.ncbi.nlm.nih.gov/XXXXX/)
        if '/pubmed/' in current_url and current_url.count('/') >= 4:
            # Extract PMID from URL
            pmid_match = re.search(r'/pubmed/(\d+)', current_url)
            if pmid_match:
                return pmid_match.group(1)
        
        # Try to find PMID in the page source
        pmid_match = re.search(r'pmid[:\s]*(\d+)', page_source, re.IGNORECASE)
        if pmid_match:
            return pmid_match.group(1)
        
        # Try to find a link to a specific PubMed page
        try:
            # Look for links to PubMed article pages
            article_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/pubmed/')]")
            for link in article_links[:5]:
                href = link.get_attribute('href')
                if href:
                    pmid_match = re.search(r'/pubmed/(\d+)', href)
                    if pmid_match:
                        return pmid_match.group(1)
        except:
            pass
        
        return None
        
    except Exception as e:
        return None


def download_via_doi_selenium(driver: webdriver.Chrome, doi: str, output_path: Path, use_library: bool = False) -> Optional[str]:
    """
    Attempt to download PDF via DOI using Selenium with improved strategies.
    
    Strategy 1: Search PubMed by DOI to get PMID, then use PubMed download (most reliable)
    Strategy 2: Try DOI resolver to publisher page with enhanced PDF detection
    
    Returns:
        PMID if found via PubMed search (so caller can use PubMed download method), None otherwise
    """
    try:
        # Check if file already exists (from previous download attempt)
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None
        
        # Strategy 1: Try to find PMID via PubMed search by DOI (most reliable for PubMed papers)
        pmid = search_pubmed_by_doi(driver, doi, use_library)
        if pmid:
            # Found PMID - return it so caller can use the proven PubMed download method
            return pmid
        
        # Strategy 2: Try DOI resolver to publisher page (if PubMed search didn't work)
        if use_library:
            doi_url = f"https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/doi/{doi}"
        else:
            doi_url = f"https://dx.doi.org/{doi}"
        
        driver.get(doi_url)
        time.sleep(8)  # Increased wait time for redirect to publisher (was 4s)
        
        # Check if we landed on a publisher page with PDF
        current_url = driver.current_url.lower()
        page_source = driver.page_source.lower()
        
        # Detect paywalls and access restrictions
        if any(term in page_source for term in ['paywall', 'access denied', 'subscription required', 
                                                 'sign in', 'login required', '403', 'forbidden']):
            # Hit a paywall - return None to indicate failure
            return None
        
        # Enhanced PDF link detection with more selectors
        pdf_selectors = [
            # Direct PDF links
            "//a[contains(@href, '.pdf')]",
            "//a[contains(@href, '/pdf/')]",
            "//a[contains(@href, 'download') and contains(@href, '.pdf')]",
            # Text-based selectors
            "//a[contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'Full Text PDF')]",
            "//a[contains(text(), 'Full Text')]",
            "//a[contains(text(), 'Download')]",
            # Href patterns
            "//a[contains(@href, 'fulltext')]",
            "//a[contains(@href, 'full-text')]",
            "//a[contains(@href, 'download')]",
            # Buttons
            "//button[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download')]",
            "//button[contains(text(), 'Download PDF')]",
            # More specific patterns
            "//a[contains(@class, 'pdf')]",
            "//a[contains(@class, 'download')]",
            "//*[@id='pdf-link']",
            "//*[@id='download-pdf']",
        ]
        
        # Try each selector
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:5]:  # Try first few matches
                    try:
                        # Scroll element into view
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        
                        # Try clicking the element
                        element.click()
                        time.sleep(4)  # Increased wait after click
                        
                        # Download attempted - success will be detected via Downloads tracking
                        time.sleep(2)
                        return None  # Return None since we tried publisher page
                    except Exception:
                        # Try getting href if it's a link
                        try:
                            href = element.get_attribute('href')
                            if href and ('.pdf' in href.lower() or 'download' in href.lower()):
                                # Try direct navigation to PDF
                                driver.get(href)
                                time.sleep(4)  # Wait for PDF to load/download
                                return None
                        except Exception:
                            continue
            except Exception:
                continue
        
        # Try to find PDF in iframes (some publishers use iframes)
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes[:3]:
                try:
                    driver.switch_to.frame(iframe)
                    pdf_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf')]")
                    for link in pdf_links[:3]:
                        try:
                            href = link.get_attribute('href')
                            if href:
                                driver.get(href)
                                time.sleep(4)
                                driver.switch_to.default_content()
                                return None
                        except:
                            continue
                    driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()
                    continue
        except:
            pass
        
        # Try constructing direct PDF URL patterns (common publisher patterns)
        current_url_lower = current_url.lower()
        pdf_url_patterns = [
            current_url + '.pdf',
            current_url.replace('/article/', '/pdf/'),
            current_url.replace('/view/', '/download/'),
            current_url + '/pdf',
        ]
        
        for pdf_url in pdf_url_patterns:
            try:
                driver.get(pdf_url)
                time.sleep(3)
                # Check if we got a PDF (content-type or file extension)
                if '.pdf' in driver.current_url.lower() or 'application/pdf' in driver.page_source.lower():
                    time.sleep(2)
                    return None
            except:
                continue
        
        # Download attempted - success will be detected via Downloads tracking
        time.sleep(2)
        return None
        
    except Exception as e:
        # Download failed - will be detected by Downloads tracking
        return None


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


def detect_publisher_type(url: str) -> str:
    """Detect publisher type from URL."""
    url_lower = url.lower()
    if 'pmc.ncbi.nlm.nih.gov' in url_lower or 'pubmed' in url_lower:
        return 'pmc'
    elif 'ieeexplore.ieee.org' in url_lower:
        return 'ieee'
    elif 'sciencedirect.com' in url_lower:
        return 'sciencedirect'
    elif 'springer.com' in url_lower or 'link.springer.com' in url_lower:
        return 'springer'
    elif 'wiley.com' in url_lower or 'onlinelibrary.wiley.com' in url_lower:
        return 'wiley'
    elif 'iopscience.iop.org' in url_lower:
        return 'iop'
    elif 'nature.com' in url_lower:
        return 'nature'
    elif 'plos.org' in url_lower:
        return 'plos'
    elif 'bmj.com' in url_lower:
        return 'bmj'
    elif 'tandfonline.com' in url_lower:
        return 'taylor_francis'
    else:
        return 'generic'


def download_from_pmc_url(driver: webdriver.Chrome, url: str) -> None:
    """Download PDF from PMC URL."""
    try:
        # Convert article URL to PDF URL
        if '/articles/' in url:
            pmc_id_match = re.search(r'/articles/(PMC\d+)', url)
            if pmc_id_match:
                pmc_id = pmc_id_match.group(1).replace('PMC', '')
                pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
                driver.get(pdf_url)
                time.sleep(4)
                return
        # If already a PDF URL, just navigate
        if '/pdf/' in url:
            driver.get(url)
            time.sleep(4)
    except:
        pass


def download_from_ieee_url(driver: webdriver.Chrome, url: str) -> None:
    """Download PDF from IEEE Xplore."""
    try:
        driver.get(url)
        time.sleep(6)  # Wait for page load
        
        # Look for PDF download button/link
        pdf_selectors = [
            "//a[contains(@href, '.pdf')]",
            "//a[contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download PDF')]",
            "//button[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download')]",
            "//a[contains(@class, 'pdf')]",
            "//*[@id='pdf-download']",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:3]:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        element.click()
                        time.sleep(4)
                        return
                    except:
                        href = element.get_attribute('href')
                        if href and '.pdf' in href.lower():
                            driver.get(href)
                            time.sleep(4)
                            return
            except:
                continue
    except:
        pass


def download_from_sciencedirect_url(driver: webdriver.Chrome, url: str) -> None:
    """Download PDF from ScienceDirect."""
    try:
        driver.get(url)
        time.sleep(6)
        
        # Try to find PDF download link
        pdf_selectors = [
            "//a[contains(@href, '.pdf')]",
            "//a[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download PDF')]",
            "//*[@id='pdfLink']",
            "//a[contains(@class, 'pdf-download')]",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:3]:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        element.click()
                        time.sleep(4)
                        return
                    except:
                        href = element.get_attribute('href')
                        if href:
                            driver.get(href)
                            time.sleep(4)
                            return
            except:
                continue
        
        # Try constructing PDF URL pattern
        if '/article/pii/' in url:
            pdf_url = url.replace('/article/pii/', '/article/pii/') + '/pdfft'
            try:
                driver.get(pdf_url)
                time.sleep(4)
            except:
                pass
    except:
        pass


def download_from_springer_url(driver: webdriver.Chrome, url: str) -> None:
    """Download PDF from Springer."""
    try:
        driver.get(url)
        time.sleep(6)
        
        pdf_selectors = [
            "//a[contains(@href, '.pdf')]",
            "//a[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download PDF')]",
            "//a[contains(@data-track-action, 'download')]",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:3]:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        element.click()
                        time.sleep(4)
                        return
                    except:
                        href = element.get_attribute('href')
                        if href:
                            driver.get(href)
                            time.sleep(4)
                            return
            except:
                continue
    except:
        pass


def download_from_wiley_url(driver: webdriver.Chrome, url: str) -> None:
    """Download PDF from Wiley Online Library."""
    try:
        driver.get(url)
        time.sleep(6)
        
        pdf_selectors = [
            "//a[contains(@href, '.pdf')]",
            "//a[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download PDF')]",
            "//a[contains(@data-article-url, 'pdf')]",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:3]:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        element.click()
                        time.sleep(4)
                        return
                    except:
                        href = element.get_attribute('href')
                        if href:
                            driver.get(href)
                            time.sleep(4)
                            return
            except:
                continue
    except:
        pass


def download_from_generic_url(driver: webdriver.Chrome, url: str) -> None:
    """Download PDF from generic publisher using common patterns."""
    try:
        driver.get(url)
        time.sleep(6)
        
        # Check for paywalls
        page_source = driver.page_source.lower()
        if any(term in page_source for term in ['paywall', 'access denied', 'subscription required', 
                                                 'sign in', 'login required', '403', 'forbidden']):
            return
        
        # Try common PDF selectors
        pdf_selectors = [
            "//a[contains(@href, '.pdf')]",
            "//a[contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'Full Text PDF')]",
            "//button[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download')]",
            "//a[contains(@href, 'download')]",
            "//a[contains(@href, 'fulltext')]",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:5]:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        element.click()
                        time.sleep(4)
                        return
                    except:
                        href = element.get_attribute('href')
                        if href and ('.pdf' in href.lower() or 'download' in href.lower()):
                            driver.get(href)
                            time.sleep(4)
                            return
            except:
                continue
        
        # Try constructing PDF URL patterns
        current_url = driver.current_url.lower()
        pdf_url_patterns = [
            current_url + '.pdf',
            current_url.replace('/article/', '/pdf/'),
            current_url.replace('/view/', '/download/'),
            current_url + '/pdf',
            current_url.replace('/abstract/', '/pdf/'),
        ]
        
        for pdf_url in pdf_url_patterns:
            try:
                driver.get(pdf_url)
                time.sleep(3)
                if '.pdf' in driver.current_url.lower():
                    time.sleep(2)
                    return
            except:
                continue
    except:
        pass


def download_via_url_selenium(driver: webdriver.Chrome, url: str, output_path: Path, use_library: bool = False) -> None:
    """
    Attempt to download PDF via direct URL from RIS file.
    Uses publisher-specific handlers for better success rates.
    """
    try:
        # Check if file already exists
        if output_path.exists() and output_path.stat().st_size > 1024:
            return
        
        # Apply library proxy if needed
        if use_library and 'proxy-hs.researchport.umd.edu' not in url:
            # Try to add proxy prefix for certain domains
            if 'ncbi.nlm.nih.gov' in url:
                url = url.replace('https://', 'https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/')
            elif 'pubmed' in url:
                url = url.replace('https://', 'https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/')
        
        # Detect publisher type and use appropriate handler
        publisher_type = detect_publisher_type(url)
        
        if publisher_type == 'pmc':
            download_from_pmc_url(driver, url)
        elif publisher_type == 'ieee':
            download_from_ieee_url(driver, url)
        elif publisher_type == 'sciencedirect':
            download_from_sciencedirect_url(driver, url)
        elif publisher_type == 'springer':
            download_from_springer_url(driver, url)
        elif publisher_type == 'wiley':
            download_from_wiley_url(driver, url)
        else:
            download_from_generic_url(driver, url)
        
        time.sleep(2)  # Give download time to start
        
    except Exception as e:
        # Download failed - will be detected by Downloads tracking
        return


def search_by_metadata_selenium(driver: webdriver.Chrome, ref: Dict[str, str], output_path: Path, use_library: bool = False) -> None:
    """
    Fallback strategy: Search for paper using metadata (title, author, journal, etc.).
    Tries multiple search engines and strategies.
    """
    try:
        # Check if file already exists
        if output_path.exists() and output_path.stat().st_size > 1024:
            return
        
        title = ref.get('title', '')
        first_author = ref.get('first_author', '')
        journal = ref.get('journal', '')
        year = ref.get('year', '')
        doi = ref.get('doi', '')
        
        if not title:
            return  # Need at least a title
        
        # Strategy 1: Google Scholar search with title + author
        if first_author:
            search_query = f"{title} {first_author}"
        else:
            search_query = title
        
        try:
            if use_library:
                scholar_url = f"https://scholar.google.com/scholar?q={search_query.replace(' ', '+')}"
            else:
                scholar_url = f"https://scholar.google.com/scholar?q={search_query.replace(' ', '+')}"
            
            driver.get(scholar_url)
            time.sleep(4)
            
            # Look for PDF links in search results
            pdf_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf') or contains(text(), '[PDF]')]")
            for link in pdf_links[:3]:
                try:
                    href = link.get_attribute('href')
                    if href and '.pdf' in href.lower():
                        driver.get(href)
                        time.sleep(4)
                        return
                except:
                    continue
        except:
            pass
        
        # Strategy 2: PubMed search with title
        if not use_library:
            try:
                pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={title.replace(' ', '+')}"
                driver.get(pubmed_url)
                time.sleep(4)
                
                # Look for PDF links
                pdf_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf') or contains(text(), 'PDF')]")
                for link in pdf_links[:3]:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            driver.get(href)
                            time.sleep(4)
                            return
                    except:
                        continue
            except:
                pass
        
        # Strategy 3: Try DOI if available (as fallback)
        if doi:
            try:
                found_pmid = search_pubmed_by_doi(driver, doi, use_library)
                if found_pmid:
                    download_via_pubmed_selenium(driver, found_pmid, output_path, use_library)
                    return
            except:
                pass
        
    except Exception as e:
        # Search failed - will be detected by Downloads tracking
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
        # Default automated behavior - look for missing_after_first_scrape*.txt first, then still_missing*.txt
        ris_file = find_input_ris_file()
        if not ris_file:
            print("ERROR: Could not find missing_after_first_scrape*.txt or still_missing*.txt file in missing_papers/still_missing/ directory")
            return
        print(f"Using automated RIS file: {ris_file}")
    output_dir = Path("found_papers/downloaded_papers/second_scrape")
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
    print("PDF DOWNLOADER - Multi-Strategy V2 - Selenium Browser Automation")
    print("="*60)
    print("\nThis script will open a Chrome browser window.")
    print("Features:")
    print("  - Direct URL downloads (highest priority)")
    print("  - Enhanced DOI support (searches PubMed by DOI first)")
    print("  - Metadata-based search fallbacks")
    print("  - Fixed download detection")
    print("  - Library proxy access support")
    print("\nYou may need to:")
    print("1. Log into HSHSL library if prompted")
    print("2. Allow downloads in the browser")
    print("3. Let the script run (it will control the browser)")
    print()
    
    # Automatically use library access (default to 'y')
    use_library = True
    
    print(f"\nParsing RIS file: {ris_file}")
    references = parse_ris_file(str(ris_file))
    print(f"Found {len(references)} references")
    
    # Count available identifiers
    refs_with_url = sum(1 for ref in references if ref.get('url'))
    refs_with_doi = sum(1 for ref in references if ref.get('doi'))
    refs_with_pmid = sum(1 for ref in references if ref.get('pmid'))
    refs_with_pmc = sum(1 for ref in references if ref.get('pmc_id'))
    print(f"  - {refs_with_url} references have URLs")
    print(f"  - {refs_with_doi} references have DOIs")
    print(f"  - {refs_with_pmid} references have PMIDs")
    print(f"  - {refs_with_pmc} references have PMC IDs\n")
    
    # Ask about pilot mode
    pilot_mode = input("Run in PILOT mode? (only processes test paper) (y/n, default=n): ").strip().lower()
    pilot_mode = pilot_mode == 'y'
    
    if pilot_mode:
        pilot_title = "Identification of suspected tuberculosis patients based on natural language processing of chest radiograph reports"
        print(f"\n??  PILOT MODE ENABLED - Searching for test paper")
        print(f"  Looking for: {pilot_title[:60]}...")
        
        # Find the reference with the matching title
        pilot_reference = None
        for ref in references:
            if ref.get('title') == pilot_title:
                pilot_reference = ref
                break
        
        if pilot_reference:
            references = [pilot_reference]  # Only keep the pilot reference
            print(f"  ? Found test paper (Record {pilot_reference.get('record_number', 'N/A')})")
            print(f"  Processing 1 reference (pilot mode)\n")
        else:
            print(f"  ? ERROR: Test paper not found in RIS file!")
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
                print(f"{record_number} ", end='')
            # Add first 20 characters of title
            title_preview = title[:20] if title else "Unknown Title"
            print(f"{title_preview} ", end='')
            # Show what identifier we have (priority: URL > DOI > PMID > Title)
            url = ref.get('url')
            if url:
                print(f"URL... ", end='')
            elif doi:
                print(f"DOI {doi[:30]}... ", end='')
            elif pmid:
                print(f"PMID {pmid}... ", end='')
            else:
                print(f"{title[:30]}... ", end='')
            
            # Record current most recent file BEFORE download attempt
            file_before = get_most_recent_downloads_file(downloads_dir)
            
            # Attempt download (but we'll determine success by tracking Downloads folder)
            download_attempted = False
            found_pmid_from_doi = None
            url = ref.get('url')
            
            # Strategy 1: Try URL first (highest priority - direct links)
            if url:
                download_via_url_selenium(driver, url, output_path, use_library)
                download_attempted = True
            
            # Strategy 2: Try DOI (enhanced - searches PubMed by DOI first)
            if not download_attempted and doi:
                found_pmid_from_doi = download_via_doi_selenium(driver, doi, output_path, use_library)
                download_attempted = True
                
                # If we found a PMID via DOI search, use PubMed download method (more reliable)
                if found_pmid_from_doi:
                    print(f"(Found PMID {found_pmid_from_doi} via DOI search) ", end='')
                    download_via_pubmed_selenium(driver, found_pmid_from_doi, output_path, use_library)
            
            # Strategy 3: Try PMC if available
            if not download_attempted and pmc_id:
                download_via_pmc_selenium(driver, pmc_id, output_path)
                download_attempted = True
            
            # Strategy 4: Try PubMed/library access with existing PMID
            if not download_attempted and pmid:
                download_via_pubmed_selenium(driver, pmid, output_path, use_library)
                download_attempted = True
            
            # Strategy 5: Try metadata-based search (fallback)
            if not download_attempted:
                print("(Trying metadata search) ", end='')
                search_by_metadata_selenium(driver, ref, output_path, use_library)
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
                
                print(f"? DOWNLOADED ({method_used})")
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
                print("? FAILED")
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
        print(f"  ??  PILOT MODE - Only processed test paper")
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
