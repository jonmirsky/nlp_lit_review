# Literature Review Flowchart Visualizer

A hierarchical flowchart visualizer for large literature reviews (3000-4000+ papers) that shows database → common search terms → unique search terms → papers with overlap visualization.

## Features

- **Hierarchical Visualization**: Database → Common Terms → Unique Terms → Overlap Groups → Papers
- **Overlap Detection**: Automatically calculates and displays all paper overlaps between search terms
- **Paper Lists**: Scrollable, sortable, and filterable paper lists within each overlap group
- **PDF Integration**: Double-click papers to open associated PDFs
- **Search & Filter**: Search within titles/abstracts, sort by year or title
- **Performance Optimized**: Virtual scrolling for large lists, efficient data processing

## Setup

### Prerequisites

- Python 3.8+
- Node.js 16+ and npm

### Installation

1. Install Python dependencies:
```bash
pip install -r requirements_lit_review_visualizer.txt
```

2. Install Node.js dependencies:
```bash
npm install
```

3. Configure queries in `config.py`:
```python
COMMON_SEARCH_TERMS = {
    "Query1_Name": {
        "query": '''("Your full query string here")''',
        "ris_file": "/path/to/query1_ris_file.txt"
    },
    "Query2_Name": {
        "query": '''("Another query string")''',
        "ris_file": "/path/to/query2_ris_file.txt"
    }
}
```

4. Update Endnote data folder path in `config.py`:
```python
ENDNOTE_DATA_PATH = "/path/to/Endnote/library.Data"
```

## Running the Application

### Development Mode

1. Start the Flask backend:
```bash
python app.py
```

2. In another terminal, start the React development server:
```bash
npm run dev
```

3. Open your browser to `http://localhost:3000`

### Production Build

1. Build the React app:
```bash
npm run build
```

2. Start the Flask server:
```bash
python app.py
```

3. Open your browser to `http://localhost:5000`

## RIS File Format

The visualizer expects RIS format files with the following fields:
- `TI` - Title
- `PY` - Year
- `AB` - Abstract
- `RN` - Research Notes (contains branch terms, comma-separated, e.g., "radiology, neuroscience")
- `L1` - PDF path (internal-pdf:// format)
- `ID` or `LB` - Paper ID

The database name is extracted from the filename (first word before underscore).

## Query and Branch Structure

- **Queries**: Configured in `config.py` as dictionary mapping query names to query strings and RIS file paths
- **Branch Terms**: Stored in RN field of RIS file, comma-separated (e.g., "radiology, neuroscience")
- **Overlaps**: Automatically calculated both within queries (between branches) and across queries (between branches from different queries)

## API Endpoints

- `GET /api/papers` - Get all papers (with optional search and sort parameters)
- `GET /api/visualization` - Get flowchart visualization data
- `GET /api/hierarchy` - Get raw hierarchy data
- `GET /api/config` - Get configuration
- `GET /api/pdf/<paper_id>` - Serve PDF file
- `GET /api/pdf/check/<paper_id>` - Check if PDF is available
- `GET /api/reload` - Reload data from RIS file

## Project Structure

```
visualizer_nlp_lit_review/
├── app.py                 # Flask application
├── ris_parser.py          # RIS file parsing
├── pdf_resolver.py        # PDF path resolution
├── overlap_calculator.py  # Overlap calculation
├── config.py              # Configuration
├── requirements_lit_review_visualizer.txt
├── package.json
├── webpack.config.js
├── templates/
│   └── index.html
├── src/
│   ├── App.jsx
│   ├── components/
│   │   ├── FlowChart.jsx
│   │   ├── PaperList.jsx
│   │   └── ...
│   └── ...
└── static/                # Build output
```

## Troubleshooting

- **PDFs not opening**: Check that Endnote data folder path is correct in `config.py`
- **No papers showing**: Verify RIS file path and format
- **Overlaps not calculating**: Ensure papers have unique IDs and search terms in N1 field
- **Performance issues**: The app uses virtual scrolling, but very large datasets (>5000 papers) may need additional optimization





