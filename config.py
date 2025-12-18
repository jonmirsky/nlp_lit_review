"""
Configuration file for Literature Review Visualizer
Edit COMMON_SEARCH_TERMS to set the query strings and their associated RIS file prefixes
"""

import os
import sys
from pathlib import Path
from typing import Optional


def get_base_path():
    """
    Get base path - works for both PyInstaller bundle and normal execution
    Returns the directory containing the executable or script
    """
    # Check if running as PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        return Path(sys.executable).parent
    else:
        # Running as normal script - use environment variable if set, otherwise script location
        if 'VISUALIZER_BASE_PATH' in os.environ:
            return Path(os.environ['VISUALIZER_BASE_PATH'])
        return Path(__file__).parent


def get_ris_source_folder():
    """Get RIS source files folder path (portable)"""
    base_path = get_base_path()
    # Try relative path first (for bundled app)
    relative_path = base_path / "data" / "RIS_source_files"
    if relative_path.exists():
        return str(relative_path)
    # Fallback to absolute path (for development)
    absolute_path = Path("/Users/jon/Documents/badjatia_hu/visualizer_nlp_lit_review/RIS_source_files")
    if absolute_path.exists():
        return str(absolute_path)
    # Return relative path anyway (will be created if needed)
    return str(relative_path)


def get_manual_groupings_folder():
    """Get manual groupings folder path (portable)"""
    base_path = get_base_path()
    # Try relative path first (for bundled app)
    relative_path = base_path / "data" / "RIS_source_files" / "manual_groupings"
    if relative_path.exists():
        return str(relative_path)
    # Fallback to absolute path (for development)
    absolute_path = Path("/Users/jon/Documents/badjatia_hu/visualizer_nlp_lit_review/RIS_source_files/manual_groupings")
    if absolute_path.exists():
        return str(absolute_path)
    # Return relative path anyway (will be created if needed)
    return str(relative_path)


def get_endnote_data_path():
    """Get Endnote data folder path (portable)"""
    base_path = get_base_path()
    # Try relative path first (for bundled app)
    relative_path = base_path / "data" / "Endnote" / "from_zotero_v3.Data"
    if relative_path.exists():
        return str(relative_path)
    # Fallback to absolute path (for development)
    absolute_path = Path("/Users/jon/Documents/badjatia_hu/Endnote/from_zotero_v3.Data")
    if absolute_path.exists():
        return str(absolute_path)
    # Return relative path anyway (will be created if needed)
    return str(relative_path)


def get_all_endnote_data_paths():
    """
    Get all Endnote data folder paths where PDFs might be located.
    Returns a list of paths to search for PDFs.
    """
    base_path = get_base_path()
    paths = []
    
    # Development paths (absolute)
    dev_paths = [
        Path("/Users/jon/Documents/badjatia_hu/Endnote/from_zotero_v3.Data/PDF"),
        Path("/Users/jon/Documents/badjatia_hu/Endnote/from_zotero_v3.Data"),
        Path("/Users/jon/Documents/badjatia_hu/Endnote/NLP_v4.Data"),
        Path("/Users/jon/Documents/badjatia_hu/Endnote/search_term_results"),
    ]
    
    # Bundled app paths (relative)
    bundled_paths = [
        base_path / "data" / "Endnote" / "from_zotero_v3.Data" / "PDF",
        base_path / "data" / "Endnote" / "from_zotero_v3.Data",
        base_path / "data" / "Endnote" / "NLP_v4.Data",
        base_path / "data" / "Endnote" / "search_term_results",
    ]
    
    # Add paths that exist
    for path_list in [dev_paths, bundled_paths]:
        for path in path_list:
            if path.exists() and str(path) not in paths:
                paths.append(str(path))
    
    # If no paths found, return at least the default
    if not paths:
        paths.append(get_endnote_data_path())
    
    return paths


# Path to RIS source files folder (portable)
RIS_SOURCE_FOLDER = get_ris_source_folder()
MANUAL_GROUPINGS_FOLDER = get_manual_groupings_folder()

def find_newest_manual_grouping_file() -> Optional[str]:
    """
    Find the most recently modified most_cited file in manual_groupings folder
    
    Returns:
        Full path to the newest most_cited*.txt file, or None if not found
    """
    manual_folder = Path(MANUAL_GROUPINGS_FOLDER)
    if not manual_folder.exists():
        return None
    
    # Find all files starting with "most_cited" and ending with .txt
    matching_files = []
    for file in manual_folder.glob("most_cited*.txt"):
        if file.is_file():
            matching_files.append(file)
    
    if not matching_files:
        return None
    
    # Return the most recently modified file
    newest_file = max(matching_files, key=lambda f: f.stat().st_mtime)
    return str(newest_file.absolute())

