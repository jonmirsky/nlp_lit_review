@echo off
REM Build script for Windows standalone app

echo ==========================================
echo Building Literature Review Visualizer
echo Platform: Windows
echo ==========================================
echo.

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Step 1: Build React frontend
echo.
echo Step 1: Building React frontend...
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: npm is not installed. Please install Node.js and npm.
    exit /b 1
)

call npm run build

if not exist "static\js\main.js" (
    echo Error: React build failed. static\js\main.js not found.
    exit /b 1
)

echo [OK] React frontend built successfully

REM Step 2: Check for required files
echo.
echo Step 2: Checking required files...

set REQUIRED_FILES=launcher.py app.py config.py ris_parser.py pdf_resolver.py overlap_calculator.py templates\index.html static\js\main.js

for %%F in (%REQUIRED_FILES%) do (
    if not exist "%%F" (
        echo Error: Required file not found: %%F
        exit /b 1
    )
)

echo [OK] All required files present

REM Step 3: Check for PyInstaller
echo.
echo Step 3: Checking PyInstaller...
where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: PyInstaller is not installed.
    echo Please install it with: pip install pyinstaller
    exit /b 1
)

echo [OK] PyInstaller found

REM Step 4: Build with PyInstaller
echo.
echo Step 4: Building executable with PyInstaller...
echo This may take several minutes...

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller
pyinstaller visualizer.spec --clean

if not exist "dist\LiteratureReviewVisualizer.exe" (
    echo Error: Build failed. Executable not found in dist\
    exit /b 1
)

echo [OK] Executable built successfully

REM Step 5: Create distribution package
echo.
echo Step 5: Creating distribution package...

set DIST_NAME=LiteratureReviewVisualizer_Windows
set DIST_DIR=dist\%DIST_NAME%

REM Clean previous distribution
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

REM Create distribution directory
mkdir "%DIST_DIR%"

REM Copy executable and all files from dist
xcopy /E /I /Y "dist\LiteratureReviewVisualizer.exe" "%DIST_DIR%\"
xcopy /E /I /Y "dist\_internal" "%DIST_DIR%\_internal\" 2>nul

REM Create README
(
echo Literature Review Visualizer - Windows Version
echo ==========================================
echo.
echo INSTRUCTIONS:
echo 1. Double-click "LiteratureReviewVisualizer.exe" to run
echo 2. The app will automatically open in your default web browser
echo 3. If the browser doesn't open automatically, go to: http://127.0.0.1:5001/
echo.
echo TROUBLESHOOTING:
echo - If Windows Defender or antivirus blocks the app, add an exception
echo - Make sure you have an internet connection for the first run
echo - The app runs a local server - no data is sent to the internet
echo.
echo For support, contact the developer.
) > "%DIST_DIR%\README.txt"

echo [OK] Created README.txt

REM Create zip file (requires PowerShell or 7-Zip)
echo.
echo Creating zip file...
powershell -Command "Compress-Archive -Path '%DIST_DIR%' -DestinationPath 'dist\%DIST_NAME%.zip' -Force" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Warning: Could not create zip file automatically.
    echo Please manually zip the %DIST_DIR% folder.
) else (
    echo [OK] Created zip file
)

echo.
echo ==========================================
echo Build completed successfully!
echo ==========================================
echo.
echo Distribution package: dist\%DIST_NAME%.zip
echo.
echo To distribute:
echo   1. Upload dist\%DIST_NAME%.zip to OneDrive
echo   2. Users download and extract the zip file
echo   3. Users double-click LiteratureReviewVisualizer.exe to run
echo.

pause


