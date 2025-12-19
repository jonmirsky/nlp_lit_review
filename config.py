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
    
    # Try paths in order of likelihood:
    # 1. Current working directory (for Render/web deployment)
    cwd_path = Path.cwd() / "RIS_source_files"
    if cwd_path.exists():
        return str(cwd_path)
    
    # 2. Same directory as script/app (for Render/web deployment)
    script_path = base_path / "RIS_source_files"
    if script_path.exists():
        return str(script_path)
    
    # 3. Relative path for bundled app
    relative_path = base_path / "data" / "RIS_source_files"
    if relative_path.exists():
        return str(relative_path)
    
    # 4. Fallback to absolute path (for development)
    absolute_path = Path("/Users/jon/Documents/badjatia_hu/visualizer_nlp_lit_review/RIS_source_files")
    if absolute_path.exists():
        return str(absolute_path)
    
    # Return script path as default (will help with error messages)
    return str(script_path)


def get_manual_groupings_folder():
    """Get manual groupings folder path (portable)"""
    base_path = get_base_path()
    
    # Try paths in order of likelihood:
    # 1. Current working directory (for Render/web deployment)
    cwd_path = Path.cwd() / "RIS_source_files" / "manual_groupings"
    if cwd_path.exists():
        return str(cwd_path)
    
    # 2. Same directory as script/app (for Render/web deployment)
    script_path = base_path / "RIS_source_files" / "manual_groupings"
    if script_path.exists():
        return str(script_path)
    
    # 3. Relative path for bundled app
    relative_path = base_path / "data" / "RIS_source_files" / "manual_groupings"
    if relative_path.exists():
        return str(relative_path)
    
    # 4. Fallback to absolute path (for development)
    absolute_path = Path("/Users/jon/Documents/badjatia_hu/visualizer_nlp_lit_review/RIS_source_files/manual_groupings")
    if absolute_path.exists():
        return str(absolute_path)
    
    # Return script path as default
    return str(script_path)


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

# Cloudflare R2 configuration for PDFs
# PDFs are stored in R2 bucket with public access
R2_BUCKET_NAME = "nlp-lit-review-pdfs"
R2_PUBLIC_URL_BASE = "https://pub-d9c17dcc87a846d9ba3abbbbc811018d.r2.dev"

def sanitize_filename_for_r2(filename: str) -> str:
    """
    Make filename URL-safe (must match the upload script logic).
    
    Args:
        filename: Original filename (e.g., "Deep Learning for NLP.pdf")
        
    Returns:
        URL-safe filename (e.g., "Deep_Learning_for_NLP.pdf")
    """
    import re
    from pathlib import Path
    
    # Remove extension, sanitize, re-add extension
    name = Path(filename).stem
    ext = Path(filename).suffix
    # Replace special chars with underscore
    safe = re.sub(r'[^\w\-]', '_', name)
    # Collapse multiple underscores
    safe = re.sub(r'_+', '_', safe)
    # Trim underscores from ends
    safe = safe.strip('_')
    # Limit length to avoid issues
    if len(safe) > 100:
        safe = safe[:100]
    return f"{safe}{ext}"


def get_r2_pdf_url(source_prefix: str, folder_id: str, filename: str) -> str:
    """
    Construct Cloudflare R2 public URL for a PDF.
    
    Args:
        source_prefix: Source folder prefix (e.g., "NLP_v4" or "zotero_v3")
        folder_id: The numeric folder ID from internal-pdf:// path
        filename: Original PDF filename
        
    Returns:
        Cloudflare R2 public URL
    """
    import json
    # #region agent log
    with open('/Users/jon/Documents/badjatia_hu/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"config.py:get_r2_pdf_url","message":"Function entry","data":{"source_prefix":source_prefix,"folder_id":folder_id,"filename":filename},"timestamp":__import__('time').time()*1000})+"\n")
    # #endregion
    safe_filename = sanitize_filename_for_r2(filename)
    full_filename = f"{source_prefix}_{folder_id}_{safe_filename}"
    url = f"{R2_PUBLIC_URL_BASE}/{R2_BUCKET_NAME}/{full_filename}"
    # #region agent log
    with open('/Users/jon/Documents/badjatia_hu/.cursor/debug.log', 'a') as f:
        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"config.py:get_r2_pdf_url","message":"URL constructed","data":{"safe_filename":safe_filename,"full_filename":full_filename,"url":url,"bucket_name":R2_BUCKET_NAME},"timestamp":__import__('time').time()*1000})+"\n")
    # #endregion
    return url
