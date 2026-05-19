#!/usr/bin/env python3
"""
Download PDFs using Selenium browser automation - Multi-Strategy V4
This version includes:
- V3 features (Elsevier API, enhanced DOI support, direct URL downloads, etc.)
- NEW: Skips references that already have attached full text files (L1/L2/L3 fields in RIS)
- Preserves existing attachment fields in output RIS file
- Error tracking and reporting
- Enhanced paywall detection
- Runtime tracking
- Optimized wait times
- Flexible file handling (still_missing*.txt pattern matching)
- arXiv preprint search and download (final fallback)

Output Files:
    - PDF files: Downloaded to found_papers/downloaded_papers/V3_scraped_papers/
                  (relative to automated_search/, one level above scripts/)
    - RIS file with attachments: Written to found_papers/RIS_files/import_to_endnote/
                                  (relative to automated_search/, one level above scripts/)
                                  Format: {input_filename}_post_scrape.txt
                                  Contains all references from input RIS file with L1 attachment fields
                                  (absolute paths) for successfully downloaded papers
                                  Preserves existing L1/L2/L3 attachment fields from input
    - Failed downloads: Written to missing_papers/still_missing/
                        (relative to automated_search/, one level above scripts/)
                        Format: missing_after_second_scrape*.txt (auto-numbered if file exists)
                        Contains RIS entries for papers that failed to download

Callable use:
    run_full_text_scrape() runs the same interactive workflow and returns the generated
    *_post_scrape.txt RIS path, or None if the workflow exits before creating it.

Requirements:
    pip install selenium webdriver-manager requests
    Also need Chrome browser installed.
"""

import re
import time
import os
import json
import logging
import datetime
import shutil
import requests
import xml.etree.ElementTree as ET
import base64
from pathlib import Path
from typing import Dict, List, Optional, Set, TYPE_CHECKING
from selenium import webdriver

try:
    from ensure_pdf_store import (
        PdfRemote,
        PdfStore,
        PdfStoreUnavailable,
        build_cas_index,
        build_master_pdf_skip_keys,
        build_remote_index,
        cas_key_for_reference,
        cas_path_for_key,
        find_newest_master_ris_path,
        health_check,
        link_into_run,
        pdf_already_on_file,
        r2_url_for_key,
        resolve_pdf_backend,
        resolve_pdf_store,
        upload_pdf_to_remote,
    )
    from search_run import (
        SearchRun,
        append_error,
        append_progress,
        read_progress,
        save_metadata,
        terminal_error_reasons_for_resume,
        terminal_outcomes_for_resume,
        utc_iso_now,
    )
    _SEARCH_RUN_AVAILABLE = True
except ImportError:
    _SEARCH_RUN_AVAILABLE = False
    if TYPE_CHECKING:
        from ensure_pdf_store import PdfRemote, PdfStore
        from search_run import SearchRun


HEALTH_CHECK_EVERY_N_PAPERS = 25
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Error reason constants
ERROR_PAYWALL = 'paywall_detected'
ERROR_NO_PDF = 'no_pdf_found'
ERROR_TIMEOUT = 'timeout'
ERROR_DOWNLOAD_FAILED = 'download_failed'
ERROR_NO_IDENTIFIER = 'no_identifier'
ERROR_PUBLISHER_ERROR = 'publisher_error'
ERROR_NOT_FOUND = 'not_found'
ERROR_UNKNOWN = 'unknown'

# Elsevier API configuration
ELSEVIER_API_KEY = '34d0457d9a5b3bbfa3547a4297cf3954'


def get_still_missing_dir() -> Path:
    """
    Get the path to missing_papers/still_missing/ directory relative to the script's location.
    This ensures the path works regardless of where the script is run from.
    """
    search_root = Path(__file__).resolve().parents[2]
    return search_root / "missing_papers" / "still_missing"


