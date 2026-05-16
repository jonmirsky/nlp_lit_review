# Move Endnote Folder to OneDrive - Instructions

## All Code Paths Updated ✓

All hardcoded paths have been updated to point to OneDrive:
- `visualizer_nlp_lit_review/config.py` ✓
- `visualizer_nlp_lit_review/scripts/prepare_pdfs_for_github.py` ✓
- `post_zotero_endnote_paper_pull/prep_merge_ris_to_source_ris.py` ✓
- `post_zotero_endnote_paper_pull/convert_ris_to_absolute_paths.py` ✓

## Move Command

**IMPORTANT**: Ensure OneDrive is synced and has enough space before moving.

```bash
# 1. Ensure OneDrive destination folder exists
mkdir -p "/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review"

# 2. Move the Endnote folder
mv "/Users/jon/Documents/badjatia_hu/Endnote" \
   "/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote"

# 3. Verify the move
ls -la "/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/NLP_lit_review/Endnote"
```

## After Moving

1. **Verify OneDrive syncs the folder** - Check OneDrive status
2. **Test scripts**:
   - Run `prep_merge_ris_to_source_ris.py` to verify it finds search_term_results
   - Run `prepare_pdfs_for_github.py` to verify it finds NLP_v4.Data
3. **Check visualizer website** - Should still work (uses R2, not local files)

## Expected Savings

Moving Endnote folder (~6 GB) will reduce badjatia_hu from ~16 GB to ~10 GB.

## Notes

- OneDrive must be synced when running scripts that access these files
- The visualizer website uses R2, so it doesn't need local files
- All scripts now point to OneDrive location

