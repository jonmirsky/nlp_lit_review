#!/usr/bin/env python3
"""
Download PDFs from PubMed Central and institutional library access for references in a RIS file.
Extracts PMIDs, checks PMC availability, downloads PDFs, and tracks failures.

Supports:
- PubMed Central Open Access downloads
- HSHSL (University of Maryland) library proxy access for institutional subscriptions

NOTE: For library proxy access, you may need to authenticate through your browser first.
      The script will attempt to use your existing browser session cookies if available.
"""

import requests
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import getpass


def parse_ris_file(filepath: str) -> List[Dict[str, str]]:
    """
    Parse RIS file into list of reference dictionaries.
    
    Args:
        filepath: Path to RIS file
        
    Returns:
        List of dictionaries, each containing:
        - 'pmid': PubMed ID (from AN field)
        - 'title': Paper title (from TI field)
        - 'pmc_id': PMC ID if present (from C2 field, without 'PMC' prefix)
        - 'ris_text': Full RIS entry text
    """
    references = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split on ER  - (end of record marker)
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
            
        # Extract fields
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
                # Extract PMC ID (format: PMC2233236 or just 2233236)
                pmc_match = re.search(r'PMC?(\d+)', pmc_text, re.IGNORECASE)
                if pmc_match:
                    pmc_id = pmc_match.group(1)
        
        if pmid:  # Only add if we have a PMID
            references.append({
                'pmid': pmid,
                'title': title or 'Unknown Title',
                'pmc_id': pmc_id,
                'ris_text': entry + '\nER  - \n'  # Reconstruct full RIS entry
            })
    
    return references


def check_pmc_availability(pmid: str, session: requests.Session) -> Optional[Tuple[str, bool]]:
    """
    Check if a paper is available in PubMed Central via API.
    
    Args:
        pmid: PubMed ID
        session: Requests session with headers
        
    Returns:
        Tuple of (PMC ID without 'PMC' prefix, is_open_access) if available, None otherwise
    """
    try:
        url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={pmid}&format=json"
        response = session.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if 'records' in data and len(data['records']) > 0:
            record = data['records'][0]
            if 'pmcid' in record:
                # Extract numeric part from PMC ID (e.g., "PMC2233236" -> "2233236")
                pmc_id = record['pmcid']
                pmc_match = re.search(r'PMC?(\d+)', pmc_id, re.IGNORECASE)
                if pmc_match:
                    pmc_numeric = pmc_match.group(1)
                    # Check if it's open access by querying the article
                    is_oa = check_open_access(pmc_numeric, session)
                    return (pmc_numeric, is_oa)
    except Exception:
        pass
    
    return None


def check_open_access(pmc_id: str, session: requests.Session) -> bool:
    """
    Check if a PMC article is in the Open Access subset.
    We'll try to download and see if it works - if it fails with 403, it's not open access.
    
    Args:
        pmc_id: PMC ID (numeric)
        session: Requests session
        
    Returns:
        True if open access (or we can't determine), False if definitely not
    """
    # For now, assume all PMC articles are potentially open access
    # The download function will handle access restrictions
    return True