def get_next_missing_filename(output_dir: Path, base_name: str) -> str:
    """
    Get the next missing filename with intelligent numbering.
    Checks existing files and returns the next number.
    Example: if missing_after_second_scrape.txt and missing_after_second_scrape2.txt exist, 
    returns 'missing_after_second_scrape3.txt'
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Pattern to match base_name#.txt files
    pattern = re.compile(rf'^{re.escape(base_name)}(\d*)\.txt$')
    
    max_number = 0
    
    # Check all files in the directory
    for file_path in output_dir.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                number_str = match.group(1)
                if number_str:
                    number = int(number_str)
                else:
                    number = 1  # Base file (no number) counts as 1
                max_number = max(max_number, number)
    
    # Return next number
    if max_number == 0:
        return f"{base_name}.txt"
    else:
        return f"{base_name}{max_number + 1}.txt"


def find_input_ris_file() -> Optional[Path]:
    """
    Find input RIS file in missing_papers/still_missing/ directory.
    Priority:
    1. missing_after_first_scrape*.txt files (prefers base file, then highest numbered)
    2. still_missing*.txt files (prefers base file, then highest numbered)
    
    Returns:
        Path to the file, or None if not found
    """
    still_missing_dir = get_still_missing_dir()
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


def find_most_recent_txt_file() -> Optional[Path]:
    """
    Find the most recently added or modified .txt file in missing_papers/still_missing/ directory.
    Checks root level only (not subdirectories).
    
    Returns the file with the most recent timestamp (either creation or modification, whichever is newest).
    
    Returns:
        Path to the most recent .txt file, or None if no .txt files are found
    """
    still_missing_dir = get_still_missing_dir()
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
                # Use whichever timestamp is most recent (creation or modification)
                most_recent_time = max(creation_time, modification_time)
                txt_files.append((most_recent_time, file_path))
            except (OSError, AttributeError):
                # Skip files we can't stat
                continue
    
    if not txt_files:
        return None
    
    # Sort by most recent time (descending) - whichever is newest (creation or modification)
    txt_files.sort(key=lambda x: x[0], reverse=True)
    return txt_files[0][1]


def parse_ris_file(filepath: str, download_dir: Optional[Path] = None) -> List[Dict[str, str]]:
    """Parse RIS file into list of reference dictionaries, including DOIs, URLs, and metadata.
    
    Args:
        filepath: Path to RIS file
        download_dir: Optional download directory to check if files exist there
    """
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
        pii = None  # PII identifier extracted from ScienceDirect URLs
        journal = None  # T2 field - journal name
        issn = None  # SN field - ISSN
        publisher = None  # PB field - publisher
        start_page = None  # SP field
        end_page = None  # EP field
        volume = None  # VL field
        year = None  # PY field
        first_author = None  # AU field - first author
        has_attachment = False  # Track if reference already has L1/L2/L3 attachment field
        existing_attachments = []  # List of existing L1/L2/L3 attachment paths
        
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
                # Extract PII from ScienceDirect URLs (e.g., /pii/S1532046424001345)
                if url and 'sciencedirect.com' in url.lower():
                    pii_match = re.search(r'/pii/([A-Z0-9]+)', url, re.IGNORECASE)
                    if pii_match:
                        pii = pii_match.group(1)
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
            elif line.startswith('L1  - ') or line.startswith('L2  - ') or line.startswith('L3  - '):
                # Attachment field (L1, L2, or L3) - check if it's an actual file path
                attachment_path = line[6:].strip()
                if attachment_path:
                    # Only treat as attachment if it's an actual file path (starts with /)
                    # internal-pdf:// references are NOT real attachments (EndNote internal format)
                    if attachment_path.startswith('/'):
                        # Check if file exists at the absolute path
                        abs_path = Path(attachment_path)
                        file_exists = False
                        
                        if abs_path.exists() and abs_path.is_file() and abs_path.stat().st_size > 1024:
                            file_exists = True
                        elif download_dir and download_dir.exists():
                            # Also check if file exists in download directory (by filename)
                            filename = abs_path.name
                            existing_file, _ = find_existing_paper_in_download_papers(filename, download_dir)
                            if existing_file:
                                file_exists = True
                                attachment_path = str(existing_file)  # Use found path
                        
                        if file_exists:
                            has_attachment = True
                            existing_attachments.append(attachment_path)
                    # Skip internal-pdf:// references - they don't have actual files
        
        # Accept if we have any identifier or metadata
        if pmid or doi or url or title:
            references.append({
                'pmid': pmid,
                'title': title or 'Unknown Title',
                'pmc_id': pmc_id,
                'doi': doi,
                'record_number': record_number,
                'url': url,
                'pii': pii,
                'journal': journal,
                'issn': issn,
                'publisher': publisher,
                'start_page': start_page,
                'end_page': end_page,
                'volume': volume,
                'year': year,
                'first_author': first_author,
                'has_attachment': has_attachment,  # True if L1/L2/L3 field exists
                'existing_attachments': existing_attachments,  # List of existing attachment paths
                'ris_text': entry + '\nER  - \n'
            })
    
    return references


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


def find_existing_paper_in_download_papers(filename: str, download_papers_dir: Path) -> tuple[Optional[Path], bool]:
    """
    Search for a paper file anywhere in download_papers directory (including subfolders).
    
    Args:
        filename: Filename to search for (e.g., "6443.pdf")
        download_papers_dir: Base download_papers directory
    
    Returns:
        Tuple of (Path to existing file if found, bool indicating if it's loose in root)
        Returns (None, False) if not found
    """
    if not download_papers_dir.exists():
        return (None, False)
    
    # Check if file exists loose in download_papers root (not in subfolders)
    loose_file = download_papers_dir / filename
    if loose_file.exists() and loose_file.is_file() and loose_file.stat().st_size > 1024:
        return (loose_file, True)  # Found loose in root
    
    # Search recursively in subfolders only (skip root level)
    for pdf_file in download_papers_dir.rglob(filename):
        if pdf_file.is_file() and pdf_file.stat().st_size > 1024:
            # Check if it's in a subdirectory (not root)
            try:
                relative_path = pdf_file.relative_to(download_papers_dir)
                # If relative path has more than just the filename, it's in a subfolder
                if len(relative_path.parts) > 1:
                    return (pdf_file, False)  # Found in subfolder
            except ValueError:
                # Path is not relative to download_papers_dir, skip
                continue
    
    return (None, False)  # Not found


def find_original_ris_file() -> Optional[Path]:
    """
    Find the original RIS file (the one the first scrape script would have read).
    Looks for missing_papers*.txt files in missing_papers/still_missing/ directory.
    """
    still_missing_dir = get_still_missing_dir()
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


# #region Commented out - Import map functionality (kept for reference)
# def get_import_map_filename(downloads: int, input_refs: int, original_refs: int, import_ids_dir: Path) -> str:
#     """
#     Generate import map filename in format: import_{downloads}_of_{input_refs}_of_{original_refs}_full_text_v3.txt
#     """
#     import_ids_dir.mkdir(parents=True, exist_ok=True)
#     return f"import_{downloads}_of_{input_refs}_of_{original_refs}_full_text_v3.txt"
# #endregion


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


def _truthy_value(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _truthy_env(name: str) -> bool:
    return _truthy_value(os.environ.get(name))


def _prepend_ld_library_path(path: Path) -> None:
    """Make user-level shared libraries visible to Chrome/ChromeDriver."""
    if not path.is_dir():
        return
    path_str = str(path)
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    parts = [p for p in existing.split(":") if p]
    if path_str not in parts:
        os.environ["LD_LIBRARY_PATH"] = ":".join([path_str] + parts)


def _ensure_user_chrome_runtime_libs() -> None:
    """Support no-sudo Chrome installs that depend on locally extracted .deb libs."""
    _prepend_ld_library_path(Path.home() / "local_libs" / "usr" / "lib" / "x86_64-linux-gnu")


def _resolve_configured_chrome_binary(configured: str) -> str:
    chrome_binary_path = Path(os.path.expandvars(os.path.expanduser(configured))).resolve()
    if not chrome_binary_path.is_file():
        raise RuntimeError(f"LIT_REVIEW_CHROME_BINARY is not a file: {chrome_binary_path}")
    if not os.access(chrome_binary_path, os.X_OK):
        raise RuntimeError(f"LIT_REVIEW_CHROME_BINARY is not executable: {chrome_binary_path}")
    return str(chrome_binary_path)


def _resolve_chrome_binary() -> Optional[str]:
    configured = os.environ.get("LIT_REVIEW_CHROME_BINARY", "").strip()
    if configured:
        if any(sep in configured for sep in ("/", os.sep)) or configured.startswith("~"):
            return _resolve_configured_chrome_binary(configured)
        found = shutil.which(configured)
        if found:
            return found
        raise RuntimeError(
            f"LIT_REVIEW_CHROME_BINARY was set but could not be found on PATH: {configured}"
        )

    for candidate in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _chrome_args(chrome_options: Options) -> list[str]:
    return list(getattr(chrome_options, "arguments", []) or [])


def _add_chrome_arg_once(chrome_options: Options, arg: str) -> None:
    if arg not in _chrome_args(chrome_options):
        chrome_options.add_argument(arg)


def setup_driver(headless: bool = False, download_dir: str = None) -> webdriver.Chrome:
    """Set up Chrome driver with download preferences.

    This is intentionally hardened for SSH/GPU servers with no desktop session:
    - honors LIT_REVIEW_CHROME_BINARY for user-installed Chrome for Testing
    - forces headless mode when LIT_REVIEW_CHROME_HEADLESS is true or DISPLAY is absent
    - uses a unique temporary Chrome profile to avoid profile-lock crashes
    - makes locally extracted Chrome runtime libraries visible without sudo
    """
    _ensure_user_chrome_runtime_libs()

    chrome_options = Options()

    chrome_binary = _resolve_chrome_binary()
    if not chrome_binary:
        raise RuntimeError(
            "Chrome/Chromium browser binary not found. Install Chrome or Chromium on this "
            "server, or set LIT_REVIEW_CHROME_BINARY to the browser path. Example for this "
            "VPS: export LIT_REVIEW_CHROME_BINARY=\"$HOME/apps/chrome-for-testing/chrome-linux64/chrome\""
        )
    chrome_options.binary_location = chrome_binary
    print(f"Using Chrome binary: {chrome_binary}")

    display = os.environ.get("DISPLAY", "").strip()
    env_forces_headless = _truthy_env("LIT_REVIEW_CHROME_HEADLESS")
    force_headless = bool(headless or env_forces_headless or not display)
    if force_headless:
        _add_chrome_arg_once(chrome_options, "--headless=new")

    # Unique per-driver profile prevents "Chrome instance exited" from stale profile locks.
    import tempfile
    profile_dir = Path(tempfile.mkdtemp(prefix="lit_review_chrome_profile_")).resolve()
    _add_chrome_arg_once(chrome_options, f"--user-data-dir={profile_dir}")

    # SSH/container-safe Chrome flags.
    for arg in (
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--remote-debugging-port=0",
        "--window-size=1920,1080",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
    ):
        _add_chrome_arg_once(chrome_options, arg)

    # Set download preferences.
    # Default to automated_search/found_papers/downloaded_papers if not specified.
    if download_dir:
        download_path_obj = Path(download_dir).expanduser().resolve()
    else:
        search_root = Path(__file__).resolve().parents[2]
        download_path_obj = search_root / "found_papers" / "downloaded_papers"
    download_path_obj.mkdir(parents=True, exist_ok=True)
    download_path = str(download_path_obj)

    prefs = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True,  # Download PDFs instead of viewing
        "profile.default_content_settings.popups": 0,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
        # Force PDFs to download instead of displaying
        "plugins.plugins_list": [{"enabled": False, "name": "Chrome PDF Viewer"}],
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    _add_chrome_arg_once(chrome_options, "--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    print(f"Chrome headless forced: {force_headless}")
    print(f"DISPLAY={display!r}")
    print(f"Chrome profile dir: {profile_dir}")
    print(f"Chrome download dir: {download_path}")
    print(f"LD_LIBRARY_PATH={os.environ.get('LD_LIBRARY_PATH', '')!r}")
    print(f"Chrome args: {' '.join(_chrome_args(chrome_options))}")

    chromedriver_path = ChromeDriverManager().install()
    chromedriver_log_path = download_path_obj / "chromedriver.log"
    try:
        service = Service(chromedriver_path, log_output=str(chromedriver_log_path))
    except TypeError:
        # Fallback for older Selenium versions.
        service = Service(chromedriver_path)
        service.service_args = ["--verbose", f"--log-path={chromedriver_log_path}"]

    print(f"ChromeDriver log: {chromedriver_log_path}")

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as exc:
        print("Chrome failed to start under Selenium.")
        print(f"  Chrome binary: {chrome_binary}")
        print(f"  Headless forced: {force_headless}")
        print(f"  DISPLAY: {display!r}")
        print(f"  ChromeDriver log: {chromedriver_log_path}")
        if chromedriver_log_path.exists():
            try:
                tail = chromedriver_log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                if tail:
                    print("----- ChromeDriver log tail -----")
                    print(tail)
                    print("----- end ChromeDriver log tail -----")
            except Exception as log_exc:
                print(f"  Could not read ChromeDriver log: {log_exc}")
        raise

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def detect_paywall(driver: webdriver.Chrome) -> bool:
    """
    Enhanced paywall detection - checks multiple indicators.
    Also checks for positive indicators (Open access, View PDF button) before marking as paywall.
    
    Returns:
        True if paywall detected, False otherwise
    """
    try:
        page_source = driver.page_source.lower()
        page_title = driver.title.lower()
        current_url = driver.current_url.lower()
        
        # Check for positive indicators first (Open access, View PDF button available)
        # If these are present and functional, don't mark as paywall
        if any(term in page_source for term in ['open access', 'view pdf', 'download pdf', '/pdfft']):
            try:
                # Check if View PDF button is actually available and enabled
                # Use multiple selectors to match the actual HTML structure
                view_pdf_selectors = [
                    # ScienceDirect-specific selectors
                    "//a[@aria-label='View PDF. Opens in a new window.']",
                    "//a[contains(@aria-label, 'View PDF')]",
                    "//a[contains(@class, 'accessbar-utility-link')]",
                    "//a[contains(@href, '/pdfft')]",
                    # Generic selectors
                    "//button[contains(text(), 'View PDF')]",
                    "//a[contains(text(), 'View PDF')]",
                    "//a[.//span[contains(text(), 'View PDF')]]",
                ]
                
                for selector in view_pdf_selectors:
                    try:
                        view_pdf_buttons = driver.find_elements(By.XPATH, selector)
                        if view_pdf_buttons:
                            for button in view_pdf_buttons[:3]:
                                try:
                                    if button.is_enabled() and button.is_displayed():
                                        return False  # PDF is accessible via View PDF button
                                except:
                                    continue
                    except:
                        continue
            except:
                pass
        
        # Expanded paywall detection terms (removed 'institutional access' as it appears on accessible pages)
        paywall_terms = [
            'paywall', 'access denied', 'subscription required', 'sign in', 'login required',
            '403', 'forbidden', 'purchase', 'buy article',
            'society member', 'article unavailable', 'not available in your region',
            'requires subscription', 'view only', 'preview only', 'locked',
            'access restricted', 'members only', 'subscriber only'
        ]
        
        # Check page source
        if any(term in page_source for term in paywall_terms):
            return True
        
        # Check page title
        if any(term in page_title for term in paywall_terms):
            return True
        
        # Check for common paywall elements
        try:
            paywall_elements = driver.find_elements(By.XPATH, 
                "//*[contains(@class, 'paywall') or contains(@class, 'access-denied') or "
                "contains(@id, 'paywall') or contains(@id, 'access-denied')]")
            if paywall_elements:
                return True
        except:
            pass
        
        return False
    except:
        return False


def detect_404_error(driver: webdriver.Chrome) -> bool:
    """
    Detect if the current page is a 404 (Not Found) error page.
    Checks page title, URL, and content for 404 indicators.
    
    Returns:
        True if 404 detected, False otherwise
    """
    try:
        # Wait a moment for page to fully load
        time.sleep(1)
        
        page_source = driver.page_source.lower()
        page_title = driver.title.lower()
        current_url = driver.current_url.lower()
        
        # Common 404 indicators - expanded list
        not_found_indicators = [
            '404', 'not found', 'page not found', 'error 404',
            'file not found', 'page does not exist', 'cannot be found',
            'the page you are looking for', 'page unavailable',
            'resource not found', 'document not found', 'not available',
            'error 404', '404 error', '404 page', 'page not available',
            'content not found', 'page does not exist', 'broken link'
        ]
        
        # Check page title first (most reliable)
        if any(term in page_title for term in not_found_indicators):
            return True
        
        # Check URL for 404 patterns (very reliable)
        if '404' in current_url or '/not-found' in current_url or '/error' in current_url or '/404' in current_url:
            return True
        
        # Check page source (check first 5000 chars for speed)
        page_preview = page_source[:5000] if len(page_source) > 5000 else page_source
        if any(term in page_preview for term in not_found_indicators):
            # Double-check by looking for common 404 phrases together
            if ('404' in page_preview and ('not found' in page_preview or 'error' in page_preview)):
                return True
        
        # Check for common 404 page elements
        try:
            error_elements = driver.find_elements(By.XPATH,
                "//*[contains(@class, 'error-404') or contains(@class, 'not-found') or "
                "contains(@id, '404') or contains(@id, 'not-found') or "
                "contains(@class, 'error-page') or contains(@class, 'page-error')]")
            if error_elements:
                return True
        except:
            pass
        
        # Check HTTP status if available (some sites show status in page)
        if 'http status: 404' in page_source or 'status code: 404' in page_source:
            return True
        
        return False
    except Exception as e:
        # If we can't check, assume it's not a 404 (conservative approach)
        return False


def transform_url_to_pdf_url(url: str, current_url: str = None) -> List[str]:
    """
    Generate alternative PDF URLs from an abstract/article URL.
    Tries common patterns to convert abstract pages to PDF download pages.
    
    Args:
        url: Original URL from RIS file
        current_url: Current URL after navigation (if different from original)
    
    Returns:
        List of potential PDF URLs to try
    """
    if not url:
        return []
    
    # Use current_url if provided (might be redirected)
    base_url = current_url if current_url else url
    base_url_lower = base_url.lower()
    
    pdf_urls = []
    
    # Common URL transformation patterns
    transformations = [
        # Article/Abstract to PDF
        (r'/article/', '/pdf/'),
        (r'/abstract/', '/pdf/'),
        (r'/view/', '/download/'),
        (r'/article/', '/fulltext/pdf/'),
        (r'/abstract/', '/fulltext/'),
        (r'/article/', '/download/pdf/'),
        # Replace patterns
        (r'/html/', '/pdf/'),
        (r'/epub/', '/pdf/'),
    ]
    
    for pattern, replacement in transformations:
        try:
            if re.search(pattern, base_url_lower):
                # Use original case for replacement
                transformed = re.sub(pattern, replacement, base_url, flags=re.IGNORECASE)
                pdf_urls.append(transformed)
        except:
            continue
    
    # Add .pdf extension (special case)
    if not base_url.endswith('.pdf') and not base_url.endswith('/'):
        pdf_urls.append(base_url + '.pdf')
    
    # Publisher-specific patterns
    if 'springer' in base_url_lower:
        # Springer: /article/10.xxx/xxx -> /content/pdf/10.xxx/xxx.pdf
        springer_match = re.search(r'/article/(10\.\d+/[^/]+)', base_url_lower)
        if springer_match:
            doi_part = springer_match.group(1)
            pdf_urls.append(f"https://link.springer.com/content/pdf/{doi_part}.pdf")
    
    if 'wiley' in base_url_lower:
        # Wiley: /doi/abs/10.xxx -> /doi/pdf/10.xxx or /doi/pdfdirect/10.xxx
        wiley_match = re.search(r'/doi/(abs|full)/(10\.\d+/[^/]+)', base_url_lower)
        if wiley_match:
            doi_part = wiley_match.group(2)
            pdf_urls.append(base_url.replace('/doi/abs/', '/doi/pdf/').replace('/doi/full/', '/doi/pdf/'))
            pdf_urls.append(base_url.replace('/doi/abs/', '/doi/pdfdirect/').replace('/doi/full/', '/doi/pdfdirect/'))
    
    if 'ieee' in base_url_lower:
        # IEEE: /document/xxx -> /document/xxx.pdf
        if '/document/' in base_url_lower and not base_url_lower.endswith('.pdf'):
            pdf_urls.append(base_url + '.pdf')
    
    if 'sciencedirect' in base_url_lower:
        # ScienceDirect: /article/pii/xxx -> /article/pii/xxx/pdfft
        if '/article/pii/' in base_url_lower:
            pii_match = re.search(r'/article/pii/([^/]+)', base_url_lower)
            if pii_match:
                pii = pii_match.group(1)
                pdf_urls.append(base_url.replace(f'/article/pii/{pii}', f'/article/pii/{pii}/pdfft'))
    
    # Remove duplicates and return
    return list(dict.fromkeys(pdf_urls))  # Preserves order while removing duplicates


def handle_cookie_popup(driver: webdriver.Chrome) -> bool:
    """
    Handle cookie consent popups by clicking Accept/Accept All buttons.
    
    Returns:
        True if cookie popup was found and handled, False otherwise
    """
    try:
        # Common cookie popup button selectors
        cookie_selectors = [
            "//button[contains(text(), 'Accept')]",
            "//button[contains(text(), 'Accept All')]",
            "//button[contains(text(), 'I Accept')]",
            "//button[contains(text(), 'Accept Cookies')]",
            "//button[contains(text(), 'Accept All Cookies')]",
            "//a[contains(text(), 'Accept')]",
            "//a[contains(text(), 'Accept All')]",
            "//button[contains(@id, 'accept')]",
            "//button[contains(@class, 'accept')]",
            "//button[contains(@class, 'cookie-accept')]",
            "//*[contains(@id, 'cookie-accept')]",
            "//button[contains(@data-testid, 'accept')]",
        ]
        
        for selector in cookie_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:3]:
                    try:
                        if element.is_displayed() and element.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView(true);", element)
                            time.sleep(0.5)
                            element.click()
                            time.sleep(1)  # Wait for popup to close
                            return True
                    except:
                        continue
            except:
                continue
        
        return False
    except:
        return False


def handle_ad_popup(driver: webdriver.Chrome, timeout: int = 5) -> bool:
    """
    Handle ad popups by finding and clicking close buttons.
    Looks for common ad popup patterns across websites.
    
    Args:
        driver: Selenium WebDriver instance
        timeout: Maximum time to spend looking for ad popup
    
    Returns:
        True if ad popup was found and closed, False otherwise
    """
    try:
        start_time = time.time()
        
        # Common ad popup close button selectors
        close_selectors = [
            # Close buttons with text
            "//button[contains(text(), 'Close')]",
            "//button[contains(text(), 'Skip')]",
            "//button[contains(text(), 'Skip Ad')]",
            "//button[contains(text(), 'No thanks')]",
            "//button[contains(text(), 'No Thanks')]",
            "//a[contains(text(), 'Close')]",
            "//a[contains(text(), 'Skip')]",
            # Close buttons with symbols (X, ×)
            "//button[contains(@aria-label, 'Close')]",
            "//button[contains(@aria-label, 'close')]",
            "//button[@class='close']",
            "//button[contains(@class, 'close-button')]",
            "//button[contains(@class, 'close-btn')]",
            "//*[contains(@class, 'close') and contains(@class, 'button')]",
            # Common ad popup container patterns
            "//div[contains(@class, 'ad-popup')]//button[contains(@class, 'close')]",
            "//div[contains(@class, 'popup')]//button[contains(@class, 'close')]",
            "//div[contains(@class, 'modal')]//button[contains(@class, 'close')]",
            "//div[contains(@id, 'ad')]//button[contains(@class, 'close')]",
            # Top-right corner close buttons (common pattern)
            "//div[contains(@class, 'popup')]//button[position()=last()]",
            "//div[contains(@class, 'modal')]//button[position()=last()]",
        ]
        
        while time.time() - start_time < timeout:
            for selector in close_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for element in elements[:5]:  # Check first few matches
                        try:
                            if element.is_displayed() and element.is_enabled():
                                # Check if element is in a popup/modal context
                                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.3)
                                element.click()
                                time.sleep(0.5)  # Wait for popup to close
                                return True
                        except:
                            continue
                except:
                    continue
            
            time.sleep(0.3)  # Brief pause before retry
        
        return False
    except:
        return False


def find_pdf_links_in_html(driver: webdriver.Chrome, base_url: str) -> List[Dict[str, str]]:
    """
    Search HTML source code directly for PDF-related links and buttons.
    Like using Ctrl+F to find PDF references in the page source.
    
    Args:
        driver: Selenium WebDriver instance
        base_url: Base URL of the current page for converting relative URLs
    
    Returns:
        List of dictionaries with 'type' (url/id/data/class) and 'value' (the actual value)
    """
    try:
        page_source = driver.page_source
        findings = []
        
        # Search for PDF URLs in href attributes
        pdf_url_patterns = [
            r'href=["\']([^"\']*\.pdf[^"\']*)["\']',  # Direct .pdf links
            r'href=["\']([^"\']*pdf[^"\']*)["\']',  # Links containing "pdf"
            r'href=["\']([^"\']*view[^"\']*pdf[^"\']*)["\']',  # "view" + "pdf"
            r'href=["\']([^"\']*download[^"\']*pdf[^"\']*)["\']',  # "download" + "pdf"
        ]
        
        for pattern in pdf_url_patterns:
            matches = re.finditer(pattern, page_source, re.IGNORECASE)
            for match in matches:
                url = match.group(1)
                # Convert relative URLs to absolute
                if url.startswith('/'):
                    url = base_url.split('/')[0] + '//' + base_url.split('/')[2] + url
                elif not url.startswith('http'):
                    url = base_url.rsplit('/', 1)[0] + '/' + url
                findings.append({'type': 'url', 'value': url})
        
        # Search for button/link IDs containing "pdf"
        id_patterns = [
            r'id=["\']([^"\']*pdf[^"\']*)["\']',
            r'id=["\']([^"\']*view[^"\']*pdf[^"\']*)["\']',
        ]
        
        for pattern in id_patterns:
            matches = re.finditer(pattern, page_source, re.IGNORECASE)
            for match in matches:
                element_id = match.group(1)
                findings.append({'type': 'id', 'value': element_id})
        
        # Search for data attributes
        data_patterns = [
            r'data-[^=]*=["\']([^"\']*pdf[^"\']*)["\']',
            r'data-testid=["\']([^"\']*pdf[^"\']*)["\']',
        ]
        
        for pattern in data_patterns:
            matches = re.finditer(pattern, page_source, re.IGNORECASE)
            for match in matches:
                data_value = match.group(1)
                findings.append({'type': 'data', 'value': data_value})
        
        # Search for class names containing "pdf"
        class_patterns = [
            r'class=["\']([^"\']*pdf[^"\']*)["\']',
            r'class=["\']([^"\']*view[^"\']*pdf[^"\']*)["\']',
        ]
        
        for pattern in class_patterns:
            matches = re.finditer(pattern, page_source, re.IGNORECASE)
            for match in matches:
                class_name = match.group(1).split()[0]  # Take first class
                findings.append({'type': 'class', 'value': class_name})
        
        return findings
    except:
        return []


def check_iframes_for_pdf(driver: webdriver.Chrome) -> Optional[str]:
    """
    Check all iframes on the page for PDF buttons/links.
    
    Returns:
        Error reason if failed, None if PDF link found and clicked
    """
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                
                # Look for PDF buttons/links in iframe
                pdf_selectors = [
                    "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
                    "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
                    "//button[contains(@aria-label, 'pdf')]",
                    "//a[contains(@href, 'pdf')]",
                ]
                
                for selector in pdf_selectors:
                    try:
                        elements = driver.find_elements(By.XPATH, selector)
                        for element in elements[:3]:
                            if element.is_displayed() and element.is_enabled():
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(0.5)
                                element.click()
                                time.sleep(2)
                                driver.switch_to.default_content()
                                return None
                    except:
                        continue
                
                driver.switch_to.default_content()
            except:
                driver.switch_to.default_content()
                continue
        
        return ERROR_NO_PDF
    except:
        return ERROR_NO_PDF


def wait_for_captcha_completion(driver: webdriver.Chrome, timeout: int = 180) -> bool:
    """
    Wait for user to complete captcha manually.
    Uses a more flexible approach: waits for any significant page change
    or waits a reasonable time for user to complete captcha.
    
    Args:
        driver: Selenium WebDriver instance
        timeout: Maximum time to wait in seconds (increased to 180 for manual completion)
    
    Returns:
        True if captcha completed or not present, False if timeout
    """
    print("  [Waiting for captcha completion - please complete captcha manually...] ", end='', flush=True)
    start_time = time.time()
    initial_url = driver.current_url
    initial_title = driver.title
    initial_page_length = len(driver.page_source)
    captcha_detected = False
    
    # Define captcha selectors (check in main page and iframes)
    captcha_selectors = [
        "//iframe[contains(@src, 'recaptcha')]",
        "//iframe[contains(@src, 'hcaptcha')]",
        "//iframe[contains(@src, 'captcha')]",
        "//div[contains(@class, 'captcha')]",
        "//*[contains(@id, 'captcha')]",
        "//div[contains(@class, 'g-recaptcha')]",
        "//div[contains(@class, 'h-captcha')]",
        "//div[contains(@class, 'recaptcha')]",
        "//div[contains(@class, 'cf-')]",  # Cloudflare captcha
    ]
    
    # Check for captcha in main page
    for _ in range(8):  # Check for captcha for first 8 seconds
        try:
            for selector in captcha_selectors:
                try:
                    if driver.find_elements(By.XPATH, selector):
                        captcha_detected = True
                        break
                except:
                    continue
            
            # Also check in iframes
            if not captcha_detected:
                try:
                    iframes = driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        try:
                            driver.switch_to.frame(iframe)
                            for selector in captcha_selectors:
                                if driver.find_elements(By.XPATH, selector):
                                    captcha_detected = True
                                    break
                            driver.switch_to.default_content()
                            if captcha_detected:
                                break
                        except:
                            driver.switch_to.default_content()
                            continue
                except:
                    pass
            
            if captcha_detected:
                break
        except:
            pass
        time.sleep(1)
    
    if captcha_detected:
        print("(captcha found) ", end='', flush=True)
    else:
        print("(checking for page changes) ", end='', flush=True)
    
    # Wait for completion - check for any significant page change
    # This is more flexible than waiting for captcha to disappear
    no_change_count = 0
    while time.time() - start_time < timeout:
        try:
            current_url = driver.current_url
            current_title = driver.title
            current_page_length = len(driver.page_source)
            
            # Check for URL change (strong indicator of completion)
            if current_url != initial_url:
                print("completed (URL changed)", flush=True)
                return True
            
            # Check if we're on a PDF page
            if '.pdf' in current_url.lower():
                print("completed (PDF URL)", flush=True)
                return True
            
            # Check page source for PDF content
            try:
                page_source_lower = driver.page_source.lower()
                if 'application/pdf' in page_source_lower or 'pdf' in current_title.lower():
                    print("completed (PDF content)", flush=True)
                    return True
            except:
                pass
            
            # Check if page content changed significantly (might indicate captcha passed)
            if abs(current_page_length - initial_page_length) > 1000:
                # Significant page change - might be captcha completed
                time.sleep(2)  # Wait a bit more to see if it stabilizes
                if driver.current_url != current_url:
                    print("completed (page changed)", flush=True)
                    return True
            
            # Check if captcha is still present (if we detected one)
            if captcha_detected:
                captcha_still_present = False
                try:
                    for selector in captcha_selectors:
                        try:
                            if driver.find_elements(By.XPATH, selector):
                                captcha_still_present = True
                                break
                        except:
                            continue
                    
                    # Also check in iframes
                    if not captcha_still_present:
                        try:
                            iframes = driver.find_elements(By.TAG_NAME, "iframe")
                            for iframe in iframes:
                                try:
                                    driver.switch_to.frame(iframe)
                                    for selector in captcha_selectors:
                                        if driver.find_elements(By.XPATH, selector):
                                            captcha_still_present = True
                                            break
                                    driver.switch_to.default_content()
                                    if captcha_still_present:
                                        break
                                except:
                                    driver.switch_to.default_content()
                                    continue
                        except:
                            pass
                    
                    if not captcha_still_present:
                        # Captcha disappeared - wait a moment to see if page loads
                        time.sleep(3)
                        if driver.current_url != current_url or '.pdf' in driver.current_url.lower():
                            print("completed (captcha gone)", flush=True)
                            return True
                except:
                    pass
            
            # If no changes for a while, might be stuck - but continue waiting
            if current_url == initial_url and current_title == initial_title:
                no_change_count += 1
            else:
                no_change_count = 0
                
        except:
            pass
        
        time.sleep(3)  # Check every 3 seconds
    
    # Timeout reached
    print("(timeout - proceeding anyway)", flush=True)
    # Return True anyway - user might have completed it, script should continue
    return True


# ============================================================================
# arXiv Search and Download Functions
# ============================================================================

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


def download_via_elsevier_api(doi: str, output_path: Path, api_key: str, pii: Optional[str] = None) -> Optional[str]:
    """
    Download PDF from ScienceDirect using Elsevier API.
    
    This function uses the direct Elsevier API endpoint to download PDFs,
    completely bypassing CAPTCHA and web scraping.
    
    Args:
        doi: DOI identifier (e.g., "10.1016/j.jbi.2024.104716")
        output_path: Path where PDF should be saved
        api_key: Elsevier API key
        pii: Optional PII identifier (alternative to DOI)
    
    Returns:
        None on success, ERROR_* string on failure
    """
    try:
        # Check if file already exists
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None  # Already downloaded
        
        # Use DOI if available, otherwise try PII
        identifier = None
        identifier_type = None
        
        if doi:
            identifier = doi
            identifier_type = 'doi'
        elif pii:
            identifier = pii
            identifier_type = 'pii'
        else:
            return ERROR_NO_IDENTIFIER
        
        # Construct API URL
        if identifier_type == 'doi':
            # Clean DOI (remove any URL prefixes)
            clean_doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', identifier, flags=re.IGNORECASE)
            clean_doi = re.sub(r'^doi:', '', clean_doi, flags=re.IGNORECASE)
            clean_doi = clean_doi.strip()
            api_url = f'https://api.elsevier.com/content/article/doi/{clean_doi}?apiKey={api_key}&httpAccept=application/pdf'
        else:  # PII
            api_url = f'https://api.elsevier.com/content/article/pii/{pii}?apiKey={api_key}&httpAccept=application/pdf'
        
        # Make API request
        try:
            response = requests.get(api_url, timeout=30, allow_redirects=True)
        except requests.exceptions.Timeout:
            return ERROR_TIMEOUT
        except requests.exceptions.RequestException as e:
            return ERROR_PUBLISHER_ERROR
        
        # Check response status
        if response.status_code == 200:
            # Check if response is actually a PDF
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' in content_type or response.content[:4] == b'%PDF':
                # Save PDF to file
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                # Verify file was saved and has content
                if output_path.exists() and output_path.stat().st_size > 1024:
                    return None  # Success
                else:
                    return ERROR_DOWNLOAD_FAILED
            else:
                # Response is not a PDF - might be HTML error page or JSON error
                # Check if it's an error message
                try:
                    error_data = response.json()
                    if 'service-error' in error_data or 'error' in error_data:
                        # Check for access denied / subscription required
                        error_msg = str(error_data).lower()
                        if 'access' in error_msg or 'subscription' in error_msg or 'entitlement' in error_msg:
                            return ERROR_PAYWALL
                        return ERROR_NO_PDF
                except:
                    pass
                
                # If we can't parse it as JSON, check if it's HTML
                if b'<html' in response.content[:100] or b'<!DOCTYPE' in response.content[:100]:
                    # Likely an error page
                    return ERROR_NO_PDF
                
                return ERROR_NO_PDF
        elif response.status_code == 401:
            # Unauthorized - API key issue or access denied
            return ERROR_PAYWALL
        elif response.status_code == 403:
            # Forbidden - likely subscription/access issue
            return ERROR_PAYWALL
        elif response.status_code == 404:
            # Not found - paper doesn't exist in Elsevier database
            return ERROR_NO_PDF
        elif response.status_code == 429:
            # Rate limit exceeded - wait and could retry, but for now return error
            return ERROR_TIMEOUT
        else:
            # Other error
            return ERROR_PUBLISHER_ERROR
            
    except Exception as e:
        # Unexpected error
        return ERROR_UNKNOWN


def download_via_pmc_api(pmc_id: str, output_path: Path) -> Optional[str]:
    """
    Download PDF from PubMed Central using the PMC Open Access API.
    
    This function uses the direct PMC Open Access API to get PDF URLs and download them,
    avoiding browser overhead and library delays.
    
    Args:
        pmc_id: PMC ID (e.g., "12032536" or "PMC12032536")
        output_path: Path where PDF should be saved
    
    Returns:
        None on success, ERROR_* string on failure
    """
    try:
        # Check if file already exists
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None  # Already downloaded
        
        # Clean PMC ID (remove "PMC" prefix if present)
        clean_pmc_id = pmc_id.replace('PMC', '').replace('pmc', '').strip()
        if not clean_pmc_id:
            return ERROR_NO_IDENTIFIER
        
        # Construct API URL
        api_url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC{clean_pmc_id}"
        
        # Make API request
        try:
            response = requests.get(api_url, timeout=30)
        except requests.exceptions.Timeout:
            return ERROR_TIMEOUT
        except requests.exceptions.RequestException:
            return ERROR_PUBLISHER_ERROR
        
        # Check response status
        if response.status_code != 200:
            if response.status_code == 404:
                return ERROR_NOT_FOUND
            return ERROR_PUBLISHER_ERROR
        
        # Parse XML response
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            # If XML parsing fails, the response might be empty or malformed
            return ERROR_PUBLISHER_ERROR
        
        # Check for error in XML response (e.g., "idIsNotOpenAccess")
        error_elem = root.find('error')
        if error_elem is not None:
            error_code = error_elem.get('code', '')
            if 'notOpenAccess' in error_code or 'not open access' in error_elem.text.lower():
                # Paper is not in open access subset - need to use browser approach
                return ERROR_NO_PDF
        
        # Find PDF link in XML response
        # The XML structure is: <OA><records><record><link format="pdf" href="..."/>
        pdf_url = None
        for record in root.iter('record'):
            for link in record.iter('link'):
                if link.get('format') == 'pdf':
                    pdf_url = link.get('href')
                    break
            if pdf_url:
                break
        
        # Also try searching all links (fallback)
        if not pdf_url:
            for link in root.iter('link'):
                if link.get('format') == 'pdf':
                    pdf_url = link.get('href')
                    break
        
        if not pdf_url:
            # No PDF link found - article might not be in open access subset
            return ERROR_NO_PDF
        
        # Convert FTP URL to HTTP if needed (PMC sometimes returns FTP URLs)
        # FTP: ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/...
        # HTTP equivalent: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{id}/pdf/
        if pdf_url.startswith('ftp://'):
            # Try to extract PMC ID from FTP path or use the one we have
            # For now, try HTTP URL pattern as fallback
            http_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{clean_pmc_id}/pdf/"
            # Try HTTP first, fallback to FTP if needed
            try:
                pdf_response = requests.get(http_url, timeout=60, stream=True)
                if pdf_response.status_code == 200:
                    # Check if it's a PDF
                    content_type = pdf_response.headers.get('Content-Type', '').lower()
                    first_bytes = pdf_response.content[:4] if len(pdf_response.content) >= 4 else b''
                    if 'application/pdf' in content_type or first_bytes == b'%PDF':
                        pdf_url = http_url  # Use HTTP URL
                    else:
                        # HTTP didn't work, will try FTP below
                        pdf_response = None
            except:
                pass
        
        # Download PDF from the URL
        try:
            if pdf_url.startswith('ftp://'):
                # Handle FTP URLs using urllib (requests doesn't support FTP well)
                from urllib.request import urlopen
                from urllib.error import URLError
                try:
                    with urlopen(pdf_url, timeout=60) as ftp_file:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, 'wb') as f:
                            f.write(ftp_file.read())
                except (URLError, IOError, TimeoutError):
                    return ERROR_DOWNLOAD_FAILED
            else:
                # HTTP/HTTPS URL
                pdf_response = requests.get(pdf_url, timeout=60, stream=True)
                if pdf_response.status_code != 200:
                    return ERROR_DOWNLOAD_FAILED
                
                # Check if response is actually a PDF
                content_type = pdf_response.headers.get('Content-Type', '').lower()
                if 'application/pdf' not in content_type:
                    # Check first bytes for PDF magic number
                    # Peek at first chunk to check
                    first_chunk = next(pdf_response.iter_content(chunk_size=4), b'')
                    if first_chunk[:4] != b'%PDF':
                        return ERROR_DOWNLOAD_FAILED
                    # Reset stream by making new request
                    pdf_response = requests.get(pdf_url, timeout=60, stream=True)
                
                # Save PDF to file
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    for chunk in pdf_response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            # Verify file was saved and has content
            if output_path.exists() and output_path.stat().st_size > 1024:
                return None  # Success
            else:
                return ERROR_DOWNLOAD_FAILED
                
        except requests.exceptions.Timeout:
            return ERROR_TIMEOUT
        except requests.exceptions.RequestException:
            return ERROR_DOWNLOAD_FAILED
        except IOError:
            return ERROR_DOWNLOAD_FAILED
        except Exception as e:
            return ERROR_DOWNLOAD_FAILED
        
    except Exception as e:
        return ERROR_UNKNOWN


