#!/usr/bin/env python3
"""
Script to remove <p> and </p> HTML tags from RN fields in RIS file.

Inputs:
- missing_neurocritical_critical_care_emergency_triage.txt in this script's directory.

Outputs:
- In-place updated missing_neurocritical_critical_care_emergency_triage.txt in this script's directory.
"""

import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ris_file = SCRIPT_DIR / "missing_neurocritical_critical_care_emergency_triage.txt"

# Read the file
with open(ris_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to match RN lines with <p> tags
# Match: RN  - <p>content</p>
# Replace with: RN  - content
pattern = r'^(RN  - )<p>(.*?)</p>$'

def remove_p_tags(match):
    """Remove <p> and </p> tags from RN field"""
    prefix = match.group(1)  # "RN  - "
    content = match.group(2)  # The content between the tags
    return f"{prefix}{content}"

# Use multiline mode to match ^ and $ correctly
updated_content = re.sub(pattern, remove_p_tags, content, flags=re.MULTILINE)

# Count how many were replaced
count = len(re.findall(pattern, content, flags=re.MULTILINE))

# Write the updated content back
with open(ris_file, 'w', encoding='utf-8') as f:
    f.write(updated_content)

print(f"Removed <p> and </p> tags from {count} RN fields")











