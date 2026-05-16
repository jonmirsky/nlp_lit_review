#!/bin/bash
# Restore from backup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

BACKUP_DIR="$1"  # Pass backup directory as argument

if [ -z "$BACKUP_DIR" ]; then
    echo "Usage: $0 <backup_directory>"
    echo "Example: $0 $SCRIPT_DIR/backup_endnote_consolidation_20250117_143022"
    exit 1
fi

if [ ! -d "$BACKUP_DIR" ]; then
    echo "Error: Backup directory not found: $BACKUP_DIR"
    exit 1
fi

echo "Restoring from: $BACKUP_DIR"
read -p "This will overwrite current files. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled"
    exit 1
fi

# Restore RIS file
if [ -f "$BACKUP_DIR/pubmed_NLP_v4_12_17_25_1114am.txt.backup" ]; then
    cp "$BACKUP_DIR/pubmed_NLP_v4_12_17_25_1114am.txt.backup" \
       "visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_12_17_25_1114am.txt"
    echo "✓ RIS file restored"
fi

# Restore config files
if [ -d "$BACKUP_DIR/visualizer_config" ]; then
    cp "$BACKUP_DIR/visualizer_config/config.py" "visualizer_nlp_lit_review/" 2>/dev/null && echo "✓ config.py restored"
    cp "$BACKUP_DIR/visualizer_config/pdf_resolver.py" "visualizer_nlp_lit_review/" 2>/dev/null && echo "✓ pdf_resolver.py restored"
    cp "$BACKUP_DIR/visualizer_config/prepare_pdfs_for_github.py" "visualizer_nlp_lit_review/scripts/" 2>/dev/null && echo "✓ prepare_pdfs_for_github.py restored"
fi

# Restore Endnote libraries
if [ -d "$BACKUP_DIR/Endnote" ]; then
    [ -d "$BACKUP_DIR/Endnote/NLP_v4.Data" ] && rm -rf "Endnote/NLP_v4.Data" && cp -r "$BACKUP_DIR/Endnote/NLP_v4.Data" "Endnote/" && echo "✓ NLP_v4.Data restored"
    [ -f "$BACKUP_DIR/Endnote/NLP_v4.enl" ] && cp "$BACKUP_DIR/Endnote/NLP_v4.enl" "Endnote/" && echo "✓ NLP_v4.enl restored"
    [ -d "$BACKUP_DIR/Endnote/from_zotero_v3.Data" ] && rm -rf "Endnote/from_zotero_v3.Data" && cp -r "$BACKUP_DIR/Endnote/from_zotero_v3.Data" "Endnote/" && echo "✓ from_zotero_v3.Data restored"
    [ -f "$BACKUP_DIR/Endnote/from_zotero_v3.enl" ] && cp "$BACKUP_DIR/Endnote/from_zotero_v3.enl" "Endnote/" && echo "✓ from_zotero_v3.enl restored"
fi

echo "Restore complete"




