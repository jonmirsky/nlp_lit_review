#!/usr/bin/env python3
"""
PDF to EndNote Record Matcher

Matches PDFs from the unmatched folder to EndNote records in map1.txt
by extracting text from page 1 and fuzzy matching titles.
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
from pypdf import PdfReader
from rapidfuzz import fuzz, process

# Configuration
MAP1_FILE = Path(__file__).parent / "map1.txt"
PDF_FOLDER = Path(__file__).parent / "found_papers" / "unmatched"
OUTPUT_FILE = Path(__file__).parent / "rescue_papers1.txt"
SIMILARITY_THRESHOLD = 97  # >=97% similarity required


def normalize_text(text):
    """Normalize text for better matching: lowercase, strip whitespace."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def read_map1(map1_path):
    """
    Read map1.txt and extract Record IDs and Titles.
    Returns: dict mapping title -> list of (record_id, title) tuples
    """
    records = {}
    print(f"Reading {map1_path}...")
    
    try:
        with open(map1_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Split on tab character
                parts = line.split('\t')
                if len(parts) < 2:
                    # Try splitting on multiple spaces as fallback
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        print(f"Warning: Line {line_num} doesn't have tab separator: {line[:50]}...")
                        continue
                
                record_id = parts[0].strip()
                title = parts[1].strip()
                
                if record_id and title:
                    records[record_id] = title
                else:
                    print(f"Warning: Line {line_num} has empty ID or title")
    
    except FileNotFoundError:
        print(f"Error: {map1_path} not found!")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading {map1_path}: {e}")
        sys.exit(1)
    
    print(f"Loaded {len(records)} records from map1.txt")
    return records


def extract_pdf_text(pdf_path):
    """
    Extract text from page 1 of a PDF.
    Returns: normalized text string, or None if extraction fails.
    """
    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) == 0:
            return None
        
        # Extract text from page 1 (index 0)
        page = reader.pages[0]
        text = page.extract_text()
        
        if not text or not text.strip():
            return None
        
        return normalize_text(text)
    
    except Exception as e:
        print(f"  Warning: Could not extract text from {pdf_path.name}: {e}")
        return None


def find_best_match(pdf_text, records, pdf_name=None, debug=False):
    """
    Find the best matching title for PDF text using fuzzy matching.
    Uses both ratio and partial_ratio to handle cases where title appears as substring.
    Returns: (record_id, title, similarity_score) if match >= threshold, 
             or (None, None, best_score) if below threshold (for diagnostics)
    """
    if not pdf_text:
        return (None, None, 0)
    
    # Create a list of titles with their record IDs for matching
    titles_with_ids = [(record_id, title) for record_id, title in records.items()]
    title_strings = [title for _, title in titles_with_ids]
    
    # Try ratio first (full string comparison) - without cutoff to see best match
    result_ratio = process.extractOne(
        pdf_text,
        title_strings,
        scorer=fuzz.ratio
    )
    
    # Try partial_ratio (better for substring matching) - without cutoff to see best match
    result_partial = process.extractOne(
        pdf_text,
        title_strings,
        scorer=fuzz.partial_ratio
    )
    
    # Take the best match from both methods
    best_result = None
    best_score = 0
    best_method = None
    
    if result_ratio:
        matched_title, score, index = result_ratio
        if score > best_score:
            best_result = (titles_with_ids[index][0], matched_title, score)
            best_score = score
            best_method = "ratio"
    
    if result_partial:
        matched_title, score, index = result_partial
        if score > best_score:
            best_result = (titles_with_ids[index][0], matched_title, score)
            best_score = score
            best_method = "partial_ratio"
    
    # Only return match if above threshold
    if best_result and best_score >= SIMILARITY_THRESHOLD:
        return best_result
    
    # Debug: show best match even if below threshold (for first few PDFs)
    if debug and best_result and pdf_name:
        print(f"    [DEBUG] Best match for {pdf_name}: Record {best_result[0]}, score: {best_score:.1f}% (method: {best_method}, threshold: {SIMILARITY_THRESHOLD}%)")
        if best_score < SIMILARITY_THRESHOLD:
            print(f"    [DEBUG]   Title: {best_result[1][:80]}...")
            print(f"    [DEBUG]   PDF text sample: {pdf_text[:200]}...")
    
    # Return None result but with best score for diagnostics
    return (None, None, best_score)


