#!/usr/bin/env python3
"""
AI Agent browser-based download v2 - uses browser to navigate and click download buttons.
Downloads PDFs and saves them with label IDs from RIS file.

V2 Improvements:
- Extracts PMC ID from URLs (not just C2 field)
- Adds direct URL download strategy (first priority)
- OUP-specific PDF button detection
- Enhanced file rename logic with longer timeout
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


def parse_ris_papers(filepath: str, limit: int = None):
    """Parse RIS file and extract papers with label IDs and record numbers.
    V2: Also extracts PMC ID from URLs if not found in C2 field.
    """
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
        
        # V2: Extract PMC ID from URL if not found in C2 field
        if not pmc_id and url:
            # Try to extract PMC ID from URL patterns like:
            # https://pmc.ncbi.nlm.nih.gov/articles/PMC8714283/
            # https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8714283/
            pmc_url_match = re.search(r'/pmc/articles/(?:PMC)?(\d+)', url, re.IGNORECASE)
            if pmc_url_match:
                pmc_id = pmc_url_match.group(1)
        
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


def download_from_oup_url(driver, url: str, output_path: Path):
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


def download_from_ios_press_url(driver, url: str, output_path: Path):
    """Download PDF from IOS Press website.
    V2: Enhanced PDF button detection for IOS Press sites with debugging and explicit waits.
    """
    try:
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
            # Generic download buttons/links
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
            "//a[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
            # Data attributes
            "//*[contains(@data-action, 'pdf')]",
            "//*[contains(@data-type, 'pdf')]",
            "//*[contains(@data-download, 'pdf')]",
            # Container-based selectors (IOS Press specific patterns)
            "//div[contains(@class, 'article')]//button[contains(text(), 'PDF')]",
            "//div[contains(@class, 'download')]//a[contains(text(), 'PDF')]",
            "//div[contains(@class, 'article-header')]//button[contains(text(), 'PDF')]",
            "//div[contains(@class, 'article-header')]//a[contains(text(), 'PDF')]",
            # Icon + text patterns
            "//button[.//*[contains(@class, 'pdf') or contains(@class, 'download')]]",
            "//a[.//*[contains(@class, 'pdf') or contains(@class, 'download')]]",
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

                            # Check if we navigated to a PDF or if download started
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

        # If no button found with selectors, try JavaScript search
        print(f"    DEBUG: Trying JavaScript-based element search")
        try:
            result = driver.execute_script('''
                var buttons = document.querySelectorAll('button, a, [role="button"], [onclick]');
                var found = [];
                for (var i = 0; i < buttons.length; i++) {
                    var btn = buttons[i];
                    var text = (btn.textContent || btn.getAttribute('aria-label') || btn.getAttribute('title') || '').toLowerCase();
                    if (text.includes('pdf') || text.includes('download pdf')) {
                        found.push({
                            text: text,
                            tag: btn.tagName,
                            visible: btn.offsetParent !== null
                        });
                        if (btn.offsetParent !== null) {
                            btn.scrollIntoView({block: 'center', behavior: 'smooth'});
                            setTimeout(function() { 
                                try {
                                    btn.click();
                                } catch(e) {
                                    console.log('Click error:', e);
                                }
                            }, 500);
                            return {success: true, found: found.length};
                        }
                    }
                }
                return {success: false, found: found.length, matches: found};
            ''')
            print(f"    DEBUG: JavaScript search result: {result}")
            if result and result.get('success'):
                time.sleep(5)
                return True
        except Exception as e:
            print(f"    DEBUG: JavaScript search error: {e}")

        print(f"    DEBUG: All methods failed to find/click download button")
        return False

    except Exception as e:
        print(f"    Error downloading from IOS Press: {e}")
        return False


def detect_publisher_from_url(url: str) -> str:
    """Detect publisher type from URL."""
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


def download_via_url(driver, url: str, output_path: Path):
    """V2: Download PDF via direct URL from RIS file.
    Detects publisher type and uses appropriate handler.
    """
    if not url:
        return False
    
    publisher = detect_publisher_from_url(url)
    
    # Handle PMC URLs specially
    if publisher == 'pmc':
        # Extract PMC ID from URL
        pmc_match = re.search(r'/pmc/articles/(?:PMC)?(\d+)', url, re.IGNORECASE)
        if pmc_match:
            pmc_id = pmc_match.group(1)
            return download_pmc_pdf(driver, pmc_id, output_path)
    
    # Handle OUP URLs
    elif publisher == 'oup':
        return download_from_oup_url(driver, url, output_path)
    
    # Handle IOS Press URLs
    elif publisher == 'ios_press':
        return download_from_ios_press_url(driver, url, output_path)
    
    # For other publishers, try generic approach
    else:
        try:
            driver.get(url)
            time.sleep(5)  # Wait for page to load
            
            # Handle cookie popups
            handle_cookie_popup(driver)
            time.sleep(1)
            
            # Try to find PDF download links/buttons (generic selectors)
            pdf_links = driver.find_elements(By.XPATH,
                "//a[contains(@href, '.pdf')] | "
                "//a[contains(@href, '/pdf/')] | "
                "//a[contains(text(), 'PDF')] | "
                "//a[contains(text(), 'Download PDF')] | "
                "//button[contains(text(), 'PDF')] | "
                "//button[contains(text(), 'Download PDF')]")
            
            if pdf_links:
                # Try clicking the first PDF link
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
            print(f"    Error downloading via URL: {e}")
    
    return False


def download_via_doi(driver, doi: str, output_path: Path):
    """Navigate to DOI resolver and try to download PDF from publisher page.
    V2: Enhanced with OUP-specific handling.
    """
    doi_url = f"https://dx.doi.org/{doi}"
    driver.get(doi_url)
    time.sleep(5)  # Wait for redirect to publisher page
    
    # Handle cookie popups first
    handle_cookie_popup(driver)
    time.sleep(1)
    
    # Check if we're on a publisher-specific site
    current_url = driver.current_url.lower()
    if 'academic.oup.com' in current_url or 'oup.com' in current_url:
        # Use OUP-specific handler
        return download_from_oup_url(driver, current_url, output_path)
    elif 'iospress.com' in current_url or 'iospress.nl' in current_url or 'content.iospress.com' in current_url:
        # Use IOS Press-specific handler
        return download_from_ios_press_url(driver, current_url, output_path)
    
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


def find_most_recent_txt_file() -> Optional[Path]:
    """
    Find the most recently added or modified .txt file in missing_papers/still_missing/ directory.
    Checks root level only (not subdirectories).
    
    Priority:
    1. Most recent creation time (st_birthtime)
    2. If creation times are equal, most recent modification time (st_mtime)
    
    Returns:
        Path to the most recent .txt file, or None if no .txt files are found
    """
    still_missing_dir = Path("missing_papers/still_missing")
    if not still_missing_dir.exists():
        return None
    
    txt_files = []
    for file_path in still_missing_dir.iterdir():
        if file_path.is_file() and file_path.suffix == '.txt':
            try:
                stat = file_path.stat()
                # Get creation time (birthtime), fall back to mtime if not available
                creation_time = getattr(stat, 'st_birthtime', stat.st_mtime)
                modification_time = stat.st_mtime
                txt_files.append((creation_time, modification_time, file_path))
            except (OSError, AttributeError):
                # Skip files we can't stat
                continue
    
    if not txt_files:
        return None
    
    # Sort by creation time (descending), then modification time (descending) if tied
    txt_files.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return txt_files[0][2]


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


def rename_downloaded_file(download_dir: Path, label_id: str, timeout: int = 20):
    """V2: Wait for download to complete and rename to label_id.pdf
    Enhanced with longer timeout (20s) and better file detection (15s window).
    """
    start_time = time.time()
    target_path = download_dir / f"{label_id}.pdf"
    
    # First check if target file already exists and is valid
    if target_path.exists() and target_path.stat().st_size > 1024:
        return True
    
    while time.time() - start_time < timeout:
        # Look for recently downloaded PDF files
        pdf_files = list(download_dir.glob('*.pdf'))
        for pdf_file in pdf_files:
            # V2: Check if file was modified recently (within last 15 seconds)
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
        # Default automated behavior - use the most recently added/modified .txt file
        ris_file = find_most_recent_txt_file()
        if not ris_file:
            print("ERROR: Could not find any .txt file in missing_papers/still_missing/ directory")
            return
        print(f"Using automated RIS file: {ris_file}")
    
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
            
            # V2: Strategy 1 - Try direct URL first (highest priority)
            if paper.get('url'):
                print(f"  Trying URL ({detect_publisher_from_url(paper['url'])}...")
                success = download_via_url(driver, paper['url'], output_path)
            
            # Strategy 2: Try PubMed -> PMC path
            if not success and paper.get('pmid'):
                print(f"  Trying PubMed (PMID: {paper['pmid']})...")
                success = download_pubmed_paper(driver, paper['pmid'], output_path)
            
            # Strategy 3: Try direct PMC
            if not success and paper.get('pmc_id'):
                print(f"  Trying PMC (PMC{paper['pmc_id']})...")
                success = download_pmc_pdf(driver, paper['pmc_id'], output_path)
            
            # Strategy 4: Try DOI-based download (with OUP handling)
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
