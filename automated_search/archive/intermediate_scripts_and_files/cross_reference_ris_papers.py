#!/usr/bin/env python3
"""
Cross-reference papers from main RIS file with search term RIS files.

This script parses the main RIS file and cross-references each paper with
7 search term RIS files to identify which papers appear in which search categories.
Generates a CSV file showing the overlap.
"""

import re
import csv
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import defaultdict


def normalize_doi(doi: str) -> str:
    """Normalize DOI for matching: lowercase, remove whitespace."""
    if not doi:
        return ""
    return doi.lower().strip().replace(" ", "")


def normalize_title(title: str) -> str:
    """Normalize title for matching: lowercase, remove extra whitespace, strip punctuation."""
    if not title:
        return ""
    # Convert to lowercase
    title = title.lower()
    # Remove extra whitespace
    title = " ".join(title.split())
    # Remove common punctuation (keep alphanumeric and spaces)
    title = re.sub(r'[^\w\s]', '', title)
    return title.strip()


def parse_ris_file(ris_file_path: Path, extract_lb: bool = False) -> List[Dict[str, str]]:
    """
    Parse RIS file into list of reference dictionaries.
    
    Args:
        ris_file_path: Path to RIS file
        extract_lb: If True, extract LB field (only for main file)
    
    Returns:
        List of dictionaries with keys: 'doi', 'title', and optionally 'lb'
    """
    references = []
    
    if not ris_file_path.exists():
        print(f"ERROR: RIS file not found: {ris_file_path}")
        return references
    
    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split entries by ER  - (end of record)
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        ref = {
            'doi': None,
            'title': None,
        }
        
        if extract_lb:
            ref['lb'] = None
        
        lines = entry.split('\n')
        current_field = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line starts with a RIS tag (2 letters, 2 spaces, hyphen)
            if re.match(r'^[A-Z]{2}\s+-\s', line):
                tag = line[0:2]
                value = line[6:].strip()
                
                if tag == 'DO':
                    ref['doi'] = value
                elif tag == 'TI':
                    ref['title'] = value
                elif tag == 'LB' and extract_lb:
                    ref['lb'] = value
                
                current_field = tag
            else:
                # Continuation of previous field (multi-line)
                if current_field == 'DO' and ref['doi']:
                    ref['doi'] += ' ' + line
                elif current_field == 'TI' and ref['title']:
                    ref['title'] += ' ' + line
                elif current_field == 'LB' and extract_lb and ref.get('lb'):
                    ref['lb'] += ' ' + line
        
        # Only add if we have at least DOI or title
        if ref['doi'] or ref['title']:
            references.append(ref)
    
    return references


def build_search_term_lookups(search_term_files: Dict[str, Path]) -> Dict[str, Dict[str, Set[str]]]:
    """
    Build lookup dictionaries for each search term file.
    
    Args:
        search_term_files: Dictionary mapping category name to RIS file path
    
    Returns:
        Dictionary mapping category name to lookup dict with 'doi' and 'title' sets
    """
    lookups = {}
    
    for category, file_path in search_term_files.items():
        print(f"Parsing {category} search term file: {file_path.name}")
        papers = parse_ris_file(file_path, extract_lb=False)
        
        doi_set = set()
        title_set = set()
        
        for paper in papers:
            if paper['doi']:
                normalized_doi = normalize_doi(paper['doi'])
                if normalized_doi:
                    doi_set.add(normalized_doi)
            
            if paper['title']:
                normalized_title = normalize_title(paper['title'])
                if normalized_title:
                    title_set.add(normalized_title)
        
        lookups[category] = {
            'doi': doi_set,
            'title': title_set
        }
        
        print(f"  Found {len(papers)} papers, {len(doi_set)} unique DOIs, {len(title_set)} unique titles")
    
    return lookups


