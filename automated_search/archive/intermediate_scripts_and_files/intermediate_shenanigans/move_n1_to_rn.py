#!/usr/bin/env python3
"""
Script to move all information from N1 fields to RN fields in RIS file.

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
    lines = f.readlines()

# Process the file line by line
output_lines = []
i = 0
n1_to_rn_count = 0

while i < len(lines):
    line = lines[i]
    
    # Check if this is an N1 line
    if line.startswith('N1  - '):
        # Extract the content from N1 (everything after "N1  - ")
        n1_content = line[6:].rstrip()
        
        # Look ahead to find the next RN line (should be soon after)
        # We'll update the RN line that comes after this N1
        j = i + 1
        rn_found = False
        
        # Look for RN within the next 10 lines (should be close)
        while j < len(lines) and j < i + 10:
            if lines[j].startswith('RN  - '):
                # Update RN with N1 content
                output_lines.append(f'RN  - {n1_content}\n')
                rn_found = True
                n1_to_rn_count += 1
                # Skip the original RN line
                j += 1
                break
            j += 1
        
        # If we didn't find RN, we'll skip this N1 for now
        if not rn_found:
            # Skip the N1 line (don't add it to output)
            i += 1
            continue
        else:
            i = j
            continue
    
    # For all other lines, just add them as-is
    output_lines.append(line)
    i += 1

# Write the updated content
with open(ris_file, 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

print(f"Updated {n1_to_rn_count} RN fields with content from N1 fields")
print(f"Removed {n1_to_rn_count} N1 fields")











