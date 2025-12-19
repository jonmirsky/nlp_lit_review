"""
Launcher script for Literature Review Visualizer standalone app
Handles path setup, starts Flask server, and opens browser automatically
"""

import sys
import os
import threading
import webbrowser
import time
import signal
from pathlib import Path


def get_base_path():
    """Get base path - works for both PyInstaller bundle and normal execution"""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        # sys.executable is the path to the executable
        return Path(sys.executable).parent
    else:
        # Running as normal script
        return Path(__file__).parent


def find_free_port(start_port=5001):
    """Find a free port starting from start_port"""
    import socket
    port = start_port
    while port < start_port + 100:  # Try up to 100 ports
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            port += 1
    raise RuntimeError(f"Could not find a free port starting from {start_port}")


def open_browser(url, delay=2):
    """Open browser after a delay"""
    time.sleep(delay)
    try:
        webbrowser.open(url)
        print(f"Opened browser at {url}")
    except Exception as e:
        print(f"Warning: Could not open browser automatically: {e}")
        print(f"Please manually open: {url}")


def main():
    """Main launcher function"""
    base_path = get_base_path()
    
    # Set environment variable for config to use
    os.environ['VISUALIZER_BASE_PATH'] = str(base_path)
    
    # Add base_path to Python path so imports work
    if str(base_path) not in sys.path:
        sys.path.insert(0, str(base_path))
    
    # Change to base_path directory
    os.chdir(base_path)
    
    # Find a free port
    try:
        port = find_free_port(5001)
    except RuntimeError as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Set port in environment
    os.environ['PORT'] = str(port)
    
    print("=" * 60)
    print("Literature Review Visualizer")
    print("=" * 60)
    print(f"Base path: {base_path}")
    print(f"Starting server on port {port}...")
    print("=" * 60)
    
    # Import Flask app (must be after path setup)
    try:
        from app import app, load_data
    except ImportError as e:
        print(f"Error importing app: {e}")
        print("Make sure all required files are present.")
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Load data in background (this might take a while)
    print("Loading data...")
    try:
        load_data()
    except Exception as e:
        print(f"Error loading data: {e}")
        print("The app may still work, but some features might be unavailable.")
        import traceback
        traceback.print_exc()
    
    # Start browser opening in background thread
    url = f"http://127.0.0.1:{port}/"
    browser_thread = threading.Thread(target=open_browser, args=(url,), daemon=True)
    browser_thread.start()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n\nShutting down server...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    # Run Flask app
    try:
        print(f"\nServer running at {url}")
        print("Press Ctrl+C to stop the server\n")
        app.run(debug=False, host='127.0.0.1', port=port, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
    except Exception as e:
        print(f"\nError running server: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == '__main__':
    main()