def download_via_doi_selenium(driver: webdriver.Chrome, doi: str, output_path: Path, use_library: bool = False) -> Optional[str]:
    """
    Attempt to download PDF via DOI using Selenium with improved strategies.
    
    Strategy 1: Search PubMed by DOI to get PMID, then use PubMed download (most reliable)
    Strategy 2: Try DOI resolver to publisher page with enhanced PDF detection
    
    Returns:
        PMID if found via PubMed search (so caller can use PubMed download method), 
        or error reason string if failed, None if attempted but outcome unknown
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
        
        # Strategy 2: Check for IOS Press DOI (10.3233/) and use direct handler
        if doi and doi.startswith('10.3233/'):
            print(f"    Detected IOS Press DOI, attempting direct download...")
            # Try direct PDF URL first
            direct_pdf_url = f"https://ebooks.iospress.nl/pdf/doi/{doi}"
            try:
                response = requests.get(direct_pdf_url, timeout=30, stream=True, allow_redirects=True)
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'pdf' in content_type:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        if output_path.exists() and output_path.stat().st_size > 1024:
                            return None  # Success
            except:
                pass
            
            # If direct URL failed, try browser navigation
            # Construct IOS Press article URL
            ios_urls = [
                f"https://content.iospress.com/articles/{doi.replace('/', '-')}",
                f"https://content.iospress.com/articles/{doi.replace('10.3233/', '')}",
                f"https://doi.org/{doi}",
            ]
            for ios_url in ios_urls:
                error_reason = download_from_ios_press_url(driver, ios_url, output_path, doi=doi)
                if error_reason is None:
                    return None  # Success
            # If all IOS Press attempts failed, continue to generic DOI resolver below
        
        # Strategy 3: Try DOI resolver to publisher page (if PubMed search didn't work and not IOS Press)
        if use_library:
            doi_url = f"https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/doi/{doi}"
        else:
            doi_url = f"https://dx.doi.org/{doi}"
        
        driver.get(doi_url)
        time.sleep(5)  # Reduced from 8s to 5s
        
        # Check if we landed on a publisher page with PDF
        current_url = driver.current_url.lower()
        page_source = driver.page_source.lower()
        
        # Check if we're on an IOS Press page (from DOI redirect)
        publisher_type = detect_publisher_type(current_url)
        if publisher_type == 'ios_press':
            print(f"    DOI redirect led to IOS Press page, attempting download...")
            error_reason = download_from_ios_press_url(driver, current_url, output_path, doi=doi)
            if error_reason is None:
                return None  # Success
            # Continue to generic handlers if IOS Press specific handler failed
        
        # Enhanced paywall detection
        if detect_paywall(driver):
            return ERROR_PAYWALL
        
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
                        time.sleep(3)  # Reduced from 4s to 3s
                        
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
                                time.sleep(3)  # Reduced from 4s to 3s
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
                                time.sleep(3)  # Reduced from 4s to 3s
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
                time.sleep(3)  # Reduced from 3s (keeping same)
                # Check if we got a PDF (content-type or file extension)
                if '.pdf' in driver.current_url.lower() or 'application/pdf' in driver.page_source.lower():
                    time.sleep(2)
                    return None
            except:
                continue
        
        # No PDF found after all attempts
        return ERROR_NO_PDF
        
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_via_pmc_selenium(driver: webdriver.Chrome, pmc_id: str, output_path: Path) -> Optional[str]:
    """Attempt to download PDF from PMC using Selenium. Returns error reason if failed."""
    try:
        # Check if file already exists (from previous download attempt)
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None
        
        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
        driver.get(url)
        time.sleep(4)  # Wait for page load
        
        # Check if we got a PDF or error page
        page_source = driver.page_source.lower()
        
        # If redirected to error page or access denied
        if 'access denied' in page_source or '403' in page_source or 'not available' in page_source:
            return ERROR_PAYWALL
        
        # Download attempted - success will be detected via Downloads tracking
        time.sleep(2)  # Give download time to start
        
        # Try to find and click download link if present
        try:
            download_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf') or contains(text(), 'Download') or contains(text(), 'PDF')]")
            for link in download_links[:3]:
                try:
                    link.click()
                    time.sleep(2)  # Give download time to start
                    return None
                except:
                    continue
        except:
            pass
        
        return None
        
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def _download_from_pubmed_url(driver: webdriver.Chrome, url: str, output_path: Path = None, doi: Optional[str] = None) -> Optional[str]:
    """
    Helper function to attempt download from a specific PubMed URL.
    Returns error reason if failed, None if attempted (success determined by Downloads tracking).
    
    Args:
        driver: Selenium WebDriver instance
        url: PubMed URL to load
        output_path: Optional path for direct PDF download (used for PMC API downloads)
        doi: Optional DOI for publisher-specific downloads (e.g., IOS Press)
    """
    try:
        driver.get(url)
        time.sleep(4)  # Give page time to load
        
        # Check for 404 first
        if detect_404_error(driver):
            return ERROR_NOT_FOUND
        
        # Handle cookie popup if present
        handle_cookie_popup(driver)
        time.sleep(1)
        
        # Look for "Free PMC article" link first (most reliable for open access papers)
        # Use PMC API for direct, reliable download
        try:
            pmc_links = driver.find_elements(By.XPATH, 
                "//a[contains(text(), 'Free PMC article')] | "
                "//a[contains(text(), 'PMC article')] | "
                "//a[contains(@href, '/pmc/') and contains(@href, 'articles')]")
            
            for pmc_link in pmc_links[:3]:
                try:
                    pmc_href = pmc_link.get_attribute('href')
                    if pmc_href and '/pmc/articles/' in pmc_href:
                        # Extract PMC ID
                        pmc_match = re.search(r'/pmc/articles/(PMC\d+)', pmc_href)
                        if pmc_match:
                            pmc_id = pmc_match.group(1)  # Keep "PMC" prefix
                            
                            # If output_path is provided, use API for direct download
                            if output_path:
                                api_result = download_via_pmc_api(pmc_id, output_path)
                                if api_result is None:  # Success
                                    return None
                                # If API says "not open access" (ERROR_NO_PDF), try direct HTTP download
                                # because some papers show "Free PMC article" but aren't in API subset
                                # Direct HTTP download from PDF URL should work
                                if api_result == ERROR_NO_PDF:
                                    # API says not in open access subset, but try direct HTTP download
                                    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
                                    try:
                                        pdf_response = requests.get(pdf_url, timeout=60, stream=True, allow_redirects=True)
                                        if pdf_response.status_code == 200:
                                            # Check if it's actually a PDF
                                            content_type = pdf_response.headers.get('Content-Type', '').lower()
                                            first_bytes = pdf_response.content[:4] if len(pdf_response.content) >= 4 else b''
                                            if 'application/pdf' in content_type or first_bytes == b'%PDF':
                                                # Save PDF directly
                                                output_path.parent.mkdir(parents=True, exist_ok=True)
                                                with open(output_path, 'wb') as f:
                                                    for chunk in pdf_response.iter_content(chunk_size=8192):
                                                        if chunk:
                                                            f.write(chunk)
                                                # Verify file was saved
                                                if output_path.exists() and output_path.stat().st_size > 1024:
                                                    return None  # Success
                                    except:
                                        pass  # Fall through to browser approach if HTTP fails
                                elif api_result in [ERROR_NOT_FOUND, ERROR_NO_IDENTIFIER]:
                                    # API clearly says not available, don't waste time with browser
                                    return api_result
                                # For other errors (timeout, download failed), try browser fallback
                            
                            # Fallback to browser-based download if API and HTTP both failed
                            # Navigate to PMC article page and click "Download PDF" button
                            # This provides the correct PDF URL with filename
                            article_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
                            driver.get(article_url)
                            time.sleep(4)  # Give page time to load
                            
                            # Check for 404
                            if detect_404_error(driver):
                                return ERROR_NOT_FOUND
                            
                            # Handle cookie popup if present
                            handle_cookie_popup(driver)
                            time.sleep(1)
                            
                            # Look for "Download PDF" button on the article page
                            # This button provides the correct PDF URL with filename
                            download_pdf_selectors = [
                                "//button[contains(text(), 'Download PDF')]",
                                "//a[contains(text(), 'Download PDF')]",
                                "//button[contains(@aria-label, 'Download PDF')]",
                                "//a[contains(@aria-label, 'Download PDF')]",
                                "//*[contains(@class, 'download-pdf')]//button",
                                "//*[contains(@class, 'download-pdf')]//a",
                            ]
                            
                            pdf_downloaded = False
                            for selector in download_pdf_selectors:
                                try:
                                    buttons = driver.find_elements(By.XPATH, selector)
                                    for button in buttons[:3]:
                                        try:
                                            # Scroll into view
                                            driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                            time.sleep(0.5)
                                            # Click the button
                                            button.click()
                                            time.sleep(5)  # Wait for navigation to PDF
                                            
                                            # Check if we navigated to a PDF URL
                                            current_url = driver.current_url.lower()
                                            if '/pdf/' in current_url and '.pdf' in current_url:
                                                # Successfully navigated to PDF - Chrome should download it
                                                time.sleep(3)  # Give download time to start
                                                pdf_downloaded = True
                                                break
                                        except:
                                            continue
                                    if pdf_downloaded:
                                        break
                                except:
                                    continue
                            
                            if pdf_downloaded:
                                return None  # Download started, will be verified by Downloads tracking
                            
                            # If button click didn't work, try finding PDF link directly
                            pdf_links = driver.find_elements(By.XPATH,
                                "//a[contains(@href, '/pdf/') and contains(@href, '.pdf')]")
                            
                            for link in pdf_links[:3]:
                                try:
                                    href = link.get_attribute('href')
                                    if href and '/pdf/' in href and '.pdf' in href:
                                        driver.get(href)
                                        time.sleep(5)
                                        if not detect_404_error(driver):
                                            time.sleep(3)
                                            return None
                                except:
                                    continue
                            
                            # If nothing worked, return error
                            return ERROR_NO_PDF
                except:
                    continue
        except:
            pass
        
        # Try to follow publisher links - detect publisher and use appropriate handler
        # Look for publisher links on current PubMed page (don't reload since we're already here)
        try:
            # Try to find "Full text links" or publisher links on current page
            fulltext_links = driver.find_elements(By.XPATH,
                "//a[contains(text(), 'Full text')] | "
                "//a[contains(text(), 'Publisher')] | "
                "//a[contains(@href, 'http') and not(contains(@href, 'pubmed')) and not(contains(@href, 'ncbi'))]")
            
            if fulltext_links:
                # Get the first external link (likely publisher site)
                for link in fulltext_links:
                    href = link.get_attribute('href')
                    if href and 'pubmed' not in href.lower() and 'ncbi' not in href.lower():
                        final_url = href
                        publisher = detect_publisher_type(final_url)
                        print(f"    Found publisher link: {publisher} - {final_url[:80]}...")
                        
                        # Handle IOS Press specifically
                        if publisher == 'ios_press':
                            print(f"    Detected IOS Press publisher, attempting download...")
                            error_reason = download_from_ios_press_url(driver, final_url, output_path, doi=doi)
                            if error_reason is None:
                                return None  # Success
                            # If IOS Press download failed, continue to generic fallback below
                        
                        # Handle OUP specifically
                        elif publisher == 'oup':
                            print(f"    Detected OUP publisher, attempting download...")
                            # Can add OUP-specific handler here if needed
                            pass
        except Exception as e:
            print(f"    Error finding publisher link: {e}")
        
        # Look for other full-text links - expanded selectors for PubMed pages
        fulltext_selectors = [
            # Full text links section
            "//a[contains(text(), 'Full text')]",
            "//a[contains(text(), 'Full text links')]",
            # Direct PDF links
            "//a[contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download')]",
            "//a[contains(@href, 'fulltext')]",
            "//a[contains(@href, '.pdf')]",
            # Publisher links
            "//a[contains(@href, 'publisher')]",
            "//a[contains(@href, 'atypon')]",
        ]
        
        for selector in fulltext_selectors:
            try:
                links = driver.find_elements(By.XPATH, selector)
                for link in links[:5]:
                    try:
                        href = link.get_attribute('href')
                        if href and ('.pdf' in href.lower() or 'fulltext' in href.lower() or 'publisher' in href.lower()):
                            # Detect publisher from link
                            link_publisher = detect_publisher_type(href)
                            
                            # If IOS Press link, use specific handler
                            if link_publisher == 'ios_press':
                                print(f"    Found IOS Press link, attempting download...")
                                error_reason = download_from_ios_press_url(driver, href, output_path, doi=doi)
                                if error_reason is None:
                                    return None  # Success
                                continue  # Try other links if this failed
                            
                            # For other publishers, try generic approach
                            # Open in new tab
                            driver.execute_script("window.open(arguments[0], '_blank');", href)
                            driver.switch_to.window(driver.window_handles[-1])
                            time.sleep(4)
                            
                            # Check for paywall
                            if detect_paywall(driver):
                                driver.close()
                                driver.switch_to.window(driver.window_handles[0])
                                return ERROR_PAYWALL
                            
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
                                        return None
                                except:
                                    continue
                            
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                    except:
                        continue
            except:
                continue
        
        return ERROR_NO_PDF
        
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_via_pubmed_selenium(driver: webdriver.Chrome, pmid: str, output_path: Path, use_library: bool = False, doi: Optional[str] = None) -> Optional[str]:
    """
    Attempt to download PDF via PubMed page using Selenium with fallback logic.
    Tries with proxy URL first if use_library is True, then falls back to direct URL if that fails.
    Returns error reason if failed, None if attempted (success determined by Downloads tracking).
    
    Args:
        driver: Selenium WebDriver instance
        pmid: PubMed ID
        output_path: Path where PDF should be saved
        use_library: Whether to use library proxy
        doi: Optional DOI for publisher-specific downloads (e.g., IOS Press)
    """
    try:
        # Check if file already exists (from previous download attempt)
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None
        
        # Try with proxy URL first if library access is enabled
        if use_library:
            proxy_url = f"https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/pubmed/{pmid}/"
            error_reason = _download_from_pubmed_url(driver, proxy_url, output_path, doi=doi)
            
            # If proxy attempt failed with retryable errors, try direct URL
            if error_reason in [ERROR_NOT_FOUND, ERROR_PAYWALL, ERROR_TIMEOUT]:
                direct_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                error_reason = _download_from_pubmed_url(driver, direct_url, output_path, doi=doi)
            
            return error_reason
        else:
            # No library access, use direct URL
            direct_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            return _download_from_pubmed_url(driver, direct_url, output_path, doi=doi)
        
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def follow_pubmed_url(driver: webdriver.Chrome, pubmed_url: str) -> tuple[str, str]:
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
                "//a[contains(@href, 'http') and not(contains(@href, 'pubmed')) and not(contains(@href, 'ncbi'))]")
            
            if fulltext_links:
                # Get the first external link (likely publisher site)
                for link in fulltext_links:
                    href = link.get_attribute('href')
                    if href and 'pubmed' not in href.lower() and 'ncbi' not in href.lower():
                        final_url = href
                        publisher = detect_publisher_type(final_url)
                        print(f"    Found publisher link: {publisher} - {final_url[:80]}...")
                        return (final_url, publisher)
        except Exception as e:
            print(f"    Warning: Could not find full text links: {e}")
        
        # If no external links found, check current URL after redirects
        current_url = driver.current_url
        publisher = detect_publisher_type(current_url)
        print(f"    Final URL after redirects: {publisher} - {current_url[:80]}...")
        return (current_url, publisher)
        
    except Exception as e:
        print(f"    Error following PubMed URL: {e}")
        return (pubmed_url, 'unknown')


def download_from_ios_press_url(driver: webdriver.Chrome, url: str, output_path: Path, doi: Optional[str] = None) -> Optional[str]:
    """Download PDF from IOS Press website.
    First tries direct PDF URL pattern if DOI is available, then falls back to browser navigation.
    
    Returns:
        Error reason string if failed, None if attempted (success determined by Downloads tracking)
    """
    # Strategy 1: Try direct PDF URL if DOI is available
    if doi:
        direct_pdf_url = f"https://ebooks.iospress.nl/pdf/doi/{doi}"
        print(f"    Trying IOS Press direct PDF URL...")
        try:
            response = requests.get(direct_pdf_url, timeout=30, stream=True, allow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' in content_type:
                    # Save PDF to file
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Verify file was downloaded and has content
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        print(f"    ✓ Downloaded via direct PDF URL")
                        return None  # Success
        except Exception as e:
            print(f"    Direct PDF URL attempt failed: {e}")
    
    # Strategy 2: Try browser navigation (even if this often fails, at least we try to navigate)
    try:
        print(f"    Attempting IOS Press download via browser...")
        driver.get(url)
        
        # Wait for page to be ready
        wait = WebDriverWait(driver, 15)
        wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)  # Additional wait for dynamic content
        
        print(f"    DEBUG: Current URL: {driver.current_url}")
        
        # Handle cookie popups
        handle_cookie_popup(driver)
        time.sleep(1)
        
        # Try to find PDF download buttons/links
        pdf_selectors = [
            "//a[contains(text(), 'PDF')]",
            "//a[contains(text(), 'Download PDF')]",
            "//button[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download PDF')]",
            "//a[contains(@href, '.pdf')]",
            "//a[contains(@href, '/pdf/')]",
            "//a[contains(@class, 'pdf')]",
            "//button[contains(@class, 'pdf')]",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:5]:
                    try:
                        if element.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            time.sleep(0.5)
                            element.click()
                            time.sleep(3)
                            # Check if we navigated to a PDF
                            if '.pdf' in driver.current_url.lower():
                                time.sleep(3)
                                return None  # Success - download attempted
                    except:
                        continue
            except:
                continue
        
        # Try extracting PDF URL from page source
        try:
            pdf_url_match = re.search(r'https?://[^\s"\'<>]+\.pdf', driver.page_source, re.IGNORECASE)
            if pdf_url_match:
                pdf_url = pdf_url_match.group(0)
                driver.get(pdf_url)
                time.sleep(3)
                if '.pdf' in driver.current_url.lower():
                    return None  # Success
        except:
            pass
        
        return ERROR_NO_PDF
        
    except Exception as e:
        print(f"    Error downloading from IOS Press: {e}")
        return ERROR_PUBLISHER_ERROR


def detect_publisher_type(url: str) -> str:
    """Detect publisher type from URL."""
    url_lower = url.lower()
    # Distinguish between PubMed (PMID) and PMC (PMC ID) URLs
    if 'pmc.ncbi.nlm.nih.gov' in url_lower or '/pmc/' in url_lower or '/articles/' in url_lower:
        return 'pmc'
    elif '/pubmed/' in url_lower or 'pubmed.ncbi.nlm.nih.gov' in url_lower:
        return 'pubmed'
    elif 'iospress.com' in url_lower or 'iospress.nl' in url_lower or 'content.iospress.com' in url_lower:
        return 'ios_press'
    elif 'academic.oup.com' in url_lower or 'oup.com' in url_lower:
        return 'oup'
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


def download_from_pmc_url(driver: webdriver.Chrome, url: str, output_path: Path = None) -> Optional[str]:
    """
    Download PDF from PMC URL. Returns error reason if failed.
    Uses PMC API for direct download if output_path is provided, otherwise uses browser.
    """
    try:
        # Extract PMC ID from URL
        pmc_id = None
        if '/articles/' in url:
            pmc_id_match = re.search(r'/articles/(PMC\d+)', url)
            if pmc_id_match:
                pmc_id = pmc_id_match.group(1)  # Keep "PMC" prefix
        elif '/pdf/' in url:
            # Extract from PDF URL
            pmc_id_match = re.search(r'/articles/(PMC\d+)', url)
            if pmc_id_match:
                pmc_id = pmc_id_match.group(1)
        
        # If we have PMC ID and output_path, try API first
        if pmc_id and output_path:
            api_result = download_via_pmc_api(pmc_id, output_path)
            if api_result is None:  # Success
                return None
            # If API failed, fall through to browser-based approach
        
        # Browser-based approach: navigate to article page and click "Download PDF" button
        # This provides the correct PDF URL with filename
        if '/articles/' in url and not '/pdf/' in url:
            # Already an article URL - navigate to it
            driver.get(url)
            time.sleep(4)
            
            # Check for 404
            if detect_404_error(driver):
                return ERROR_NOT_FOUND
            
            # Handle cookie popup if present
            handle_cookie_popup(driver)
            time.sleep(1)
            
            # Look for "Download PDF" button on the article page
            download_pdf_selectors = [
                "//button[contains(text(), 'Download PDF')]",
                "//a[contains(text(), 'Download PDF')]",
                "//button[contains(@aria-label, 'Download PDF')]",
                "//a[contains(@aria-label, 'Download PDF')]",
                "//*[contains(@class, 'download-pdf')]//button",
                "//*[contains(@class, 'download-pdf')]//a",
            ]
            
            for selector in download_pdf_selectors:
                try:
                    buttons = driver.find_elements(By.XPATH, selector)
                    for button in buttons[:3]:
                        try:
                            # Scroll into view
                            driver.execute_script("arguments[0].scrollIntoView(true);", button)
                            time.sleep(0.5)
                            # Click the button
                            button.click()
                            time.sleep(5)  # Wait for navigation to PDF
                            
                            # Check if we navigated to a PDF URL
                            current_url = driver.current_url.lower()
                            if '/pdf/' in current_url:
                                # Successfully navigated to PDF - Chrome should download it
                                time.sleep(3)  # Give download time to start
                                return None
                        except:
                            continue
                except:
                    continue
            
            # If button click didn't work, try finding PDF link directly
            pdf_links = driver.find_elements(By.XPATH,
                "//a[contains(@href, '/pdf/') and contains(@href, '.pdf')]")
            
            for link in pdf_links[:3]:
                try:
                    href = link.get_attribute('href')
                    if href and '/pdf/' in href and '.pdf' in href:
                        driver.get(href)
                        time.sleep(5)
                        if not detect_404_error(driver):
                            time.sleep(3)
                            return None
                except:
                    continue
            
            return ERROR_NO_PDF
        
        # If already a PDF URL, just navigate (should download with our preferences)
        if '/pdf/' in url:
            driver.get(url)
            time.sleep(4)
            if detect_404_error(driver):
                return ERROR_NOT_FOUND
            time.sleep(3)  # Give download time to start
            return None
        
        return ERROR_NO_PDF
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_from_ieee_url(driver: webdriver.Chrome, url: str) -> Optional[str]:
    """Download PDF from IEEE Xplore. Returns error reason if failed."""
    try:
        driver.get(url)
        time.sleep(4)  # Reduced from 6s to 4s
        
        # Check for 404 immediately after page load
        if detect_404_error(driver):
            return ERROR_NOT_FOUND
        
        # Handle cookie popup first (before checking for paywall)
        handle_cookie_popup(driver)
        time.sleep(0.5)
        
        # Handle ad popup (after cookie popup)
        handle_ad_popup(driver, timeout=5)
        time.sleep(0.5)  # Brief wait after ad popup dismissal
        
        # Check for paywall
        if detect_paywall(driver):
            return ERROR_PAYWALL
        
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
                        time.sleep(3)  # Reduced from 4s to 3s
                        return None
                    except:
                        href = element.get_attribute('href')
                        if href and '.pdf' in href.lower():
                            driver.get(href)
                            time.sleep(3)  # Reduced from 4s to 3s
                            return None
            except:
                continue
        
        return ERROR_NO_PDF
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_from_sciencedirect_url(driver: webdriver.Chrome, url: str) -> Optional[str]:
    """Download PDF from ScienceDirect. Returns error reason if failed."""
    try:
        driver.get(url)
        time.sleep(4)  # Reduced from 6s to 4s
        
        # Check for 404 immediately after page load
        if detect_404_error(driver):
            return ERROR_NOT_FOUND
        
        # Handle cookie popup first (before checking for paywall)
        cookie_handled = handle_cookie_popup(driver)
        if cookie_handled:
            time.sleep(1)  # Additional wait after cookie popup dismissal
        
        # Handle ad popup (after cookie popup)
        handle_ad_popup(driver, timeout=5)
        time.sleep(0.5)  # Brief wait after ad popup dismissal
        
        # Wait for dynamic content to load
        try:
            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except:
            pass
        
        # Check for paywall
        if detect_paywall(driver):
            return ERROR_PAYWALL
        
        # Strategy 1: Search HTML source code directly
        html_findings = find_pdf_links_in_html(driver, url)
        for finding in html_findings:
            try:
                if finding['type'] == 'url':
                    # Try navigating directly to PDF URL
                    driver.get(finding['value'])
                    time.sleep(3)
                    return None
                elif finding['type'] == 'id':
                    # Try finding element by ID
                    element = driver.find_element(By.ID, finding['value'])
                    if element.is_displayed() and element.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(0.5)
                        element_text = element.text.lower() if hasattr(element, 'text') else ''
                        is_view_pdf = 'view pdf' in element_text
                        element.click()
                        time.sleep(2)
                        if is_view_pdf:
                            wait_for_captcha_completion(driver, timeout=120)
                            time.sleep(3)
                            if len(driver.window_handles) > 1:
                                driver.switch_to.window(driver.window_handles[-1])
                                time.sleep(2)
                        return None
                elif finding['type'] == 'class':
                    # Try finding element by class
                    elements = driver.find_elements(By.CLASS_NAME, finding['value'])
                    for element in elements[:3]:
                        if element.is_displayed() and element.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            time.sleep(0.5)
                            element_text = element.text.lower() if hasattr(element, 'text') else ''
                            is_view_pdf = 'view pdf' in element_text
                            element.click()
                            time.sleep(2)
                            if is_view_pdf:
                                wait_for_captcha_completion(driver, timeout=120)
                                time.sleep(3)
                                if len(driver.window_handles) > 1:
                                    driver.switch_to.window(driver.window_handles[-1])
                                    time.sleep(2)
                            return None
            except:
                continue
        
        # Strategy 2: Check iframes
        iframe_result = check_iframes_for_pdf(driver)
        if iframe_result is None:  # Success
            return None
        
        # Strategy 3: Use existing XPath selectors (fallback)
        # ScienceDirect-specific selectors (based on actual HTML structure) - try these first
        sciencedirect_selectors = [
            # Aria-label selector (most specific)
            "//a[@aria-label='View PDF. Opens in a new window.']",
            "//a[contains(@aria-label, 'View PDF')]",
            # Class-based selectors (exact match)
            "//a[contains(@class, 'accessbar-utility-link') and contains(@class, 'link-button')]",
            "//a[contains(@class, 'link-button-primary')]",
            "//a[contains(@class, 'accessbar-utility-component')]",
            # Href pattern matching
            "//a[contains(@href, '/pdfft')]",
            "//a[contains(@href, '/science/article/pii/') and contains(@href, '/pdfft')]",
            # Text content in nested spans
            "//a[.//span[contains(text(), 'View PDF')]]",
            "//a[.//span[contains(text(), 'View')] and .//strong[contains(text(), 'PDF')]]",
        ]
        
        for selector in sciencedirect_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:3]:
                    try:
                        if not element.is_displayed() or not element.is_enabled():
                            continue
                        
                        # Get href - might be relative URL
                        href = element.get_attribute('href')
                        if href:
                            # Convert relative URL to absolute
                            if href.startswith('/'):
                                # Extract base URL from current URL
                                base_url_parts = url.split('/')
                                base_url = f"{base_url_parts[0]}//{base_url_parts[2]}"
                                href = base_url + href
                            elif not href.startswith('http'):
                                # Relative URL without leading slash
                                base_url_parts = url.rsplit('/', 1)[0]
                                href = base_url_parts + '/' + href
                            
                            # Check if this is a PDF link
                            if '/pdfft' in href or '.pdf' in href.lower():
                                # Navigate directly to PDF URL
                                driver.get(href)
                                time.sleep(3)
                                # Handle captcha if needed
                                captcha_completed = wait_for_captcha_completion(driver, timeout=180)
                                
                                if captcha_completed:
                                    # Wait for PDF to load
                                    for _ in range(10):  # Wait up to 10 seconds for PDF
                                        try:
                                            current_url = driver.current_url.lower()
                                            page_source = driver.page_source.lower()
                                            
                                            if '.pdf' in current_url or 'application/pdf' in page_source:
                                                time.sleep(2)
                                                return None
                                            
                                            if 'pdf' in driver.title.lower():
                                                time.sleep(2)
                                                return None
                                        except:
                                            pass
                                        
                                        time.sleep(1)
                                    
                                    time.sleep(5)  # Additional wait for PDF
                                
                                return None
                        
                        # If href navigation didn't work, try clicking
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(0.5)
                        element.click()
                        time.sleep(2)
                        
                        # Handle new window (target="_blank")
                        if len(driver.window_handles) > 1:
                            driver.switch_to.window(driver.window_handles[-1])
                            time.sleep(2)
                        
                        # Handle captcha
                        captcha_completed = wait_for_captcha_completion(driver, timeout=120)
                        
                        if captcha_completed:
                            # After captcha, wait for PDF to load
                            # Check if we're on a PDF page or if PDF is downloading
                            for _ in range(10):  # Wait up to 10 seconds for PDF
                                try:
                                    current_url = driver.current_url.lower()
                                    page_source = driver.page_source.lower()
                                    
                                    # Check if we're viewing a PDF
                                    if '.pdf' in current_url or 'application/pdf' in page_source:
                                        time.sleep(2)  # Give PDF time to fully load
                                        return None
                                    
                                    # Check if page title indicates PDF
                                    if 'pdf' in driver.title.lower():
                                        time.sleep(2)
                                        return None
                                except:
                                    pass
                                
                                time.sleep(1)
                            
                            # If we get here, PDF might still be loading or downloading
                            # Give it more time
                            time.sleep(5)
                        
                        return None
                    except Exception as e:
                        continue
            except:
                continue
        
        # Try to find PDF download link - prioritize "View PDF" button
        # Expanded selectors for ScienceDirect (generic fallback)
        pdf_selectors = [
            # View PDF - case insensitive and various formats
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view pdf')]",
            "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view pdf')]",
            "//button[contains(text(), 'View PDF')]",
            "//button[contains(text(), 'view pdf')]",
            "//a[contains(text(), 'View PDF')]",
            "//a[contains(text(), 'view pdf')]",
            # Buttons with aria-label
            "//button[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'view pdf')]",
            "//button[@aria-label='View PDF']",
            # Class-based selectors
            "//*[contains(@class, 'view-pdf')]",
            "//*[contains(@class, 'viewPdf')]",
            "//*[contains(@class, 'view_pdf')]",
            "//button[contains(@class, 'pdf')]",
            "//a[contains(@class, 'pdf')]",
            # Data attributes
            "//button[contains(@data-testid, 'pdf')]",
            "//a[contains(@data-testid, 'pdf')]",
            "//button[contains(@data-action, 'pdf')]",
            # ID-based
            "//*[@id='pdfLink']",
            "//*[@id='viewPdf']",
            "//*[@id='view-pdf']",
            # Generic PDF links
            "//a[contains(@href, '.pdf')]",
            "//a[contains(text(), 'Download PDF')]",
            "//a[contains(text(), 'PDF')]",
            "//button[contains(text(), 'Download PDF')]",
            "//a[contains(@class, 'pdf-download')]",
            # Fallback: any button/link containing "pdf" in text (case insensitive)
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
            "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pdf')]",
        ]
        
        for selector in pdf_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements[:5]:  # Check more elements
                    try:
                        # Get element text for checking
                        element_text = ''
                        try:
                            element_text = element.text.lower()
                        except:
                            try:
                                element_text = element.get_attribute('textContent').lower() if element.get_attribute('textContent') else ''
                            except:
                                pass
                        
                        # Check if element is visible and enabled
                        if not element.is_displayed():
                            continue
                        if not element.is_enabled():
                            continue
                        
                        # Check if this looks like a View PDF button
                        is_view_pdf = ('view pdf' in element_text or 
                                      'viewpdf' in element_text.replace(' ', '') or
                                      'view-pdf' in element_text.replace(' ', '-'))
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                        time.sleep(0.5)
                        
                        element.click()
                        time.sleep(2)  # Wait for page to load after click
                        
                        # If we clicked "View PDF", wait for captcha completion
                        if is_view_pdf:
                            wait_for_captcha_completion(driver, timeout=120)
                            time.sleep(3)  # Wait after captcha completion
                            
                            # After captcha, check if PDF opened in new tab or same tab
                            # If new tab opened, switch to it
                            if len(driver.window_handles) > 1:
                                driver.switch_to.window(driver.window_handles[-1])
                                time.sleep(2)
                        
                        return None
                    except Exception as e:
                        # Try getting href if it's a link
                        try:
                            href = element.get_attribute('href')
                            if href and ('.pdf' in href.lower() or 'pdf' in href.lower()):
                                driver.get(href)
                                time.sleep(3)
                                return None
                        except Exception:
                            continue
            except:
                continue
        
        # Fallback: Search all buttons and links for PDF-related text
        try:
            all_buttons = driver.find_elements(By.TAG_NAME, "button")
            all_links = driver.find_elements(By.TAG_NAME, "a")
            all_elements = all_buttons + all_links
            
            for element in all_elements[:20]:  # Check first 20 elements
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    
                    # Check text content
                    text = ''
                    try:
                        text = element.text.lower()
                    except:
                        try:
                            text = element.get_attribute('textContent').lower() if element.get_attribute('textContent') else ''
                        except:
                            pass
                    
                    # Check aria-label
                    aria_label = element.get_attribute('aria-label') or ''
                    aria_label = aria_label.lower()
                    
                    # Check class
                    class_attr = element.get_attribute('class') or ''
                    class_attr = class_attr.lower()
                    
                    # Check if any contain "pdf" or "view"
                    if ('pdf' in text or 'pdf' in aria_label or 'pdf' in class_attr or 
                        ('view' in text and 'pdf' in text) or ('view' in aria_label and 'pdf' in aria_label)):
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            time.sleep(0.5)
                            
                            is_view_pdf = ('view pdf' in text or 'view pdf' in aria_label)
                            
                            element.click()
                            time.sleep(2)
                            
                            if is_view_pdf:
                                wait_for_captcha_completion(driver, timeout=120)
                                time.sleep(3)
                                
                                if len(driver.window_handles) > 1:
                                    driver.switch_to.window(driver.window_handles[-1])
                                    time.sleep(2)
                            
                            return None
                        except:
                            continue
                except:
                    continue
        except:
            pass
        
        # Try constructing PDF URL pattern
        if '/article/pii/' in url:
            pdf_url = url.replace('/article/pii/', '/article/pii/') + '/pdfft'
            try:
                driver.get(pdf_url)
                time.sleep(4)
                return None
            except:
                pass
        
        return ERROR_NO_PDF
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_from_springer_url(driver: webdriver.Chrome, url: str) -> Optional[str]:
    """Download PDF from Springer. Returns error reason if failed."""
    try:
        driver.get(url)
        time.sleep(4)  # Reduced from 6s to 4s
        
        # Check for 404 immediately after page load
        if detect_404_error(driver):
            return ERROR_NOT_FOUND
        
        # Handle cookie popup first (before checking for paywall)
        handle_cookie_popup(driver)
        time.sleep(0.5)
        
        # Handle ad popup (after cookie popup)
        handle_ad_popup(driver, timeout=5)
        time.sleep(0.5)  # Brief wait after ad popup dismissal
        
        # Check for paywall
        if detect_paywall(driver):
            return ERROR_PAYWALL
        
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
                        time.sleep(3)  # Reduced from 4s to 3s
                        return None
                    except:
                        href = element.get_attribute('href')
                        if href:
                            driver.get(href)
                            time.sleep(3)  # Reduced from 4s to 3s
                            return None
            except:
                continue
        
        return ERROR_NO_PDF
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_from_wiley_url(driver: webdriver.Chrome, url: str) -> Optional[str]:
    """Download PDF from Wiley Online Library. Returns error reason if failed."""
    try:
        driver.get(url)
        time.sleep(4)  # Reduced from 6s to 4s
        
        # Check for 404 immediately after page load
        if detect_404_error(driver):
            return ERROR_NOT_FOUND
        
        # Handle cookie popup first (before checking for paywall)
        handle_cookie_popup(driver)
        time.sleep(0.5)
        
        # Handle ad popup (after cookie popup)
        handle_ad_popup(driver, timeout=5)
        time.sleep(0.5)  # Brief wait after ad popup dismissal
        
        # Check for paywall
        if detect_paywall(driver):
            return ERROR_PAYWALL
        
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
                        time.sleep(3)  # Reduced from 4s to 3s
                        return None
                    except:
                        href = element.get_attribute('href')
                        if href:
                            driver.get(href)
                            time.sleep(3)  # Reduced from 4s to 3s
                            return None
            except:
                continue
        
        return ERROR_NO_PDF
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_from_generic_url(driver: webdriver.Chrome, url: str) -> Optional[str]:
    """Download PDF from generic publisher using common patterns. Returns error reason if failed."""
    try:
        driver.get(url)
        time.sleep(4)  # Reduced from 6s to 4s
        
        # Check for 404 immediately after page load
        if detect_404_error(driver):
            return ERROR_NOT_FOUND
        
        # Handle cookie popup first (before checking for paywall)
        handle_cookie_popup(driver)
        time.sleep(1)  # Additional wait after cookie popup dismissal
        
        # Handle ad popup (after cookie popup)
        handle_ad_popup(driver, timeout=5)
        time.sleep(0.5)  # Brief wait after ad popup dismissal
        
        # Enhanced paywall detection
        if detect_paywall(driver):
            return ERROR_PAYWALL
        
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
                        time.sleep(3)  # Reduced from 4s to 3s
                        return None
                    except:
                        href = element.get_attribute('href')
                        if href and ('.pdf' in href.lower() or 'download' in href.lower()):
                            driver.get(href)
                            time.sleep(3)  # Reduced from 4s to 3s
                            return None
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
                    return None
            except:
                continue
        
        return ERROR_NO_PDF
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def download_via_url_selenium(driver: webdriver.Chrome, url: str, output_path: Path, use_library: bool = False, doi: str = None) -> Optional[str]:
    """
    Attempt to download PDF via direct URL from RIS file.
    Uses publisher-specific handlers for better success rates.
    If URL results in 404, tries URL transformations and optionally falls back to DOI resolution.
    
    Args:
        driver: Selenium WebDriver instance
        url: URL from RIS file
        output_path: Path where PDF should be saved
        use_library: Whether to use library proxy
        doi: Optional DOI for fallback if URL fails
    
    Returns:
        Error reason string if failed, None if attempted (success determined by Downloads tracking)
        Returns ERROR_NOT_FOUND if 404 detected and all alternatives failed (signals DOI fallback should be tried)
    """
    try:
        # Check if file already exists
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None
        
        original_url = url
        
        # Detect publisher type early to handle special cases
        publisher_type = detect_publisher_type(url)
        
        # For PubMed URLs, skip early 404 check and go straight to handler
        # (PubMed pages have dynamic content that might trigger false 404s)
        # The download_via_pubmed_selenium() function handles proxy with fallback logic
        if publisher_type == 'pubmed':
            # Extract PMID and use PubMed handler directly
            pmid_match = re.search(r'/pubmed/(\d+)', url)
            if pmid_match:
                pmid = pmid_match.group(1)
                # Call PubMed handler which will try proxy first, then fallback to direct URL if needed
                return download_via_pubmed_selenium(driver, pmid, output_path, use_library, doi=doi)
        
        # Apply library proxy if needed
        if use_library and 'proxy-hs.researchport.umd.edu' not in url:
            # Try to add proxy prefix for certain domains
            if 'ncbi.nlm.nih.gov' in url:
                url = url.replace('https://', 'https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/')
            elif 'pubmed' in url:
                url = url.replace('https://', 'https://www-hshsl-umaryland-edu.proxy-hs.researchport.umd.edu/')
        
        # First, try to load the URL and check for 404 immediately
        try:
            driver.get(url)
            time.sleep(3)  # Give page time to load
            
            # Check for 404 immediately after page load
            if detect_404_error(driver):
                # URL is 404 - try transformations before giving up
                current_url = driver.current_url
                transformed_urls = transform_url_to_pdf_url(original_url, current_url)
                
                if transformed_urls:
                    # Try each transformed URL
                    for transformed_url in transformed_urls[:3]:  # Limit to first 3 transformations
                        try:
                            driver.get(transformed_url)
                            time.sleep(3)
                            
                            # Check if still 404
                            if detect_404_error(driver):
                                continue
                            
                            # Not a 404 - try to find PDF using appropriate handler
                            publisher_type = detect_publisher_type(transformed_url)
                            if publisher_type == 'pmc':
                                error_reason = download_from_pmc_url(driver, transformed_url, output_path)
                            elif publisher_type == 'ieee':
                                error_reason = download_from_ieee_url(driver, transformed_url)
                            elif publisher_type == 'sciencedirect':
                                error_reason = download_from_sciencedirect_url(driver, transformed_url)
                            elif publisher_type == 'springer':
                                error_reason = download_from_springer_url(driver, transformed_url)
                            elif publisher_type == 'wiley':
                                error_reason = download_from_wiley_url(driver, transformed_url)
                            else:
                                error_reason = download_from_generic_url(driver, transformed_url)
                            
                            # If transformation worked (no error or different error), return
                            if error_reason != ERROR_NOT_FOUND and not detect_404_error(driver):
                                time.sleep(2)
                                return error_reason
                        except:
                            continue
                
                # All transformations failed or no transformations available - return NOT_FOUND to signal DOI fallback
                return ERROR_NOT_FOUND
        except:
            pass  # If initial load fails, continue to normal handler
        
        # If no 404 detected, proceed with normal publisher handler
        # Publisher type already detected above, use appropriate handler
        error_reason = None
        if publisher_type == 'pmc':
            error_reason = download_from_pmc_url(driver, url, output_path)
        elif publisher_type == 'ieee':
            error_reason = download_from_ieee_url(driver, url)
        elif publisher_type == 'sciencedirect':
            error_reason = download_from_sciencedirect_url(driver, url)
        elif publisher_type == 'springer':
            error_reason = download_from_springer_url(driver, url)
        elif publisher_type == 'wiley':
            error_reason = download_from_wiley_url(driver, url)
        else:
            error_reason = download_from_generic_url(driver, url)
        
        # Check if we got a 404 error (either from publisher handler or detected on page)
        if error_reason == ERROR_NOT_FOUND or (error_reason == ERROR_NO_PDF or error_reason is None):
            # Check current page for 404 if not already detected
            is_404 = (error_reason == ERROR_NOT_FOUND)
            if not is_404:
                try:
                    is_404 = detect_404_error(driver)
                except:
                    pass
            
            if is_404:
                # Try URL transformations
                current_url = driver.current_url
                transformed_urls = transform_url_to_pdf_url(original_url, current_url)
                
                # Try each transformed URL
                for transformed_url in transformed_urls[:3]:  # Limit to first 3 transformations
                    try:
                        driver.get(transformed_url)
                        time.sleep(3)
                        
                        # Check if still 404
                        if detect_404_error(driver):
                            continue
                        
                        # Not a 404 - try to find PDF
                        publisher_type = detect_publisher_type(transformed_url)
                        if publisher_type == 'pmc':
                            error_reason = download_from_pmc_url(driver, transformed_url, output_path)
                        elif publisher_type == 'ieee':
                            error_reason = download_from_ieee_url(driver, transformed_url)
                        elif publisher_type == 'sciencedirect':
                            error_reason = download_from_sciencedirect_url(driver, transformed_url)
                        elif publisher_type == 'springer':
                            error_reason = download_from_springer_url(driver, transformed_url)
                        elif publisher_type == 'wiley':
                            error_reason = download_from_wiley_url(driver, transformed_url)
                        else:
                            error_reason = download_from_generic_url(driver, transformed_url)
                        
                        # If transformation worked (no error or different error), break
                        if error_reason != ERROR_NOT_FOUND and not detect_404_error(driver):
                            time.sleep(2)
                            return error_reason
                    except:
                        continue
                
                # All transformations failed - return NOT_FOUND to signal DOI fallback
                return ERROR_NOT_FOUND
        
        time.sleep(2)  # Give download time to start
        
        return error_reason
        
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_PUBLISHER_ERROR


def search_by_metadata_selenium(driver: webdriver.Chrome, ref: Dict[str, str], output_path: Path, use_library: bool = False) -> Optional[str]:
    """
    Fallback strategy: Search for paper using metadata (title, author, journal, etc.).
    Tries multiple search engines and strategies.
    
    Returns:
        Error reason string if failed, None if attempted
    """
    try:
        # Check if file already exists
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None
        
        title = ref.get('title', '')
        first_author = ref.get('first_author', '')
        journal = ref.get('journal', '')
        year = ref.get('year', '')
        doi = ref.get('doi', '')
        
        if not title:
            return ERROR_NO_IDENTIFIER  # Need at least a title
        
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
                        return None
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
                            return None
                    except:
                        continue
            except:
                pass
        
        # Strategy 3: Try DOI if available (as fallback)
        if doi:
            try:
                found_pmid = search_pubmed_by_doi(driver, doi, use_library)
                if found_pmid:
                    error_reason = download_via_pubmed_selenium(driver, found_pmid, output_path, use_library, doi=doi)
                    return error_reason
            except:
                pass
        
        return ERROR_NO_PDF
        
    except TimeoutException:
        return ERROR_TIMEOUT
    except Exception as e:
        return ERROR_UNKNOWN


def download_via_arxiv(ref: Dict[str, str], output_path: Path) -> Optional[str]:
    """
    Final fallback strategy: Search arXiv for preprint version and download.
    Only attempts if title is available.
    
    Args:
        ref: Reference dictionary with title, first_author, year
        output_path: Path where PDF should be saved
    
    Returns:
        Error reason string if failed, None if successful
    """
    try:
        # Check if file already exists
        if output_path.exists() and output_path.stat().st_size > 1024:
            return None
        
        title = ref.get('title', '')
        first_author = ref.get('first_author', '')
        year = ref.get('year', '')
        
        # Require at least a title for arXiv search
        if not title or title == 'Unknown Title':
            return ERROR_NO_IDENTIFIER
        
        # Search arXiv API
        arxiv_id = search_arxiv_api(title, first_author, year)
        
        if not arxiv_id:
            return ERROR_NOT_FOUND  # No match found on arXiv
        
        # Download PDF from arXiv
        if download_arxiv_pdf(arxiv_id, output_path):
            # Verify file was downloaded successfully
            if output_path.exists() and output_path.stat().st_size > 1024:
                return None  # Success
            else:
                return ERROR_DOWNLOAD_FAILED
        else:
            return ERROR_DOWNLOAD_FAILED
        
    except requests.RequestException as e:
        return ERROR_DOWNLOAD_FAILED
    except Exception as e:
        return ERROR_UNKNOWN


def generate_ris_with_attachments(references: List[Dict[str, str]], downloaded_files: Dict[str, str]) -> str:
    """
    Generate RIS content with L1 attachment fields for references that have downloaded files.
    V4: Preserves existing L1/L2/L3 attachment fields from input RIS file.
    
    Args:
        references: List of reference dictionaries, each containing 'ris_text', 'record_number',
                    'has_attachment', and 'existing_attachments'
        downloaded_files: Dictionary mapping record_number to absolute file path
    
    Returns:
        Complete RIS file content as string with L1 fields added before ER markers
        (preserves existing L1/L2/L3 fields from input)
    """
    ris_lines = []
    
    for ref in references:
        # Get original RIS text (includes ER marker at end)
        ris_text = ref.get('ris_text', '')
        record_number = ref.get('record_number')
        has_attachment = ref.get('has_attachment', False)
        existing_attachments = ref.get('existing_attachments', [])
        
        # Remove trailing ER marker and whitespace (we'll add it back after L1 field)
        ris_text = ris_text.rstrip()
        # Handle various ER marker formats
        if ris_text.endswith('ER  -\n'):
            ris_text = ris_text[:-6].rstrip()
        elif ris_text.endswith('ER  -'):
            ris_text = ris_text[:-5].rstrip()
        
        # Remove existing L1/L2/L3 fields from ris_text (they're already stored in existing_attachments)
        # This prevents duplicates when we add new attachments
        lines = ris_text.split('\n')
        cleaned_lines = []
        for line in lines:
            line_stripped = line.strip()
            # Skip L1/L2/L3 attachment fields (we'll add them back if needed)
            if not (line_stripped.startswith('L1  - ') or 
                    line_stripped.startswith('L2  - ') or 
                    line_stripped.startswith('L3  - ')):
                cleaned_lines.append(line)
        ris_text = '\n'.join(cleaned_lines).rstrip()
        
        # Add all original RIS fields (without L1/L2/L3)
        ris_lines.append(ris_text)
        
        # Add existing attachment fields first (if any) to preserve them
        # These were already in the original RIS file
        if has_attachment and existing_attachments:
            for attachment_idx, attachment_path in enumerate(existing_attachments):
                # Determine which L field to use (L1 for first, L2 for second, L3 for third)
                if attachment_idx == 0:
                    ris_lines.append(f"L1  - {attachment_path}")
                elif attachment_idx == 1:
                    ris_lines.append(f"L2  - {attachment_path}")
                elif attachment_idx == 2:
                    ris_lines.append(f"L3  - {attachment_path}")
                # If more than 3 attachments, continue with L3 (though this is uncommon)
        
        # Add L1 field if file was newly downloaded (only for references without existing attachments)
        # References with existing attachments are skipped in main loop, so this shouldn't happen
        # But handle it just in case
        if record_number and record_number in downloaded_files:
            new_path = downloaded_files[record_number]
            # Check if this is a new download (path not in existing attachments)
            is_new_download = not (has_attachment and new_path in existing_attachments)
            if is_new_download:
                if has_attachment and existing_attachments:
                    # Shouldn't happen (references with attachments are skipped), but handle gracefully
                    # Add as next available L field
                    if len(existing_attachments) == 1:
                        ris_lines.append(f"L2  - {new_path}")
                    elif len(existing_attachments) == 2:
                        ris_lines.append(f"L3  - {new_path}")
                    else:
                        # Already have 3+ attachments, add to L3 (though should not happen)
                        ris_lines.append(f"L3  - {new_path}")
                else:
                    # No existing attachments, use L1 (normal case for newly downloaded files)
                    ris_lines.append(f"L1  - {new_path}")
        
        # End of record
        ris_lines.append("ER  -")
        ris_lines.append("")  # Empty line between records
    
    return "\n".join(ris_lines)


def run_full_text_scrape(
    run: "Optional[SearchRun]" = None,
    *,
    resume: bool = False,
) -> Optional[Path]:
    """Run the scraper workflow and return the generated RIS output path.

    Args:
        run: Optional SearchRun. When provided, V4 reads from `run.input_ris`,
            writes PDFs into the CAS store at `$LIT_REVIEW_PDF_STORE/pdfs/`
            with symlinks under `run.pdfs_dir`, appends progress to
            `run.progress_path`, mirrors stdout/stderr to `run.log_path`, and
            updates `run.metadata_path` atomically. Returns the path to
            `run.found_ris`.
        resume: When True (with `run`), reads `run.progress_path` and skips
            records whose outcome is terminal (success / skipped_existing /
            terminal error reasons per SCHEMA.md).

    When `run` is None, falls back to the legacy interactive workflow that
    reads/writes under automated_search/missing_papers/ and
    automated_search/found_papers/. The legacy path is removed in Phase 7.
    """
    if run is not None:
        if not _SEARCH_RUN_AVAILABLE:
            raise RuntimeError(
                "run= was provided but ensure_pdf_store/search_run helpers are not "
                "importable. Ensure automated_search/scripts/helpers/ is on sys.path."
            )
        return _run_full_text_scrape_with_run(run, resume=resume)

    return _run_full_text_scrape_interactive()


def _setup_run_logging(log_path: Path) -> logging.Handler:
    """Tee V4 stdout/stderr to <run>/log.txt via the logging module.

    Returns the handler so the caller can remove it on exit.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.setLevel(logging.INFO)
    root_logger = logging.getLogger()
    if root_logger.level > logging.INFO or root_logger.level == 0:
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    class _StdoutTee:
        def __init__(self, original, log_file):
            self._original = original
            self._log_file = log_file
        def write(self, data):
            try:
                self._original.write(data)
            except Exception:
                pass
            try:
                self._log_file.write(data)
                self._log_file.flush()
            except Exception:
                pass
        def flush(self):
            try:
                self._original.flush()
            except Exception:
                pass
            try:
                self._log_file.flush()
            except Exception:
                pass

    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    log_file.write(f"\n=== V4 run started at {datetime.datetime.utcnow().isoformat()}Z ===\n")
    import sys as _sys
    _sys.stdout = _StdoutTee(_sys.__stdout__, log_file)
    _sys.stderr = _StdoutTee(_sys.__stderr__, log_file)
    handler._log_file = log_file  # type: ignore[attr-defined]
    return handler


