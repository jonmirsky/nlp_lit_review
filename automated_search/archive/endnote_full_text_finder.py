import keyboard  # Requires: pip install keyboard
import time
import threading

# --- CONFIGURATION ---
BATCH_SIZE = 250  # How many papers to select
# ---------------------

# Global flag for abort
abort_flag = False

def check_abort():
    """Poll for Esc key press to abort (less intrusive than keyboard.wait)"""
    global abort_flag
    try:
        while not abort_flag:
            if keyboard.is_pressed('esc'):
                abort_flag = True
                print("\n\nABORTED! Releasing shift key...")
                break
            time.sleep(0.05)  # Poll every 50ms
    except:
        pass  # Clean exit if keyboard hook fails

print("--- INSTRUCTIONS ---")
print(f"1. Open EndNote and click the FIRST paper in your batch.")
print(f"2. Make sure the EndNote window is active.")
print(f"3. Do not touch the mouse/keyboard.")
print(f"4. Press 'Esc' at any time to abort.")
print(f"Script starting in 5 seconds...")

# Start abort monitoring thread (using polling instead of blocking wait)
abort_thread = threading.Thread(target=check_abort, daemon=True)
abort_thread.start()

# Give you time to switch windows - with abort option
for i in range(5, 0, -1):
    if abort_flag:
        print("\nAborted by user.")
        exit()
    print(f"Starting in {i}... (Press Esc to abort)", end='\r')
    time.sleep(1)

if abort_flag:
    print("\nAborted by user.")
    exit()

print(f"\nSelecting {BATCH_SIZE} papers...")
start_time = time.time()
last_timing_check = start_time

# The "Robotic" Selection Logic - Using keyboard library directly for reliable shift holding
try:
    # Hold shift down FIRST using keyboard library (more reliable than pyautogui)
    keyboard.press('shift')
    time.sleep(0.02)  # Small pause to ensure shift is registered by EndNote
    
    # Press down arrow multiple times while shift is held
    # Optimized for maximum speed - minimal delays
    for i in range(BATCH_SIZE-1):
        # Check for abort every 20 presses (faster - less overhead)
        if i % 20 == 0 and abort_flag:
            keyboard.release('shift')  # Release shift before aborting
            print(f"\n\nAborted! Selected {i+1} papers before stopping (started with 1).")
            exit()
        
        # Timing diagnostics - check speed every 50 papers
        if i > 0 and i % 50 == 0:
            current_time = time.time()
            elapsed = current_time - last_timing_check
            rate = 50 / elapsed if elapsed > 0 else 0
            print(f"Progress: {i+1}/{BATCH_SIZE-1} papers | Rate: {rate:.1f} papers/sec", end='\r')
            last_timing_check = current_time
        
        # Press and release down arrow while shift is still held
        keyboard.press_and_release('down')
        
        # Minimal delay - only every 10 presses
        # If EndNote starts missing selections, reduce this interval
        if i % 10 == 0:
            time.sleep(0.0003)  # Ultra-tiny delay every 10 presses (0.3ms)
    
    # Release shift AFTER all keypresses
    time.sleep(0.02)  # Small pause before releasing
    keyboard.release('shift')
    
    if not abort_flag:
        elapsed = time.time() - start_time
        print(f"\nDone! Selected {BATCH_SIZE} papers in {elapsed:.2f} seconds.")
        print("Right-click the selection and 'Find Full Text'.")
    
except KeyboardInterrupt:
    keyboard.release('shift')  # Make sure shift is released
    print("\n\nAborted by user (Ctrl+C).")
except Exception as e:
    keyboard.release('shift')  # Make sure shift is released
    print(f"\n\nError: {e}")