def find_newest_most_relevant_file() -> Optional[str]:
    """
    Find the most recently modified most_relevant file in manual_groupings folder
    
    Returns:
        Full path to the newest most_relevant*.txt file, or None if not found
    """
    manual_folder = Path(MANUAL_GROUPINGS_FOLDER)
    if not manual_folder.exists():
        return None
    
    # Find all files starting with "most_relevant" and ending with .txt
    matching_files = []
    for file in manual_folder.glob("most_relevant*.txt"):
        if file.is_file():
            matching_files.append(file)
    
    if not matching_files:
        return None
    
    # Return the most recently modified file
    newest_file = max(matching_files, key=lambda f: f.stat().st_mtime)
    return str(newest_file.absolute())

def find_newest_ris_file_by_prefix(prefix: str) -> str:
    """
    Find the most recently modified RIS file with the given prefix in RIS_source_files folder
    
    Args:
        prefix: File prefix to search for (e.g., "pubmed", "arxiv")
        
    Returns:
        Full path to the newest file, or None if not found
    """
    source_folder = Path(RIS_SOURCE_FOLDER)
    if not source_folder.exists():
        return None
    
    # Find all files starting with prefix and ending with .txt
    matching_files = []
    for file in source_folder.glob(f"{prefix}*.txt"):
        if file.is_file():
            matching_files.append(file)
    
    if not matching_files:
        return None
    
    # Return the most recently modified file
    newest_file = max(matching_files, key=lambda f: f.stat().st_mtime)
    return str(newest_file.absolute())

# Dictionary mapping query names to their query strings and RIS file prefixes
# The ris_file will be automatically resolved to the newest file with that prefix
# Each query can have multiple branch terms stored in the RN field of the RIS file
COMMON_SEARCH_TERMS = {
    "NLP_Extraction": {
        "query": '''("Large Language Models"[Title/Abstract] OR "LLMs"[Title/Abstract] OR "Large Language Model"[Title/Abstract] OR "LLM"[Title/Abstract] OR "Natural Language Processing"[Title/Abstract] OR "NLP"[Title/Abstract]) AND ("Extraction"[Title/Abstract] OR "Mining"[Title/Abstract] OR "Structuring"[Title/Abstract] OR "Identification"[Title/Abstract] OR "Phenotyping"[Title/Abstract] OR "Labeling"[Title/Abstract] OR "Scoring"[Title/Abstract])''',
        "prefix": "pubmed"  # Will auto-find newest pubmed*.txt file
    }
    # Add more queries here:
    # "Query2_Name": {
    #     "query": '''("Your query string here")''',
    #     "prefix": "arxiv"  # Will auto-find newest arxiv*.txt file
    # }
}

def get_queries_with_ris_files():
    """
    Resolve RIS file paths for all queries based on their prefixes
    Returns queries dict with ris_file paths populated
    """
    resolved_queries = {}
    for query_name, query_info in COMMON_SEARCH_TERMS.items():
        resolved_info = query_info.copy()
        
        # If prefix is specified, find the newest file
        if "prefix" in query_info:
            prefix = query_info["prefix"]
            ris_file = find_newest_ris_file_by_prefix(prefix)
            if ris_file:
                resolved_info["ris_file"] = ris_file
                resolved_info.pop("prefix", None)  # Remove prefix, keep ris_file
            else:
                print(f"Warning: No RIS file found with prefix '{prefix}' for query '{query_name}'")
        # If ris_file is already specified, keep it
        elif "ris_file" in query_info:
            pass  # Already has ris_file, keep it
        
        resolved_queries[query_name] = resolved_info
    
    return resolved_queries

# Endnote library data folder path (portable)
ENDNOTE_DATA_PATH = get_endnote_data_path()
# All Endnote data folder paths for PDF search (portable)
ENDNOTE_DATA_PATHS = get_all_endnote_data_paths()

# OneDrive configuration
ONEDRIVE_BASE_URL = "https://somumaryland-my.sharepoint.com/:f:/g/personal/jonathan_mirsky_som_umaryland_edu/IgCwkAVnmvluQpWftpTullncAexB3IxNsGS4gMZFr7jbAB8?e=PtZ3AW"

def get_onedrive_file_url(relative_path: str) -> str:
    """
    Construct OneDrive download URL for a file.
    
    Args:
        relative_path: Relative path from OneDrive base folder (e.g., "full_text_files/NLP_v4.Data/PDF/0352406214/filename.pdf")
        
    Returns:
        Direct download URL for the file
    """
    from urllib.parse import quote
    
    # For SharePoint/OneDrive for Business share links, the format is:
    # https://[tenant]-my.sharepoint.com/:f:/g/personal/[user]/[folder_id]?e=[token]
    # To access a file within the folder:
    # https://[tenant]-my.sharepoint.com/:f:/g/personal/[user]/[folder_id]/[file_path]?download=1
    
    # Extract base URL and folder ID
    base_url = ONEDRIVE_BASE_URL.split('?')[0]
    
    # URL encode each path component separately (preserve slashes)
    # SharePoint expects path segments to be URL-encoded
    encoded_path = '/'.join(quote(part, safe='') for part in relative_path.split('/'))
    
    # Construct the download URL by appending the file path to the folder ID
    # Format: base_url/file_path?download=1
    file_url = f"{base_url}/{encoded_path}?download=1"
    
    return file_url
