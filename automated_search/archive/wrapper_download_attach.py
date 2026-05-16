#!/usr/bin/env python3
"""
Wrapper script to run download and attach scripts in sequence.
"""

import subprocess
import sys
from pathlib import Path

def main():
    script_dir = Path(__file__).parent
    
    print("=" * 70)
    print("Download and Attach Workflow")
    print("=" * 70)
    print()
    
    # Step 1: Run download script
    print("Step 1: Running download script...")
    print("-" * 70)
    download_script = script_dir / "first_pdf_scrape_PMID.py"
    
    result = subprocess.run([sys.executable, str(download_script)])
    
    if result.returncode != 0:
        print("\n" + "=" * 70)
        print("Download script failed. Not running attach script.")
        print("=" * 70)
        sys.exit(result.returncode)
    
    print("\n" + "=" * 70)
    print("Download script completed successfully.")
    print("=" * 70)
    print()
    
    # Step 2: Run attach script
    print("Step 2: Running attach script...")
    print("-" * 70)
    attach_script = script_dir / "attach_files_to_endnote.py"
    
    result = subprocess.run([sys.executable, str(attach_script)])
    
    print("\n" + "=" * 70)
    if result.returncode == 0:
        print("Both scripts completed successfully!")
    else:
        print(f"Attach script exited with code {result.returncode}")
    print("=" * 70)
    
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()




