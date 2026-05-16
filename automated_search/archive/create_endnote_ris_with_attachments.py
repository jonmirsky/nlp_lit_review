#!/usr/bin/env python3
"""
Create RIS file with PDF file attachments from RIS file and import_map.

This script generates a RIS file that can be directly imported into EndNote,
with PDF files already attached via L1 fields. This avoids the need for manual attachment automation.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional
import html


def map_ris_type_to_endnote(ris_type: str) -> str:
    """
    Map RIS reference type to EndNote type name.
    """
    type_map = {
        'JOUR': 'Journal Article',
        'BOOK': 'Book',
        'CHAP': 'Book Section',
        'THES': 'Thesis',
        'CONF': 'Conference Paper',
        'RPRT': 'Report',
        'WEB': 'Web Page',
        'ELEC': 'Electronic Article',
        'GEN': 'Generic',
        'SER': 'Serial',
        'UNPB': 'Unpublished Work',
        'SOUND': 'Sound Recording',
        'ART': 'Artwork',
        'MAP': 'Map',
        'PAMP': 'Pamphlet',
        'COMP': 'Computer Program',
        'HEAR': 'Hearing',
        'PAT': 'Patent',
        'STAT': 'Statute',
        'BILL': 'Bill',
        'NEWS': 'Newspaper Article',
        'ADVS': 'Audiovisual Material',
        'CTLG': 'Catalog',
        'COMM': 'Online Database',
        'INPR': 'In Press',
        'JFULL': 'Full Journal',
        'SLIDE': 'Slide',
        'VIDEO': 'Video Recording',
        'MGZN': 'Magazine Article'
    }
    return type_map.get(ris_type, 'Journal Article')


def parse_ris_file(ris_file_path: Path) -> List[Dict[str, any]]:
    """
    Parse RIS file into list of reference dictionaries.
    Captures ALL RIS fields dynamically, handling multi-line fields.
    """
    references = []
    
    if not ris_file_path.exists():
        print(f"ERROR: RIS file not found: {ris_file_path}")
        return references
    
    with open(ris_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = re.split(r'^ER\s+-\s*$', content, flags=re.MULTILINE)
    
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        
        ref = {
            'fields': {},  # Store all RIS fields by tag
            'record_number': None,
            'type': 'Journal Article'  # Default
        }
        
        lines = entry.split('\n')
        current_field = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line starts with a RIS tag (2 alphanumeric chars, 2 spaces, hyphen)
            # Tags can be like TY, AU, L1, N1, etc.
            if re.match(r'^[A-Z][A-Z0-9]\s+-\s', line):
                tag = line[0:2]
                value = line[6:].strip()
                
                # Handle special cases
                if tag == 'ID':
                    ref['record_number'] = value
                elif tag == 'TY':
                    # Map RIS type to EndNote type
                    ref['type'] = map_ris_type_to_endnote(value)
                
                # Store field (handle multi-value fields)
                if tag in ref['fields']:
                    if isinstance(ref['fields'][tag], list):
                        ref['fields'][tag].append(value)
                    else:
                        ref['fields'][tag] = [ref['fields'][tag], value]
                else:
                    ref['fields'][tag] = value
                current_field = tag
            else:
                # Continuation of previous field (multi-line)
                if current_field and current_field in ref['fields']:
                    if isinstance(ref['fields'][current_field], list):
                        ref['fields'][current_field][-1] += ' ' + line
                    else:
                        ref['fields'][current_field] += ' ' + line
        
        # Only add if we have a record number or title
        if ref['record_number'] or ref['fields'].get('TI'):
            references.append(ref)
    
    return references


def read_import_map(import_map_path: Path) -> Dict[str, str]:
    """
    Read import_map file and return dictionary mapping record numbers to PDF paths.
    All paths are normalized to absolute paths for consistent handling.
    """
    import_map = {}
    
    if not import_map_path.exists():
        print(f"WARNING: Import map file not found: {import_map_path}")
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
                # Normalize to absolute path to ensure consistency
                pdf_file = Path(pdf_path)
                import_map[record_number] = str(pdf_file.resolve())
    
    return import_map


def map_ris_fields_to_xml(record_elem: ET.Element, ris_fields: Dict[str, any]) -> None:
    """
    Map all RIS fields to appropriate EndNote XML elements.
    """
    # Helper to get field value(s)
    def get_field(tag: str, default=None):
        return ris_fields.get(tag, default)
    
    def get_field_list(tag: str):
        value = ris_fields.get(tag)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]
    
    # Titles
    titles_elem = None
    if get_field('TI'):
        titles_elem = ET.SubElement(record_elem, 'titles')
        title_elem = ET.SubElement(titles_elem, 'title')
        title_elem.text = get_field('TI')
    
    if get_field('ST'):
        if titles_elem is None:
            titles_elem = ET.SubElement(record_elem, 'titles')
        short_title_elem = ET.SubElement(titles_elem, 'short-title')
        short_title_elem.text = get_field('ST')
    
    if get_field('T2'):
        if titles_elem is None:
            titles_elem = ET.SubElement(record_elem, 'titles')
        secondary_title_elem = ET.SubElement(titles_elem, 'secondary-title')
        secondary_title_elem.text = get_field('T2')
    
    if get_field('T3'):
        if titles_elem is None:
            titles_elem = ET.SubElement(record_elem, 'titles')
        tertiary_title_elem = ET.SubElement(titles_elem, 'tertiary-title')
        tertiary_title_elem.text = get_field('T3')
    
    # Contributors - Authors
    authors = get_field_list('AU')
    # Also check A1-A5 for additional authors
    for tag in ['A1', 'A2', 'A3', 'A4', 'A5']:
        authors.extend(get_field_list(tag))
    
    if authors:
        contributors_elem = ET.SubElement(record_elem, 'contributors')
        authors_elem = ET.SubElement(contributors_elem, 'authors')
        for author in authors:
            if author:
                author_elem = ET.SubElement(authors_elem, 'author')
                author_elem.text = author
    
    # Contributors - Editors
    editors = get_field_list('ED')
    if editors:
        contributors_elem = record_elem.find('contributors')
        if contributors_elem is None:
            contributors_elem = ET.SubElement(record_elem, 'contributors')
        editors_elem = ET.SubElement(contributors_elem, 'editors')
        for editor in editors:
            if editor:
                editor_elem = ET.SubElement(editors_elem, 'editor')
                editor_elem.text = editor
    
    # Dates
    dates_elem = None
    if get_field('PY'):
        dates_elem = ET.SubElement(record_elem, 'dates')
        year_elem = ET.SubElement(dates_elem, 'year')
        year_text = get_field('PY')
        # Extract year if it's a full date
        year_match = re.search(r'(\d{4})', year_text)
        if year_match:
            year_elem.text = year_match.group(1)
        else:
            year_elem.text = year_text
    
    if get_field('DA'):
        if dates_elem is None:
            dates_elem = ET.SubElement(record_elem, 'dates')
        date_elem = ET.SubElement(dates_elem, 'date')
        date_elem.text = get_field('DA')
    
    # Volume, Issue, Pages
    if get_field('VL'):
        volume_elem = ET.SubElement(record_elem, 'volume')
        volume_elem.text = get_field('VL')
    
    if get_field('IS'):
        number_elem = ET.SubElement(record_elem, 'number')
        number_elem.text = get_field('IS')
    
    if get_field('SP') or get_field('EP'):
        pages_elem = ET.SubElement(record_elem, 'pages')
        sp = get_field('SP', '')
        ep = get_field('EP', '')
        if sp and ep:
            pages_elem.text = f"{sp}-{ep}"
        elif sp:
            pages_elem.text = sp
        elif ep:
            pages_elem.text = ep
    
    # Publication location and publisher
    if get_field('CY'):
        pub_location_elem = ET.SubElement(record_elem, 'pub-location')
        pub_location_elem.text = get_field('CY')
    
    if get_field('PB'):
        publisher_elem = ET.SubElement(record_elem, 'publisher')
        publisher_elem.text = get_field('PB')
    
    # ISBN/ISSN
    if get_field('SN'):
        # Determine if ISBN or ISSN based on format or reference type
        sn_value = get_field('SN')
        # ISSN typically has format XXXX-XXXX, ISBN is 10 or 13 digits
        if re.match(r'^\d{4}-\d{3}[\dX]$', sn_value.replace(' ', '')):
            issn_elem = ET.SubElement(record_elem, 'issn')
            issn_elem.text = sn_value
        else:
            isbn_elem = ET.SubElement(record_elem, 'isbn')
            isbn_elem.text = sn_value
    
    # URLs and DOI
    urls_elem = None
    if get_field('DO') or get_field('UR'):
        urls_elem = ET.SubElement(record_elem, 'urls')
        related_urls_elem = ET.SubElement(urls_elem, 'related-urls')
        
        if get_field('DO'):
            doi = get_field('DO')
            # Clean DOI
            doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
            doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
            doi = doi.strip()
            
            # Add as URL
            url_elem = ET.SubElement(related_urls_elem, 'url')
            url_elem.text = f"https://doi.org/{doi}"
            
            # Also add as electronic-resource-num
            electronic_elem = ET.SubElement(record_elem, 'electronic-resource-num')
            electronic_elem.text = doi
        
        if get_field('UR'):
            url_elem = ET.SubElement(related_urls_elem, 'url')
            url_elem.text = get_field('UR')
    
    # Abstract
    if get_field('AB'):
        abstract_elem = ET.SubElement(record_elem, 'abstract')
        abstract_elem.text = get_field('AB')
    
    # Keywords
    keywords = get_field_list('KW')
    if keywords:
        keywords_elem = ET.SubElement(record_elem, 'keywords')
        for keyword in keywords:
            if keyword:
                keyword_elem = ET.SubElement(keywords_elem, 'keyword')
                keyword_elem.text = keyword
    
    # Language
    if get_field('LA'):
        language_elem = ET.SubElement(record_elem, 'language')
        language_elem.text = get_field('LA')
    
    # Accession number (PMID, etc.)
    if get_field('AN'):
        accession_elem = ET.SubElement(record_elem, 'accession-num')
        accession_elem.text = get_field('AN')
    
    # Notes
    notes = get_field_list('N1')
    if notes:
        notes_elem = ET.SubElement(record_elem, 'notes')
        notes_text = '\n'.join(notes)
        notes_elem.text = notes_text
    
    # Address
    if get_field('AD'):
        address_elem = ET.SubElement(record_elem, 'address')
        address_elem.text = get_field('AD')
    
    # Database
    if get_field('DB'):
        database_elem = ET.SubElement(record_elem, 'database')
        database_elem.text = get_field('DB')
    
    # Database provider
    if get_field('DP'):
        database_provider_elem = ET.SubElement(record_elem, 'database-provider')
        database_provider_elem.text = get_field('DP')
    
    # Label
    if get_field('LB'):
        label_elem = ET.SubElement(record_elem, 'label')
        label_elem.text = get_field('LB')
    
    # PMC ID (C2)
    if get_field('C2'):
        # Store in custom field or alt-title
        alt_title_elem = ET.SubElement(record_elem, 'alt-title')
        alt_title_elem.text = f"PMC: {get_field('C2')}"
    
    # Custom fields (M1-M3, U1-U5)
    custom_mapping = {
        'M1': 'custom1',
        'M2': 'custom2',
        'M3': 'custom3',
        'U1': 'custom4',
        'U2': 'custom5',
        'U3': 'custom6',
        'U4': 'custom7',
        'U5': 'custom8'
    }
    
    for ris_tag, xml_tag in custom_mapping.items():
        if get_field(ris_tag):
            custom_elem = ET.SubElement(record_elem, xml_tag)
            custom_elem.text = get_field(ris_tag)
    
    # Edition
    if get_field('ET'):
        edition_elem = ET.SubElement(record_elem, 'edition')
        edition_elem.text = get_field('ET')
    
    # Section
    if get_field('SE'):
        section_elem = ET.SubElement(record_elem, 'section')
        section_elem.text = get_field('SE')
    
    # Reprint status
    if get_field('RP'):
        reprint_elem = ET.SubElement(record_elem, 'reprint-status')
        reprint_elem.text = get_field('RP')


def validate_import_map_against_ris(references: List[Dict], import_map: Dict[str, str]) -> List[str]:
    """
    Check for import map entries missing from RIS file.
    Returns list of record numbers from import_map that are not found in RIS references.
    """
    ris_record_numbers = {ref['record_number'] for ref in references if ref['record_number']}
    missing = [record_num for record_num in import_map.keys() if record_num not in ris_record_numbers]
    return missing


def generate_ris_with_attachments(references: List[Dict], import_map: Dict[str, str]) -> str:
    """
    Generate RIS format with file attachments (L1 field) for references that have PDFs.
    Only includes references that have a matching entry in import_map.
    Preserves original RIS field order and structure.
    All L1 field paths are absolute paths for EndNote compatibility.
    """
    ris_lines = []
    
    for ref in references:
        # Only process references that have a matching entry in import_map
        if not ref['record_number'] or ref['record_number'] not in import_map:
            continue
        
        # Get all fields
        fields = ref['fields'].copy()
        
        # Write all original fields first
        for tag, value in fields.items():
            if isinstance(value, list):
                for v in value:
                    ris_lines.append(f"{tag}  - {v}")
            else:
                ris_lines.append(f"{tag}  - {value}")
        
        # Add file attachment if PDF exists (L1 field for local file path)
        # Path from import_map is already absolute
        pdf_path = import_map[ref['record_number']]
        pdf_file = Path(pdf_path)
        if pdf_file.exists():
            # Use the absolute path directly
            ris_lines.append(f"L1  - {str(pdf_file.resolve())}")
        
        # End of record
        ris_lines.append("ER  -")
        ris_lines.append("")  # Blank line between records
    
    return "\n".join(ris_lines)


def generate_ris_with_absolute_l1_paths(references: List[Dict], ris_base_dir: Path) -> str:
    """
    Generate RIS format with ALL references, converting any existing L1 paths to absolute.
    
    This function processes ALL references (not just those in import_map) and:
    1. Preserves all original fields
    2. Converts relative L1 paths to absolute paths based on ris_base_dir
    3. Keeps already-absolute L1 paths unchanged
    
    Args:
        references: List of parsed RIS reference dictionaries
        ris_base_dir: Base directory for resolving relative L1 paths
    
    Returns:
        RIS content as a string with absolute L1 paths
    """
    ris_lines = []
    converted_count = 0
    
    for ref in references:
        # Get all fields
        fields = ref['fields'].copy()
        
        # Write all original fields, converting L1 paths to absolute
        for tag, value in fields.items():
            if isinstance(value, list):
                for v in value:
                    if tag == 'L1':
                        # Convert L1 path to absolute
                        absolute_path = _convert_to_absolute_path(v, ris_base_dir)
                        ris_lines.append(f"{tag}  - {absolute_path}")
                        if absolute_path != v:
                            converted_count += 1
                    else:
                        ris_lines.append(f"{tag}  - {v}")
            else:
                if tag == 'L1':
                    # Convert L1 path to absolute
                    absolute_path = _convert_to_absolute_path(value, ris_base_dir)
                    ris_lines.append(f"{tag}  - {absolute_path}")
                    if absolute_path != value:
                        converted_count += 1
                else:
                    ris_lines.append(f"{tag}  - {value}")
        
        # End of record
        ris_lines.append("ER  -")
        ris_lines.append("")  # Blank line between records
    
    print(f"  Converted {converted_count} L1 paths to absolute")
    return "\n".join(ris_lines)


def _convert_to_absolute_path(path_str: str, base_dir: Path) -> str:
    """
    Convert a path string to an absolute path.
    
    Args:
        path_str: Path string (may be relative or absolute)
        base_dir: Base directory for resolving relative paths
    
    Returns:
        Absolute path as a string
    """
    path_str = path_str.strip()
    
    # Check if already absolute
    if path_str.startswith('/') or path_str.startswith('file://'):
        return path_str
    
    # Convert relative path to absolute
    full_path = (base_dir / path_str).resolve()
    return str(full_path)


def find_newest_ris_in_search_term_results() -> Optional[Path]:
    """
    Find the newest RIS file in the search_term_results directory.
    """
    # Endnote folder is now in OneDrive
    search_term_results_dir = Path("/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote/search_term_results")
    
    if not search_term_results_dir.exists():
        return None
    
    folders = []
    for item in search_term_results_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            stat = item.stat()
            mtime = stat.st_mtime
            folders.append((mtime, item))
    
    if not folders:
        return None
    
    # Sort by modification time (most recent first)
    folders.sort(key=lambda x: x[0], reverse=True)
    newest_folder = folders[0][1]
    
    # Look for RIS file in this folder
    ris_files = list(newest_folder.glob("*.ris"))
    if ris_files:
        return ris_files[0]
    return None


def main_convert_l1_to_absolute():
    """
    Mode 1: Convert existing L1 paths in a RIS file to absolute paths.
    No import map needed - just converts relative paths to absolute.
    """
    print("="*70)
    print("CONVERT L1 PATHS TO ABSOLUTE")
    print("="*70)
    print()
    
    # Find default RIS file in search_term_results
    default_ris_file = find_newest_ris_in_search_term_results()
    
    if default_ris_file:
        print(f"Default RIS file (newest in search_term_results):")
        print(f"  {default_ris_file}")
        print()
        
        use_default = input("Use default RIS file? (y/n): ").strip().lower()
        if use_default == 'y':
            input_ris_path = default_ris_file
        else:
            user_input = input("Enter path to RIS file: ").strip()
            if not user_input:
                print("ERROR: No file specified")
                return
            user_input = user_input.strip("'\"")
            input_ris_path = Path(user_input)
    else:
        print("No default RIS file found in search_term_results")
        user_input = input("Enter path to RIS file: ").strip()
        if not user_input:
            print("ERROR: No file specified")
            return
        user_input = user_input.strip("'\"")
        input_ris_path = Path(user_input)
    
    if not input_ris_path.exists():
        print(f"ERROR: RIS file not found: {input_ris_path}")
        return
    
    print()
    print(f"Processing: {input_ris_path}")
    print()
    
    # Parse the RIS file
    print("Parsing RIS file...")
    references = parse_ris_file(input_ris_path)
    print(f"  Found {len(references)} references")
    print()
    
    # Count L1 fields
    l1_count = 0
    for ref in references:
        if 'L1' in ref['fields']:
            l1_value = ref['fields']['L1']
            if isinstance(l1_value, list):
                l1_count += len(l1_value)
            else:
                l1_count += 1
    print(f"  Found {l1_count} L1 (file attachment) fields")
    print()
    
    # Generate RIS with absolute L1 paths
    print("Converting L1 paths to absolute...")
    ris_base_dir = input_ris_path.parent
    ris_content = generate_ris_with_absolute_l1_paths(references, ris_base_dir)
    
    # Output file in same directory with _absolute_paths suffix
    output_ris_path = ris_base_dir / f"{input_ris_path.stem}_absolute_paths.ris"
    
    with open(output_ris_path, 'w', encoding='utf-8') as f:
        f.write(ris_content)
    
    print()
    print("="*70)
    print("COMPLETE")
    print("="*70)
    print(f"  Input:  {input_ris_path.name}")
    print(f"  Output: {output_ris_path.name}")
    print(f"  Location: {output_ris_path.parent}")
    print(f"  Total references: {len(references)}")
    print(f"  L1 fields processed: {l1_count}")
    print()
    print("Next steps:")
    print("  1. Open EndNote")
    print("  2. Go to File > Import > File...")
    print(f"  3. Select: {output_ris_path.name}")
    print("  4. Set Import Option to: Reference Manager (RIS)")
    print("  5. Click Import")
    print("  6. Attachments should now work with absolute paths")
    print("="*70)


def ris_to_endnote_xml(references: List[Dict], import_map: Dict[str, str]) -> str:
    """
    Convert RIS references to EndNote XML format with file attachments.
    Includes ALL RIS fields in the XML output.
    """
    # Create XML structure
    xml_root = ET.Element('xml')
    records_elem = ET.SubElement(xml_root, 'records')
    
    # Map EndNote type names to type numbers
    type_number_map = {
        'Journal Article': '17',
        'Book': '6',
        'Book Section': '5',
        'Thesis': '32',
        'Conference Paper': '10',
        'Report': '27',
        'Web Page': '12',
        'Electronic Article': '17',
        'Generic': '13',
        'Serial': '17',
        'Unpublished Work': '28',
        'Sound Recording': '29',
        'Artwork': '1',
        'Map': '18',
        'Pamphlet': '24',
        'Computer Program': '9',
        'Hearing': '15',
        'Patent': '25',
        'Statute': '30',
        'Bill': '3',
        'Newspaper Article': '20',
        'Audiovisual Material': '2',
        'Catalog': '4',
        'Online Database': '12',
        'In Press': '17',
        'Full Journal': '17',
        'Slide': '26',
        'Video Recording': '31',
        'Magazine Article': '19'
    }
    
    # Only process references that have a matching entry in import_map
    for ref in references:
        if not ref['record_number'] or ref['record_number'] not in import_map:
            continue  # Skip this reference - not in import map
        
        record_elem = ET.SubElement(records_elem, 'record')
        
        # Record number
        if ref['record_number']:
            rec_number_elem = ET.SubElement(record_elem, 'rec-number')
            rec_number_elem.text = ref['record_number']
        
        # Reference type
        ref_type_elem = ET.SubElement(record_elem, 'ref-type')
        ref_type_elem.set('name', ref['type'])
        ref_type_elem.text = type_number_map.get(ref['type'], '17')
        
        # Map all RIS fields to XML
        map_ris_fields_to_xml(record_elem, ref['fields'])
        
        # File attachments
        if ref['record_number'] and ref['record_number'] in import_map:
            pdf_path = import_map[ref['record_number']]
            # Verify file exists
            pdf_file = Path(pdf_path)
            if pdf_file.exists():
                file_attachments_elem = ET.SubElement(record_elem, 'file-attachments')
                file_attachment_elem = ET.SubElement(file_attachments_elem, 'file-attachment')
                # EndNote XML format: use href attribute with absolute path
                # Also include the path as text content for compatibility
                absolute_path = str(pdf_file.absolute())
                file_attachment_elem.set('href', absolute_path)
                file_attachment_elem.text = absolute_path
    
    # Convert to string with proper formatting
    try:
        ET.indent(xml_root, space='  ')  # Python 3.9+
    except AttributeError:
        pass  # Older Python versions - XML will still be valid, just not indented
    
    xml_string = ET.tostring(xml_root, encoding='unicode', xml_declaration=True)
    return xml_string


def get_latest_ris_file(ris_files_dir: Path) -> Optional[Path]:
    """
    Find the most recently added/modified RIS file in the directory.
    Returns Path to the file, or None if not found.
    """
    if not ris_files_dir.exists():
        return None
    
    ris_files = []
    for file_path in ris_files_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in ['.txt', '.ris']:
            stat = file_path.stat()
            # Use modification time, and creation time as tiebreaker
            mtime = stat.st_mtime
            ctime = stat.st_ctime if hasattr(stat, 'st_ctime') else mtime
            ris_files.append((mtime, ctime, file_path))
    
    if not ris_files:
        return None
    
    # Sort by modification time (most recent first), then creation time
    ris_files.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return ris_files[0][2]


def get_latest_import_map(import_ids_dir: Path) -> Optional[Path]:
    """
    Find the most recently added/modified import map file in the directory.
    Returns Path to the file, or None if not found.
    """
    if not import_ids_dir.exists():
        return None
    
    import_map_files = []
    for file_path in import_ids_dir.iterdir():
        if file_path.is_file() and (file_path.name.startswith('import_map') or file_path.name.startswith('import_')):
            stat = file_path.stat()
            # Use modification time, and creation time as tiebreaker
            mtime = stat.st_mtime
            ctime = stat.st_ctime if hasattr(stat, 'st_ctime') else mtime
            import_map_files.append((mtime, ctime, file_path))
    
    if not import_map_files:
        return None
    
    # Sort by modification time (most recent first), then creation time
    import_map_files.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return import_map_files[0][2]


def get_next_versioned_filename(base_filename: str, output_dir: Path) -> Path:
    """
    Get the next available versioned filename.
    If base_filename exists, find the highest version number and increment it.
    
    Examples:
    - If 'file.xml' exists, return 'file2.xml'
    - If 'file2.xml' exists, return 'file3.xml'
    - If 'file33.xml' exists, return 'file34.xml'
    """
    base_path = output_dir / base_filename
    
    # Extract base name without extension
    base_stem = base_path.stem
    extension = base_path.suffix
    
    # Find all files matching the pattern: base_stem<number>.xml
    # Pattern: base_stem followed by digits, then extension
    pattern = re.compile(rf'^{re.escape(base_stem)}(\d+){re.escape(extension)}$')
    
    max_version = 0
    
    # Check if base file exists (treat as version 1)
    if base_path.exists():
        max_version = 1
    
    # Check all files in the directory for numbered versions
    for file_path in output_dir.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                version = int(match.group(1))
                max_version = max(max_version, version)
    
    # If base file doesn't exist and no numbered versions found, use base filename
    if max_version == 0:
        return base_path
    
    # Return next version
    next_version = max_version + 1
    return output_dir / f"{base_stem}{next_version}{extension}"


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent
    
    print("="*70)
    print("RIS EXPORT WITH FILE ATTACHMENTS")
    print("="*70)
    print()
    
    # Ask which mode to use
    print("Choose mode:")
    print("  1. Convert existing L1 paths to absolute (no import map needed)")
    print("  2. Add attachments from import map (requires matching record IDs)")
    print()
    
    mode = input("Enter mode (1 or 2) [default: 1]: ").strip()
    if mode not in ['1', '2']:
        mode = '1'
    print()
    
    if mode == '1':
        # Mode 1: Convert existing L1 paths to absolute
        main_convert_l1_to_absolute()
        return
    
    # Mode 2: Original functionality with import map
    # Ask for RIS file (with retry and default)
    ris_files_dir = base_dir / "found_papers" / "RIS_files"
    print(f"RIS files are located in: {ris_files_dir}")
    
    # Find default RIS file
    default_ris_file = get_latest_ris_file(ris_files_dir)
    
    ris_file = None
    ris_input = None
    while ris_file is None or not ris_file.exists():
        if ris_file is not None and not ris_file.exists():
            error_msg = ris_input if ris_input else "default file"
            print(f"ERROR: RIS file not found: {error_msg}")
            print(f"  Searched in: {ris_files_dir}")
            print()
            default_ris_file = get_latest_ris_file(ris_files_dir)  # Re-check default
        
        if default_ris_file and default_ris_file.exists():
            use_default = input(f"Default RIS file: {default_ris_file.name} - Default (y) or enter filename (n)? ").strip().lower()
            if use_default == 'y':
                ris_file = default_ris_file
                if ris_file.exists():
                    break
                # If default file doesn't exist, continue loop
                continue
            elif use_default == 'n':
                ris_input = input("Enter RIS filename: ").strip()
            else:
                print("Please enter 'y' for default or 'n' to enter filename")
                print()
                continue
        else:
            ris_input = input("Which RIS file would you like to use? (enter filename): ").strip()
        
        if not ris_input:
            print("ERROR: No RIS file specified")
            print()
            continue
        
        # Check if it's an absolute path
        if Path(ris_input).is_absolute():
            ris_file = Path(ris_input)
        else:
            # Only look in found_papers/RIS_files/
            ris_file = ris_files_dir / ris_input
    
    print(f"Using RIS file: {ris_file.name}")
    print()
    
    # Ask for import_map file (with retry and default)
    import_ids_dir = base_dir / "found_papers" / "import_IDs"
    print(f"Import map files are located in: {import_ids_dir}")
    
    # Find default import map file
    default_import_map_file = get_latest_import_map(import_ids_dir)
    
    import_map_file = None
    while import_map_file is None or not import_map_file.exists():
        if import_map_file is not None and not import_map_file.exists():
            print(f"ERROR: Import map file not found")
            print(f"  Searched in: {import_ids_dir}")
            print()
            default_import_map_file = get_latest_import_map(import_ids_dir)  # Re-check default
        
        use_default = None
        import_map_input = None
        
        if default_import_map_file and default_import_map_file.exists():
            use_default = input(f"Default import map file: {default_import_map_file.name} - Default (y) or enter filename (n)? ").strip().lower()
            if use_default == 'y':
                import_map_file = default_import_map_file
                break
            elif use_default == 'n':
                import_map_input = input("Enter import map filename (or 'auto' to find latest): ").strip()
            else:
                print("Please enter 'y' for default or 'n' to enter filename")
                print()
                continue
        else:
            import_map_input = input("Which import_map file? (enter filename, 'auto' to find latest, or press Enter for auto): ").strip()
        
        # Process user input
        if use_default == 'n' or (use_default is None and import_map_input):
            # User chose not to use default or no default available
            if import_map_input.lower() == 'auto' or not import_map_input:
                # Auto-detect: look for latest import_map file
                if import_ids_dir.exists():
                    # Find latest import_map file
                    import_map_files = []
                    for file_path in import_ids_dir.iterdir():
                        if file_path.is_file() and (file_path.name.startswith('import_map') or file_path.name.startswith('import_')):
                            mtime = file_path.stat().st_mtime
                            import_map_files.append((mtime, file_path))
                    
                    if import_map_files:
                        import_map_files.sort(key=lambda x: x[0], reverse=True)
                        import_map_file = import_map_files[0][1]
                        print(f"Auto-detected: {import_map_file.name}")
                        break
                    else:
                        print(f"ERROR: No import_map files found in {import_ids_dir}")
                        print()
                        continue
                else:
                    print(f"ERROR: import_IDs directory not found: {import_ids_dir}")
                    print()
                    continue
            else:
                # User specified file - look in import_IDs folder
                import_map_file = import_ids_dir / import_map_input
                if import_map_file.exists():
                    break
    
    print(f"Using import map: {import_map_file.name}")
    print()
    
    # Parse files
    print("Parsing RIS file...")
    references = parse_ris_file(ris_file)
    print(f"  Found {len(references)} references")
    print()
    
    print("Reading import map...")
    import_map = read_import_map(import_map_file)
    print(f"  Found {len(import_map)} PDF file mappings")
    print()
    
    # Validate import map against RIS file
    missing_from_ris = validate_import_map_against_ris(references, import_map)
    if missing_from_ris:
        print(f"WARNING: {len(missing_from_ris)} import map entries not found in RIS file:")
        for record_num in missing_from_ris:
            print(f"  Record number: {record_num} (title not available - not in RIS file)")
        print()
    
    # Count matches (references that exist in both files)
    matched = sum(1 for ref in references if ref['record_number'] and ref['record_number'] in import_map)
    print(f"  {matched} references will be included in RIS (found in both RIS and import map)")
    
    # Count how many PDF files actually exist
    pdf_files_exist = 0
    pdf_files_missing = 0
    for record_num, pdf_path in import_map.items():
        if Path(pdf_path).exists():
            pdf_files_exist += 1
        else:
            pdf_files_missing += 1
    
    print(f"  PDF files found: {pdf_files_exist}")
    if pdf_files_missing > 0:
        print(f"  WARNING: {pdf_files_missing} PDF files from import map not found at specified paths")
    print()
    
    # Generate RIS with attachments
    print("Generating RIS file with attachments...")
    ris_content = generate_ris_with_attachments(references, import_map)
    
    # Save RIS file to found_papers/RIS_files/import_to_endnote/
    ris_output_dir = base_dir / "found_papers" / "RIS_files" / "import_to_endnote"
    ris_output_dir.mkdir(parents=True, exist_ok=True)
    base_output_filename = f"{ris_file.stem}_with_attachments.txt"
    output_file = get_next_versioned_filename(base_output_filename, ris_output_dir)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(ris_content)
    
    print(f"  RIS file created: {output_file}")
    print()
    
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  RIS file: {ris_file.name}")
    print(f"  Import map: {import_map_file.name}")
    print(f"  Total references in RIS file: {len(references)}")
    print(f"  References included in RIS (matched): {matched}")
    if missing_from_ris:
        print(f"  Import map entries missing from RIS: {len(missing_from_ris)}")
    print(f"  Output RIS: {output_file.name}")
    print()
    print("Next steps:")
    print("  1. Open EndNote")
    print("  2. Go to File > Import > File...")
    print(f"  3. Select: {output_file.name}")
    print("  4. Set Import Option to: Reference Manager (RIS)")
    print("  5. Click Import")
    print("  6. EndNote should automatically attach PDFs using the L1 field paths")
    print("="*70)


if __name__ == "__main__":
    main()
