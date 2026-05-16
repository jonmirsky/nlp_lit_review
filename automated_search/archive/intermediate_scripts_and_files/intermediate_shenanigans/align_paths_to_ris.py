#!/usr/bin/env python3
"""
Script to align paths from import file to RIS entries by ID and add L1 fields.

Inputs:
- import_22_of_72_of_72_full_text_v3.txt in this script's directory.
- missing_neurocritical_critical_care_emergency_triage.txt in this script's directory.

Outputs:
- In-place updated missing_neurocritical_critical_care_emergency_triage.txt in this script's directory.
"""

import re
from pathlib import Path

# Read the import file to get ID -> path mappings
SCRIPT_DIR = Path(__file__).resolve().parent
import_file = SCRIPT_DIR / "import_22_of_72_of_72_full_text_v3.txt"
missing_file = SCRIPT_DIR / "missing_neurocritical_critical_care_emergency_triage.txt"

# Parse import file to create ID -> path dictionary
id_to_path = {}
with open(import_file, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and '\t' in line:
            parts = line.split('\t', 1)
            if len(parts) == 2:
                paper_id = parts[0].strip()
                path = parts[1].strip()
                id_to_path[paper_id] = path

print(f"Loaded {len(id_to_path)} ID -> path mappings")

# Read the missing file and update it
with open(missing_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to match ID lines: "ID  - <number>"
# We'll insert L1 right after the ID line if we have a matching path
id_pattern = r'^(ID  - (\d+))$'

def replace_id_with_id_and_l1(match):
    """Replace ID line with ID line + L1 line if path exists"""
    full_match = match.group(0)
    paper_id = match.group(2)
    
    if paper_id in id_to_path:
        path = id_to_path[paper_id]
        return f"{full_match}\nL1  - {path}"
    return full_match

# Use multiline mode to match ^ and $ correctly
updated_content = re.sub(id_pattern, replace_id_with_id_and_l1, content, flags=re.MULTILINE)

# Write the updated content back
with open(missing_file, 'w', encoding='utf-8') as f:
    f.write(updated_content)

print(f"Updated {missing_file} with L1 fields for matching IDs")
print(f"Matched {sum(1 for id in id_to_path.keys() if f'ID  - {id}' in content)} IDs")