def match_paper_to_categories(paper: Dict[str, str], lookups: Dict[str, Dict[str, Set[str]]]) -> List[str]:
    """
    Match a paper against all search term categories.
    
    Args:
        paper: Dictionary with 'doi' and 'title'
        lookups: Dictionary of category lookups
    
    Returns:
        List of category names where this paper was found
    """
    matches = []
    
    normalized_doi = normalize_doi(paper.get('doi', ''))
    normalized_title = normalize_title(paper.get('title', ''))
    
    for category, lookup in lookups.items():
        matched = False
        
        # Try DOI match first
        if normalized_doi and normalized_doi in lookup['doi']:
            matched = True
        # Fallback to title match
        elif normalized_title and normalized_title in lookup['title']:
            matched = True
        
        if matched:
            matches.append(category)
    
    return matches


def main():
    """Main function to cross-reference papers and generate CSV."""
    
    # Define file paths
    base_dir = Path(__file__).parent
    main_ris_file = base_dir / "found_papers" / "RIS_files" / "import_to_endnote" / "1033_papers_ris_with_attachments.txt"
    search_term_dir = base_dir.parent / "Endnote" / "search_term_results"
    
    # Define search term files mapping
    search_term_files = {
        'brain': search_term_dir / "pubmed_brain.ris",
        'clinical': search_term_dir / "pubmed_clinical.ris",
        'neurology': search_term_dir / "pubmed_neurology.ris",
        'neuroscience': search_term_dir / "pubmed_neuroscience.ris",
        'pathology': search_term_dir / "pubmed_pathology.ris",
        'radiology': search_term_dir / "pubmed_radiology.ris",
        'stroke': search_term_dir / "pubmed_stroke.ris",
    }
    
    # Verify main file exists
    if not main_ris_file.exists():
        print(f"ERROR: Main RIS file not found: {main_ris_file}")
        return
    
    # Parse main RIS file
    print(f"Parsing main RIS file: {main_ris_file.name}")
    main_papers = parse_ris_file(main_ris_file, extract_lb=True)
    print(f"Found {len(main_papers)} papers in main file")
    
    # Count papers with LB labels
    papers_with_lb = [p for p in main_papers if p.get('lb')]
    print(f"Found {len(papers_with_lb)} papers with LB labels")
    
    if len(papers_with_lb) == 0:
        print("ERROR: No papers with LB labels found in main file!")
        return
    
    # Build lookup dictionaries for search term files
    print("\nBuilding search term lookups...")
    lookups = build_search_term_lookups(search_term_files)
    
    # Match papers to categories
    print("\nMatching papers to search term categories...")
    results = []
    match_stats = defaultdict(int)
    
    for paper in papers_with_lb:
        paper_label = paper.get('lb', '')
        if not paper_label:
            continue
        
        matched_categories = match_paper_to_categories(paper, lookups)
        
        # Create result row
        row = {
            'Paper Label': paper_label,
            'brain': 'x' if 'brain' in matched_categories else '',
            'clinical': 'x' if 'clinical' in matched_categories else '',
            'neurology': 'x' if 'neurology' in matched_categories else '',
            'neuroscience': 'x' if 'neuroscience' in matched_categories else '',
            'pathology': 'x' if 'pathology' in matched_categories else '',
            'radiology': 'x' if 'radiology' in matched_categories else '',
            'stroke': 'x' if 'stroke' in matched_categories else '',
        }
        
        results.append(row)
        
        # Update statistics
        for category in matched_categories:
            match_stats[category] += 1
    
    # Print statistics
    print("\nMatch Statistics:")
    print(f"Total papers processed: {len(results)}")
    for category in ['brain', 'clinical', 'neurology', 'neuroscience', 'pathology', 'radiology', 'stroke']:
        print(f"  {category}: {match_stats[category]} matches")
    
    # Write CSV file
    output_file = main_ris_file.parent / "cross_reference_results.csv"
    print(f"\nWriting results to: {output_file}")
    
    fieldnames = ['Paper Label', 'brain', 'clinical', 'neurology', 'neuroscience', 'pathology', 'radiology', 'stroke']
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Successfully wrote {len(results)} rows to CSV file")


if __name__ == "__main__":
    main()
