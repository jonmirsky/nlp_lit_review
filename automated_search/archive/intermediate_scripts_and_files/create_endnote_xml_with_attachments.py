#!/usr/bin/env python3
"""
Create EndNote XML file with PDF file attachments from RIS file and import_map.

This script generates an EndNote XML file that can be directly imported into EndNote,
with PDF files already attached. This avoids the need for manual attachment automation.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional
import html


def parse_ris_file(ris_file_path: Path) -> List[Dict[str, any]]:
    """
    Parse RIS file into list of reference dictionaries.
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
            'record_number': None,
            'type': 'Journal Article',  # Default
            'title': None,
            'authors': [],
            'journal': None,
            'year': None,
            'doi': None,
            'url': None,
            'volume': None,
            'pages': None,
            'abstract': None,
            'ris_text': entry
        }
        
        lines = entry.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ID  - '):
                ref['record_number'] = line[6:].strip()
            elif line.startswith('TY  - '):
                ris_type = line[6:].strip()
                # Map RIS types to EndNote types
                type_map = {
                    'JOUR': 'Journal Article',
                    'BOOK': 'Book',
                    'CHAP': 'Book Section',
                    'THES': 'Thesis',
                    'CONF': 'Conference Paper',
                    'RPRT': 'Report',
                    'WEB': 'Web Page'
                }
                ref['type'] = type_map.get(ris_type, 'Journal Article')
            elif line.startswith('TI  - '):
                ref['title'] = line[6:].strip()
            elif line.startswith('AU  - '):
                author = line[6:].strip()
                if author:
                    ref['authors'].append(author)
            elif line.startswith('T2  - '):
                ref['journal'] = line[6:].strip()
            elif line.startswith('PY  - '):
                year_text = line[6:].strip()
                year_match = re.search(r'(\d{4})', year_text)
                if year_match:
                    ref['year'] = year_match.group(1)
            elif line.startswith('DO  - '):
                doi = line[6:].strip()
                doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
                doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
                ref['doi'] = doi.strip()
            elif line.startswith('UR  - '):
                ref['url'] = line[6:].strip()
            elif line.startswith('VL  - '):
                ref['volume'] = line[6:].strip()
            elif line.startswith('SP  - ') or line.startswith('EP  - '):
                if not ref['pages']:
                    ref['pages'] = line[6:].strip()
                else:
                    ref['pages'] = f"{ref['pages']}-{line[6:].strip()}"
            elif line.startswith('AB  - '):
                ref['abstract'] = line[6:].strip()
        
        if ref['record_number'] or ref['title']:
            references.append(ref)
    
    return references


