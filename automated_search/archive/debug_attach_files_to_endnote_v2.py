#!/usr/bin/env python3
"""
EndNote File Attachment Automation Script

Automates attaching PDF files to EndNote records by reading import_map files
and using keyboard shortcuts to search, open records, and attach files.
"""

import re
import time
import subprocess
import threading
from pathlib import Path
import pyautogui
import pandas as pd
import keyboard  # For Esc key detection

# Configuration
IMPORT_IDS_DIR = Path(__file__).parent / "found_papers" / "import_IDs"
ENDNOTE_APP = "EndNote 2025"

# Global abort flag
abort_flag = False


def check_abort():
    """Poll for Esc key press to abort (runs in background thread)."""
    global abort_flag
    try:
        # Note: keyboard library requires admin privileges on macOS
        # If this fails, Esc detection won't work but script will continue
        while not abort_flag:
            if keyboard.is_pressed('esc'):
                abort_flag = True
                print("\n\nABORTED by user (Esc pressed)!")
                break
            time.sleep(0.05)  # Poll every 50ms
    except OSError as e:
        # keyboard library requires admin privileges on macOS
        print("\nWARNING: Esc key abort detection is not available (requires admin privileges)")
        print("         The script will continue, but you cannot abort with Esc.")
        print("         To enable Esc abort, run the script with sudo or grant accessibility permissions.")
    except Exception as e:
        # Other errors - show them
        print(f"\nWARNING: Esc key abort detection error: {e}")
        print("         The script will continue, but Esc abort may not work.")


def get_latest_import_map():
    """
    Find the latest import map file in import_IDs folder.
    Handles both naming schemes:
    - Old format: import_map#.txt (e.g., import_map31.txt)
    - New format: import_{#}_of_{#}_of_{#}.txt (e.g., import_196_of_196_of_1033.txt)
    
    Returns Path to the file, or None if not found.
    Uses modification time to determine "latest" file.
    """
    if not IMPORT_IDS_DIR.exists():
        return None
    
    # Patterns to match both naming schemes
    old_pattern = re.compile(r'^import_map(\d+)\.txt$')
    new_pattern = re.compile(r'^import_\d+_of_\d+_of_\d+\.txt$')
    
    import_map_files = []
    
    # Check all files in the directory
    for file_path in IMPORT_IDS_DIR.iterdir():
        if file_path.is_file():
            # Check if it matches old format
            old_match = old_pattern.match(file_path.name)
            # Check if it matches new format
            new_match = new_pattern.match(file_path.name)
            
            if old_match or new_match:
                # Get modification time to determine latest
                mtime = file_path.stat().st_mtime
                import_map_files.append((mtime, file_path))
    
    if not import_map_files:
        return None
    
    # Sort by modification time (most recent first) and return the latest
    import_map_files.sort(key=lambda x: x[0], reverse=True)
    return import_map_files[0][1]


def read_import_map(file_path: Path):
    """
    Read import_map file (tab-delimited, no header).
    Returns list of tuples: [(record_number, file_path), ...]
    """
    records = []
    try:
        # Read without header, column 0 = Record Number, column 1 = File Path
        df = pd.read_csv(file_path, sep='\t', header=None, names=['Record_Number', 'File_Path'])
        
        for _, row in df.iterrows():
            record_num = str(row['Record_Number']).strip()
            file_path = str(row['File_Path']).strip()
            if record_num and file_path:
                records.append((record_num, file_path))
        
        return records
    except Exception as e:
        print(f"Error reading import_map file: {e}")
        return []


