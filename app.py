"""
Flask application for Literature Review Visualizer
Provides API endpoints for frontend
"""

import os
import requests
from flask import Flask, jsonify, send_file, request, Response
from flask_cors import CORS
from ris_parser import RISParser
from pdf_resolver import PDFResolver
from overlap_calculator import OverlapCalculator
from config import COMMON_SEARCH_TERMS, get_queries_with_ris_files, ONEDRIVE_BASE_URL
from pathlib import Path

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)  # Enable CORS for React frontend

# Global cache for parsed data
_papers_cache = None
_hierarchy_cache = None
_visualization_cache = None
_pdf_resolver = None


def load_data():
    """Load and parse RIS files from all queries, build hierarchy"""
    global _papers_cache, _hierarchy_cache, _visualization_cache, _pdf_resolver
    
    if _papers_cache is not None:
        return  # Already loaded
    
    # Resolve RIS files from prefixes
    resolved_queries = get_queries_with_ris_files()
    print(f"Loading papers from {len(resolved_queries)} query/queries")
    
    # Initialize PDF resolver
    _pdf_resolver = PDFResolver()
    
    # Build hierarchy using OverlapCalculator (it will load papers from all RIS files)
    calculator = OverlapCalculator(resolved_queries)
    query_databases = calculator.load_papers_from_queries()
    
    # Get all papers from calculator
    _papers_cache = calculator.all_papers
    print(f"Parsed {len(_papers_cache)} total papers from all queries")
    
    # Load most-cited papers
    calculator.load_most_cited_papers()
    
    # Load most-relevant papers
    calculator.load_most_relevant_papers()
    
    # Build hierarchy
    _hierarchy_cache = calculator.build_hierarchy()
    _visualization_cache = calculator.get_visualization_data(_hierarchy_cache)
    
    print("Data loaded successfully")


@app.route('/')
def index():
    """Serve main HTML page"""
    return send_file('templates/index.html')


@app.route('/api/papers')
def get_papers():
    """Get all papers with metadata"""
    load_data()
    
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
    return jsonify(_visualization_cache)


@app.route('/api/hierarchy')
def get_hierarchy():
    """Get raw hierarchy data"""
    load_data()
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
    
    # Try OneDrive first if configured
    if ONEDRIVE_BASE_URL:
        onedrive_url = _pdf_resolver.resolve_to_onedrive_url(paper.pdf_path)
        if onedrive_url:
            try:
                # Fetch PDF from OneDrive with timeout
                response = requests.get(onedrive_url, timeout=30, stream=True)
                if response.status_code == 200:
                    # Stream PDF data to client
                    def generate():
                        for chunk in response.iter_content(chunk_size=8192):
                            yield chunk
                    
                    flask_response = Response(
                        generate(),
                        mimetype='application/pdf',
                        headers={
                            'Content-Disposition': 'inline; filename="paper.pdf"',
                            'X-Content-Type-Options': 'nosniff'
                        }
                    )
                    return flask_response
                # If OneDrive returns error, fall through to local filesystem
            except (requests.RequestException, requests.Timeout) as e:
                # Network error or timeout, fall through to local filesystem
                print(f"OneDrive fetch failed: {e}, falling back to local filesystem")
    
    # Fallback to local filesystem
    resolved_path = _pdf_resolver.resolve(paper.pdf_path)
    
    if not resolved_path or not Path(resolved_path).exists():
        return jsonify({"error": "PDF file not found on disk"}), 404
    
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
    global _papers_cache, _hierarchy_cache, _visualization_cache
    _papers_cache = None
    _hierarchy_cache = None
    _visualization_cache = None
    load_data()
    return jsonify({"status": "reloaded"})


if __name__ == '__main__':
    # Load data on startup
    load_data()
    
    # Run Flask app
    port = int(os.getenv('PORT', 5001))  # Changed default to 5001
    # Disable debug mode in production (set FLASK_DEBUG=false in production)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)