def read_import_map(import_map_path: Path) -> Dict[str, str]:
    """
    Read import_map file and return dictionary mapping record numbers to PDF paths.
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
                import_map[record_number] = pdf_path
    
    return import_map


def ris_to_endnote_xml(references: List[Dict], import_map: Dict[str, str]) -> str:
    """
    Convert RIS references to EndNote XML format with file attachments.
    """
    # Create XML structure
    xml_root = ET.Element('xml')
    records_elem = ET.SubElement(xml_root, 'records')
    
    for ref in references:
        record_elem = ET.SubElement(records_elem, 'record')
        
        # Record number
        if ref['record_number']:
            rec_number_elem = ET.SubElement(record_elem, 'rec-number')
            rec_number_elem.text = ref['record_number']
        
        # Reference type
        ref_type_elem = ET.SubElement(record_elem, 'ref-type')
        ref_type_elem.set('name', ref['type'])
        # Map type name to EndNote type number
        type_map = {
            'Journal Article': '17',
            'Book': '6',
            'Book Section': '5',
            'Thesis': '32',
            'Conference Paper': '10',
            'Report': '27',
            'Web Page': '12'
        }
        ref_type_elem.text = type_map.get(ref['type'], '17')
        
        # Contributors (authors)
        if ref['authors']:
            contributors_elem = ET.SubElement(record_elem, 'contributors')
            authors_elem = ET.SubElement(contributors_elem, 'authors')
            for author in ref['authors']:
                author_elem = ET.SubElement(authors_elem, 'author')
                author_elem.text = author
        
        # Titles
        if ref['title'] or ref['journal']:
            titles_elem = ET.SubElement(record_elem, 'titles')
            if ref['title']:
                title_elem = ET.SubElement(titles_elem, 'title')
                title_elem.text = ref['title']
            if ref['journal']:
                secondary_title_elem = ET.SubElement(titles_elem, 'secondary-title')
                secondary_title_elem.text = ref['journal']
        
        # Dates
        if ref['year']:
            dates_elem = ET.SubElement(record_elem, 'dates')
            year_elem = ET.SubElement(dates_elem, 'year')
            year_elem.text = ref['year']
        
        # URLs (DOI)
        if ref['doi'] or ref['url']:
            urls_elem = ET.SubElement(record_elem, 'urls')
            related_urls_elem = ET.SubElement(urls_elem, 'related-urls')
            if ref['doi']:
                url_elem = ET.SubElement(related_urls_elem, 'url')
                url_elem.text = f"https://doi.org/{ref['doi']}"
            elif ref['url']:
                url_elem = ET.SubElement(related_urls_elem, 'url')
                url_elem.text = ref['url']
        
        # Volume and pages
        if ref['volume']:
            volume_elem = ET.SubElement(record_elem, 'volume')
            volume_elem.text = ref['volume']
        
        if ref['pages']:
            pages_elem = ET.SubElement(record_elem, 'pages')
            pages_elem.text = ref['pages']
        
        # Abstract
        if ref['abstract']:
            abstract_elem = ET.SubElement(record_elem, 'abstract')
            abstract_elem.text = ref['abstract']
        
        # File attachments
        if ref['record_number'] and ref['record_number'] in import_map:
            pdf_path = import_map[ref['record_number']]
            # Verify file exists
            pdf_file = Path(pdf_path)
            if pdf_file.exists():
                file_attachments_elem = ET.SubElement(record_elem, 'file-attachments')
                file_attachment_elem = ET.SubElement(file_attachments_elem, 'file-attachment')
                file_attachment_elem.text = str(pdf_file.absolute())
    
    # Convert to string with proper formatting
    try:
        ET.indent(xml_root, space='  ')  # Python 3.9+
    except AttributeError:
        pass  # Older Python versions - XML will still be valid, just not indented
    
    xml_string = ET.tostring(xml_root, encoding='unicode', xml_declaration=True)
    return xml_string


def main():
    """Main execution function."""
    base_dir = Path(__file__).parent.parent
    
    print("="*70)
    print("ENDNOTE XML EXPORT WITH FILE ATTACHMENTS")
    print("="*70)
    print()
    
    # Ask for RIS file
    ris_input = input("Which RIS file would you like to use? (enter path or filename): ").strip()
    
    if not ris_input:
        print("ERROR: No RIS file specified")
        return
    
    # Try to find the RIS file
    ris_file = None
    
    # Check if it's an absolute path
    if Path(ris_input).is_absolute():
        ris_file = Path(ris_input)
    else:
        # Try relative to base directory
        ris_file = base_dir / ris_input
        if not ris_file.exists():
            # Try in missing_papers/still_missing/
            ris_file = base_dir / "missing_papers" / "still_missing" / ris_input
        if not ris_file.exists():
            # Try in missing_papers/still_missing/archive/
            ris_file = base_dir / "missing_papers" / "still_missing" / "archive" / ris_input
    
    if not ris_file or not ris_file.exists():
        print(f"ERROR: RIS file not found: {ris_input}")
        print("  Tried:")
        print(f"    {base_dir / ris_input}")
        print(f"    {base_dir / 'missing_papers' / 'still_missing' / ris_input}")
        print(f"    {base_dir / 'missing_papers' / 'still_missing' / 'archive' / ris_input}")
        return
    
    print(f"Using RIS file: {ris_file}")
    print()
    
    # Ask for import_map file
    import_map_input = input("Which import_map file corresponds to this RIS file? (enter filename or 'auto' to search): ").strip()
    
    import_map_file = None
    
    if import_map_input.lower() == 'auto' or not import_map_input:
        # Auto-detect: look for latest import_map file
        import_ids_dir = base_dir / "found_papers" / "import_IDs"
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
            else:
                print("ERROR: No import_map files found")
                return
        else:
            print("ERROR: import_IDs directory not found")
            return
    else:
        # User specified file
        import_ids_dir = base_dir / "found_papers" / "import_IDs"
        import_map_file = import_ids_dir / import_map_input
        if not import_map_file.exists():
            print(f"ERROR: Import map file not found: {import_map_file}")
            return
    
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
    
    # Count matches
    matched = sum(1 for ref in references if ref['record_number'] and ref['record_number'] in import_map)
    print(f"  {matched} references have matching PDF files")
    print()
    
    # Generate XML
    print("Generating EndNote XML...")
    xml_content = ris_to_endnote_xml(references, import_map)
    
    # Save XML file
    output_file = base_dir / f"{ris_file.stem}_with_attachments.xml"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(xml_content)
    
    print(f"  XML file created: {output_file}")
    print()
    
    print("="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  RIS file: {ris_file.name}")
    print(f"  Import map: {import_map_file.name}")
    print(f"  References: {len(references)}")
    print(f"  References with PDF attachments: {matched}")
    print(f"  Output XML: {output_file.name}")
    print()
    print("Next steps:")
    print("  1. Open EndNote")
    print("  2. Go to File > Import > File...")
    print(f"  3. Select: {output_file.name}")
    print("  4. Set Import Option to: EndNote generated XML")
    print("  5. Click Import")
    print("  6. Delete duplicate references without attachments")
    print("="*70)


if __name__ == "__main__":
    main()