def activate_endnote():
    """Open EndNote application and bring it to front with focus."""
    try:
        # Use AppleScript to ensure EndNote gets focus
        applescript = f'''
        tell application "{ENDNOTE_APP}"
            activate
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript], check=True)
        time.sleep(2)  # Wait for EndNote to activate and come to front
        
        # Additional verification: ensure EndNote window is active
        # Click on a safe area to ensure focus (center of screen)
        screen_width, screen_height = pyautogui.size()
        pyautogui.click(screen_width // 2, screen_height // 2)
        time.sleep(0.5)
        
        print(f"EndNote activated and focused")
    except Exception as e:
        print(f"Error activating EndNote: {e}")
        return False
    return True


def attach_file_to_record(record_number: str, file_path: str) -> bool:
    """
    Attach a file to an EndNote record using keyboard shortcuts.
    Returns True if successful, False otherwise.
    """
    global abort_flag
    
    if abort_flag:
        return False
    
    # Extract filename from full path (e.g., "3606.pdf" from "/path/to/3606.pdf")
    filename = Path(file_path).name
    
    try:
        # Step 1: Press Cmd+F (search)
        pyautogui.hotkey('command', 'f')
        time.sleep(0.2)
        
        if abort_flag:
            return False
        
        # Step 2: Clear search field and type Record Number
        pyautogui.hotkey('command', 'a')  # Select all in search field
        time.sleep(0.1)
        pyautogui.write(record_number, interval=0.05)  # Type new number (replaces selected text)
        time.sleep(0.2)
        pyautogui.press('enter')
        time.sleep(0.5)  # Wait for search results to appear
        
        if abort_flag:
            return False
        
        # Step 3: Press Tab to move to the record in search results
        pyautogui.press('tab')
        time.sleep(0.2)
        
        if abort_flag:
            return False
        
        # Step 4: Press Enter to open the record
        pyautogui.press('enter')
        time.sleep(0.5)  # Wait for record window to fully open
        
        if abort_flag:
            return False
        
        # Step 5: Press Cmd+Shift+A (attach file - opens Finder window)
        # Use AppleScript to ensure all keys are pressed correctly and simultaneously
        # This prevents accidentally pressing Cmd+A instead of Cmd+Shift+A
        applescript_attach = '''
        tell application "System Events"
            key down command
            key down shift
            key down "a"
            delay 0.1
            key up "a"
            key up shift
            key up command
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript_attach], check=False)
        time.sleep(1.2)  # Wait longer for Finder window to fully appear and be ready
        
        if abort_flag:
            return False
        
        # Step 6: Press Cmd+F in Finder to open search
        # Use AppleScript to ensure the key combination is sent correctly
        applescript_search = '''
        tell application "System Events"
            key down command
            key down "f"
            delay 0.1
            key up "f"
            key up command
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript_search], check=False)
        time.sleep(1.2)  # Wait longer for search field to appear and be ready
        
        if abort_flag:
            return False
        
        # Step 7: Type the filename (e.g., "3606.pdf")
        # Use slower interval to ensure all characters are typed correctly
        # and to avoid triggering macOS accessibility features
        pyautogui.write(filename, interval=0.1)
        time.sleep(0.6)  # Wait for search results to appear
        
        if abort_flag:
            return False
        
        # Step 8: Press down arrow to select first result
        pyautogui.press('down')
        time.sleep(0.2)
        
        if abort_flag:
            return False
        
        # Step 9: Press return, then tab, then down arrow, then return to select and attach
        pyautogui.press('enter')
        time.sleep(0.2)
        
        if abort_flag:
            return False
        
        pyautogui.press('tab')
        time.sleep(0.2)
        
        if abort_flag:
            return False
        
        pyautogui.press('down')
        time.sleep(0.2)
        
        if abort_flag:
            return False
        
        pyautogui.press('enter')
        time.sleep(0.25)  # Wait for file to attach and EndNote to be ready
        
        if abort_flag:
            return False
        
        # Step 10: Press Cmd+S to save the record
        # Use AppleScript to ensure the key combination is sent correctly on macOS
        applescript = '''
        tell application "System Events"
            key down command
            key down "s"
            delay 0.1
            key up "s"
            key up command
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript], check=False)
        time.sleep(0.3)  # Wait for save to complete
        
        if abort_flag:
            return False
        
        # Step 11: Click on library window to ensure it has focus for next search
        # This prevents searching in the reference panel instead of the library
        # Click at specific coordinates (650, 500) in main library window area
        # This targets the main library window, avoiding the group panel on the left
        pyautogui.click(650, 500)
        time.sleep(0.3)  # Brief wait for focus to switch
        
        if abort_flag:
            return False
        
        # Step 12: Press Escape to close the record window and return to library view
        # This is safer than clicking and prevents the Author field from being selected
        # Escape should close the record window without closing the library
        pyautogui.press('escape')
        time.sleep(0.8)  # Wait for record window to close
        
        if abort_flag:
            return False
        
        # Step 12: Press Escape again to ensure we're fully back at the library view
        # and to clear any field selection (like Author field) that might be active
        # This should deselect any fields and ensure we're ready for the next search
        pyautogui.press('escape')
        time.sleep(0.5)  # Wait for any selection to clear
        
        return True
        
    except Exception as e:
        print(f"  Error during attachment: {e}")
        return False