def _teardown_run_logging(handler: logging.Handler) -> None:
    import sys as _sys
    _sys.stdout = _sys.__stdout__
    _sys.stderr = _sys.__stderr__
    log_file = getattr(handler, "_log_file", None)
    if log_file is not None:
        try:
            log_file.close()
        except Exception:
            pass
    logging.getLogger().removeHandler(handler)


def _resume_skip_set(run: "SearchRun") -> set:
    """Read progress.jsonl and return record_numbers whose outcome is terminal."""
    skip: set = set()
    terminal_outcomes = terminal_outcomes_for_resume()
    terminal_errors = terminal_error_reasons_for_resume()
    for entry in read_progress(run):
        rn = entry.get("record_number")
        if not rn:
            continue
        if entry.get("outcome") in terminal_outcomes:
            skip.add(rn)
        elif entry.get("error_reason") in terminal_errors:
            skip.add(rn)
    return skip


def _run_full_text_scrape_with_run(run: "SearchRun", *, resume: bool) -> Optional[Path]:
    """SearchRun-aware V4 orchestration.

    Supports two PDF storage backends selected by environment variable:

    * **rclone-copy mode** (``$LIT_REVIEW_PDF_REMOTE`` set): downloads each
      PDF to a local temp dir under ``automated_search/.tmp_pdfs/<run_id>/``,
      then immediately ``rclone copy``s it to the remote (e.g.
      ``gdrive:nlp_lit_review_1_papers/pdfs``) and deletes the local copy.
      A ``found/pdfs.txt`` manifest records the R2 URL for each downloaded
      paper.  No local storage accumulates across papers.

    * **mount mode** (``$LIT_REVIEW_PDF_STORE`` set, FUSE mount active): writes
      PDFs directly into the CAS store at ``$LIT_REVIEW_PDF_STORE/pdfs/<key>.pdf``
      and creates symlinks under ``<run>/found/pdfs/``.

    In both modes the function appends per-record progress to
    ``<run>/progress.jsonl``, tees stdout/stderr to ``<run>/log.txt``, and
    updates ``metadata.json`` atomically at startup / every-25-papers / end.
    """
    import os as _os

    # ---- backend detection -------------------------------------------- #
    backend = resolve_pdf_backend()
    rclone_mode = isinstance(backend, PdfRemote)

    if rclone_mode:
        remote_path: str = backend.remote_path  # type: ignore[union-attr]
        store = None
        _search_root = Path(__file__).resolve().parents[2]
        tmp_dir: Optional[Path] = _search_root / ".tmp_pdfs" / run.run_id
        tmp_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
        output_dir = tmp_dir
        cas_index: Dict = build_remote_index(remote_path)
        store_label = f"rclone-copy → {remote_path}"
    else:
        store = backend  # type: ignore[assignment]
        remote_path = ""
        tmp_dir = None
        output_dir = store.pdfs_dir  # type: ignore[union-attr]
        cas_index = build_cas_index(store)
        store_label = str(store.pdfs_dir)  # type: ignore[union-attr]

    handler = _setup_run_logging(run.log_path)
    skip_set = _resume_skip_set(run) if resume else set()

    try:
        print(f"V4 (SearchRun mode): run_id={run.run_id}")
        print(f"  PDF store: {store_label}")
        if rclone_mode:
            print(f"  Mode: rclone-copy (no FUSE mount required)")
            print(f"  Temp dir: {tmp_dir}")
        if resume and skip_set:
            print(f"  Resume: will skip {len(skip_set)} already-attempted records")

        save_metadata(run, started_at=utc_iso_now())

        master_ris_dir = Path(__file__).resolve().parents[3] / "visualizer_nlp_lit_review" / "RIS_source_files"
        master_ris_path = find_newest_master_ris_path(master_ris_dir)
        master_skip_keys = build_master_pdf_skip_keys(master_ris_path)
        if master_ris_path:
            print(f"  Master RIS (for skip-existing): {master_ris_path.name}")
        print(f"  Master RIS entries with PDF (skip download): {len(master_skip_keys)} keys")

        if not run.input_ris.exists():
            raise FileNotFoundError(f"input.ris not found: {run.input_ris}")

        print(f"\nParsing input.ris: {run.input_ris}")
        references = parse_ris_file(str(run.input_ris), download_dir=str(output_dir))
        print(f"Found {len(references)} references")

        save_metadata(run, input_count=len(references))

        already_on_file_count = sum(
            1 for ref in references if pdf_already_on_file(ref, cas_index, master_skip_keys)
        )
        need_download_count = len(references) - already_on_file_count
        print(
            f"\n  Already on file (skip download): {already_on_file_count}/{len(references)}"
        )
        print(f"  Will attempt download only for: {need_download_count}/{len(references)}")
        if need_download_count == 0:
            print("  No new PDF downloads needed for this run.\n")

        downloaded_files: Dict[str, str] = {}
        successful: List[Dict] = []
        failed: List[Dict] = []
        error_reasons: Dict[str, str] = {}
        skipped_existing = 0

        downloads_dir = Path.home() / "Downloads"
        last_seen_file = get_most_recent_downloads_file(downloads_dir)

        start_time = datetime.datetime.now()
        driver = None
        use_library = True
        try:
            for i, ref in enumerate(references, 1):
                record_number = ref.get("record_number") or f"record_{i}"
                title = ref.get("title") or "Unknown"
                pmid = ref.get("pmid")
                doi = ref.get("doi")
                pmc_id = ref.get("pmc_id")
                url = ref.get("url")
                pii = ref.get("pii")
                publisher = (ref.get("publisher") or "").lower()

                if resume and record_number in skip_set:
                    print(f"[{i}/{len(references)}] {record_number} {title[:20]} (resume: skipping)")
                    continue

                # Health check only for mount mode (remote listing is expensive).
                if not rclone_mode and (i - 1) % HEALTH_CHECK_EVERY_N_PAPERS == 0 and i > 1:
                    try:
                        health_check(store.root)  # type: ignore[union-attr]
                    except PdfStoreUnavailable as exc:
                        print(f"\nFATAL: PDF store became unavailable mid-run: {exc}")
                        save_metadata(run, error_summary=_count_errors(error_reasons))
                        raise

                cas_key = cas_key_for_reference(ref)
                identifier_used = None
                if pmid:
                    identifier_used = f"pmid:{pmid}"
                elif doi:
                    identifier_used = f"doi:{doi}"
                elif ref.get("title"):
                    identifier_used = f"title:{ref['title'][:60]}"

                if pdf_already_on_file(ref, cas_index, master_skip_keys):
                    on_drive = bool(cas_key and cas_key in cas_index)
                    label = "on Drive" if on_drive else "in master RIS"
                    print(f"[{i}/{len(references)}] {record_number} {title[:20]} ✓ skip ({label})")
                    if rclone_mode and cas_key:
                        if on_drive:
                            downloaded_files[record_number] = cas_index[cas_key]
                        else:
                            downloaded_files[record_number] = r2_url_for_key(cas_key)
                    elif cas_key and cas_key in cas_index:
                        existing = cas_index[cas_key]  # Path
                        try:
                            link_into_run(existing, run.pdfs_dir, cas_key)
                        except Exception as exc:
                            print(f"  WARNING: could not symlink into run: {exc}")
                        downloaded_files[record_number] = str(existing)
                    successful.append(ref)
                    skipped_existing += 1
                    append_progress(
                        run,
                        record_number=record_number,
                        identifier_used=identifier_used,
                        outcome="skipped_existing",
                    )
                    continue

                if ref.get("has_attachment", False):
                    existing_attachments = ref.get("existing_attachments", [])
                    print(f"[{i}/{len(references)}] {record_number} {title[:20]} ⏭️  already has L1")
                    successful.append(ref)
                    if existing_attachments:
                        downloaded_files[record_number] = existing_attachments[0]
                    append_progress(
                        run,
                        record_number=record_number,
                        identifier_used=identifier_used,
                        outcome="skipped_existing",
                    )
                    skipped_existing += 1
                    continue

                # Compute the local path where this paper should land.
                if rclone_mode:
                    output_path = output_dir / f"{cas_key or record_number}.pdf"  # type: ignore[operator]
                else:
                    output_path = (
                        cas_path_for_key(store, cas_key)  # type: ignore[arg-type]
                        if cas_key
                        else store.pdfs_dir / f"record_{record_number}.pdf"  # type: ignore[union-attr]
                    )

                is_elsevier = False
                if url and "sciencedirect.com" in url.lower():
                    is_elsevier = True
                elif "elsevier" in publisher:
                    is_elsevier = True
                elif doi and doi.startswith("10.1016"):
                    is_elsevier = True

                print(f"[{i}/{len(references)}] {record_number} {title[:20]} ", end="")
                attempt_start = datetime.datetime.now()
                download_attempted = False
                error_reason: Optional[str] = None
                found_pmid_from_doi = None

                file_before = get_most_recent_downloads_file(downloads_dir)

                if is_elsevier and (doi or pii):
                    error_reason = download_via_elsevier_api(doi, output_path, ELSEVIER_API_KEY, pii)
                    if error_reason is None and output_path.exists() and output_path.stat().st_size > 1024:
                        download_attempted = True
                        print("SUCCESS (Elsevier API) ", end="")
                    else:
                        download_attempted = False

                if not download_attempted and driver is None:
                    print("\nSetting up Chrome browser...")
                    driver = setup_driver(headless=False, download_dir=str(output_dir))

                if not download_attempted and url:
                    error_reason = download_via_url_selenium(driver, url, output_path, use_library, doi)
                    if error_reason == ERROR_NOT_FOUND:
                        download_attempted = False
                    else:
                        download_attempted = True

                if not download_attempted and doi:
                    result = download_via_doi_selenium(driver, doi, output_path, use_library)
                    download_attempted = True
                    if result and result.isdigit():
                        found_pmid_from_doi = result
                        error_reason = download_via_pubmed_selenium(
                            driver, found_pmid_from_doi, output_path, use_library, doi=doi
                        )
                    elif result and result.startswith("ERROR_"):
                        error_reason = result
                    else:
                        error_reason = result

                if not download_attempted and pmc_id:
                    error_reason = download_via_pmc_selenium(driver, pmc_id, output_path)
                    download_attempted = True

                if not download_attempted and pmid:
                    error_reason = download_via_pubmed_selenium(driver, pmid, output_path, use_library, doi=doi)
                    download_attempted = True

                if not download_attempted:
                    error_reason = search_by_metadata_selenium(driver, ref, output_path, use_library)
                    download_attempted = True

                if not download_attempted:
                    error_reason = download_via_arxiv(ref, output_path)
                    download_attempted = True

                time.sleep(2)
                file_after = get_most_recent_downloads_file(downloads_dir)

                download_success = False
                downloaded_file_path = None
                if file_after and (not file_before or file_after[0] != file_before[0] or file_after[1] > file_before[1]):
                    download_success = True
                    downloaded_file_path = downloads_dir / file_after[0]
                if not download_success and output_path.exists() and output_path.stat().st_size > 1024:
                    download_success = True

                elapsed_ms = int((datetime.datetime.now() - attempt_start).total_seconds() * 1000)

                if download_success:
                    if downloaded_file_path and downloaded_file_path.exists() and not output_path.exists():
                        try:
                            downloaded_file_path.rename(output_path)
                        except Exception as exc:
                            print(f"  Warning: rename failed: {exc}")

                    print("✓ DOWNLOADED")
                    successful.append(ref)

                    if rclone_mode:
                        # In rclone-copy mode, rename to key-based name, upload,
                        # delete local, and record the R2 URL for found.ris.
                        if cas_key:
                            keyed = output_dir / f"{cas_key}.pdf"  # type: ignore[operator]
                            if output_path != keyed and output_path.exists():
                                try:
                                    output_path.rename(keyed)
                                    output_path = keyed
                                except OSError:
                                    pass
                        try:
                            upload_pdf_to_remote(output_path, remote_path, delete_after=True)
                            final_ref = r2_url_for_key(cas_key) if cas_key else f"{remote_path}/{output_path.name}"
                            downloaded_files[record_number] = final_ref
                            if cas_key:
                                cas_index[cas_key] = final_ref
                            print(f"  → uploaded to {remote_path}")
                        except Exception as exc:
                            print(f"  WARNING: rclone upload failed: {exc}; local copy kept at {output_path}")
                            downloaded_files[record_number] = str(output_path)
                    else:
                        # Mount mode: update in-memory CAS index and create symlink.
                        downloaded_files[record_number] = str(output_path)
                        if cas_key:
                            cas_index[cas_key] = output_path
                            try:
                                link_into_run(output_path, run.pdfs_dir, cas_key)
                            except Exception as exc:
                                print(f"  WARNING: symlink into run failed: {exc}")

                    append_progress(
                        run,
                        record_number=record_number,
                        identifier_used=identifier_used,
                        outcome="success",
                        elapsed_ms=elapsed_ms,
                    )
                    if file_after:
                        last_seen_file = file_after
                else:
                    if not error_reason:
                        error_reason = ERROR_DOWNLOAD_FAILED
                    error_reasons[record_number] = error_reason
                    print(f"✗ FAILED ({error_reason})")
                    failed.append(ref)
                    append_progress(
                        run,
                        record_number=record_number,
                        identifier_used=identifier_used,
                        outcome="fail",
                        error_reason=error_reason,
                        elapsed_ms=elapsed_ms,
                    )
                    append_error(
                        run,
                        record_number=record_number,
                        identifier_used=identifier_used,
                        error_reason=error_reason,
                    )
                    if file_after:
                        last_seen_file = file_after

                if i % 25 == 0:
                    save_metadata(
                        run,
                        download_success=len(successful) - skipped_existing,
                        download_fail=len(failed),
                        download_skipped_existing=skipped_existing,
                        error_summary=_count_errors(error_reasons),
                    )

        finally:
            if driver is not None:
                print("\nClosing browser...")
                driver.quit()

        run.missing_ris.parent.mkdir(parents=True, exist_ok=True)
        if failed:
            with open(run.missing_ris, "w", encoding="utf-8") as f:
                for ref in failed:
                    f.write(ref["ris_text"])
                    f.write("\n")
            print(f"\nMissing RIS written: {run.missing_ris}")
        else:
            run.missing_ris.write_text("", encoding="utf-8")

        print(f"\nGenerating found.ris with attachments...")
        ris_content = generate_ris_with_attachments(references, downloaded_files)
        run.found_ris.parent.mkdir(parents=True, exist_ok=True)
        with open(run.found_ris, "w", encoding="utf-8") as f:
            f.write("; generated by automated_search/scripts/helpers/full_text_scrape_V4.py (SearchRun mode)\n")
            f.write(f"; run_id: {run.run_id}\n\n")
            f.write(ris_content)
        print(f"  Found RIS: {run.found_ris}")

        # In rclone-copy mode write a manifest of remote/R2 paths and clean up
        # the local temp dir (should be empty if all uploads succeeded).
        if rclone_mode:
            manifest_path = run.found_ris.parent / "pdfs.txt"
            with open(manifest_path, "w", encoding="utf-8") as mf:
                mf.write("; PDF manifest — generated by full_text_scrape_V4.py (rclone-copy mode)\n")
                mf.write(f"; run_id: {run.run_id}\n")
                mf.write("; format: <record_number>\\t<r2_url_or_remote_path>\n\n")
                for rn, ref_url in downloaded_files.items():
                    mf.write(f"{rn}\t{ref_url}\n")
            print(f"  PDF manifest: {manifest_path}")

            if tmp_dir and tmp_dir.exists():
                leftovers = [p for p in tmp_dir.iterdir()]
                if leftovers:
                    print(f"  WARNING: {len(leftovers)} file(s) remain in tmp dir "
                          f"(rclone upload may have failed):")
                    for p in leftovers[:5]:
                        print(f"    {p.name}")
                    print(f"  Temp dir kept for inspection: {tmp_dir}")
                else:
                    try:
                        tmp_dir.rmdir()
                    except OSError:
                        pass

        save_metadata(
            run,
            finished_at=utc_iso_now(),
            download_success=len(successful) - skipped_existing,
            download_fail=len(failed),
            download_skipped_existing=skipped_existing,
            error_summary=_count_errors(error_reasons),
        )

        runtime = datetime.datetime.now() - start_time
        print(f"\n{'='*60}")
        print(f"SUMMARY (SearchRun mode):")
        print(f"  Run: {run.run_id}")
        print(f"  Input: {len(references)}  Success: {len(successful) - skipped_existing}  "
              f"Skipped (existing): {skipped_existing}  Failed: {len(failed)}")
        print(f"  Runtime: {runtime}")
        print(f"{'='*60}")
        return run.found_ris

    finally:
        _teardown_run_logging(handler)