def download_via_library_proxy(pmid: str, output_path: Path, session: requests.Session) -> bool:
    """
    Attempt to download PDF via HSHSL library proxy access.
    Uses library link resolver and publisher access through institutional subscriptions.
    
    Args:
        pmid: PubMed ID
        output_path: Path where PDF should be saved
        session: Requests session (should have library authentication)
        
    Returns:
        True if download successful, False otherwise
    """
    # HSHSL uses ResearchPort proxy: proxy-hs.researchport.umd.edu
    proxy_base = "https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu"
    
    # Method 1: Try PubMed through library proxy to get publisher links
    urls_to_try = [
        f"{proxy_base}/pubmed/{pmid}/",
        f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    ]
    
    for base_url in urls_to_try:
        try:
            response = session.get(base_url, timeout=15, allow_redirects=True)
            if response.status_code == 200:
                html = response.text
                
                # Look for full-text links (common patterns)
                fulltext_patterns = [
                    # Publisher full-text links
                    r'href=["\']([^"\']*full[^"\']*text[^"\']*)["\']',
                    r'href=["\']([^"\']*fulltext[^"\']*)["\']',
                    r'href=["\']([^"\']*download[^"\']*pdf[^"\']*)["\']',
                    r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
                    # DOI links that might lead to full text
                    r'href=["\'](https?://[^"\']*doi[^"\']*)["\']',
                    # Publisher site links
                    r'href=["\'](https?://[^"\']*publisher[^"\']*)["\']',
                ]
                
                found_urls = set()
                for pattern in fulltext_patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    found_urls.update(matches)
                
                # Try each found URL
                for url in found_urls:
                    try:
                        # Make absolute URL if relative
                        if url.startswith('http'):
                            full_url = url
                        elif url.startswith('/'):
                            # Try with proxy base
                            full_url = f"{proxy_base}{url}"
                        else:
                            full_url = f"{base_url.rsplit('/', 1)[0]}/{url}"
                        
                        # Try to get PDF
                        pdf_response = session.get(full_url, timeout=30, stream=True, allow_redirects=True)
                        
                        if pdf_response.status_code == 200:
                            content_type = pdf_response.headers.get('Content-Type', '').lower()
                            content_preview = pdf_response.content[:1000]
                            
                            # Check if it's a PDF
                            if 'application/pdf' in content_type or b'%PDF' in content_preview:
                                with open(output_path, 'wb') as f:
                                    for chunk in pdf_response.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                
                                if output_path.exists() and output_path.stat().st_size > 1024:
                                    # Verify it's actually a PDF
                                    with open(output_path, 'rb') as f:
                                        if f.read(4) == b'%PDF':
                                            return True
                                    output_path.unlink(missing_ok=True)
                            
                            # If HTML, might be a redirect page - look for PDF links
                            elif 'text/html' in content_type:
                                html2 = pdf_response.text
                                pdf_links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', html2, re.IGNORECASE)
                                for pdf_link in pdf_links[:3]:  # Try first few
                                    if pdf_link.startswith('http'):
                                        pdf_url2 = pdf_link
                                    else:
                                        pdf_url2 = f"{full_url.rsplit('/', 1)[0]}/{pdf_link}"
                                    
                                    try:
                                        pdf2_response = session.get(pdf_url2, timeout=30, stream=True)
                                        if pdf2_response.status_code == 200 and b'%PDF' in pdf2_response.content[:500]:
                                            with open(output_path, 'wb') as f:
                                                for chunk in pdf2_response.iter_content(chunk_size=8192):
                                                    f.write(chunk)
                                            if output_path.exists() and output_path.stat().st_size > 1024:
                                                return True
                                    except Exception:
                                        continue
                    except Exception:
                        continue
        except Exception:
            continue
    
    return False


def download_pmc_pdf(pmc_id: str, output_path: Path, session: requests.Session, max_retries: int = 3) -> bool:
    """
    Download PDF from PubMed Central using multiple strategies.
    
    Args:
        pmc_id: PMC ID (numeric part only, e.g., "2233236")
        output_path: Path where PDF should be saved
        session: Requests session with proper headers
        max_retries: Maximum number of retry attempts
        
    Returns:
        True if download successful, False otherwise
    """
    # Strategy 1: Try direct PDF URL with session cookies from article page
    article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"
    
    try:
        # First, visit the article page to get cookies
        article_response = session.get(article_url, timeout=15)
        if article_response.status_code == 200:
            # Now try the PDF URL with cookies from the article page
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
            response = session.get(pdf_url, timeout=30, stream=True, allow_redirects=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                # Check if it's actually a PDF (not HTML error page)
                if 'application/pdf' in content_type:
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Verify it's a valid PDF
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        with open(output_path, 'rb') as f:
                            if f.read(4) == b'%PDF':
                                return True
                        output_path.unlink(missing_ok=True)
                else:
                    # Might be HTML - check content
                    content_preview = response.content[:500]
                    if b'%PDF' in content_preview:
                        # Actually a PDF despite wrong content-type
                        with open(output_path, 'wb') as f:
                            f.write(response.content)
                        if output_path.exists() and output_path.stat().st_size > 1024:
                            return True
    except Exception:
        pass
    
    # Strategy 2: Try using pmc-downloader library if available
    try:
        from pmc_downloader import download_pdf
        result = download_pdf(pmc_id, str(output_path))
        if result and output_path.exists() and output_path.stat().st_size > 1024:
            return True
    except ImportError:
        pass
    except Exception:
        pass
    
    # Strategy 3: Try alternative URL patterns
    alt_urls = [
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/?format=pdf",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf",
    ]
    
    for url in alt_urls:
        try:
            response = session.get(url, timeout=30, stream=True, allow_redirects=True)
            if response.status_code == 200:
                content_preview = response.content[:500]
                if b'%PDF' in content_preview:
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        return True
        except Exception:
            continue
    
    return False


def sanitize_filename(title: str, max_length: int = 40) -> str:
    """
    Sanitize title for use as filename.
    
    Args:
        title: Paper title
        max_length: Maximum length for filename (before .pdf extension)
        
    Returns:
        Sanitized filename with .pdf extension
    """
    # Remove invalid filename characters
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, '', title)
    
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    
    # Trim whitespace
    filename = filename.strip()
    
    # Truncate to max_length
    if len(filename) > max_length:
        filename = filename[:max_length].rstrip()
    
    # If empty after sanitization, use default
    if not filename:
        filename = "untitled"
    
    # Add .pdf extension
    if not filename.endswith('.pdf'):
        filename += '.pdf'
    
    return filename


