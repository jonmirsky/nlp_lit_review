#!/bin/bash
# Build script for Mac standalone app

set -e  # Exit on error

echo "=========================================="
echo "Building Literature Review Visualizer"
echo "Platform: macOS"
echo "=========================================="

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Step 1: Build React frontend
echo ""
echo "Step 1: Building React frontend..."
if ! command -v npm &> /dev/null; then
    echo "Error: npm is not installed. Please install Node.js and npm."
    exit 1
fi

npm run build

if [ ! -f "static/js/main.js" ]; then
    echo "Error: React build failed. static/js/main.js not found."
    exit 1
fi

echo "? React frontend built successfully"

# Step 2: Check for required files
echo ""
echo "Step 2: Checking required files..."

REQUIRED_FILES=(
    "launcher.py"
    "app.py"
    "config.py"
    "ris_parser.py"
    "pdf_resolver.py"
    "overlap_calculator.py"
    "templates/index.html"
    "static/js/main.js"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "Error: Required file not found: $file"
        exit 1
    fi
done

echo "? All required files present"

# Step 3: Check for PyInstaller
echo ""
echo "Step 3: Checking PyInstaller..."
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: PyInstaller is not installed."
    echo "Please install it with: pip install pyinstaller"
    exit 1
fi

echo "? PyInstaller found"

# Step 4: Build with PyInstaller
echo ""
echo "Step 4: Building executable with PyInstaller..."
echo "This may take several minutes..."

# Clean previous builds
rm -rf build dist

# Run PyInstaller
pyinstaller visualizer.spec --clean

if [ ! -d "dist/LiteratureReviewVisualizer.app" ] && [ ! -f "dist/LiteratureReviewVisualizer" ]; then
    echo "Error: Build failed. Executable not found in dist/"
    exit 1
fi

echo "? Executable built successfully"

# Step 5: Create distribution package
echo ""
echo "Step 5: Creating distribution package..."

DIST_NAME="LiteratureReviewVisualizer_Mac"
DIST_DIR="dist/${DIST_NAME}"

# Clean previous distribution
rm -rf "$DIST_DIR"

# Create distribution directory
mkdir -p "$DIST_DIR"

# Copy executable
if [ -d "dist/LiteratureReviewVisualizer.app" ]; then
    cp -r "dist/LiteratureReviewVisualizer.app" "$DIST_DIR/"
    echo "? Copied .app bundle"
elif [ -f "dist/LiteratureReviewVisualizer" ]; then
    cp "dist/LiteratureReviewVisualizer" "$DIST_DIR/"
    echo "? Copied executable"
fi

# Create README
cat > "$DIST_DIR/README.txt" << 'EOF'
Literature Review Visualizer - Mac Version
==========================================

INSTRUCTIONS:
1. Double-click "LiteratureReviewVisualizer.app" to run
2. The app will automatically open in your default web browser
3. If the browser doesn't open automatically, go to: http://127.0.0.1:5001/

TROUBLESHOOTING:
- If you get a security warning, right-click the app and select "Open"
- Make sure you have an internet connection for the first run (to verify certificates)
- The app runs a local server - no data is sent to the internet

For support, contact the developer.
EOF

echo "? Created README.txt"

# Create zip file
cd dist
zip -r "${DIST_NAME}.zip" "${DIST_NAME}" > /dev/null
cd ..

echo ""
echo "=========================================="
echo "Build completed successfully!"
echo "=========================================="
echo ""
echo "Distribution package: dist/${DIST_NAME}.zip"
echo ""
echo "To distribute:"
echo "  1. Upload dist/${DIST_NAME}.zip to OneDrive"
echo "  2. Users download and extract the zip file"
echo "  3. Users double-click LiteratureReviewVisualizer.app to run"
echo ""

