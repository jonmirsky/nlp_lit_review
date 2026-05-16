#!/usr/bin/env python3
"""
Generate report of papers in RIS file that don't have RN (Research Notes) fields.

This script identifies unmatched papers and reports which identifiers they have
(AN/PMID, DO/DOI, TI/Title) to help diagnose why they weren't matched.
"""

import csv
import re
from pathlib import Path
from collections import defaultdict


def parse_ris_entry(entry: str) -> dict:
    """
    Parse a RIS entry and extract relevant fields.
    
    Returns:
        Dictionary with extracted fields
    """
    result = {
        'has_rn': False,
        'id': None,
        'year': None,
        'has_an': False,
        'an_value': None,
        'has_doi': False,
        'doi_value': None,
        'has_title': False,
        'title_value': None,
    }
    
    lines = entry.split('\n')
    current_field = None
    
    for line in lines:
        line_stripped = line.rstrip()
        
        # Check if line starts with a RIS tag
        if re.match(r'^[A-Z]{2}\s+-', line_stripped):
            tag = line_stripped[0:2]
            value = line_stripped[6:].strip()
            
            if tag == 'RN':
                result['has_rn'] = True
                current_field = None
            elif tag == 'ID':
                result['id'] = value
                current_field = None
            elif tag == 'PY':
                result['year'] = value
                current_field = None
            elif tag == 'AN':
                result['has_an'] = True
                result['an_value'] = value
                current_field = None
            elif tag == 'DO':
                result['has_doi'] = True
                result['doi_value'] = value
                current_field = None
            elif tag == 'TI':
                result['has_title'] = True
                result['title_value'] = value
                current_field = 'TI'
            else:
                current_field = None
        else:
            # Continuation of previous field
            if current_field == 'TI' and result['title_value'] is not None:
                result['title_value'] += ' ' + line_stripped.strip()
            current_field = None
    
    return result


def analyze_ris_file(ris_path: Path) -> tuple:
    """
    Analyze RIS file and identify unmatched papers.
    
    Returns:
        Tuple of (unmatched_papers list, statistics dict)
    """
    with open(ris_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split entries by ER  -
    entries = re.split(r'^ER\s+-', content, flags=re.MULTILINE)
    
    unmatched = []
    stats = defaultdict(int)
    
    for entry in entries[1:]:  # Skip first empty split
        parsed = parse_ris_entry(entry)
        
        if not parsed['has_rn']:
            unmatched.append(parsed)
            
            # Count field presence
            field_count = sum([
                parsed['has_an'],
                parsed['has_doi'],
                parsed['has_title']
            ])
            
            stats['total_unmatched'] += 1
            if parsed['has_an']:
                stats['with_an'] += 1
            if parsed['has_doi']:
                stats['with_doi'] += 1
            if parsed['has_title']:
                stats['with_title'] += 1
            if field_count == 0:
                stats['no_fields'] += 1
            elif field_count == 1:
                stats['one_field'] += 1
            elif field_count == 2:
                stats['two_fields'] += 1
            else:
                stats['all_fields'] += 1
    
    return unmatched, stats


def generate_report(unmatched: list, stats: dict, output_path: Path):
    """Generate CSV report of unmatched papers."""
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow([
            'Record ID',
            'Year',
            'Has AN/PMID',
            'AN/PMID Value',
            'Has DOI',
            'DOI Value',
            'Has Title',
            'Title (first 100 chars)',
            'All Fields Missing'
        ])
        
        # Write data rows
        for paper in unmatched:
            all_missing = not (paper['has_an'] or paper['has_doi'] or paper['has_title'])
            
            # Truncate long values for readability
            doi_display = paper['doi_value'][:50] + '...' if paper['doi_value'] and len(paper['doi_value']) > 50 else paper['doi_value']
            title_display = paper['title_value'][:100] + '...' if paper['title_value'] and len(paper['title_value']) > 100 else paper['title_value']
            
            writer.writerow([
                paper['id'] or 'N/A',
                paper['year'] or 'N/A',
                'Yes' if paper['has_an'] else 'No',
                paper['an_value'] or '',
                'Yes' if paper['has_doi'] else 'No',
                doi_display or '',
                'Yes' if paper['has_title'] else 'No',
                title_display or '',
                'Yes' if all_missing else 'No'
            ])


def main():
    """Main function."""
    base_dir = Path(__file__).parent
    ris_file = base_dir.parent / "visualizer_nlp_lit_review" / "pubmed_endnote_12_14_25_1043pm_with_rn.txt"
    output_file = base_dir / "unmatched_papers_report.csv"
    
    if not ris_file.exists():
        print(f"ERROR: RIS file not found: {ris_file}")
        return
    
    print(f"Analyzing RIS file: {ris_file.name}")
    unmatched, stats = analyze_ris_file(ris_file)
    
    print(f"\n=== Statistics ===")
    print(f"Total unmatched papers: {stats['total_unmatched']}")
    print(f"\nField presence:")
    print(f"  Papers with AN/PMID field: {stats['with_an']}")
    print(f"  Papers with DOI field: {stats['with_doi']}")
    print(f"  Papers with Title field: {stats['with_title']}")
    print(f"\nField combination counts:")
    print(f"  Papers with all 3 fields: {stats['all_fields']}")
    print(f"  Papers with 2 fields: {stats['two_fields']}")
    print(f"  Papers with 1 field: {stats['one_field']}")
    print(f"  Papers with no matching fields: {stats['no_fields']}")
    
    # Generate CSV report
    print(f"\nGenerating report...")
    generate_report(unmatched, stats, output_file)
    
    print(f"\nReport saved to: {output_file}")
    print(f"\nFirst 5 unmatched papers:")
    for i, paper in enumerate(unmatched[:5], 1):
        print(f"\n{i}. Record ID: {paper['id'] or 'N/A'}")
        print(f"   Year: {paper['year'] or 'N/A'}")
        print(f"   AN/PMID: {'Yes' if paper['has_an'] else 'No'} - {paper['an_value'] or 'N/A'}")
        print(f"   DOI: {'Yes' if paper['has_doi'] else 'No'} - {paper['doi_value'][:50] if paper['doi_value'] else 'N/A'}")
        print(f"   Title: {'Yes' if paper['has_title'] else 'No'} - {paper['title_value'][:80] if paper['title_value'] else 'N/A'}...")


if __name__ == "__main__":
    main()