def _count_errors(error_reasons: Dict[str, str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for reason in error_reasons.values():
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _run_full_text_scrape_interactive() -> Optional[Path]:
    """Legacy interactive entry point. Body unchanged from pre-refactor V4."""
    # Find the most recent .txt file for the prompt
    most_recent_file = find_most_recent_txt_file()
    if most_recent_file:
        print(f"\nDefault file (if you press 'n'): {most_recent_file.name}")
        print(f"  Full path: {most_recent_file}")
        prompt_message = f"Would you like to enter RIS file name manually? If not, I'll use {most_recent_file.name} (newest file). (y/n, default=n): "
    else:
        prompt_message = "Would you like to enter RIS file name manually? If not, I will try to find the newest file. (y/n, default=n): "
    
    # Ask user if they want to manually specify RIS file
    manual_input = input(prompt_message).strip().lower()
    
    if manual_input == 'y':
        ris_file_input = input("Enter RIS file name or path (relative to missing_papers/still_missing/, or absolute path): ").strip()
        # Check if it's an absolute path
        if os.path.isabs(ris_file_input):
            ris_file = Path(ris_file_input)
        else:
            # Build path - if it starts with archive/, use that, otherwise assume it's in still_missing/
            still_missing_dir = get_still_missing_dir()
            if ris_file_input.startswith('archive/'):
                ris_file = still_missing_dir / ris_file_input
            else:
                ris_file = still_missing_dir / ris_file_input
        
        if not ris_file.exists():
            print(f"ERROR: RIS file not found: {ris_file}")
            return
        print(f"Using manually specified RIS file: {ris_file}")
    else:
        # Default automated behavior - use the most recently added/modified .txt file (newest)
        ris_file = find_most_recent_txt_file()
        if not ris_file:
            print("ERROR: Could not find any .txt file in missing_papers/still_missing/ directory")
            return
        print(f"\nUsing default (newest) RIS file: {ris_file.name}")
        print(f"  Full path: {ris_file}")
    
    # Ask user for output directory path
    script_dir = Path(__file__).resolve().parent
    search_root = script_dir.parent.parent
    default_output_dir = search_root / "found_papers" / "downloaded_papers" / "V3_scraped_papers"
    output_dir_input = input(f"\nEnter path to save downloaded PDF files (default: {default_output_dir}): ").strip()
    
    if output_dir_input:
        # User provided a path - use it (can be relative or absolute)
        if os.path.isabs(output_dir_input):
            output_dir = Path(output_dir_input)
        else:
            # Relative path - resolve relative to automated_search/
            output_dir = (search_root / output_dir_input).resolve()
    else:
        # Use default under automated_search/
        output_dir = default_output_dir
    
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"PDF files will be saved to: {output_dir.absolute()}")
    
    # Base download_papers directory for checking existing files (parent of output_dir by default)
    # If custom path provided, use its parent; otherwise use default
    if output_dir_input:
        download_papers_base_dir = output_dir.parent
    else:
        download_papers_base_dir = search_root / "found_papers" / "downloaded_papers"
    
    # RIS output directory (relative to automated_search/, two levels above helpers/)
    ris_output_dir = search_root / "found_papers" / "RIS_files" / "import_to_endnote"
    ris_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate output RIS filename: {input_filename}_post_scrape.txt
    input_ris_stem = ris_file.stem
    output_ris_filename = f"{input_ris_stem}_post_scrape.txt"
    output_ris_path = ris_output_dir / output_ris_filename
    
    # #region Commented out - Import map functionality (kept for reference)
    # # Import map directory
    # import_ids_dir = Path("found_papers/import_IDs")
    # import_ids_dir.mkdir(parents=True, exist_ok=True)
    # 
    # # Use temporary filename during execution, will rename at end with final counts
    # import_map_temp_path = import_ids_dir / "import_map_temp.txt"
    # import_map_path = import_map_temp_path  # Will be updated at end
    # 
    # # Initialize import map file (no header)
    # with open(import_map_path, 'w', encoding='utf-8') as f:
    #     pass  # File will be created, entries appended later
    # #endregion
    
    print("="*60)
    print("PDF DOWNLOADER - Multi-Strategy V4 - Selenium Browser Automation")
    print("="*60)
    print("\nThis script will open a Chrome browser window.")
    print("Features:")
    print("  - V4 NEW: Skips references that already have attached full text files (L1/L2/L3 fields)")
    print("  - Direct URL downloads (highest priority)")
    print("  - Enhanced DOI support (searches PubMed by DOI first)")
    print("  - Publisher-specific handlers (IOS Press, OUP, etc.)")
    print("  - PubMed publisher link following (IOS Press, etc.)")
    print("  - Metadata-based search fallbacks")
    print("  - Error tracking and reporting")
    print("  - Enhanced paywall detection")
    print("  - Runtime tracking")
    print("  - Fixed download detection")
    print("  - Library proxy access support")
    print("  - arXiv preprint search and download (final fallback)")
    print("\nYou may need to:")
    print("1. Log into HSHSL library if prompted")
    print("2. Allow downloads in the browser")
    print("3. Let the script run (it will control the browser)")
    print()
    
    # Automatically use library access (default to 'y')
    use_library = True
    
    # Ask about pilot mode BEFORE parsing
    pilot_mode_input = input("Run in PILOT mode? (processes Elsevier papers only) (y/n, default=n): ").strip().lower()
    pilot_mode = pilot_mode_input == 'y'
    
    if pilot_mode:
        # Override RIS file to use missing_elsevier_papers.txt
        elsevier_ris_file = get_still_missing_dir() / "missing_elsevier_papers.txt"
        if elsevier_ris_file.exists():
            ris_file = elsevier_ris_file
            print(f"\n??  PILOT MODE ENABLED - Using Elsevier papers file")
            print(f"  RIS file: {ris_file}")
        else:
            print(f"\n??  ERROR: Elsevier papers file not found: {elsevier_ris_file}")
            print("  Exiting...\n")
            return
    
    print(f"\nParsing RIS file: {ris_file}")
    references = parse_ris_file(str(ris_file), download_dir=output_dir)
    print(f"Found {len(references)} references")
    
    # Dictionary to track downloaded files: {record_number: absolute_path}
    downloaded_files = {}  # Maps record_number to absolute file path
    
    # Get counts for final import map filename
    input_refs = len(references)  # References in current RIS file
    original_ris_file = find_original_ris_file()
    if original_ris_file:
        original_refs = count_ris_references(original_ris_file)
    else:
        original_refs = input_refs  # Fallback: use input_refs if original not found
    
    # Count available identifiers
    refs_with_url = sum(1 for ref in references if ref.get('url'))
    refs_with_doi = sum(1 for ref in references if ref.get('doi'))
    refs_with_pmid = sum(1 for ref in references if ref.get('pmid'))
    refs_with_pmc = sum(1 for ref in references if ref.get('pmc_id'))
    print(f"  - {refs_with_url} references have URLs")
    print(f"  - {refs_with_doi} references have DOIs")
    print(f"  - {refs_with_pmid} references have PMIDs")
    print(f"  - {refs_with_pmc} references have PMC IDs\n")
    
    if pilot_mode:
        print(f"  ??  PILOT MODE - Processing {len(references)} Elsevier papers\n")
    else:
        print(f"\nProcessing all {len(references)} references\n")
    
    # Record start time for runtime tracking
    start_time = datetime.datetime.now()
    
    # Setup driver (lazy - only if needed for Selenium strategies)
    driver = None
    
    successful = []
    failed = []
    error_reasons = {}  # Track error reasons per paper
    
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
            
            # Check if file already exists anywhere in download_papers directory (including subfolders)
            existing_file, is_loose = find_existing_paper_in_download_papers(filename, download_papers_base_dir)
            if existing_file:
                if is_loose:
                    print(f"[{i}/{len(references)}] {record_number or 'N/A'} {title[:20] if title else 'Unknown'}")
                    print(f"  ⚠️  WARNING: PAPER ALREADY EXISTS LOOSE IN downloaded_papers, IT LIKELY DOES NOT HAVE AN IMPORT MAP AND HAS NOT BEEN IMPORTED INTO ENDNOTE")
                    print(f"  Location: {existing_file}")
                else:
                    print(f"[{i}/{len(references)}] {record_number or 'N/A'} {title[:20] if title else 'Unknown'}")
                    print(f"  ✓ Already exists in: {existing_file.relative_to(download_papers_base_dir)}")
                # Skip processing - file already exists
                successful.append(ref)
                # Store absolute path in tracking dictionary for RIS output
                if record_number:
                    absolute_path = os.path.abspath(existing_file)
                    downloaded_files[record_number] = absolute_path
                # #region Commented out - Import map write (kept for reference)
                # if record_number:
                #     absolute_path = os.path.abspath(existing_file)
                #     with open(import_map_path, 'a', encoding='utf-8') as f:
                #         f.write(f"{record_number}\t{absolute_path}\n")
                # #endregion
                continue
            
            # Also check if file already exists in target output directory
            if output_path.exists() and output_path.stat().st_size > 1024:
                print(f"[{i}/{len(references)}] {record_number or 'N/A'} {title[:20] if title else 'Unknown'}")
                print(f"  ✓ Already exists in output directory")
                successful.append(ref)
                # Store absolute path in tracking dictionary for RIS output
                if record_number:
                    absolute_path = os.path.abspath(output_path)
                    downloaded_files[record_number] = absolute_path
                # #region Commented out - Import map write (kept for reference)
                # if record_number:
                #     absolute_path = os.path.abspath(output_path)
                #     with open(import_map_path, 'a', encoding='utf-8') as f:
                #         f.write(f"{record_number}\t{absolute_path}\n")
                # #endregion
                continue
            
            # V4: Skip references that already have attachments (L1/L2/L3 fields)
            if ref.get('has_attachment', False):
                existing_attachments = ref.get('existing_attachments', [])
                attachment_info = ', '.join(existing_attachments[:2])  # Show first 2 attachments
                if len(existing_attachments) > 2:
                    attachment_info += f", ... ({len(existing_attachments)} total)"
                print(f"[{i}/{len(references)}] {record_number or 'N/A'} {title[:20] if title else 'Unknown'}")
                print(f"  ⏭️  SKIPPED - Already has attachment(s): {attachment_info}")
                successful.append(ref)
                # Preserve existing attachments - they'll be included in output RIS file
                if record_number and existing_attachments:
                    # Use first attachment path (L1 is typically primary)
                    absolute_path = os.path.abspath(existing_attachments[0])
                    # Verify the path exists before storing
                    if os.path.exists(absolute_path):
                        downloaded_files[record_number] = absolute_path
                    else:
                        # If path doesn't exist, still preserve it (might be on different machine)
                        downloaded_files[record_number] = existing_attachments[0]
                continue
            
            print(f"[{i}/{len(references)}] ", end='')
            if record_number:
                print(f"{record_number} ", end='')
            # Add first 20 characters of title
            title_preview = title[:20] if title else "Unknown Title"
            print(f"{title_preview} ", end='')
            # Get identifiers
            url = ref.get('url')
            pii = ref.get('pii')
            publisher = (ref.get('publisher') or '').lower()
            
            # Check if this is an Elsevier/ScienceDirect paper for API strategy
            is_elsevier = False
            if url and 'sciencedirect.com' in url.lower():
                is_elsevier = True
            elif publisher and 'elsevier' in publisher:
                is_elsevier = True
            elif doi and doi.startswith('10.1016'):  # Elsevier DOI prefix
                is_elsevier = True
            
            # Show what identifier we have (priority: API > URL > DOI > PMID > Title)
            if is_elsevier and (doi or pii):
                print(f"Elsevier API... ", end='')
            elif url:
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
            error_reason = None
            
            # Strategy 0: Try Elsevier API if this is a ScienceDirect paper (bypasses CAPTCHA)
            if is_elsevier and (doi or pii):
                error_reason = download_via_elsevier_api(doi, output_path, ELSEVIER_API_KEY, pii)
                
                # Check if API download was successful (no error means success)
                if error_reason is None:
                    # API download succeeded - check if file exists
                    if output_path.exists() and output_path.stat().st_size > 1024:
                        # Success! File was downloaded via API - skip other strategies
                        download_attempted = True
                        error_reason = None  # Clear error to indicate success
                        print("SUCCESS (Elsevier API) ", end='')
                    else:
                        # API returned success but file not found - treat as failed, try other strategies
                        error_reason = ERROR_DOWNLOAD_FAILED
                        download_attempted = False  # Allow fallback to other strategies
                else:
                    # API failed - try other strategies
                    download_attempted = False
                    print(f"API failed ({error_reason}), trying Selenium... ", end='')
            
            # Setup driver only if we need Selenium strategies
            if not download_attempted and driver is None:
                print("\nSetting up Chrome browser...")
                print(f"  Download directory: {output_dir.absolute()}")
                driver = setup_driver(headless=False, download_dir=str(output_dir))
            
            # Strategy 1: Try URL first (highest priority - direct links)
            if not download_attempted and url:
                error_reason = download_via_url_selenium(driver, url, output_path, use_library, doi)
                # If URL returned NOT_FOUND, allow DOI fallback
                if error_reason == ERROR_NOT_FOUND:
                    download_attempted = False  # Allow DOI fallback
                    print("(URL 404, trying DOI fallback) ", end='')
                else:
                    download_attempted = True
            
            # Strategy 2: Try DOI (enhanced - searches PubMed by DOI first)
            # Also try if URL returned NOT_FOUND (404)
            if not download_attempted and doi:
                result = download_via_doi_selenium(driver, doi, output_path, use_library)
                download_attempted = True
                
                # Check if result is a PMID (success) or error reason
                if result and result.isdigit():
                    # Found PMID via DOI search
                    found_pmid_from_doi = result
                    print(f"(Found PMID {found_pmid_from_doi} via DOI search) ", end='')
                    error_reason = download_via_pubmed_selenium(driver, found_pmid_from_doi, output_path, use_library, doi=doi)
                elif result and result.startswith('ERROR_'):
                    error_reason = result
                else:
                    # result is None or empty - attempted but outcome unknown
                    error_reason = result
            
            # Strategy 3: Try PMC if available
            if not download_attempted and pmc_id:
                error_reason = download_via_pmc_selenium(driver, pmc_id, output_path)
                download_attempted = True
            
            # Strategy 4: Try PubMed/library access with existing PMID
            if not download_attempted and pmid:
                error_reason = download_via_pubmed_selenium(driver, pmid, output_path, use_library, doi=doi)
                download_attempted = True
            
            # Strategy 5: Try metadata-based search (fallback)
            if not download_attempted:
                print("(Trying metadata search) ", end='')
                error_reason = search_by_metadata_selenium(driver, ref, output_path, use_library)
                download_attempted = True
            
            # Strategy 6: Try arXiv search (final fallback)
            if not download_attempted:
                print("(Trying arXiv search) ", end='')
                error_reason = download_via_arxiv(ref, output_path)
                download_attempted = True
            
            # Wait a bit for download to complete
            time.sleep(2)  # Reduced from 3s to 2s
            
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
                
                # Store absolute path in tracking dictionary for RIS output
                if record_number:
                    absolute_path = os.path.abspath(output_path)
                    downloaded_files[record_number] = absolute_path
                
                # #region Commented out - Import map write (kept for reference)
                # # Append to import map file
                # if record_number:
                #     absolute_path = os.path.abspath(output_path)
                #     with open(import_map_path, 'a', encoding='utf-8') as f:
                #         f.write(f"{record_number}\t{absolute_path}\n")
                # #endregion
                
                # Update last_seen_file for next iteration
                last_seen_file = file_after
                time.sleep(1)
            else:
                # Determine final error reason if not already set
                if not error_reason:
                    error_reason = ERROR_DOWNLOAD_FAILED
                
                # Store error reason
                error_reasons[record_number or f"record_{i}"] = error_reason
                
                # Print failure with error reason
                error_display = error_reason.replace('_', ' ').title() if error_reason else "Unknown"
                print(f"? FAILED ({error_display})")
                failed.append(ref)
                # Update last_seen_file even on failure (for next iteration)
                if file_after:
                    last_seen_file = file_after
                time.sleep(0.5)
    
    finally:
        # Close browser (only if it was opened)
        if driver is not None:
            print("\nClosing browser...")
            driver.quit()
        else:
            print("\nNo browser was opened (API download succeeded).")
    
    # Calculate runtime
    end_time = datetime.datetime.now()
    runtime = end_time - start_time
    
    # Write failed references
    missing_path = None
    if failed:
        output_dir = get_still_missing_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        missing_filename = get_next_missing_filename(output_dir, "missing_after_second_scrape")
        missing_path = output_dir / missing_filename
        with open(missing_path, 'w', encoding='utf-8') as f:
            for ref in failed:
                f.write(ref['ris_text'])
                f.write('\n')
        print(f"\nFailed downloads written to: {missing_path}")
    
    # Count error reasons
    error_counts = {}
    for error_reason in error_reasons.values():
        error_counts[error_reason] = error_counts.get(error_reason, 0) + 1
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  Input RIS file: {ris_file}")
    if pilot_mode:
        print(f"  ??  PILOT MODE - Processed Elsevier papers only")
    print(f"  Total references processed: {len(references)}")
    print(f"  Successfully downloaded: {len(successful)}")
    print(f"  Failed: {len(failed)}")
    if len(references) > 0:
        print(f"  Success rate: {len(successful)/len(references)*100:.1f}%")
    print(f"  Total runtime: {runtime}")
    
    # Print error summary
    if error_counts:
        print(f"\n  ERROR SUMMARY:")
        for error_reason, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
            error_display = error_reason.replace('_', ' ').title()
            print(f"    {error_display}: {count}")
    
    if failed and missing_path:
        print(f"\n  Failed references output file: {missing_path}")
        print(f"  ({len(failed)} references written to {missing_path.name})")
    
    # #region Commented out - Import map rename logic (kept for reference)
    # # Rename import map file with final counts
    # downloads_count = len(successful)
    # final_import_map_filename = get_import_map_filename(downloads_count, input_refs, original_refs, import_ids_dir)
    # final_import_map_path = import_ids_dir / final_import_map_filename
    # 
    # if import_map_path.exists():
    #     import_map_path.rename(final_import_map_path)
    #     import_map_path = final_import_map_path
    # 
    # print(f"\n  Import map file: {import_map_path}")
    # print(f"  ({len(successful)} entries written to import map)")
    # #endregion
    
    # Generate and write RIS file with L1 attachments
    print(f"\nGenerating RIS file with attachments...")
    ris_content = generate_ris_with_attachments(references, downloaded_files)
    with open(output_ris_path, 'w', encoding='utf-8') as f:
        f.write(ris_content)
    print(f"  RIS file written: {output_ris_path}")
    print(f"  ({len(downloaded_files)} references with file attachments)")
    print(f"{'='*60}")
    return output_ris_path


def main():
    """Main execution function for standalone script use."""
    run_full_text_scrape()


if __name__ == "__main__":
    main()
