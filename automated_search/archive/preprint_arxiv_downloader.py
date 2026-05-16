#!/usr/bin/env python3
"""
arXiv Pre-print Downloader - searches arXiv for papers with PubMed URLs and downloads PDFs.
Also downloads free texts from OUP (Oxford University Press) and IOS Press URLs/DOIs.

Identifies papers with PubMed URLs from RIS file, searches arXiv for matching pre-prints,
and downloads PDFs if found. Also handles OUP URLs and IOS Press DOIs with free texts available.
"""

import re
import time
import shutil
import os
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from urllib.parse import quote_plus

# Selenium imports for browser downloads
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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


def parse_ris_file(filepath: str) -> List[Dict[str, str]]:
    """Parse RIS file and extract papers with PubMed URLs, OUP URLs, or IOS Press DOIs.
    Extracts label_id, record_number, title, first_author, url, doi, year, and full RIS text.
    """
    references = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
            
        label_id = None
        record_number = None
        title = None
        first_author = None
        url = None
        doi = None
        year = None
        
        lines = entry.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('LB  - '):
                label_id = line[6:].strip()
            elif line.startswith('ID  - '):
                record_number = line[6:].strip()
            elif line.startswith('TI  - '):
                title = line[6:].strip()
            elif line.startswith('UR  - '):
                url = line[6:].strip()
            elif line.startswith('DO  - '):
                doi = line[6:].strip()
                # Clean up DOI
                doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
                doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
                doi = doi.strip()
            elif line.startswith('PY  - '):
                year_text = line[6:].strip()
                year_match = re.search(r'(\d{4})', year_text)
                if year_match:
                    year = year_match.group(1)
            elif line.startswith('AU  - ') and first_author is None:
                # First author (take first one)
                first_author = line[6:].strip()
        
        # Include papers with label_id and either URL or DOI
        # For IOS Press, we can work with just DOI
        if label_id and (url or doi):
            references.append({
                'label_id': label_id,
                'record_number': record_number or label_id,
                'title': title or 'Unknown Title',
                'first_author': first_author,
                'url': url,
                'doi': doi,
                'year': year,
                'ris_text': entry + '\nER  - \n'
            })
    
    return references


def is_pubmed_url(url: str) -> bool:
    """Check if URL is a PubMed URL."""
    if not url:
        return False
    url_lower = url.lower()
    return 'pubmed.ncbi.nlm.nih.gov' in url_lower or 'www.ncbi.nlm.nih.gov/pubmed/' in url_lower


def is_oup_url(url: str) -> bool:
    """Check if URL is an Oxford University Press (OUP) URL."""
    if not url:
        return False
    url_lower = url.lower()
    return 'academic.oup.com' in url_lower or 'oup.com' in url_lower


def is_ios_press_doi(doi: str) -> bool:
    """Check if DOI is from IOS Press (DOIs starting with 10.3233/)."""
    if not doi:
        return False
    return doi.startswith('10.3233/')


def is_ios_press_url(url: str) -> bool:
    """Check if URL is from IOS Press."""
    if not url:
        return False
    url_lower = url.lower()
    return 'iospress.com' in url_lower or 'iospress.nl' in url_lower or 'content.iospress.com' in url_lower


def normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, remove punctuation)."""
    if not text:
        return ""
    # Convert to lowercase
    text = text.lower()
    # Remove common punctuation
    text = re.sub(r'[^\w\s]', ' ', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text


def extract_author_last_name(author: str) -> str:
    """Extract last name from author string (e.g., 'Smith, John' -> 'Smith')."""
    if not author:
        return ""
    # Handle formats like "Smith, John" or "John Smith"
    if ',' in author:
        return author.split(',')[0].strip()
    else:
        # Assume last word is last name
        parts = author.split()
        return parts[-1] if parts else ""


def match_arxiv_result(arxiv_title: str, arxiv_authors: str, target_title: str, target_author: str) -> float:
    """Calculate match score between arXiv result and target paper.
    Returns score between 0 and 1, where 1 is perfect match.
    Uses improved matching with multiple metrics.
    """
    if not arxiv_title or not target_title:
        return 0.0
    
    # Normalize titles
    norm_arxiv_title = normalize_text(arxiv_title)
    norm_target_title = normalize_text(target_title)
    
    # Calculate title word overlap
    arxiv_words = set(norm_arxiv_title.split())
    target_words = set(norm_target_title.split())
    
    if not target_words:
        return 0.0
    
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can'}
    arxiv_words = arxiv_words - stop_words
    target_words = target_words - stop_words
    
    if not target_words:
        return 0.0
    
    # Calculate Jaccard similarity for title words
    intersection = arxiv_words & target_words
    union = arxiv_words | target_words
    jaccard_score = len(intersection) / len(union) if union else 0.0
    
    # Calculate word overlap percentage (how many target words appear in arxiv)
    overlap_score = len(intersection) / len(target_words) if target_words else 0.0
    
    # Check for substring match (for cases where titles are very similar)
    substring_score = 0.0
    if norm_target_title in norm_arxiv_title or norm_arxiv_title in norm_target_title:
        substring_score = 0.3  # Bonus for substring match
    
    # Title score: combination of Jaccard and overlap
    title_score = 0.6 * jaccard_score + 0.4 * overlap_score + substring_score
    title_score = min(title_score, 1.0)  # Cap at 1.0
    
    # Check author match
    author_score = 0.0
    if target_author and arxiv_authors:
        target_last_name = normalize_text(extract_author_last_name(target_author))
        arxiv_authors_lower = normalize_text(arxiv_authors)
        
        if target_last_name:
            if target_last_name in arxiv_authors_lower:
                author_score = 1.0
            else:
                # Check if any part of target author name appears
                target_parts = target_last_name.split()
                for part in target_parts:
                    if len(part) > 3 and part in arxiv_authors_lower:
                        author_score = 0.5  # Partial match
                        break
    
    # Combined score: 65% title, 35% author (slightly more weight on title)
    combined_score = 0.65 * title_score + 0.35 * author_score
    
    return combined_score


def search_arxiv_api(title: str, first_author: str, year: Optional[str] = None) -> Optional[str]:
    """Search arXiv using the REST API and return arXiv ID if found.
    Uses multiple search strategies with fallbacks.
    
    Args:
        title: Paper title
        first_author: First author name
        year: Publication year (optional)
    
    Returns:
        arXiv ID (e.g., '2301.12345') if match found, None otherwise
    """
    # Try multiple search strategies
    search_strategies = []
    
    # Strategy 1: Title with author (if available)
    if first_author:
        author_last_name = extract_author_last_name(first_author)
        if author_last_name:
            # Use more title words for better matching
            title_words = title.split()[:12]
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
            title_words = [w for w in title_words if w.lower() not in stop_words]
            if title_words:
                search_terms = ' '.join(title_words)
                search_strategies.append(f'ti:{search_terms} AND au:{author_last_name}')
    
    # Strategy 2: Title only (broader search, no quotes for flexible matching)
    title_words = title.split()[:10]
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    title_words = [w for w in title_words if w.lower() not in stop_words]
    if title_words:
        search_terms = ' '.join(title_words)
        search_strategies.append(f'ti:{search_terms}')
    
    # Strategy 3: All fields search (most flexible)
    if title_words:
        search_strategies.append(f'all:{search_terms}')
    
    # Strategy 4: Title with quotes (exact phrase, if other strategies fail)
    if title_words:
        search_strategies.append(f'ti:"{search_terms}"')
    
    base_url = 'http://export.arxiv.org/api/query'
    namespace = {'atom': 'http://www.w3.org/2005/Atom'}
    
    best_match_score = 0.0
    best_arxiv_id = None
    
    for strategy_idx, search_query in enumerate(search_strategies):
        try:
            print(f"    Strategy {strategy_idx+1}: Searching arXiv API: {search_query[:60]}...")
            
            params = {
                'search_query': search_query,
                'start': 0,
                'max_results': 20,  # Check more results
                'sortBy': 'relevance',
                'sortOrder': 'descending'
            }
            
            # Make API request
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.content)
            
            # Find all entries
            entries = root.findall('atom:entry', namespace)
            
            if not entries:
                print(f"    No results for this strategy")
                continue
            
            print(f"    Found {len(entries)} results")
            
            # Check entries for best match
            for i, entry in enumerate(entries):
                try:
                    # Extract arXiv ID
                    id_elem = entry.find('atom:id', namespace)
                    if id_elem is None or id_elem.text is None:
                        continue
                    
                    id_text = id_elem.text
                    arxiv_id_match = re.search(r'/(\d{4}\.\d{4,5})(?:v\d+)?$', id_text)
                    if not arxiv_id_match:
                        continue
                    arxiv_id = arxiv_id_match.group(1)
                    
                    # Extract title
                    title_elem = entry.find('atom:title', namespace)
                    if title_elem is None or title_elem.text is None:
                        continue
                    arxiv_title = title_elem.text.strip()
                    arxiv_title = ' '.join(arxiv_title.split())
                    
                    # Extract authors
                    author_elems = entry.findall('atom:author', namespace)
                    arxiv_authors = []
                    for author_elem in author_elems:
                        name_elem = author_elem.find('atom:name', namespace)
                        if name_elem is not None and name_elem.text:
                            arxiv_authors.append(name_elem.text.strip())
                    arxiv_authors_str = ', '.join(arxiv_authors)
                    
                    # Calculate match score
                    score = match_arxiv_result(arxiv_title, arxiv_authors_str, title, first_author)
                    
                    if i < 3:  # Only print first 3 results to avoid spam
                        print(f"      Result {i+1}: {arxiv_id} - score: {score:.2f}")
                        print(f"        Title: {arxiv_title[:50]}...")
                    
                    if score > best_match_score:
                        best_match_score = score
                        best_arxiv_id = arxiv_id
                        
                except Exception as e:
                    continue
            
            # If we found a good match, return it (don't try other strategies)
            if best_match_score >= 0.4 and best_arxiv_id:  # Lowered threshold from 0.5 to 0.4
                print(f"    Best match: {best_arxiv_id} (score: {best_match_score:.2f})")
                return best_arxiv_id
                
        except requests.RequestException as e:
            print(f"    Error with strategy {strategy_idx+1}: {e}")
            continue
        except ET.ParseError as e:
            print(f"    Error parsing response for strategy {strategy_idx+1}: {e}")
            continue
        except Exception as e:
            print(f"    Error with strategy {strategy_idx+1}: {e}")
            continue
    
    # If we get here, no strategy found a good match
    if best_arxiv_id:
        print(f"    Best match found: {best_arxiv_id} (score: {best_match_score:.2f}, below threshold)")
    else:
        print(f"    No results found across all strategies")
    return None


def download_arxiv_pdf(arxiv_id: str, output_path: Path) -> bool:
    """Download PDF from arXiv using direct PDF URL with requests library.
    
    Args:
        arxiv_id: arXiv ID (e.g., '2301.12345')
        output_path: Path where PDF should be saved
    
    Returns:
        True if download successful, False otherwise
    """
    try:
        # Direct PDF URL
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        print(f"    Downloading from: {pdf_url}")
        
        # Download PDF using requests
        response = requests.get(pdf_url, timeout=30, stream=True)
        response.raise_for_status()
        
        # Check if response is actually a PDF
        content_type = response.headers.get('content-type', '').lower()
        if 'pdf' not in content_type and not pdf_url.endswith('.pdf'):
            print(f"    Warning: Response doesn't appear to be a PDF (content-type: {content_type})")
            return False
        
        # Save PDF to file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Verify file was downloaded and has content
        if output_path.exists() and output_path.stat().st_size > 1024:
            print(f"    Downloaded: {output_path.stat().st_size} bytes")
            return True
        else:
            print(f"    Download failed - file too small or missing")
            if output_path.exists():
                output_path.unlink()
            return False
        
    except requests.RequestException as e:
        print(f"    Error downloading arXiv PDF: {e}")
        if output_path.exists():
            output_path.unlink()
        return False
    except Exception as e:
        print(f"    Error downloading arXiv PDF: {e}")
        if output_path.exists():
            output_path.unlink()
        return False


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


def extract_pmc_id_from_pubmed(driver, pubmed_url: str) -> Optional[str]:
    """Extract PMC ID from PubMed page by looking for PMC links.
    
    Args:
        driver: Selenium WebDriver instance
        pubmed_url: PubMed URL (e.g., https://www.ncbi.nlm.nih.gov/pubmed/12345678)
    
    Returns:
        PMC ID (e.g., '12345678') if found, None otherwise
    """
    try:
        print(f"    Checking PubMed page for PMC link...")
        driver.get(pubmed_url)
        time.sleep(3)  # Wait for page to load
        
        # Handle cookie popups
        handle_cookie_popup(driver)
        time.sleep(1)
        
        # Look for "Free PMC article" link or PMC links
        pmc_links = driver.find_elements(By.XPATH,
            "//a[contains(text(), 'Free PMC article')] | "
            "//a[contains(text(), 'PMC')] | "
            "//a[contains(@href, '/pmc/articles/')]")
        
        if pmc_links:
            for link in pmc_links:
                try:
                    href = link.get_attribute('href')
                    if href:
                        # Extract PMC ID from URL patterns like:
                        # /pmc/articles/PMC12345678/
                        # https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12345678/
                        pmc_match = re.search(r'/pmc/articles/(?:PMC)?(\d+)', href, re.IGNORECASE)
                        if pmc_match:
                            pmc_id = pmc_match.group(1)
                            print(f"    Found PMC ID: {pmc_id}")
                            return pmc_id
                except:
                    continue
        
        print(f"    No PMC link found on PubMed page")
        return None
        
    except Exception as e:
        print(f"    Error extracting PMC ID from PubMed: {e}")
        return None


def download_from_pmc(driver, pmc_id: str, output_path: Path) -> bool:
    """Download PDF from PMC (PubMed Central) article.
    
    Args:
        driver: Selenium WebDriver instance
        pmc_id: PMC ID (e.g., '12345678')
        output_path: Path where PDF should be saved
    
    Returns:
        True if download successful, False otherwise
    """
    try:
        article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"
        print(f"    Navigating to PMC article: {article_url}")
        
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
                
                # Step 4: Wait for download
                time.sleep(5)
                return True
            else:
                print(f"    Could not find Download PDF button on PMC article page")
                return False
                
        except Exception as e:
            print(f"    Error navigating to PMC article: {e}")
            return False
            
    except Exception as e:
        print(f"    Error downloading from PMC: {e}")
        return False


def detect_publisher_from_url(url: str) -> str:
    """Detect publisher type from URL.
    
    Args:
        url: URL to analyze
    
    Returns:
        Publisher identifier string (pmc, pubmed, oup, ios_press, etc.)
    """
    if not url:
        return 'unknown'
    
    url_lower = url.lower()
    
    if 'pmc.ncbi.nlm.nih.gov' in url_lower or '/pmc/articles/' in url_lower:
        return 'pmc'
    elif 'pubmed.ncbi.nlm.nih.gov' in url_lower:
        return 'pubmed'
    elif 'academic.oup.com' in url_lower or 'oup.com' in url_lower:
        return 'oup'
    elif 'iospress.com' in url_lower or 'iospress.nl' in url_lower or 'content.iospress.com' in url_lower:
        return 'ios_press'
    elif 'sciencedirect.com' in url_lower:
        return 'sciencedirect'
    elif 'springer.com' in url_lower or 'link.springer.com' in url_lower:
        return 'springer'
    elif 'wiley.com' in url_lower or 'onlinelibrary.wiley.com' in url_lower:
        return 'wiley'
    elif 'ieeexplore.ieee.org' in url_lower:
        return 'ieee'
    else:
        return 'generic'


def follow_pubmed_url(driver, pubmed_url: str) -> Tuple[str, str]:
    """Follow PubMed URL and detect final publisher after redirects.
    
    Args:
        driver: Selenium WebDriver instance
        pubmed_url: PubMed URL to follow
    
    Returns:
        Tuple of (final_url, publisher)
    """
    try:
        print(f"    Following PubMed URL to detect publisher...")
        driver.get(pubmed_url)
        time.sleep(4)  # Wait for page load and redirects
        
        # Handle cookie popups
        handle_cookie_popup(driver)
        time.sleep(1)
        
        # Look for links to full text or publisher sites
        # PubMed pages often have "Full text links" section
        try:
            # Try to find "Full text links" or publisher links
            fulltext_links = driver.find_elements(By.XPATH,
                "//a[contains(text(), 'Full text')] | "
                "//a[contains(text(), 'Publisher')] | "
                "//a[contains(@href, 'http') and not(contains(@href, 'pubmed'))]")
            
            if fulltext_links:
                # Get the first external link (likely publisher site)
                for link in fulltext_links:
                    href = link.get_attribute('href')
                    if href and 'pubmed' not in href.lower() and 'ncbi' not in href.lower():
                        final_url = href
                        publisher = detect_publisher_from_url(final_url)
                        print(f"    Found publisher link: {publisher} - {final_url[:80]}...")
                        return (final_url, publisher)
        except Exception as e:
            print(f"    Warning: Could not find full text links: {e}")
        
        # If no external links found, check current URL after redirects
        current_url = driver.current_url
        publisher = detect_publisher_from_url(current_url)
        print(f"    Final URL after redirects: {publisher} - {current_url[:80]}...")
        return (current_url, publisher)
        
    except Exception as e:
        print(f"    Error following PubMed URL: {e}")
        return (pubmed_url, 'unknown')


def download_from_oup_url(driver, url: str, output_path: Path) -> bool:
    """Download PDF from Oxford University Press (OUP) website.
    V2: Enhanced PDF button detection for OUP sites.
    """
    try:
        driver.get(url)
        time.sleep(5)  # Wait for page to load

        # Handle cookie popups first
        handle_cookie_popup(driver)
        time.sleep(1)

        # OUP-specific PDF button selectors
        pdf_selectors = [
            # Direct PDF buttons/links
            "//button[contains(text(), 'PDF')]",
            "//a[contains(text(), 'PDF')]",
            "//button[contains(@class, 'pdf')]",
            "//a[contains(@class, 'pdf')]",
            "//button[contains(@aria-label, 'PDF')]",
            "//a[contains(@aria-label, 'PDF')]",
            "//button[contains(@title, 'PDF')]",
            "//a[contains(@title, 'PDF')]",
            # Download PDF variants
            "//button[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'Download PDF')]",
            # Links with PDF in href
            "//a[contains(@href, '.pdf')]",
            "//a[contains(@href, '/pdf/')]",
            # OUP-specific classes/IDs (common patterns)
            "//*[contains(@class, 'download-pdf')]",
            "//*[contains(@id, 'pdf')]",
            "//*[contains(@data-action, 'pdf')]",
        ]

        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:5]:  # Check first 5 matches
                    try:
                        # Check if element is visible and enabled
                        if not element.is_displayed():
                            continue
                        if hasattr(element, 'is_enabled') and not element.is_enabled():
                            continue

                        # Scroll into view
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(0.5)

                        # Try clicking
                        try:
                            element.click()
                        except:
                            # Fallback to JavaScript click
                            driver.execute_script("arguments[0].click();", element)

                        time.sleep(3)  # Wait for PDF to load/start downloading

                        # Check if we navigated to a PDF or if download started
                        current_url = driver.current_url.lower()
                        if '.pdf' in current_url:
                            # Direct PDF URL - should download automatically
                            time.sleep(3)
                            return True

                        # Check if PDF opened in new window
                        if len(driver.window_handles) > 1:
                            driver.switch_to.window(driver.window_handles[-1])
                            time.sleep(2)
                            if '.pdf' in driver.current_url.lower():
                                time.sleep(3)
                                return True

                        # If we get here, PDF might be downloading
                        time.sleep(5)
                        return True

                    except Exception as e:
                        continue
            except:
                continue

        return False

    except Exception as e:
        print(f"    Error downloading from OUP: {e}")
        return False


def download_from_ios_press_url(driver, url: str, output_path: Path, doi: Optional[str] = None) -> bool:
    """Download PDF from IOS Press website.
    First tries direct PDF URL pattern if DOI is available, then falls back to button clicking.
    Enhanced PDF button detection for IOS Press sites with comprehensive selectors and debugging.
    Handles cases where PDF button may not exist (returns False gracefully).
    """
    # Strategy 1: Try direct PDF URL if DOI is available
    if doi:
        # IOS Press direct PDF URL pattern: https://ebooks.iospress.nl/pdf/doi/{DOI}
        direct_pdf_url = f"https://ebooks.iospress.nl/pdf/doi/{doi}"
        print(f"    Trying direct PDF URL: {direct_pdf_url[:80]}...")
        try:
            response = requests.get(direct_pdf_url, timeout=30, stream=True, allow_redirects=True)
            # Check if we got a PDF (status 200 and content-type or file extension)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' in content_type or direct_pdf_url.endswith('.pdf'):
                    # Save PDF to file
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Verify file was downloaded and has content
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        print(f"    ✓ Downloaded via direct PDF URL: {output_path.stat().st_size} bytes")
                        return True
                    else:
                        print(f"    Direct PDF URL returned invalid file")
                else:
                    print(f"    Direct PDF URL did not return PDF (content-type: {content_type})")
            else:
                print(f"    Direct PDF URL returned status {response.status_code}")
        except Exception as e:
            print(f"    Direct PDF URL attempt failed: {e}")
    
    # Strategy 2: Fall back to browser-based button clicking
    try:
        print(f"    Attempting IOS Press download via browser from: {url[:80]}...")
        driver.get(url)
        
        # Wait for page to be ready
        wait = WebDriverWait(driver, 15)
        wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)  # Additional wait for dynamic content

        print(f"    DEBUG: Current URL: {driver.current_url}")
        print(f"    DEBUG: Page title: {driver.title}")

        # Handle cookie popups first
        handle_cookie_popup(driver)
        time.sleep(1)

        # Debug: Log all buttons and links on the page
        all_buttons = driver.find_elements(By.TAG_NAME, "button")
        all_links = driver.find_elements(By.TAG_NAME, "a")
        print(f"    DEBUG: Found {len(all_buttons)} buttons and {len(all_links)} links on page")
        
        # Log first few buttons/links for debugging
        for i, btn in enumerate(all_buttons[:10]):
            btn_text = btn.text.strip()[:50] if btn.text else ''
            btn_class = btn.get_attribute('class') or ''
            btn_id = btn.get_attribute('id') or ''
            btn_visible = btn.is_displayed()
            print(f"    DEBUG: Button {i+1}: text='{btn_text}', class='{btn_class[:30]}', id='{btn_id}', visible={btn_visible}")
        
        for i, link in enumerate(all_links[:10]):
            link_text = link.text.strip()[:50] if link.text else ''
            link_href = link.get_attribute('href') or ''
            if 'pdf' in link_text.lower() or 'pdf' in link_href.lower() or 'download' in link_text.lower():
                print(f"    DEBUG: Link {i+1}: text='{link_text}', href='{link_href[:50]}'")

        # Wait a bit more for dynamic content to load
        time.sleep(3)
        
        # Check for iframes and switch to them if needed
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                print(f"    DEBUG: Found {len(iframes)} iframes, checking them...")
                for iframe_idx, iframe in enumerate(iframes):
                    try:
                        driver.switch_to.frame(iframe)
                        print(f"    DEBUG: Switched to iframe {iframe_idx+1}")
                        time.sleep(1)
                        # Check for PDF buttons in iframe
                        iframe_buttons = driver.find_elements(By.XPATH, "//button | //a")
                        print(f"    DEBUG: Found {len(iframe_buttons)} buttons/links in iframe")
                        driver.switch_to.default_content()
                    except:
                        driver.switch_to.default_content()
        except:
            pass
        
        # Try to find direct PDF URL in page source
        try:
            page_source = driver.page_source.lower()
            if '.pdf' in page_source:
                print(f"    DEBUG: Found '.pdf' in page source, searching for PDF URLs...")
                # Try to extract PDF URL from page source
                pdf_url_match = re.search(r'https?://[^\s"\'<>]+\.pdf', driver.page_source, re.IGNORECASE)
                if pdf_url_match:
                    pdf_url = pdf_url_match.group(0)
                    print(f"    DEBUG: Found potential PDF URL: {pdf_url[:80]}...")
                    # Try to navigate directly to PDF
                    driver.get(pdf_url)
                    time.sleep(3)
                    if '.pdf' in driver.current_url.lower():
                        print(f"    DEBUG: Successfully navigated to PDF URL")
                        time.sleep(3)
                        return True
        except Exception as e:
            print(f"    DEBUG: Error searching for PDF URL: {e}")
        
        # IOS Press-specific PDF button selectors (comprehensive list)
        pdf_selectors = [
            # Direct PDF buttons/links with various text patterns
            "//button[contains(text(), 'PDF')]",
            "//a[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'Download PDF')]",
            "//button[contains(text(), 'Download') and contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download') and contains(text(), 'PDF')]",
            # Case-insensitive variations
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
            "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
            # Class-based selectors
            "//button[contains(@class, 'pdf')]",
            "//a[contains(@class, 'pdf')]",
            "//button[contains(@class, 'download')]",
            "//a[contains(@class, 'download')]",
            # ID-based selectors
            "//button[contains(@id, 'pdf')]",
            "//a[contains(@id, 'pdf')]",
            "//button[contains(@id, 'download')]",
            "//a[contains(@id, 'download')]",
            # Aria-label and title attributes
            "//button[contains(@aria-label, 'PDF')]",
            "//a[contains(@aria-label, 'PDF')]",
            "//button[contains(@aria-label, 'Download')]",
            "//a[contains(@aria-label, 'Download')]",
            "//button[contains(@title, 'PDF')]",
            "//a[contains(@title, 'PDF')]",
            "//button[contains(@title, 'Download')]",
            "//a[contains(@title, 'Download')]",
            # Links with PDF in href
            "//a[contains(@href, '.pdf')]",
            "//a[contains(@href, '/pdf/')]",
            "//a[contains(@href, 'pdf')]",
            # Container-based selectors (IOS Press specific patterns)
            "//div[contains(@class, 'article')]//button[contains(text(), 'PDF')]",
            "//div[contains(@class, 'download')]//a[contains(text(), 'PDF')]",
            "//div[contains(@class, 'article-header')]//button[contains(text(), 'PDF')]",
            "//div[contains(@class, 'article-header')]//a[contains(text(), 'PDF')]",
            # Sidebar patterns (IOS Press often has PDF button in sidebar)
            "//aside//button[contains(text(), 'PDF')]",
            "//aside//a[contains(text(), 'PDF')]",
            "//div[contains(@class, 'sidebar')]//button[contains(text(), 'PDF')]",
            "//div[contains(@class, 'sidebar')]//a[contains(text(), 'PDF')]",
            # Icon + text patterns
            "//button[.//*[contains(@class, 'pdf') or contains(@class, 'download')]]",
            "//a[.//*[contains(@class, 'pdf') or contains(@class, 'download')]]",
            # CSS selector equivalents
            "//*[@class and contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
            "//*[@id and contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
        ]

        for selector_idx, selector in enumerate(pdf_selectors):
            try:
                print(f"    DEBUG: Trying selector {selector_idx+1}/{len(pdf_selectors)}: {selector[:60]}...")
                elements = driver.find_elements(By.XPATH, selector)
                print(f"    DEBUG: Found {len(elements)} elements with this selector")
                
                for element_idx, element in enumerate(elements[:10]):  # Check first 10 matches
                    try:
                        # Get element text/attributes for debugging
                        element_text = element.text or element.get_attribute('aria-label') or element.get_attribute('title') or ''
                        element_text_lower = element_text.lower()
                        
                        print(f"    DEBUG: Element {element_idx+1}: text='{element_text[:50]}', tag={element.tag_name}")
                        
                        # Skip if it's clearly not a PDF download button
                        if element_text_lower and 'abstract' in element_text_lower and 'pdf' not in element_text_lower:
                            print(f"    DEBUG: Skipping - appears to be abstract link")
                            continue

                        # Check if element is visible and in viewport
                        is_displayed = element.is_displayed()
                        is_in_viewport = driver.execute_script(
                            "var rect = arguments[0].getBoundingClientRect(); "
                            "return (rect.top >= 0 && rect.left >= 0 && "
                            "rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) && "
                            "rect.right <= (window.innerWidth || document.documentElement.clientWidth));",
                            element
                        )
                        
                        print(f"    DEBUG: Element visible={is_displayed}, in_viewport={is_in_viewport}")
                        
                        if not is_displayed:
                            print(f"    DEBUG: Element not displayed, skipping")
                            continue
                        if hasattr(element, 'is_enabled') and not element.is_enabled():
                            print(f"    DEBUG: Element not enabled, skipping")
                            continue

                        # Scroll into view with multiple strategies
                        try:
                            # Strategy 1: Scroll element into center of viewport
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", element)
                            time.sleep(1)
                            
                            # Strategy 2: If still not in viewport, scroll page
                            if not driver.execute_script(
                                "var rect = arguments[0].getBoundingClientRect(); "
                                "return (rect.top >= 0 && rect.left >= 0 && "
                                "rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) && "
                                "rect.right <= (window.innerWidth || document.documentElement.clientWidth));",
                                element
                            ):
                                driver.execute_script("window.scrollTo(0, arguments[0].offsetTop - window.innerHeight/2);", element)
                                time.sleep(1)
                        except Exception as e:
                            print(f"    DEBUG: Scroll error: {e}")

                        # Wait for element to be clickable using WebDriverWait
                        try:
                            wait_clickable = WebDriverWait(driver, 5)
                            clickable_element = wait_clickable.until(EC.element_to_be_clickable(element))
                            print(f"    DEBUG: Element is clickable")
                        except TimeoutException:
                            print(f"    DEBUG: Element not clickable within timeout, trying anyway")
                            clickable_element = element

                        # Try multiple click methods
                        clicked = False
                        click_method = None
                        
                        try:
                            # Method 1: Regular click
                            clickable_element.click()
                            clicked = True
                            click_method = "regular click"
                        except Exception as e1:
                            try:
                                # Method 2: JavaScript click
                                driver.execute_script("arguments[0].click();", clickable_element)
                                clicked = True
                                click_method = "JavaScript click"
                            except Exception as e2:
                                try:
                                    # Method 3: ActionChains click with move to element
                                    actions = ActionChains(driver)
                                    actions.move_to_element(clickable_element).pause(0.5).click().perform()
                                    clicked = True
                                    click_method = "ActionChains click"
                                except Exception as e3:
                                    print(f"    DEBUG: All click methods failed: regular={e1}, js={e2}, actions={e3}")

                        if clicked:
                            print(f"    DEBUG: Successfully clicked using {click_method}")
                            time.sleep(3)  # Wait for download to start

                            # Check if we navigated to a PDF
                            current_url = driver.current_url.lower()
                            if '.pdf' in current_url:
                                print(f"    DEBUG: Navigated to PDF URL")
                                time.sleep(3)
                                return True

                            # Check if PDF opened in new window
                            if len(driver.window_handles) > 1:
                                print(f"    DEBUG: New window opened, switching to it")
                                driver.switch_to.window(driver.window_handles[-1])
                                time.sleep(2)
                                if '.pdf' in driver.current_url.lower():
                                    print(f"    DEBUG: PDF in new window")
                                    time.sleep(3)
                                    return True

                            # If we get here, PDF might be downloading
                            print(f"    DEBUG: Click successful, assuming download started")
                            time.sleep(5)
                            return True
                        else:
                            print(f"    DEBUG: Click failed for this element")

                    except Exception as e:
                        print(f"    DEBUG: Error processing element: {e}")
                        continue
            except Exception as e:
                print(f"    DEBUG: Error with selector: {e}")
                continue

        # If no button found with selectors, try JavaScript search with broader criteria
        print(f"    DEBUG: Trying JavaScript-based element search (broader)")
        try:
            result = driver.execute_script('''
                // Search all clickable elements
                var allElements = document.querySelectorAll('button, a, [role="button"], [onclick], [class*="pdf"], [class*="download"], [id*="pdf"], [id*="download"]');
                var found = [];
                var clicked = false;
                
                for (var i = 0; i < allElements.length; i++) {
                    var el = allElements[i];
                    var text = (el.textContent || el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('class') || el.getAttribute('id') || '').toLowerCase();
                    var href = (el.getAttribute('href') || '').toLowerCase();
                    
                    // Check if element is related to PDF
                    if (text.includes('pdf') || text.includes('download pdf') || href.includes('.pdf') || href.includes('/pdf/')) {
                        var isVisible = el.offsetParent !== null && 
                                       window.getComputedStyle(el).display !== 'none' &&
                                       window.getComputedStyle(el).visibility !== 'hidden';
                        
                        found.push({
                            text: text.substring(0, 50),
                            tag: el.tagName,
                            visible: isVisible,
                            href: href.substring(0, 50)
                        });
                        
                        if (isVisible && !clicked) {
                            try {
                                el.scrollIntoView({block: 'center', behavior: 'smooth'});
                                setTimeout(function() { 
                                    try {
                                        el.click();
                                        clicked = true;
                                    } catch(e) {
                                        console.log('Click error:', e);
                                    }
                                }, 500);
                            } catch(e) {
                                console.log('Scroll/click error:', e);
                            }
                        }
                    }
                }
                
                // Also try direct href navigation if we found PDF links
                if (!clicked && found.length > 0) {
                    for (var j = 0; j < found.length; j++) {
                        var match = found[j];
                        if (match.href && (match.href.includes('.pdf') || match.href.includes('/pdf/'))) {
                            return {success: true, method: 'direct_navigation', url: match.href, found: found.length, matches: found};
                        }
                    }
                }
                
                return {success: clicked, found: found.length, matches: found};
            ''')
            print(f"    DEBUG: JavaScript search result: {result}")
            if result and result.get('success'):
                if result.get('method') == 'direct_navigation' and result.get('url'):
                    print(f"    DEBUG: Attempting direct navigation to PDF URL")
                    driver.get(result.get('url'))
                    time.sleep(3)
                    return True
                time.sleep(5)
                return True
        except Exception as e:
            print(f"    DEBUG: JavaScript search error: {e}")
        
        # Last resort: Try to find any link with PDF in URL and navigate directly
        print(f"    DEBUG: Last resort - searching for any PDF links in page")
        try:
            all_links = driver.find_elements(By.TAG_NAME, "a")
            for link in all_links:
                try:
                    href = link.get_attribute('href') or ''
                    if href and ('.pdf' in href.lower() or '/pdf/' in href.lower()):
                        print(f"    DEBUG: Found PDF link: {href[:80]}...")
                        if link.is_displayed():
                            print(f"    DEBUG: Attempting to click/navigate to PDF link")
                            try:
                                link.click()
                                time.sleep(3)
                                if '.pdf' in driver.current_url.lower():
                                    return True
                            except:
                                # Try direct navigation
                                driver.get(href)
                                time.sleep(3)
                                if '.pdf' in driver.current_url.lower():
                                    return True
                except:
                    continue
        except Exception as e:
            print(f"    DEBUG: Error in last resort search: {e}")

        print(f"    DEBUG: All methods failed to find/click download button")
        print(f"    No PDF download button found on IOS Press page")
        return False

    except Exception as e:
        print(f"    Error downloading from IOS Press: {e}")
        return False


def rename_downloaded_file(download_dir: Path, label_id: str, timeout: int = 20) -> bool:
    """Wait for download to complete and rename to label_id.pdf"""
    start_time = time.time()
    target_path = download_dir / f"{label_id}.pdf"
    
    # First check if target file already exists and is valid
    if target_path.exists() and target_path.stat().st_size > 1024:
        return True
    
    while time.time() - start_time < timeout:
        # Look for recently downloaded PDF files
        pdf_files = list(download_dir.glob('*.pdf'))
        for pdf_file in pdf_files:
            # Check if file was modified recently (within last 15 seconds)
            file_age = time.time() - pdf_file.stat().st_mtime
            if file_age < 15:
                # Rename to label_id.pdf
                if target_path.exists() and target_path != pdf_file:
                    # Already have the correct file
                    if pdf_file != target_path:
                        try:
                            pdf_file.unlink()  # Delete duplicate
                        except:
                            pass
                    return True
                else:
                    try:
                        shutil.move(str(pdf_file), str(target_path))
                        # Verify the move was successful
                        if target_path.exists() and target_path.stat().st_size > 1024:
                            return True
                    except Exception as e:
                        print(f"    Warning: Could not rename {pdf_file.name}: {e}")
                        # Continue trying
        time.sleep(1)
    
    # Final check: maybe file was downloaded directly to target location
    if target_path.exists() and target_path.stat().st_size > 1024:
        return True
    
    return False


def find_most_recent_txt_file() -> Optional[Path]:
    """Find the most recently added or modified .txt file in missing_papers/still_missing/ directory."""
    still_missing_dir = Path("missing_papers/still_missing")
    if not still_missing_dir.exists():
        return None
    
    txt_files = []
    for file_path in still_missing_dir.iterdir():
        if file_path.is_file() and file_path.suffix == '.txt':
            try:
                stat = file_path.stat()
                creation_time = getattr(stat, 'st_birthtime', stat.st_mtime)
                modification_time = stat.st_mtime
                txt_files.append((creation_time, modification_time, file_path))
            except (OSError, AttributeError):
                continue
    
    if not txt_files:
        return None
    
    txt_files.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return txt_files[0][2]


def find_original_ris_file() -> Optional[Path]:
    """Find the original RIS file (missing_papers*.txt)."""
    still_missing_dir = Path("missing_papers/still_missing")
    if not still_missing_dir.exists():
        return None
    
    pattern = re.compile(r'^missing_papers(\d*)\.txt$')
    
    base_file = still_missing_dir / "missing_papers.txt"
    if base_file.exists():
        return base_file
    
    numbered_files = []
    for file_path in still_missing_dir.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                number_str = match.group(1)
                number = int(number_str) if number_str else 0
                numbered_files.append((number, file_path))
    
    if numbered_files:
        numbered_files.sort(key=lambda x: x[0], reverse=True)
        return numbered_files[0][1]
    
    return None


def count_ris_references(ris_file_path: Path) -> int:
    """Count the number of references in a RIS file."""
    if not ris_file_path.exists():
        return 0
    
    try:
        with open(ris_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
        return len([e for e in entries if e.strip()])
    except:
        return 0


def get_import_map_filename(downloads: int, input_refs: int, original_refs: int, import_ids_dir: Path) -> str:
    """Generate import map filename in format: import_{downloads}_of_{input_refs}_of_{original_refs}_preprint.txt"""
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    return f"import_{downloads}_of_{input_refs}_of_{original_refs}_preprint.txt"


def main():
    """Main execution function."""
    # Find the most recent .txt file for the prompt
    most_recent_file = find_most_recent_txt_file()
    if most_recent_file:
        prompt_message = f"Would you like to enter RIS file name manually? If not, I'll go with {most_recent_file.name}. (y/n, default=n): "
    else:
        prompt_message = "Would you like to enter RIS file name manually? If not, I will automate. (y/n, default=n): "
    
    # Ask user if they want to manually specify RIS file
    manual_input = input(prompt_message).strip().lower()
    
    if manual_input == 'y':
        ris_file_input = input("Enter RIS file name or path (relative to missing_papers/still_missing/): ").strip()
        if ris_file_input.startswith('archive/'):
            ris_file = Path("missing_papers/still_missing") / ris_file_input
        else:
            ris_file = Path("missing_papers/still_missing") / ris_file_input
        
        if not ris_file.exists():
            print(f"ERROR: RIS file not found: {ris_file}")
            return
        print(f"Using RIS file: {ris_file}")
    else:
        ris_file = find_most_recent_txt_file()
        if not ris_file:
            print("ERROR: Could not find any .txt file in missing_papers/still_missing/ directory")
            return
        print(f"Using automated RIS file: {ris_file}")
    
    output_dir = Path('found_papers/downloaded_papers/preprint_arxiv')
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_file = output_dir / 'label_to_filename.txt'
    
    # Import map directory
    import_ids_dir = Path("found_papers/import_IDs")
    import_ids_dir.mkdir(parents=True, exist_ok=True)
    
    # Use temporary filename during execution
    import_map_temp_path = import_ids_dir / "import_map_temp.txt"
    import_map_path = import_map_temp_path
    
    # Initialize import map file
    with open(import_map_path, 'w', encoding='utf-8') as f:
        pass
    
    print("Parsing RIS file...")
    all_papers = parse_ris_file(str(ris_file))
    
    # Filter papers with:
    # - PubMed URLs (for multi-strategy download)
    # - OUP URLs (for direct download)
    # - IOS Press DOIs (can download directly from DOI)
    target_papers = []
    for p in all_papers:
        url = p.get('url', '')
        doi = p.get('doi', '')
        if is_pubmed_url(url) or is_oup_url(url) or is_ios_press_doi(doi):
            target_papers.append(p)
    
    # Count by type
    pubmed_count = sum(1 for p in target_papers if is_pubmed_url(p.get('url', '')))
    oup_count = sum(1 for p in target_papers if is_oup_url(p.get('url', '')))
    ios_press_count = sum(1 for p in target_papers if is_ios_press_doi(p.get('doi', '')) and not is_pubmed_url(p.get('url', '')) and not is_oup_url(p.get('url', '')))
    
    print(f"Found {len(all_papers)} total papers")
    print(f"Found {len(target_papers)} target papers:")
    print(f"  - {pubmed_count} papers with PubMed URLs (will try PMC, then publisher sites, then arXiv)")
    print(f"  - {oup_count} papers with OUP URLs (will download directly)")
    print(f"  - {ios_press_count} papers with IOS Press DOIs (will download directly from DOI)\n")
    
    if not target_papers:
        print("No target papers found (PubMed URLs, OUP URLs, or IOS Press DOIs). Exiting.")
        return
    
    # Get counts for final import map filename
    input_refs = len(target_papers)
    original_ris_file = find_original_ris_file()
    if original_ris_file:
        original_refs = count_ris_references(original_ris_file)
    else:
        original_refs = input_refs
    
    # Initialize browser driver if we have papers that need browser automation
    # IOS Press papers need browser to access PDFs (direct URLs return 403)
    driver = None
    if pubmed_count > 0 or oup_count > 0 or ios_press_count > 0:
        print("Initializing browser for downloads...")
        driver = setup_driver(output_dir)
        print("Browser initialized.\n")
    else:
        print("Using direct downloads and arXiv API (no browser needed)\n")
    
    mapping_fp = open(mapping_file, 'w', encoding='utf-8')
    mapping_fp.write("# label_id|filename|title|status|error_reason|source|arxiv_id\n")
    
    successful = []  # Track successful downloads for import map
    
    try:
        for i, paper in enumerate(target_papers, 1):
            label_id = paper['label_id']
            record_number = paper['record_number']
            title = paper['title'][:60] + '...' if len(paper['title']) > 60 else paper['title']
            first_author = paper.get('first_author', '')
            output_path = output_dir / f"{label_id}.pdf"
            
            paper_url = paper.get('url', '')
            paper_doi = paper.get('doi', '')
            is_pubmed = is_pubmed_url(paper_url)
            is_oup = is_oup_url(paper_url)
            is_ios_press_doi_only = is_ios_press_doi(paper_doi) and not paper_url
            
            print(f"\n[{i}/{len(target_papers)}] Label {label_id}: {title}")
            print(f"  Author: {first_author}")
            if is_pubmed:
                print(f"  Type: PubMed (multi-strategy download)")
            elif is_oup:
                print(f"  Type: OUP (will download directly)")
            elif is_ios_press_doi_only:
                print(f"  Type: IOS Press (DOI only, will download directly from DOI)")
            
            # Check if already exists
            if output_path.exists() and output_path.stat().st_size > 1024:
                print(f"  ✓ Already exists\n")
                # Try to determine source from existing file context
                if is_pubmed:
                    source = "arxiv"
                elif is_oup:
                    source = "oup"
                elif is_ios_press_doi_only:
                    source = "ios_press"
                else:
                    source = "unknown"
                mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success|already_exists|{source}|\n")
                mapping_fp.flush()
                successful.append((record_number, output_path))
                continue
            
            success = False
            error = ""
            arxiv_id = None
            source = ""
            
            # Handle IOS Press papers with DOI only (no URL)
            if is_ios_press_doi_only:
                print(f"  Attempting IOS Press download from DOI...")
                source = "ios_press"
                if paper_doi:
                    if driver is None:
                        error = "Browser not initialized - cannot access IOS Press PDFs"
                    else:
                        # Construct article URL from DOI - try multiple patterns
                        article_urls = [
                            f"https://content.iospress.com/articles/{paper_doi.replace('/', '-')}",
                            f"https://content.iospress.com/articles/{paper_doi.replace('10.3233/', '')}",
                            f"https://doi.org/{paper_doi}",
                            f"https://www.iospress.nl/article/{paper_doi}",
                        ]
                        
                        # Try direct PDF URL first (might work for some)
                        direct_pdf_url = f"https://ebooks.iospress.nl/pdf/doi/{paper_doi}"
                        print(f"    Trying direct PDF URL: {direct_pdf_url[:80]}...")
                        try:
                            response = requests.get(direct_pdf_url, timeout=30, stream=True, allow_redirects=True)
                            if response.status_code == 200:
                                content_type = response.headers.get('content-type', '').lower()
                                if 'pdf' in content_type or direct_pdf_url.endswith('.pdf'):
                                    # Save PDF to file
                                    with open(output_path, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=8192):
                                            f.write(chunk)
                                    
                                    # Verify file was downloaded and has content
                                    if output_path.exists() and output_path.stat().st_size > 1024:
                                        print(f"  ✓ Downloaded from IOS Press (direct PDF URL): {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                        mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                        successful.append((record_number, output_path))
                                        success = True
                                    else:
                                        print(f"    Direct PDF URL returned invalid file, trying browser...")
                                else:
                                    print(f"    Direct PDF URL did not return PDF (content-type: {content_type}), trying browser...")
                            else:
                                print(f"    Direct PDF URL returned status {response.status_code}, trying browser...")
                        except Exception as e:
                            print(f"    Direct PDF URL failed: {e}, trying browser...")
                        
                        # If direct URL failed, try browser-based approach with multiple URL patterns
                        if not success:
                            print(f"    Trying browser-based approach...")
                            for article_url in article_urls:
                                print(f"    Trying article URL: {article_url[:80]}...")
                                if download_from_ios_press_url(driver, article_url, output_path, doi=paper_doi):
                                    if output_path.exists() and output_path.stat().st_size > 1024:
                                        print(f"  ✓ Downloaded from IOS Press (browser): {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                        mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                        successful.append((record_number, output_path))
                                        success = True
                                        break
                                    elif rename_downloaded_file(output_dir, label_id, timeout=20):
                                        if output_path.exists() and output_path.stat().st_size > 1024:
                                            print(f"  ✓ Downloaded from IOS Press (browser): {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                            mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                            successful.append((record_number, output_path))
                                            success = True
                                            break
                                        else:
                                            continue
                                    else:
                                        continue
                                else:
                                    continue
                            
                            if not success:
                                error = "IOS Press download failed - tried direct PDF URL and browser with multiple article URL patterns"
                else:
                    error = "IOS Press DOI not found in paper data"
            
            elif is_pubmed:
                # PubMed URL: Multi-strategy approach
                print(f"  Strategy 1: Checking for PMC access...")
                
                # Strategy 1: Check PMC first (most reliable)
                if driver is None:
                    print(f"    Browser not initialized, skipping PMC check")
                else:
                    pmc_id = extract_pmc_id_from_pubmed(driver, paper_url)
                    if pmc_id:
                        print(f"    Found PMC ID: {pmc_id}, attempting download...")
                        if download_from_pmc(driver, pmc_id, output_path):
                            # Wait for download and rename
                            if rename_downloaded_file(output_dir, label_id, timeout=20):
                                if output_path.exists() and output_path.stat().st_size > 1024:
                                    print(f"  ✓ Downloaded from PMC: {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                    source = "pmc"
                                    mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                    successful.append((record_number, output_path))
                                    success = True
                                else:
                                    error = "PMC download failed - file not found or too small after rename"
                            else:
                                error = "PMC download failed - could not rename downloaded file"
                        else:
                            error = "PMC download failed - could not download PDF"
                    else:
                        print(f"    No PMC access available")
                
                # Strategy 2: Follow PubMed URL to detect publisher
                if not success and driver is not None:
                    print(f"  Strategy 2: Following PubMed URL to detect publisher...")
                    final_url, publisher = follow_pubmed_url(driver, paper_url)
                    
                    # Strategy 3: Publisher-specific handlers
                    if publisher == 'ios_press':
                        print(f"  Strategy 3: Attempting IOS Press download...")
                        source = "ios_press"
                        # Get DOI from paper if available
                        paper_doi = paper.get('doi', '')
                        if download_from_ios_press_url(driver, final_url, output_path, doi=paper_doi):
                            # If direct PDF URL was used, file is already in place, no rename needed
                            if output_path.exists() and output_path.stat().st_size > 1024:
                                print(f"  ✓ Downloaded from IOS Press: {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                successful.append((record_number, output_path))
                                success = True
                            elif rename_downloaded_file(output_dir, label_id, timeout=20):
                                # Browser download - need to rename
                                if output_path.exists() and output_path.stat().st_size > 1024:
                                    print(f"  ✓ Downloaded from IOS Press: {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                    mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                    successful.append((record_number, output_path))
                                    success = True
                                else:
                                    error = "IOS Press download failed - file not found or too small after rename"
                            else:
                                error = "IOS Press download failed - could not rename downloaded file"
                        else:
                            error = "IOS Press download failed - direct PDF URL and PDF button both failed"
                    elif publisher == 'oup':
                        print(f"  Strategy 3: Attempting OUP download...")
                        source = "oup"
                        if download_from_oup_url(driver, final_url, output_path):
                            if rename_downloaded_file(output_dir, label_id, timeout=20):
                                if output_path.exists() and output_path.stat().st_size > 1024:
                                    print(f"  ✓ Downloaded from OUP: {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                    mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                    successful.append((record_number, output_path))
                                    success = True
                                else:
                                    error = "OUP download failed - file not found or too small after rename"
                            else:
                                error = "OUP download failed - could not rename downloaded file"
                        else:
                            error = "OUP download failed - could not click PDF button"
                    elif publisher != 'pubmed' and publisher != 'unknown':
                        print(f"  Strategy 3: Detected publisher '{publisher}', but no specific handler available")
                        error = f"Publisher '{publisher}' detected but no handler implemented"
                
                # Strategy 4: Fallback to arXiv search
                if not success:
                    print(f"  Strategy 4: Falling back to arXiv search...")
                    source = "arxiv"
                    error = "not found on arXiv"
                    arxiv_id = search_arxiv_api(paper['title'], first_author, paper.get('year'))
                    
                    if arxiv_id:
                        # Download PDF from arXiv using requests
                        if download_arxiv_pdf(arxiv_id, output_path):
                            if output_path.exists() and output_path.stat().st_size > 1024:
                                print(f"  ✓ Downloaded from arXiv: {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|{arxiv_id}\n")
                                successful.append((record_number, output_path))
                                success = True
                            else:
                                error = "arXiv download failed - file not found or too small"
                        else:
                            error = "arXiv download failed - could not download PDF"
                    else:
                        error = "all strategies failed (no PMC, publisher download failed, not on arXiv)"
                    
            elif is_oup:
                # OUP URL: download directly using browser
                source = "oup"
                if driver is None:
                    error = "browser driver not initialized"
                else:
                    if download_from_oup_url(driver, paper_url, output_path):
                        # Wait for download and rename
                        if rename_downloaded_file(output_dir, label_id, timeout=20):
                            if output_path.exists() and output_path.stat().st_size > 1024:
                                print(f"  ✓ Downloaded from OUP: {label_id}.pdf ({output_path.stat().st_size} bytes)\n")
                                mapping_fp.write(f"{label_id}|{label_id}.pdf|{paper['title']}|success||{source}|\n")
                                successful.append((record_number, output_path))
                                success = True
                            else:
                                error = "OUP download failed - file not found or too small after rename"
                        else:
                            error = "OUP download failed - could not rename downloaded file"
                    else:
                        error = "OUP download failed - could not click PDF button"
            
            if not success:
                print(f"  ✗ Failed: {error}\n")
                mapping_fp.write(f"{label_id}||{paper['title']}|failed|{error}|{source}|\n")
            
            mapping_fp.flush()
            # Delay between papers (longer for browser-based downloads)
            if is_ios_press_doi_only and source == "ios_press" and success:
                time.sleep(1)  # Small delay for direct PDF URL downloads
            elif is_pubmed and source == "arxiv":
                time.sleep(1)  # Small delay for API-based arXiv downloads
            else:
                time.sleep(2)  # Longer delay for browser-based downloads
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    finally:
        # Close browser driver if it was opened
        if driver is not None:
            try:
                driver.quit()
                print("\nBrowser closed.")
            except:
                pass
        
        mapping_fp.close()
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
        
        print(f"\nSummary:")
        print(f"  Total target papers: {len(target_papers)}")
        print(f"    - PubMed URLs: {pubmed_count}")
        print(f"    - OUP URLs: {oup_count}")
        print(f"    - IOS Press DOIs: {ios_press_count}")
        print(f"  Successfully downloaded: {downloads_count}")
        print(f"  Failed: {len(target_papers) - downloads_count}")


if __name__ == '__main__':
    main()
