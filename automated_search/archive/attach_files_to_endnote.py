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
    except Exception as e:
        # Silently fail - Esc detection won't work but script continues
        pass


def get_latest_import_map():
    """
    Find the latest import_map#.txt file in import_IDs folder.
    Returns Path to the file, or None if not found.
    """
    if not IMPORT_IDS_DIR.exists():
        return None
    
    # Pattern to match import_map#.txt files
    pattern = re.compile(r'^import_map(\d+)\.txt$')
    
    max_number = 0
    latest_file = None
    
    # Check all files in the directory
    for file_path in IMPORT_IDS_DIR.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                number = int(match.group(1))
                if number > max_number:
                    max_number = number
                    latest_file = file_path
    
    return latest_file


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
    
    try:
        # Step 1: Press Cmd+F (search)
        pyautogui.hotkey('command', 'f')
        time.sleep(0.3)
        
        if abort_flag:
            return False
        
        # Step 2: Clear search field and type Record Number
        pyautogui.hotkey('command', 'a')  # Select all in search field
        time.sleep(0.1)
        pyautogui.write(record_number, interval=0.05)  # Type new number (replaces selected text)
        time.sleep(0.2)
        pyautogui.press('enter')
        time.sleep(0.5)
        
        if abort_flag:
            return False
        
        # Step 4: Press Tab then Enter (open record)
        pyautogui.press('tab')
        time.sleep(0.2)
        pyautogui.press('enter')
        time.sleep(0.5)
        
        if abort_flag:
            return False
        
        # Step 5: Press Cmd+Shift+A (attach file)
        pyautogui.hotkey('command', 'shift', 'a')
        time.sleep(0.5)
        
        if abort_flag:
            return False
        
        # Step 6: Press Cmd+Shift+G (Go to Folder)
        pyautogui.hotkey('command', 'shift', 'g')
        time.sleep(2.5)  # Wait even longer for dialog to fully appear and be ready
        
        if abort_flag:
            return False
        
        # Step 7: Click in the dialog input field to ensure it has focus
        # The dialog typically appears near center of screen
        screen_width, screen_height = pyautogui.size()
        # Click slightly above center (where the input field usually is)
        pyautogui.click(screen_width // 2, screen_height // 2 - 50)
        time.sleep(0.5)
        
        if abort_flag:
            return False
        
        # Step 8: Clear any existing text first, then type the full file path
        pyautogui.hotkey('command', 'a')  # Select all to clear any existing text
        time.sleep(0.6)  # Wait for selection to complete
        # Type the path character by character with small delays
        for char in file_path:
            pyautogui.write(char)
            time.sleep(0.01)  # Small delay between each character
        time.sleep(1.5)  # Wait longer for typing to complete - ensure all characters are entered
        
        if abort_flag:
            return False
        
        # Step 9: Press Enter to navigate to the file (first Enter)
        # This closes the "Go to Folder" dialog and navigates to the file
        # Wait a moment to ensure typing is fully complete before pressing Enter
        time.sleep(1.0)  # Extra pause before Enter to ensure typing is done
        pyautogui.press('enter')
        time.sleep(2.5)  # Wait longer for navigation to complete and file to be selected
        
        if abort_flag:
            return False
        
        # Step 10: Press Enter again to confirm/open the selected file
        # This opens/attaches the file
        pyautogui.press('enter')
        time.sleep(1.5)  # Wait longer for file to attach - save dialog appears here
        
        if abort_flag:
            return False
        
        # Step 10: Handle "Save changes to the record?" dialog - press Return to Save
        # The Save button is the default (blue), so Return will select it
        # This dialog appears immediately after attaching the file
        pyautogui.press('return')
        time.sleep(1.0)  # Wait longer for save to complete
        
        if abort_flag:
            return False
        
        # Step 11: Close the record window (Cmd+W)
        pyautogui.hotkey('command', 'w')
        time.sleep(1.0)  # Wait longer - save dialog may appear again when closing
        
        if abort_flag:
            return False
        
        # Step 12: Handle "Save changes to the record?" dialog if it appears when closing window
        # This can happen when closing the window if changes weren't saved yet
        # Press Return to Save (Save is the default button)
        pyautogui.press('return')
        time.sleep(0.8)  # Wait for dialog to close
        
        # Step 13: Press Escape to clear any field selection in the main library view
        # This prevents accidental input in fields like Author after closing the record window
        pyautogui.press('escape')
        time.sleep(0.3)
        
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
    
    # Find latest import_map file
    print("Finding latest import_map file...")
    import_map_file = get_latest_import_map()
    
    if not import_map_file:
        print(f"Error: No import_map files found in {IMPORT_IDS_DIR}")
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
