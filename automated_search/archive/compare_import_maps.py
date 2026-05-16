#!/usr/bin/env python3
"""
Compare two import map files and create a comparison table showing:
- Papers unique to first file
- Papers in both files
- Papers unique to second file

Includes: titles, record numbers, journals, URLs, DOIs
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


def parse_ris_file(ris_file_path: Path) -> Dict[str, Dict]:
    """
    Parse RIS file and return list of references with metadata.
    Returns: List of {title, journal, doi, url, authors, ...}
    """
    references = []
    
    if not ris_file_path.exists():
        print(f"WARNING: RIS file not found: {ris_file_path}")
        return {}
    
    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        ref = {
            'record_number': None,
            'title': '',
            'journal': '',
            'doi': '',
            'url': '',
            'authors': []
        }
        
        lines = entry.split('\n')
        current_field = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if re.match(r'^[A-Z]{2}\s+-\s', line):
                tag = line[0:2]
                value = line[6:].strip()
                
                if tag == 'ID':
                    ref['record_number'] = value
                elif tag == 'TI':
                    ref['title'] = value
                elif tag == 'T2':
                    ref['journal'] = value
                elif tag == 'DO':
                    ref['doi'] = value
                elif tag == 'UR':
                    ref['url'] = value
                elif tag == 'AU':
                    ref['authors'].append(value)
                
                current_field = tag
            else:
                # Continuation of previous field
                if current_field == 'TI' and line:
                    ref['title'] += ' ' + line
                elif current_field == 'T2' and line:
                    ref['journal'] += ' ' + line
        
        # Add reference if it has at least a title
        if ref['title']:
            references.append(ref)
    
    return references


def read_import_map(import_map_path: Path) -> Dict[str, str]:
    """
    Read import map file and return dictionary mapping record numbers to PDF paths.
    """
    import_map = {}
    
    if not import_map_path.exists():
        print(f"ERROR: Import map file not found: {import_map_path}")
        return import_map
    
    with open(import_map_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split('\t')
            if len(parts) >= 2:
                record_number = parts[0].strip()
                pdf_path = parts[1].strip()
                import_map[record_number] = pdf_path
    
    return import_map


def find_ris_file_for_import_map(import_map_path: Path, base_dir: Path) -> Optional[Path]:
    """
    Try to find the corresponding RIS file for an import map.
    Looks in common locations.
    """
    # Try to infer RIS file location from import map name
    map_name = import_map_path.stem
    
    # Common locations to search
    search_locations = [
        base_dir / "found_papers" / "RIS_files",
        base_dir / "missing_papers" / "still_missing",
        # Endnote folder is now in OneDrive
        Path("/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/search_term_results"),
    ]
    
    # Also try to find RIS files in parent directories
    for location in search_locations:
        if location.exists():
            for ris_file in location.rglob("*.ris"):
                # Check if filename suggests it might match
                if "full_text" in map_name.lower() or "v3" in map_name.lower():
                    if "full_text" in ris_file.name.lower() or "v3" in ris_file.name.lower():
                        return ris_file
                elif "pubmed_CT_extraction" in map_name.lower():
                    if "pubmed_CT_extraction" in ris_file.name.lower():
                        return ris_file
    
    return None


def normalize_doi(doi: str) -> str:
    """Normalize DOI for comparison."""
    if not doi:
        return ""
    # Remove http://dx.doi.org/, https://doi.org/, doi: prefixes
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
    return doi.strip().lower()


def normalize_title(title: str) -> str:
    """Normalize title for comparison."""
    if not title:
        return ""
    # Remove extra whitespace, convert to lowercase, remove punctuation
    title = re.sub(r'\s+', ' ', title)
    title = title.lower()
    title = re.sub(r'[^\w\s]', '', title)
    return title.strip()


def match_references(ref1: Dict, ref2: Dict) -> bool:
    """
    Check if two references match based on DOI or normalized title.
    """
    # Try DOI first (most reliable)
    if ref1.get('doi') and ref2.get('doi'):
        if normalize_doi(ref1['doi']) == normalize_doi(ref2['doi']):
            return True
    
    # Try normalized title
    if ref1.get('title') and ref2.get('title'):
        if normalize_title(ref1['title']) == normalize_title(ref2['title']):
            return True
    
    return False


def main():
    base_dir = Path(__file__).parent
    
    # Import map files
    map1_path = base_dir / "found_papers" / "import_IDs" / "import_25_of_111_of_111_full_text_v3.txt"
    map2_path = base_dir / "found_papers" / "import_IDs" / "import_62_of_111_of_111_pubmed_CT_extraction_12_15_1220pm.txt"
    
    print("="*70)
    print("COMPARING IMPORT MAP FILES")
    print("="*70)
    print()
    
    # Read import maps
    print("Reading import maps...")
    map1 = read_import_map(map1_path)
    map2 = read_import_map(map2_path)
    
    print(f"  Map 1 ({map1_path.name}): {len(map1)} entries")
    print(f"  Map 2 ({map2_path.name}): {len(map2)} entries")
    print()
    
    # Find RIS files
    print("Finding RIS files...")
    ris1_path = find_ris_file_for_import_map(map1_path, base_dir)
    ris2_path = find_ris_file_for_import_map(map2_path, base_dir)
    
    # For map2, we know it's in the EndNote folder - now in OneDrive
    if not ris2_path:
        ris2_path = Path("/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/search_term_results/pubmed_CT_extraction_12_15_1220pm/pubmed_CT_extraction_12_15_1220pm.ris")
    
    # For map1, try to find it
    if not ris1_path:
        # Try common locations
        possible_ris1 = [
            base_dir / "found_papers" / "RIS_files" / "1033_papers_ris.txt",
            base_dir / "missing_papers" / "still_missing" / "pubmed_CT_exctraction_12_15_25.txt",
        ]
        for ris in possible_ris1:
            if ris.exists():
                ris1_path = ris
                break
    
    if not ris1_path or not ris1_path.exists():
        print(f"ERROR: Could not find RIS file for map 1")
        print(f"  Please specify the RIS file path manually")
        return
    
    if not ris2_path or not ris2_path.exists():
        print(f"ERROR: Could not find RIS file for map 2")
        print(f"  Please specify the RIS file path manually")
        return
    
    print(f"  RIS 1: {ris1_path.name}")
    print(f"  RIS 2: {ris2_path.name}")
    print()
    
    # Parse RIS files
    print("Parsing RIS files...")
    ris1_refs = parse_ris_file(ris1_path)
    ris2_refs = parse_ris_file(ris2_path)
    
    print(f"  RIS 1: {len(ris1_refs)} references")
    print(f"  RIS 2: {len(ris2_refs)} references")
    print()
    
    # Create lookup dictionaries by DOI and normalized title
    ris1_by_doi = {}
    ris1_by_title = {}
    for ref in ris1_refs:
        if ref.get('doi'):
            ris1_by_doi[normalize_doi(ref['doi'])] = ref
        if ref.get('title'):
            ris1_by_title[normalize_title(ref['title'])] = ref
    
    ris2_by_doi = {}
    ris2_by_title = {}
    for ref in ris2_refs:
        if ref.get('doi'):
            ris2_by_doi[normalize_doi(ref['doi'])] = ref
        if ref.get('title'):
            ris2_by_title[normalize_title(ref['title'])] = ref
    
    # Build lookup dictionary for RIS1 by record number
    ris1_by_record = {}
    for ref in ris1_refs:
        if ref.get('record_number'):
            ris1_by_record[ref['record_number']] = ref
    
    # Get reference data for each import map by matching record numbers to RIS entries
    # For map1: record numbers are from RIS file
    map1_refs = {}
    for record_num in map1.keys():
        # Try to find by record number first
        found = ris1_by_record.get(record_num)
        
        if not found:
            # Create minimal entry
            found = {
                'record_number': record_num,
                'title': 'Not found in RIS',
                'journal': '',
                'doi': '',
                'url': '',
                'authors': []
            }
        else:
            found = found.copy()
            found['record_number'] = record_num  # Ensure record number is set
        
        map1_refs[record_num] = found
    
    # For map2: record numbers are folder numbers, match by L1 field pattern
    # Parse RIS file again to extract L1 fields
    map2_refs = {}
    ris2_with_l1 = []
    
    with open(ris2_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        ref = {
            'record_number': None,
            'title': '',
            'journal': '',
            'doi': '',
            'url': '',
            'authors': [],
            'l1_path': ''
        }
        
        lines = entry.split('\n')
        current_field = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if re.match(r'^[A-Z]{2}\s+-\s', line):
                tag = line[0:2]
                value = line[6:].strip()
                
                if tag == 'TI':
                    ref['title'] = value
                elif tag == 'T2':
                    ref['journal'] = value
                elif tag == 'DO':
                    ref['doi'] = value
                elif tag == 'UR':
                    ref['url'] = value
                elif tag == 'AU':
                    ref['authors'].append(value)
                elif tag == 'L1':
                    ref['l1_path'] = value
                
                current_field = tag
            else:
                if current_field == 'TI' and line:
                    ref['title'] += ' ' + line
                elif current_field == 'T2' and line:
                    ref['journal'] += ' ' + line
        
        if ref['title']:
            ris2_with_l1.append(ref)
    
    # Match map2 record numbers to RIS entries by L1 field
    for record_num in map2.keys():
        found = None
        # Look for L1 field containing files/record_num/
        pattern = rf'files/{record_num}/'
        for ref in ris2_with_l1:
            if pattern in ref.get('l1_path', ''):
                found = ref.copy()
                found['record_number'] = record_num
                break
        
        if not found:
            # Create minimal entry
            found = {
                'record_number': record_num,
                'title': 'Not found in RIS',
                'journal': '',
                'doi': '',
                'url': '',
                'authors': []
            }
        
        map2_refs[record_num] = found
    
    # Match references by DOI or title
    print("Matching references...")
    matched_pairs = []
    map1_matched = set()
    map2_matched = set()
    
    # First, try to get map1 metadata by matching to map2 (since map1 record numbers don't match RIS)
    # We'll match by trying to find the same papers in both maps
    for rec1, ref1 in map1_refs.items():
        best_match = None
        best_rec2 = None
        
        for rec2, ref2 in map2_refs.items():
            if rec2 in map2_matched:
                continue  # Already matched
            
            if match_references(ref1, ref2):
                # Use map2's metadata (which is more complete)
                best_match = ref2.copy()
                best_rec2 = rec2
                break
        
        if best_match:
            matched_pairs.append((rec1, ref1, best_rec2, best_match))
            map1_matched.add(rec1)
            map2_matched.add(best_rec2)
        else:
            # Try to find in RIS1 by DOI or title if we have that info
            # For now, keep ref1 as is
            pass
    
    print(f"  Found {len(matched_pairs)} matching papers")
    print()
    
    # Categorize
    map1_unique = {rec: ref for rec, ref in map1_refs.items() if rec not in map1_matched}
    map2_unique = {rec: ref for rec, ref in map2_refs.items() if rec not in map2_matched}
    
    # Create output file
    output_path = base_dir / "found_papers" / "import_IDs" / "import_map_comparison_table.txt"
    
    print(f"Writing comparison table to: {output_path}")
    print()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("="*200 + "\n")
        f.write("IMPORT MAP COMPARISON TABLE\n")
        f.write("="*200 + "\n\n")
        f.write(f"Map 1: {map1_path.name} ({len(map1)} entries)\n")
        f.write(f"Map 2: {map2_path.name} ({len(map2)} entries)\n")
        f.write(f"Matching papers: {len(matched_pairs)}\n")
        f.write(f"Unique to Map 1: {len(map1_unique)}\n")
        f.write(f"Unique to Map 2: {len(map2_unique)}\n")
        f.write("\n" + "="*200 + "\n\n")
        
        # Write table header
        f.write(f"{'UNIQUE TO MAP 1 (25_of_111)':<80} | {'IN BOTH FILES':<80} | {'UNIQUE TO MAP 2 (62_of_111)':<80}\n")
        f.write("-" * 200 + "\n")
        
        # Determine max rows needed
        max_rows = max(len(map1_unique), len(matched_pairs), len(map2_unique))
        
        # Write rows
        for i in range(max_rows):
            col1 = ""
            col2 = ""
            col3 = ""
            
            # Column 1: Unique to map 1
            if i < len(map1_unique):
                rec, ref = list(map1_unique.items())[i]
                col1 = f"Rec: {rec}\nTitle: {ref['title'][:60]}...\nJournal: {ref['journal'][:40]}\nDOI: {ref['doi']}\nURL: {ref['url'][:50]}"
            
            # Column 2: In both
            if i < len(matched_pairs):
                rec1, ref1, rec2, ref2 = matched_pairs[i]
                col2 = f"Rec1: {rec1} | Rec2: {rec2}\nTitle: {ref1['title'][:60]}...\nJournal: {ref1['journal'][:40]}\nDOI: {ref1['doi']}\nURL: {ref1['url'][:50]}"
            
            # Column 3: Unique to map 2
            if i < len(map2_unique):
                rec, ref = list(map2_unique.items())[i]
                col3 = f"Rec: {rec}\nTitle: {ref['title'][:60]}...\nJournal: {ref['journal'][:40]}\nDOI: {ref['doi']}\nURL: {ref['url'][:50]}"
            
            # Write row
            lines1 = col1.split('\n') if col1 else ['']
            lines2 = col2.split('\n') if col2 else ['']
            lines3 = col3.split('\n') if col3 else ['']
            
            max_lines = max(len(lines1), len(lines2), len(lines3))
            for j in range(max_lines):
                line1 = lines1[j] if j < len(lines1) else ""
                line2 = lines2[j] if j < len(lines2) else ""
                line3 = lines3[j] if j < len(lines3) else ""
                f.write(f"{line1:<80} | {line2:<80} | {line3:<80}\n")
            
            f.write("-" * 200 + "\n")
    
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Papers in common: {len(matched_pairs)}")
    print(f"  Unique to Map 1: {len(map1_unique)}")
    print(f"  Unique to Map 2: {len(map2_unique)}")
    print(f"  Comparison table: {output_path}")
    print("="*70)


if __name__ == '__main__':
    main()















