#!/usr/bin/env python3
"""
PDF Paper Sorting Pipeline

Extracts information from PDF papers and sorts them into folders by:
- Model used (auto-detected)
- Medical field (keyword-based detection)

Original papers in all_papers/ remain untouched.
"""

import os
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Set, Tuple
import pdfplumber

# Add script directory to path so we can import sorter_config
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from sorter_config import MODEL_PATTERNS, FIELD_KEYWORDS, METHODS_SECTION_KEYWORDS, RESULTS_SECTION_KEYWORDS


class PaperSorter:
    """Main class for sorting PDF papers by model and field."""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.all_papers_dir = self.base_dir / 'all_papers'
        self.by_model_dir = self.base_dir / 'by_model'
        self.by_field_dir = self.base_dir / 'by_field'
        
        # Ensure directories exist
        self.by_model_dir.mkdir(exist_ok=True)
        self.by_field_dir.mkdir(exist_ok=True)
    
    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text from a PDF file."""
        try:
            text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except Exception as e:
            print(f"Warning: Could not extract text from {pdf_path.name}: {e}")
            return ""
    
    def find_methods_results_sections(self, text: str) -> Tuple[str, str]:
        """Identify methods and results sections in the text."""
        text_lower = text.lower()
        
        # Find methods section
        methods_start = -1
        for keyword in METHODS_SECTION_KEYWORDS:
            pattern = rf'\b{re.escape(keyword)}\b'
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                methods_start = match.start()
                break
        
        # Find results section
        results_start = -1
        for keyword in RESULTS_SECTION_KEYWORDS:
            pattern = rf'\b{re.escape(keyword)}\b'
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                results_start = match.start()
                break
        
        # Extract methods section (from methods to results, or to end if no results)
        if methods_start >= 0:
            if results_start > methods_start:
                methods_text = text[methods_start:results_start]
            else:
                methods_text = text[methods_start:methods_start + 5000]  # First 5000 chars of methods
        else:
            methods_text = ""
        
        # Extract results section
        if results_start >= 0:
            results_text = text[results_start:results_start + 5000]  # First 5000 chars of results
        else:
            results_text = ""
        
        return methods_text, results_text
    
    def detect_models(self, text: str, methods_text: str, results_text: str) -> Set[str]:
        """Detect which models are mentioned, focusing on methods/results sections."""
        detected_models = set()
        
        # Combine methods and results for primary model detection
        primary_text = (methods_text + " " + results_text).lower()
        
        # Check each model pattern
        for model_name, patterns in MODEL_PATTERNS.items():
            for pattern in patterns:
                # Check in primary sections first
                if re.search(pattern, primary_text, re.IGNORECASE):
                    detected_models.add(model_name)
                    break
                # Also check full text as fallback
                elif re.search(pattern, text.lower(), re.IGNORECASE):
                    detected_models.add(model_name)
                    break
        
        return detected_models
    
    def detect_fields(self, text: str) -> Set[str]:
        """Detect medical fields based on keyword matching."""
        detected_fields = set()
        text_lower = text.lower()
        
        for field_name, keywords in FIELD_KEYWORDS.items():
            for keyword in keywords:
                pattern = rf'\b{re.escape(keyword)}\b'
                if re.search(pattern, text_lower, re.IGNORECASE):
                    detected_fields.add(field_name)
                    break
        
        return detected_fields
    
    def process_all_papers(self) -> Tuple[Dict[str, List[Path]], Dict[str, List[Path]]]:
        """Process all PDFs and extract models and fields."""
        model_to_papers = defaultdict(list)
        field_to_papers = defaultdict(list)
        
        pdf_files = list(self.all_papers_dir.glob('*.pdf'))
        total = len(pdf_files)
        
        print(f"\nProcessing {total} papers...")
        print("=" * 60)
        
        for i, pdf_path in enumerate(pdf_files, 1):
            print(f"[{i}/{total}] Processing: {pdf_path.name}")
            
            # Extract text
            text = self.extract_text_from_pdf(pdf_path)
            if not text:
                print(f"  ⚠️  Could not extract text, skipping")
                continue
            
            # Find sections
            methods_text, results_text = self.find_methods_results_sections(text)
            
            # Detect models
            models = self.detect_models(text, methods_text, results_text)
            if models:
                print(f"  📊 Models detected: {', '.join(sorted(models))}")
                for model in models:
                    model_to_papers[model].append(pdf_path)
            else:
                print(f"  📊 No models detected")
                model_to_papers['unknown'].append(pdf_path)
            
            # Detect fields
            fields = self.detect_fields(text)
            if fields:
                print(f"  🏥 Fields detected: {', '.join(sorted(fields))}")
                for field in fields:
                    field_to_papers[field].append(pdf_path)
            else:
                print(f"  🏥 No fields detected")
                field_to_papers['unknown'].append(pdf_path)
        
        return dict(model_to_papers), dict(field_to_papers)
    
    def sort_by_model(self, model_to_papers: Dict[str, List[Path]]):
        """Sort papers into model folders."""
        print("\n" + "=" * 60)
        print("Sorting papers by model...")
        print("=" * 60)
        
        for model, papers in model_to_papers.items():
            # Create model folder
            model_folder = self.by_model_dir / model.replace(' ', '_')
            model_folder.mkdir(exist_ok=True)
            
            print(f"\n📁 Model: {model} ({len(papers)} papers)")
            
            for paper in papers:
                dest_path = model_folder / paper.name
                if not dest_path.exists():
                    shutil.copy2(paper, dest_path)
                    print(f"  ✓ Copied: {paper.name}")
                else:
                    print(f"  ⊙ Already exists: {paper.name}")
    
    def report_field_statistics(self, field_to_papers: Dict[str, List[Path]]):
        """Report field statistics to terminal."""
        print("\n" + "=" * 60)
        print("FIELD DETECTION STATISTICS")
        print("=" * 60)
        print("\nDetected fields and paper counts:\n")
        
        # Sort by count descending
        sorted_fields = sorted(field_to_papers.items(), key=lambda x: len(x[1]), reverse=True)
        
        for field, papers in sorted_fields:
            print(f"  {field:20s}: {len(papers):3d} papers")
        
        print("\n" + "=" * 60)
        print("NOTE: Papers can belong to multiple fields.")
        print("=" * 60)
    
    def sort_by_field(self, field_to_papers: Dict[str, List[Path]]):
        """Sort papers into field folders (automatically creates folders for all detected fields)."""
        print("\n" + "=" * 60)
        print("Sorting papers by field...")
        print("=" * 60)
        
        # Filter out 'unknown' field if it exists
        fields_to_process = {k: v for k, v in field_to_papers.items() if k != 'unknown'}
        
        if not fields_to_process:
            print("No fields detected to sort.")
            return
        
        print(f"Creating folders and sorting papers for {len(fields_to_process)} fields...\n")
        
        for field, papers in fields_to_process.items():
            # Create field folder
            field_folder = self.by_field_dir / field
            field_folder.mkdir(exist_ok=True)
            
            print(f"📁 Field: {field} ({len(papers)} papers)")
            
            for paper in papers:
                dest_path = field_folder / paper.name
                if not dest_path.exists():
                    shutil.copy2(paper, dest_path)
                    print(f"  ✓ Copied: {paper.name}")
                else:
                    print(f"  ⊙ Already exists: {paper.name}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sort PDF papers by model and field')
    # Default to script's directory (NLP_review)
    default_base_dir = str(SCRIPT_DIR)
    parser.add_argument('--base-dir', type=str, default=default_base_dir,
                        help='Base directory containing all_papers, by_model, by_field folders')
    parser.add_argument('--models-only', action='store_true',
                        help='Only sort by models (skip field analysis)')
    parser.add_argument('--fields-only', action='store_true',
                        help='Only sort by fields (skip model sorting)')
    parser.add_argument('--skip-analysis', action='store_true',
                        help='Skip field analysis (assume folders already exist)')
    
    args = parser.parse_args()
    
    # Resolve base directory
    base_dir = Path(args.base_dir).resolve()
    if not (base_dir / 'all_papers').exists():
        print(f"Error: 'all_papers' directory not found in {base_dir}")
        return
    
    sorter = PaperSorter(str(base_dir))
    
    # Process papers
    if not args.fields_only:
        model_to_papers, field_to_papers = sorter.process_all_papers()
        
        # Sort by model
        if not args.models_only:
            sorter.sort_by_model(model_to_papers)
        
        # Report field statistics and sort by field
        if not args.models_only and not args.skip_analysis:
            sorter.report_field_statistics(field_to_papers)
            # Automatically sort papers into field folders
            sorter.sort_by_field(field_to_papers)
    else:
        # Fields-only mode: need to reprocess to get field mappings
        if args.skip_analysis:
            print("Error: --fields-only requires paper processing. Remove --skip-analysis")
            return
        _, field_to_papers = sorter.process_all_papers()
        sorter.sort_by_field(field_to_papers)


if __name__ == '__main__':
    main()



