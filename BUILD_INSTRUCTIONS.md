# Building Standalone App

This document explains how to build the Literature Review Visualizer as a standalone executable for Mac and Windows.

## Prerequisites

1. **Python 3.8+** installed
2. **Node.js and npm** installed (for building React frontend)
3. **All Python dependencies** installed:
   ```bash
   pip install -r requirements_lit_review_visualizer.txt
   ```

## Building for Mac

1. Open Terminal
2. Navigate to the project directory:
   ```bash
   cd /path/to/visualizer_nlp_lit_review
   ```
3. Run the build script:
   ```bash
   ./build_mac.sh
   ```
4. The build process will:
   - Build the React frontend
   - Package everything with PyInstaller
   - Create a distribution zip file in `dist/LiteratureReviewVisualizer_Mac.zip`

## Building for Windows

1. Open Command Prompt or PowerShell
2. Navigate to the project directory:
   ```cmd
   cd C:\path\to\visualizer_nlp_lit_review
   ```
3. Run the build script:
   ```cmd
   build_windows.bat
   ```
4. The build process will:
   - Build the React frontend
   - Package everything with PyInstaller
   - Create a distribution zip file in `dist\LiteratureReviewVisualizer_Windows.zip`

## Manual Build (Alternative)

If the build scripts don't work, you can build manually:

1. **Build React frontend:**
   ```bash
   npm run build
   ```

2. **Run PyInstaller:**
   ```bash
   pyinstaller visualizer.spec --clean
   ```

3. **Package the distribution:**
   - Copy the executable from `dist/` to a new folder
   - Include a README with usage instructions
   - Zip the folder

## Distribution

After building:

1. **Upload to OneDrive:**
   - Upload `dist/LiteratureReviewVisualizer_Mac.zip` (for Mac users)
   - Upload `dist/LiteratureReviewVisualizer_Windows.zip` (for Windows users)

2. **User Instructions:**
   - Download the appropriate zip file for their OS
   - Extract the zip file
   - Double-click the executable to run
   - The app will automatically open in their browser

## Troubleshooting

### Build Fails

- **"npm not found"**: Install Node.js from https://nodejs.org/
- **"pyinstaller not found"**: Run `pip install pyinstaller`
- **"Module not found"**: Make sure all dependencies are installed: `pip install -r requirements_lit_review_visualizer.txt`

### App Doesn't Run

- **Mac**: Right-click the app and select "Open" if you get a security warning
- **Windows**: Add an exception in Windows Defender if it blocks the app
- **Port in use**: The app will automatically find a free port, but if issues persist, check what's using port 5001

### Missing Data Files

- Make sure `RIS_source_files/` folder exists and contains your RIS files
- Make sure `Endnote/from_zotero_v3.Data/` folder exists if you want PDFs included
- These folders should be in the same directory as the executable after building

## File Structure After Build

```
LiteratureReviewVisualizer/
??? LiteratureReviewVisualizer.exe (or .app on Mac)
??? _internal/ (PyInstaller internal files)
??? data/
?   ??? RIS_source_files/
?   ?   ??? pubmed_*.txt
?   ?   ??? manual_groupings/
?   ?       ??? most_cited*.txt
?   ?       ??? most_relevant*.txt
?   ??? Endnote/
?       ??? from_zotero_v3.Data/
?           ??? [PDF files]
??? static/
?   ??? js/
?       ??? main.js
??? templates/
    ??? index.html
```

## Notes

- The first run may take longer as data is loaded
- PDFs are only included if the Endnote data folder exists at build time
- The app runs a local server - no internet connection required after initial setup
- All data stays local - nothing is sent to the internet


