#!/bin/bash
# Backup script for Endnote consolidation
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

BACKUP_DIR="$SCRIPT_DIR/backup_endnote_consolidation_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "Creating backup in: $BACKUP_DIR"

# Backup RIS file
if [ -f "visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_12_17_25_1114am.txt" ]; then
    cp "visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_12_17_25_1114am.txt" \
       "$BACKUP_DIR/pubmed_NLP_v4_12_17_25_1114am.txt.backup"
    echo "✓ RIS file backed up"
else
    echo "⚠ Warning: RIS file not found"
fi

# Backup config files
mkdir -p "$BACKUP_DIR/visualizer_config"
if [ -f "visualizer_nlp_lit_review/config.py" ]; then
    cp "visualizer_nlp_lit_review/config.py" "$BACKUP_DIR/visualizer_config/" && echo "✓ config.py backed up"
fi
if [ -f "visualizer_nlp_lit_review/pdf_resolver.py" ]; then
    cp "visualizer_nlp_lit_review/pdf_resolver.py" "$BACKUP_DIR/visualizer_config/" && echo "✓ pdf_resolver.py backed up"
fi
if [ -f "visualizer_nlp_lit_review/scripts/prepare_pdfs_for_github.py" ]; then
    cp "visualizer_nlp_lit_review/scripts/prepare_pdfs_for_github.py" "$BACKUP_DIR/visualizer_config/" && echo "✓ prepare_pdfs_for_github.py backed up"
fi

# Backup Endnote libraries
mkdir -p "$BACKUP_DIR/Endnote"
if [ -d "Endnote/NLP_v4.Data" ]; then
    echo "Backing up NLP_v4.Data (this may take a few minutes)..."
    cp -r "Endnote/NLP_v4.Data" "$BACKUP_DIR/Endnote/" && echo "✓ NLP_v4.Data backed up"
fi
if [ -f "Endnote/NLP_v4.enl" ]; then
    cp "Endnote/NLP_v4.enl" "$BACKUP_DIR/Endnote/" && echo "✓ NLP_v4.enl backed up"
fi
if [ -d "Endnote/from_zotero_v3.Data" ]; then
    echo "Backing up from_zotero_v3.Data (this may take several minutes - large directory)..."
    cp -r "Endnote/from_zotero_v3.Data" "$BACKUP_DIR/Endnote/" && echo "✓ from_zotero_v3.Data backed up"
fi
if [ -f "Endnote/from_zotero_v3.enl" ]; then
    cp "Endnote/from_zotero_v3.enl" "$BACKUP_DIR/Endnote/" && echo "✓ from_zotero_v3.enl backed up"
fi
if [ -d "Endnote/NLP_favorites.Data" ]; then
    cp -r "Endnote/NLP_favorites.Data" "$BACKUP_DIR/Endnote/" 2>/dev/null && echo "✓ NLP_favorites.Data backed up" || true
fi
if [ -f "Endnote/NLP_favorites.enl" ]; then
    cp "Endnote/NLP_favorites.enl" "$BACKUP_DIR/Endnote/" 2>/dev/null && echo "✓ NLP_favorites.enl backed up" || true
fi
if [ -d "Endnote/NLP_v6.Data" ]; then
    cp -r "Endnote/NLP_v6.Data" "$BACKUP_DIR/Endnote/" 2>/dev/null && echo "✓ NLP_v6.Data backed up" || true
fi
if [ -f "Endnote/NLP_v6.enl" ]; then
    cp "Endnote/NLP_v6.enl" "$BACKUP_DIR/Endnote/" 2>/dev/null && echo "✓ NLP_v6.enl backed up" || true
fi

# Create manifest
echo "Backup created: $(date)" > "$BACKUP_DIR/BACKUP_MANIFEST.txt"
echo "Backup location: $BACKUP_DIR" >> "$BACKUP_DIR/BACKUP_MANIFEST.txt"
echo "" >> "$BACKUP_DIR/BACKUP_MANIFEST.txt"
echo "Backup contents:" >> "$BACKUP_DIR/BACKUP_MANIFEST.txt"
du -sh "$BACKUP_DIR" >> "$BACKUP_DIR/BACKUP_MANIFEST.txt"
echo "" >> "$BACKUP_DIR/BACKUP_MANIFEST.txt"
find "$BACKUP_DIR" -type f | wc -l | xargs echo "Total files:" >> "$BACKUP_DIR/BACKUP_MANIFEST.txt"

echo ""
echo "Backup complete: $BACKUP_DIR"
echo "Manifest saved to: $BACKUP_DIR/BACKUP_MANIFEST.txt"




