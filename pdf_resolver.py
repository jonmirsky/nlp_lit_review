"""
PDF path resolver for Literature Review Visualizer
Resolves internal-pdf:// paths to actual file system paths
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, List
from config import ENDNOTE_DATA_PATHS, get_r2_pdf_url, R2_BUCKET_NAME


class PDFResolver:
    """Resolves internal-pdf:// paths to actual file paths"""
    
    def __init__(self, endnote_data_paths: List[str] = None):
        if endnote_data_paths is None:
            endnote_data_paths = ENDNOTE_DATA_PATHS
        self.endnote_data_paths = [Path(p) for p in endnote_data_paths]
        self._cache: Dict[str, Optional[str]] = {}
        self._filename_cache: Dict[str, Optional[str]] = {}
        
    def resolve(self, internal_path: str) -> Optional[str]:
        """
        Resolve internal-pdf:// path to actual file path
        
        Args:
            internal_path: Path in format internal-pdf://[id]/[filename].pdf
            
        Returns:
            Actual file path if found, None otherwise
        """
        if not internal_path:
            return None
        
        # Check cache first
        if internal_path in self._cache:
            return self._cache[internal_path]
        
        # Parse internal-pdf:// format
        match = re.match(r'internal-pdf://(\d+)/(.+)', internal_path)
        if not match:
            # Not in expected format, try to find by filename
            return self._find_by_filename(internal_path)
        
        pdf_id = match.group(1)
        filename = match.group(2)
        
        # Search in all Endnote data paths
        for endnote_path in self.endnote_data_paths:
            if not endnote_path.exists():
                continue
                
            # Strategy 1: Look by ID and filename
            # Note: We check the ID folder directly (primary location matching internal-pdf:// format)
            # Removed expensive iterdir() loop that was iterating through 3,545+ folders
            # Removed endnote_path / filename check - unlikely to find files in root PDF dir (3,544 folders)
            possible_paths = [
                endnote_path / pdf_id / filename,
                endnote_path / f"{pdf_id}.pdf",
            ]
            
            # Try each possible path
            for path in possible_paths:
                if path.exists() and path.is_file():
                    resolved = str(path.absolute())
                    self._cache[internal_path] = resolved
                    return resolved
        
        # Strategy 2: Search by filename in all data folders
        resolved = self._find_by_filename(filename)
        if resolved:
            self._cache[internal_path] = resolved
            return resolved
        
        # Not found
        self._cache[internal_path] = None
        return None
    
    def _find_by_filename(self, filename: str) -> Optional[str]:
        """Search for PDF by filename in all Endnote data folders"""
        if filename in self._filename_cache:
            return self._filename_cache[filename]
        
        # Clean filename for comparison
        clean_filename = filename.lower().strip()
        
        # Search recursively in all Endnote data paths
        for endnote_path in self.endnote_data_paths:
            if not endnote_path.exists():
                continue
                
            for root, dirs, files in os.walk(endnote_path):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        # Check if filename matches (case-insensitive, partial match)
                        if clean_filename in file.lower() or file.lower() in clean_filename:
                            resolved = str(Path(root) / file)
                            self._filename_cache[filename] = resolved
                            return resolved
        
        self._filename_cache[filename] = None
        return None
    
    def is_pdf_available(self, internal_path: str) -> bool:
        """Check if PDF is available (without resolving full path)"""
        resolved = self.resolve(internal_path)
        return resolved is not None and Path(resolved).exists()
    
    def resolve_to_r2_url(self, internal_path: str) -> Optional[str]:
        """
        Resolve internal-pdf:// path to Cloudflare R2 URL.
        
        Args:
            internal_path: Path in format internal-pdf://[id]/[filename].pdf
            
        Returns:
            Cloudflare R2 public URL if path can be constructed, None otherwise
        """
        if not internal_path or not R2_BUCKET_NAME:
            return None
        
        # Parse internal-pdf:// format
        match = re.match(r'internal-pdf://(\d+)/(.+)', internal_path)
        if not match:
            return None
        
        folder_id = match.group(1)
        filename = match.group(2)
        
        # Try NLP_v4 first (all R2 files use NLP_v4 prefix), then zotero_v3 as fallback
        # The prefixes must match what the upload script uses
        # Note: After consolidation, local PDFs are in from_zotero_v3.Data, but R2 files still use NLP_v4 prefix
        prefixes = ['NLP_v4', 'zotero_v3']
        
        # Return the first URL - the caller will check if it works
        # NLP_v4 is tried first since all files in R2 use that prefix
        return get_r2_pdf_url(prefixes[0], folder_id, filename)
    
    def get_all_r2_urls(self, internal_path: str) -> List[str]:
        """
        Get all possible Cloudflare R2 URLs for a PDF.
        
        Args:
            internal_path: Path in format internal-pdf://[id]/[filename].pdf
            
        Returns:
            List of possible R2 URLs to try
        """
        print(f"[PDF RESOLVER] get_all_r2_urls called with: internal_path={internal_path}, R2_BUCKET_NAME={R2_BUCKET_NAME}")
        if not internal_path or not R2_BUCKET_NAME:
            print(f"[PDF RESOLVER] Early return: internal_path={internal_path}, R2_BUCKET_NAME={R2_BUCKET_NAME}")
            return []
        
        # Parse internal-pdf:// format
        match = re.match(r'internal-pdf://(\d+)/(.+)', internal_path)
        if not match:
            print(f"[PDF RESOLVER] Failed to parse internal_path: {internal_path}")
            return []
        
        folder_id = match.group(1)
        filename = match.group(2)
        print(f"[PDF RESOLVER] Parsed: folder_id={folder_id}, filename={filename}")
        
        # Return URLs for both possible prefixes
        # NLP_v4 tried first (all R2 files use NLP_v4 prefix), zotero_v3 as fallback
        prefixes = ['NLP_v4', 'zotero_v3']
        urls = [get_r2_pdf_url(prefix, folder_id, filename) for prefix in prefixes]
        print(f"[PDF RESOLVER] Generated URLs: {urls}")
        return urls