def main():
    print("=" * 70)
    print("PDF to EndNote Record Matcher")
    print("=" * 70)
    print()
    
    # Read map1.txt
    records = read_map1(MAP1_FILE)
    if not records:
        print("Error: No records found in map1.txt")
        sys.exit(1)
    
    # Get list of PDFs
    if not PDF_FOLDER.exists():
        print(f"Error: PDF folder not found: {PDF_FOLDER}")
        sys.exit(1)
    
    pdf_files = list(PDF_FOLDER.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {PDF_FOLDER}")
    print()
    
    # Track matches and statistics
    matches = {}  # record_id -> (pdf_path, similarity_score) - best match only
    all_matches = defaultdict(list)  # record_id -> list of (pdf_path, score) - all matches
    unmatched_pdfs = []
    best_scores_below_threshold = []  # Track best scores that were below threshold
    processed_count = 0
    error_count = 0
    
    # Process each PDF
    print("Processing PDFs...")
    debug_count = 0
    for pdf_path in pdf_files:
        print(f"  Processing: {pdf_path.name}...", end=" ")
        
        # Extract text from page 1
        pdf_text = extract_pdf_text(pdf_path)
        
        if pdf_text is None:
            print("(no text extracted)")
            error_count += 1
            unmatched_pdfs.append(pdf_path.name)
            continue
        
        # Find best match (debug first 3 unmatched PDFs)
        debug_this = (debug_count < 3 and len(unmatched_pdfs) < 3)
        match_result = find_best_match(pdf_text, records, pdf_path.name, debug=debug_this)
        if debug_this:
            debug_count += 1
        
        # Track best scores even if below threshold (for diagnostics)
        if match_result[0] is None:  # No match found
            best_score = match_result[2]  # Get the best score that was below threshold
            if best_score > 0:
                best_scores_below_threshold.append(best_score)
            print("(no match found)")
            unmatched_pdfs.append(pdf_path.name)
        else:
            # We have a valid match
            record_id, title, score = match_result
            print(f"MATCHED: Record {record_id} (similarity: {score:.1f}%)")
            
            # Track all matches for this record
            all_matches[record_id].append((pdf_path, score))
            
            # Keep the best match (highest score) for output
            if record_id not in matches or score > matches[record_id][1]:
                matches[record_id] = (pdf_path, score)
        
        processed_count += 1
    
    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()
    
    # Generate output file
    print(f"Writing output to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for record_id, (pdf_path, score) in sorted(matches.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
            f.write(f"{record_id}\t{pdf_path}\n")
    
    print(f"Wrote {len(matches)} matches to {OUTPUT_FILE}")
    print()
    
    # Print statistics
    records_with_multiple = {rid: matches_list for rid, matches_list in all_matches.items() if len(matches_list) > 1}
    print("STATISTICS:")
    print(f"  Total PDFs processed: {processed_count}")
    print(f"  PDFs with extraction errors: {error_count}")
    print(f"  Successfully matched (one-to-one): {len(matches)}")
    print(f"  Unmatched PDFs: {len(unmatched_pdfs)}")
    print(f"  Records with multiple PDF matches: {len(records_with_multiple)}")
    print(f"  Records from map1.txt with no PDF match: {len(records) - len(matches)}")
    if best_scores_below_threshold:
        avg_best_score = sum(best_scores_below_threshold) / len(best_scores_below_threshold)
        max_best_score = max(best_scores_below_threshold)
        print(f"  Average best match score (below threshold): {avg_best_score:.1f}%")
        print(f"  Highest best match score (below threshold): {max_best_score:.1f}%")
        print(f"  (Threshold is {SIMILARITY_THRESHOLD}%)")
    print()
    
    # Report unmatched PDFs
    if unmatched_pdfs:
        print("UNMATCHED PDFs:")
        for pdf_name in sorted(unmatched_pdfs):
            print(f"  - {pdf_name}")
        print()
    
    # Report multiple matches (records with more than one PDF match)
    records_with_multiple = {rid: matches_list for rid, matches_list in all_matches.items() if len(matches_list) > 1}
    if records_with_multiple:
        print("RECORDS WITH MULTIPLE PDF MATCHES:")
        for record_id in sorted(records_with_multiple.keys(), key=lambda x: int(x) if x.isdigit() else x):
            matches_list = records_with_multiple[record_id]
            print(f"  Record {record_id}: {records[record_id]}")
            # Sort by score descending
            matches_list_sorted = sorted(matches_list, key=lambda x: x[1], reverse=True)
            for pdf_path, score in matches_list_sorted:
                marker = " -> CHOSEN" if pdf_path == matches[record_id][0] else ""
                print(f"    - {pdf_path.name} (similarity: {score:.1f}%){marker}")
        print()
    
    # Report records with no PDF match
    unmatched_records = set(records.keys()) - set(matches.keys())
    if unmatched_records:
        print(f"RECORDS FROM map1.txt WITH NO PDF MATCH ({len(unmatched_records)}):")
        for record_id in sorted(unmatched_records, key=lambda x: int(x) if x.isdigit() else x):
            print(f"  Record {record_id}: {records[record_id]}")
        print()
    
    print("=" * 70)
    print("Done!")
    print("=" * 70)


if __name__ == "__main__":
    main()




