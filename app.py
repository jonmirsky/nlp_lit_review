"""
Flask application for Literature Review Visualizer
Provides API endpoints for frontend
"""

import os
import requests
from flask import Flask, jsonify, send_file, request, Response, redirect
from flask_cors import CORS
from ris_parser import RISParser
from pdf_resolver import PDFResolver
from overlap_calculator import OverlapCalculator
from config import COMMON_SEARCH_TERMS, get_queries_with_ris_files, R2_BUCKET_NAME, RIS_SOURCE_FOLDER, MANUAL_GROUPINGS_FOLDER
from pathlib import Path

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)  # Enable CORS for React frontend

# Global cache for parsed data
_papers_cache = None
_hierarchy_cache = None
_visualization_cache = None
_pdf_resolver = None
_load_error = None  # Store error message if loading fails


def load_data():
    """Load and parse RIS files from all queries, build hierarchy"""
    global _papers_cache, _hierarchy_cache, _visualization_cache, _pdf_resolver, _load_error
    
    if _papers_cache is not None:
        return  # Already loaded
    
    if _load_error is not None:
        return  # Already tried and failed
    
    try:
        # Resolve RIS files from prefixes
        resolved_queries = get_queries_with_ris_files()
        print(f"Loading papers from {len(resolved_queries)} query/queries")
        
        if not resolved_queries:
            error_msg = "No queries found. Check RIS_SOURCE_FOLDER path and COMMON_SEARCH_TERMS configuration."
            print(f"ERROR: {error_msg}")
            _load_error = error_msg
            return
        
        # Initialize PDF resolver
        _pdf_resolver = PDFResolver()
        
        # Build hierarchy using OverlapCalculator (it will load papers from all RIS files)
        calculator = OverlapCalculator(resolved_queries)
        query_databases = calculator.load_papers_from_queries()
        
        # Get all papers from calculator
        _papers_cache = calculator.all_papers
        print(f"Parsed {len(_papers_cache)} total papers from all queries")
        
        if len(_papers_cache) == 0:
            error_msg = "No papers found in RIS files. Check RIS file paths and content."
            print(f"ERROR: {error_msg}")
            _load_error = error_msg
            return
        
        # Load most-cited papers
        calculator.load_most_cited_papers()
        
        # Load most-relevant papers
        calculator.load_most_relevant_papers()
        
        # Build hierarchy
        _hierarchy_cache = calculator.build_hierarchy()
        _visualization_cache = calculator.get_visualization_data(_hierarchy_cache)
        
        print("Data loaded successfully")
        
    except FileNotFoundError as e:
        error_msg = f"RIS file not found: {str(e)}. Check RIS_SOURCE_FOLDER path."
        print(f"ERROR: {error_msg}")
        _load_error = error_msg
    except Exception as e:
        error_msg = f"Error loading data: {str(e)}"
        print(f"ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        _load_error = error_msg


@app.route('/')
def index():
    """Serve main HTML page"""
    return send_file('templates/index.html')


@app.route('/api/papers')
def get_papers():
    """Get all papers with metadata"""
    load_data()
    
    if _load_error:
        return jsonify({"error": _load_error}), 500
    
    if _papers_cache is None:
        return jsonify({"error": "Data not loaded"}), 500
    
    # Optional filtering
    search_query = request.args.get('search', '').lower()
    sort_by = request.args.get('sort', 'year')  # 'year' or 'title'
    
    papers = _papers_cache.copy()
    
    # Filter by search query (title or abstract)
    if search_query:
        papers = [
            p for p in papers
            if search_query in p.title.lower() or search_query in p.abstract.lower()
        ]
    
    # Sort
    if sort_by == 'year':
        papers.sort(key=lambda p: (p.year or 0, p.title), reverse=True)
    elif sort_by == 'title':
        papers.sort(key=lambda p: p.title.lower())
    
    return jsonify([p.to_dict() for p in papers])


@app.route('/api/visualization')
def get_visualization():
    """Get visualization data for React Flow"""
    load_data()
    
    if _load_error:
        return jsonify({"error": _load_error}), 500
    
    if _visualization_cache is None:
        return jsonify({"error": "Data not loaded"}), 500
    
    return jsonify(_visualization_cache)


@app.route('/api/hierarchy')
def get_hierarchy():
    """Get raw hierarchy data"""
    load_data()
    
    if _load_error:
        return jsonify({"error": _load_error}), 500
    
    if _hierarchy_cache is None:
        return jsonify({"error": "Data not loaded"}), 500
    
    return jsonify(_hierarchy_cache)


@app.route('/api/config')
def get_config():
    """Get configuration (queries with resolved RIS files)"""
    resolved_queries = get_queries_with_ris_files()
    return jsonify({
        "queries": resolved_queries
    })


@app.route('/api/pdf/<paper_id>')
def get_pdf(paper_id):
    """Serve PDF file for a paper"""
    load_data()
    
    # Find paper by ID
    paper = None
    for p in _papers_cache:
        if str(p.id) == str(paper_id):
            paper = p
            break
    
    if not paper or not paper.pdf_path:
        return jsonify({"error": "PDF not found"}), 404
    
    # Try Cloudflare R2 first if configured
    if R2_BUCKET_NAME:
        # Get all possible R2 URLs (tries both NLP_v4 and zotero_v3 prefixes)
        r2_urls = _pdf_resolver.get_all_r2_urls(paper.pdf_path)
        
        for r2_url in r2_urls:
            try:
                # Quick HEAD request to check if file exists
                response = requests.head(r2_url, timeout=5, allow_redirects=True)
                if response.status_code == 200:
                    # Redirect to R2 - faster than proxying through our server
                    print(f"Redirecting to R2: {r2_url}")
                    return redirect(r2_url)
                else:
                    print(f"R2 URL returned {response.status_code}: {r2_url}")
            except (requests.RequestException, requests.Timeout) as e:
                print(f"R2 check failed for {r2_url}: {e}")
                continue
        
        # If all R2 URLs failed, fall through to local filesystem
        print(f"All R2 URLs failed for paper {paper_id}, trying local filesystem")
    
    # Fallback to local filesystem (for development)
    resolved_path = _pdf_resolver.resolve(paper.pdf_path)
    
    if not resolved_path or not Path(resolved_path).exists():
        return jsonify({"error": "PDF file not found. Please check that PDFs have been uploaded to Cloudflare R2."}), 404
    
    # Send file with headers to ensure it opens in new tab/window
    response = send_file(resolved_path, mimetype='application/pdf')
    # Add headers to prevent same-tab navigation
    response.headers['Content-Disposition'] = 'inline; filename="paper.pdf"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.route('/api/pdf/check/<paper_id>')
def check_pdf(paper_id):
    """Check if PDF is available for a paper"""
    load_data()
    
    # Find paper by ID
    paper = None
    for p in _papers_cache:
        if str(p.id) == str(paper_id):
            paper = p
            break
    
    if not paper:
        return jsonify({"available": False, "error": "Paper not found"}), 404
    
    if not paper.pdf_path:
        return jsonify({"available": False, "error": "No PDF path in record"})
    
    available = _pdf_resolver.is_pdf_available(paper.pdf_path)
    return jsonify({
        "available": available,
        "path": paper.pdf_path
    })


@app.route('/api/reload')
def reload_data():
    """Reload data from RIS file (for development)"""
    global _papers_cache, _hierarchy_cache, _visualization_cache, _load_error
    _papers_cache = None
    _hierarchy_cache = None
    _visualization_cache = None
    _load_error = None
    load_data()
    if _load_error:
        return jsonify({"status": "reload failed", "error": _load_error}), 500
    return jsonify({"status": "reloaded"})


@app.route('/api/health')
def health_check():
    """Health check endpoint for diagnostics"""
    from config import get_ris_source_folder, get_manual_groupings_folder
    
    health_status = {
        "status": "unknown",
        "data_loaded": _papers_cache is not None,
        "error": _load_error,
        "paper_count": len(_papers_cache) if _papers_cache else 0,
        "paths": {
            "ris_source_folder": RIS_SOURCE_FOLDER,
            "ris_source_exists": Path(RIS_SOURCE_FOLDER).exists(),
            "manual_groupings_folder": MANUAL_GROUPINGS_FOLDER,
            "manual_groupings_exists": Path(MANUAL_GROUPINGS_FOLDER).exists(),
        },
        "queries": {}
    }
    
    # Check RIS files
    ris_folder = Path(RIS_SOURCE_FOLDER)
    if ris_folder.exists():
        ris_files = list(ris_folder.glob("*.txt"))
        health_status["paths"]["ris_files_found"] = len(ris_files)
        health_status["paths"]["ris_file_names"] = [f.name for f in ris_files[:5]]  # First 5
    else:
        health_status["paths"]["ris_files_found"] = 0
        health_status["paths"]["ris_file_names"] = []
    
    # Check queries
    try:
        resolved_queries = get_queries_with_ris_files()
        for query_name, query_info in resolved_queries.items():
            ris_file = query_info.get("ris_file", "Not found")
            health_status["queries"][query_name] = {
                "ris_file": ris_file,
                "ris_file_exists": Path(ris_file).exists() if ris_file else False
            }
    except Exception as e:
        health_status["queries"]["error"] = str(e)
    
    # Determine overall status
    if _load_error:
        health_status["status"] = "error"
    elif _papers_cache is not None and len(_papers_cache) > 0:
        health_status["status"] = "healthy"
    elif not Path(RIS_SOURCE_FOLDER).exists():
        health_status["status"] = "error"
        health_status["error"] = f"RIS source folder not found: {RIS_SOURCE_FOLDER}"
    else:
        health_status["status"] = "warning"
    
    status_code = 200 if health_status["status"] == "healthy" else 500
    return jsonify(health_status), status_code


if __name__ == '__main__':
    # Load data on startup
    load_data()
    
    # Run Flask app
    port = int(os.getenv('PORT', 5001))  # Changed default to 5001
    # Disable debug mode in production (set FLASK_DEBUG=false in production)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)