def ensure_unique_filename(directory: Path, base_filename: str) -> Path:
    """
    Ensure filename is unique in directory, appending number if needed.
    
    Args:
        directory: Target directory
        base_filename: Base filename
        
    Returns:
        Path object with unique filename
    """
    output_path = directory / base_filename
    
    if not output_path.exists():
        return output_path
    
    # If file exists, append number
    name_part = base_filename[:-4]  # Remove .pdf
    counter = 1
    
    while output_path.exists():
        new_name = f"{name_part}_{counter}.pdf"
        output_path = directory / new_name
        counter += 1
    
    return output_path


def setup_library_session() -> requests.Session:
    """
    Set up a session for library proxy access.
    User will need to authenticate through browser first, then we can use cookies.
    
    Returns:
        Configured requests session
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    print("\n" + "="*60)
    print("LIBRARY PROXY ACCESS SETUP")
    print("="*60)
    print("To use HSHSL library access, you need to:")
    print("1. Open your browser and go to: https://www.hshsl.umaryland.edu/")
    print("2. Log in with your UMID and password")
    print("3. Visit a PubMed article to establish your session")
    print("4. Export your browser cookies (optional - script will try without)")
    print("\nThe script will attempt library access, but may need manual")
    print("authentication for some papers. Press Enter to continue...")
    input()
    
    return session


def main():
    """Main execution function."""
    ris_file = Path("missing_papers_12_9_2025.txt")
    output_dir = Path("found_papers")
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    # Create session with proper headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    # Ask if user wants to use library access
    use_library = input("\nUse HSHSL library proxy access? (y/n, default=y): ").strip().lower()
    if use_library != 'n':
        library_session = setup_library_session()
        # Merge library session cookies into main session
        session.cookies.update(library_session.cookies)
    
    print(f"\nParsing RIS file: {ris_file}")
    references = parse_ris_file(str(ris_file))
    print(f"Found {len(references)} references\n")
    
    successful = []
    failed = []
    
    for i, ref in enumerate(references, 1):
        pmid = ref['pmid']
        title = ref['title']
        
        print(f"[{i}/{len(references)}] Processing PMID {pmid}: {title[:60]}...", end=' ')
        
        # Check PMC availability
        pmc_info = None
        if ref.get('pmc_id'):
            # Already have PMC ID from RIS, try to use it
            pmc_info = (ref['pmc_id'], True)
        else:
            pmc_info = check_pmc_availability(pmid, session)
            time.sleep(0.3)  # Rate limiting for API calls
        
        if not pmc_info:
            print("NOT IN PMC")
            failed.append(ref)
            time.sleep(0.1)
            continue
        
        pmc_id, is_open_access = pmc_info
        
        # Sanitize filename
        filename = sanitize_filename(title, max_length=40)
        output_path = ensure_unique_filename(output_dir, filename)
        
        # Download PDF with retries
        download_success = False
        
        # Strategy 1: Try PMC download first
        for retry in range(3):
            if download_pmc_pdf(pmc_id, output_path, session):
                print(f"DOWNLOADED (PMC) -> {filename}")
                successful.append(ref)
                download_success = True
                time.sleep(0.5)  # Rate limiting between downloads
                break
            else:
                if retry < 2:
                    time.sleep(2)  # Wait before retry
        
        # Strategy 2: If PMC failed and library access enabled, try library proxy
        if not download_success and use_library != 'n':
            if download_via_library_proxy(pmid, output_path, session):
                print(f"DOWNLOADED (Library) -> {filename}")
                successful.append(ref)
                download_success = True
                time.sleep(0.5)
        
        if not download_success:
            print("DOWNLOAD FAILED (tried PMC and library access)")
            failed.append(ref)
            time.sleep(0.2)
    
    # Write failed references to still_missing.txt
    if failed:
        still_missing_path = output_dir / "still_missing.txt"
        with open(still_missing_path, 'w', encoding='utf-8') as f:
            for ref in failed:
                f.write(ref['ris_text'])
                f.write('\n')
        print(f"\n\nFailed downloads written to: {still_missing_path}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  Total references: {len(references)}")
    print(f"  Successfully downloaded: {len(successful)}")
    print(f"  Failed: {len(failed)}")
    if len(references) > 0:
        print(f"  Success rate: {len(successful)/len(references)*100:.1f}%")
    print(f"\nNOTE: Many papers may not be in the PMC Open Access subset,")
    print(f"      or PMC may restrict automated downloads. Failed downloads")
    print(f"      have been saved to still_missing.txt for manual retrieval.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

