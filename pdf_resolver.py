"""
PDF path resolver for Literature Review Visualizer
Resolves internal-pdf:// paths to actual file system paths
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, List
from config import ENDNOTE_DATA_PATHS, get_onedrive_file_url


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
            possible_paths = [
                endnote_path / pdf_id / filename,
                endnote_path / f"{pdf_id}.pdf",
                endnote_path / filename,
            ]
            
            # Also check subdirectories
            for item in endnote_path.iterdir():
                if item.is_dir():
                    possible_paths.extend([
                        item / filename,
                        item / f"{pdf_id}.pdf",
                    ])
            
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
    
    def resolve_to_onedrive_url(self, internal_path: str) -> Optional[str]:
        """
        Resolve internal-pdf:// path to OneDrive URL
        
        Args:
            internal_path: Path in format internal-pdf://[id]/[filename].pdf
            
        Returns:
            OneDrive download URL if path can be constructed, None otherwise
        """
        if not internal_path:
            return None
        
        # Parse internal-pdf:// format
        match = re.match(r'internal-pdf://(\d+)/(.+)', internal_path)
        if not match:
            return None
        
        pdf_id = match.group(1)
        filename = match.group(2)
        
        # The OneDrive share link points to the "full_text_files" folder
        # So paths should be relative to that folder (don't include "full_text_files" prefix)
        # Try NLP_v4.Data first (based on analysis showing 98 unique PDFs there)
        # Then fallback to from_zotero_v3.Data
        possible_paths = [
            f"NLP_v4.Data/PDF/{pdf_id}/{filename}",
            f"from_zotero_v3.Data/PDF/{pdf_id}/{filename}",
            # Also try without PDF subfolder (in case structure differs)
            f"NLP_v4.Data/{pdf_id}/{filename}",
            f"from_zotero_v3.Data/{pdf_id}/{filename}",
        ]
        
        # Return the first constructed URL (we'll let OneDrive return 404 if wrong)
        # In practice, we could try each, but for now return the most likely
        return get_onedrive_file_url(possible_paths[0])




