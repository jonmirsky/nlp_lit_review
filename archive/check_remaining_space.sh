#!/bin/bash
# Quick script to check remaining large folders
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "=== Checking folder sizes in $(basename "$SCRIPT_DIR") ==="
echo ""

# Check main folders
for dir in visualizer_nlp_lit_review post_zotero_endnote_paper_pull found_papers archive nbib_files; do
    if [ -d "$dir" ]; then
        size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        echo "$dir: $size"
    fi
done

echo ""
echo "=== Checking for cache/temp files ==="
echo ""

# Check node_modules
if [ -d "visualizer_nlp_lit_review/node_modules" ]; then
    size=$(du -sh "visualizer_nlp_lit_review/node_modules" 2>/dev/null | cut -f1)
    echo "node_modules: $size"
fi

# Check __pycache__ folders
find . -type d -name "__pycache__" -exec du -sh {} \; 2>/dev/null | head -5

echo ""
echo "=== Checking post_zotero_endnote_paper_pull/found_papers ==="
if [ -d "post_zotero_endnote_paper_pull/found_papers" ]; then
    size=$(du -sh "post_zotero_endnote_paper_pull/found_papers" 2>/dev/null | cut -f1)
    pdf_count=$(find "post_zotero_endnote_paper_pull/found_papers" -name "*.pdf" 2>/dev/null | wc -l)
    echo "Size: $size"
    echo "PDF count: $pdf_count"
fi

