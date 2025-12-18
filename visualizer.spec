# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Literature Review Visualizer
Creates a standalone executable with all dependencies and data files
"""

import os
from pathlib import Path

block_cipher = None

# Get the project root directory (where the spec file is located)
# Use os.path to handle path resolution more reliably
try:
    # SPECPATH might be the spec file path or the directory
    specpath_abs = os.path.abspath(SPECPATH)
    
    # Check if SPECPATH is a file or directory
    if os.path.isfile(specpath_abs):
        # SPECPATH is the spec file itself
        project_root = os.path.dirname(specpath_abs)
    elif os.path.isdir(specpath_abs):
        # SPECPATH is the directory (unusual but possible)
        project_root = specpath_abs
    else:
        # Fallback: assume it's a directory
        project_root = specpath_abs
    specpath_debug = f"{SPECPATH} -> {specpath_abs}"
except NameError:
    # Fallback: use current working directory
    project_root = os.getcwd()
    specpath_debug = 'N/A (SPECPATH not available)'

# Convert to Path for easier manipulation
project_root = Path(project_root).absolute()

# Verify paths exist and convert to absolute paths
static_path = project_root / 'static'
templates_path = project_root / 'templates'
ris_source_path = project_root / 'RIS_source_files'

# Check if paths exist
if not static_path.exists():
    raise FileNotFoundError(
        f"Static folder not found: {static_path}\n"
        f"Project root: {project_root}\n"
        f"SPECPATH was: {specpath_debug}\n"
        f"Please ensure you're running pyinstaller from the project directory."
    )
if not templates_path.exists():
    raise FileNotFoundError(f"Templates folder not found: {templates_path}")
if not ris_source_path.exists():
    raise FileNotFoundError(f"RIS source folder not found: {ris_source_path}")

# Build datas list
datas_list = [
    # Static files (React build) - use absolute paths
    (str(static_path.absolute()), 'static'),
    # Templates
    (str(templates_path.absolute()), 'templates'),
    # RIS source files - will be placed in data/RIS_source_files
    (str(ris_source_path.absolute()), 'data/RIS_source_files'),
]

# Add Endnote data folder if it exists
# Try multiple possible locations
endnote_paths = [
    project_root.parent.parent / 'Endnote' / 'from_zotero_v3.Data',  # Development location
    project_root / 'Endnote' / 'from_zotero_v3.Data',  # Alternative location
    Path('/Users/jon/Documents/badjatia_hu/Endnote/from_zotero_v3.Data'),  # Absolute path
]

for endnote_path in endnote_paths:
    endnote_path_abs = Path(endnote_path).absolute()
    if endnote_path_abs.exists() and endnote_path_abs.is_dir():
        # Add as tuple: (source_path, destination_path_in_bundle)
        datas_list.append((str(endnote_path_abs), 'data/Endnote/from_zotero_v3.Data'))
        break

# Collect all Python files
a = Analysis(
    ['launcher.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas_list,
    hiddenimports=[
        'flask',
        'flask_cors',
        'werkzeug',
        'jinja2',
        'itsdangerous',
        'click',
        'markupsafe',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LiteratureReviewVisualizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Show console for error messages
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