def main():
    global abort_flag
    
    print("=" * 70)
    print("EndNote File Attachment Automation")
    print("=" * 70)
    print()
    
    # Ask user if they want to manually specify import map file
    manual_input = input("Would you like to enter import map file name manually? If not, I will automate. (y/n, default=n): ").strip().lower()
    
    if manual_input == 'y':
        import_map_input = input("Enter import map file name (e.g., import_map31.txt or import_196_of_196_of_1033.txt): ").strip()
        import_map_file = IMPORT_IDS_DIR / import_map_input
        
        if not import_map_file.exists():
            print(f"ERROR: Import map file not found: {import_map_file}")
            return
        print(f"Using import map file: {import_map_file.name}")
    else:
        # Default automated behavior - find latest import map file
        print("Finding latest import map file...")
        import_map_file = get_latest_import_map()
        
        if not import_map_file:
            print(f"ERROR: No import_map files found in {IMPORT_IDS_DIR}")
            return
        print(f"Found: {import_map_file.name}")
    print()
    
    # Read import_map file
    print("Reading import_map file...")
    records = read_import_map(import_map_file)
    
    if not records:
        print("Error: No records found in import_map file")
        return
    
    print(f"Found {len(records)} records to process")
    print()
    
    # Start abort monitoring thread
    print("Starting abort monitoring (press Esc to abort)...")
    abort_thread = threading.Thread(target=check_abort, daemon=True)
    abort_thread.start()
    
    print("\nInstructions:")
    print("1. The script will activate and focus EndNote automatically")
    print("2. Press Esc at any time to abort")
    print("\nStarting in 3 seconds...")
    time.sleep(3)
    
    if abort_flag:
        print("Aborted before starting.")
        return
    
    # Activate EndNote
    if not activate_endnote():
        print("Failed to activate EndNote. Exiting.")
        return
    
    if abort_flag:
        print("Aborted after activating EndNote.")
        return
    
    # Process records
    successful = []
    failed = []
    
    print("\n" + "=" * 70)
    print("Processing records...")
    print("=" * 70)
    print()
    
    for i, (record_number, file_path) in enumerate(records, 1):
        if abort_flag:
            print(f"\nAborted at record {i}/{len(records)}")
            break
        
        print(f"[{i}/{len(records)}] Processing Record {record_number}...", end=" ")
        
        # Verify file exists
        if not Path(file_path).exists():
            print("FAILED (file not found)")
            failed.append((record_number, file_path, "File not found"))
            continue
        
        # Attempt attachment
        success = attach_file_to_record(record_number, file_path)
        
        if success and not abort_flag:
            print("SUCCESS")
            successful.append((record_number, file_path))
        else:
            if abort_flag:
                print("ABORTED")
                break
            else:
                print("FAILED")
                failed.append((record_number, file_path, "Attachment failed"))
        
        # Sleep 2 seconds between records
        if i < len(records) and not abort_flag:
            time.sleep(2)
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total records processed: {len(records)}")
    print(f"Successfully attached: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if successful:
        print(f"\nSuccessful attachments:")
        for record_num, file_path in successful:
            print(f"  Record {record_num}: {Path(file_path).name}")
    
    if failed:
        print(f"\nFailed attachments:")
        for record_num, file_path, reason in failed:
            print(f"  Record {record_num}: {reason}")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
