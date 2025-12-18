"""
RIS file parser for Literature Review Visualizer
Parses RIS format files and extracts paper metadata
"""

import re
from typing import List, Dict, Optional
from pathlib import Path


class Paper:
    """Represents a single paper from RIS file"""
    
    def __init__(self):
        self.id = None
        self.title = ""
        self.year = None
        self.abstract = ""
        self.authors = []
        self.doi = ""
        self.unique_search_terms = []  # From N1 field, comma-separated
        self.branch_terms = []  # From RN field, comma-separated (e.g., "radiology, neuroscience")
        self.pdf_path = ""  # From L1 field
        self.database = ""
        self.journal = ""
        self.volume = ""
        self.issue = ""
        self.pages = ""
        self.url = ""
        self.keywords = []
        
    def to_dict(self):
        """Convert paper to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "year": self.year,
            "abstract": self.abstract,
            "authors": self.authors,
            "doi": self.doi,
            "unique_search_terms": self.unique_search_terms,
            "branch_terms": self.branch_terms,
            "pdf_path": self.pdf_path,
            "database": self.database,
            "journal": self.journal,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "url": self.url,
            "keywords": self.keywords
        }


class RISParser:
    """Parser for RIS format files"""
    
    def __init__(self, ris_file_path: str):
        self.ris_file_path = Path(ris_file_path)
        self.database = self._extract_database_from_filename()
        
    def _extract_database_from_filename(self) -> str:
        """Extract database name from filename (first word before underscore)"""
        filename = self.ris_file_path.stem
        # Split by underscore and take first part
        parts = filename.split('_')
        return parts[0] if parts else "unknown"
    
    def parse(self) -> List[Paper]:
        """Parse RIS file and return list of Paper objects"""
        papers = []
        id_counter = 1  # Fallback ID counter
        
        with open(self.ris_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Split by record terminator (ER  - with spaces and dash)
        records = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
        
        for record in records:
            if not record.strip():
                continue
                
            paper = self._parse_record(record)
            if paper and paper.title:  # Only add papers with titles
                paper.database = self.database
                # Ensure paper has an ID
                if not paper.id:
                    paper.id = f"paper_{id_counter}"
                    id_counter += 1
                papers.append(paper)
        
        return papers
    
    def _parse_record(self, record: str) -> Optional[Paper]:
        """Parse a single RIS record"""
        paper = Paper()
        
        # Split into lines
        lines = record.strip().split('\n')
        current_field = None
        current_value = []
        
        for line in lines:
            line = line.rstrip()
            if not line:
                continue
            
            # Check if line starts with a field tag (2-3 letters, space, dash)
            match = re.match(r'^([A-Z0-9]{2,3})\s+-\s+(.+)$', line)
            if match:
                # Save previous field
                if current_field:
                    self._set_field(paper, current_field, '\n'.join(current_value))
                
                # Start new field
                current_field = match.group(1)
                current_value = [match.group(2)]
            else:
                # Continuation of previous field
                if current_field:
                    current_value.append(line)
        
        # Save last field
        if current_field:
            self._set_field(paper, current_field, '\n'.join(current_value))
        
        return paper
    
    def _set_field(self, paper: Paper, field_tag: str, value: str):
        """Set paper field based on RIS field tag"""
        value = value.strip()
        
        if field_tag == 'TI':
            paper.title = value
        elif field_tag == 'PY':
            # Extract year (first 4 digits)
            year_match = re.search(r'\d{4}', value)
            if year_match:
                paper.year = int(year_match.group())
        elif field_tag == 'AB':
            paper.abstract = value
        elif field_tag == 'AU':
            paper.authors.append(value)
        elif field_tag == 'DO':
            paper.doi = value
        elif field_tag == 'N1':
            # Extract unique search terms (comma-separated)
            # Remove any non-search-term content
            terms = [t.strip() for t in value.split(',') if t.strip()]
            paper.unique_search_terms = terms
        elif field_tag == 'RN':
            # Extract branch terms (comma-separated from Research Notes field)
            # These are the unique terms that branch from each query (e.g., "radiology", "neuroscience")
            # Clean value to remove any accidental content from record splitting issues
            clean_value = value.strip()
            # Remove any "ER" that might have been accidentally included
            if clean_value.endswith('ER'):
                clean_value = clean_value[:-2].strip()
            terms = [t.strip() for t in clean_value.split(',') if t.strip()]
            paper.branch_terms = terms
        elif field_tag == 'L1':
            paper.pdf_path = value
        elif field_tag == 'T2':
            paper.journal = value
        elif field_tag == 'VL':
            paper.volume = value
        elif field_tag == 'IS':
            paper.issue = value
        elif field_tag == 'SP':
            paper.pages = value
        elif field_tag == 'UR':
            paper.url = value
        elif field_tag == 'KW':
            paper.keywords.append(value)
        elif field_tag == 'ID':
            # Use ID as paper ID
            try:
                paper.id = int(value)
            except ValueError:
                paper.id = value
        elif field_tag == 'LB':
            # Alternative ID field
            if not paper.id:
                try:
                    paper.id = int(value)
                except ValueError:
                    paper.id = value




