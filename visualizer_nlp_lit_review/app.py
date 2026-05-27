"""
Flask application for Literature Review Visualizer
Provides API endpoints for frontend
"""

import datetime
import os
import subprocess
import sys
import time
import uuid
import requests
from flask import Flask, jsonify, send_file, request, Response, redirect
from flask_cors import CORS
from ris_parser import RISParser
from pdf_resolver import PDFResolver
from overlap_calculator import OverlapCalculator
from config import COMMON_SEARCH_TERMS, get_queries_with_ris_files, R2_BUCKET_NAME, RIS_SOURCE_FOLDER, MANUAL_GROUPINGS_FOLDER
from pdf_overrides import apply_pdf_overrides
from pathlib import Path

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)  # Enable CORS for React frontend

# Global cache for parsed data
_papers_cache = None
_hierarchy_cache = None
_visualization_cache = None
_pdf_resolver = None
_load_error = None  # Store error message if loading fails

# Admin: background job tracking (populated only when ADMIN_ENABLED=true)
_jobs: dict = {}


def load_data():
    """Load and parse RIS files from all queries, build hierarchy"""
    global _papers_cache, _hierarchy_cache, _visualization_cache, _pdf_resolver, _load_error
    
    if _papers_cache is not None:
        return  # Already loaded
    
    if _load_error is not None:
        return  # Already tried and failed
    
    try:
        start_total = time.time()
        
        # Resolve RIS files from prefixes
        start = time.time()
        resolved_queries = get_queries_with_ris_files()
        print(f"[TIMING] Resolve queries: {time.time() - start:.2f}s")
        print(f"Loading papers from {len(resolved_queries)} query/queries")
        
        if not resolved_queries:
            error_msg = "No queries found. Check RIS_SOURCE_FOLDER path and COMMON_SEARCH_TERMS configuration."
            print(f"ERROR: {error_msg}")
            _load_error = error_msg
            return
        
        # Initialize PDF resolver
        start = time.time()
        _pdf_resolver = PDFResolver()
        print(f"[TIMING] Initialize PDF resolver: {time.time() - start:.2f}s")
        
        # Build hierarchy using OverlapCalculator (it will load papers from all RIS files)
        start = time.time()
        calculator = OverlapCalculator(resolved_queries)
        query_databases = calculator.load_papers_from_queries()
        print(f"[TIMING] Load papers from queries: {time.time() - start:.2f}s")

        changed_pdf_links = apply_pdf_overrides(calculator.all_papers)
        if changed_pdf_links:
            print(f"[PDF WARNING] Applied {changed_pdf_links} PDF override/suppression rule(s)")
        
        # Get all papers from calculator
        _papers_cache = calculator.all_papers
        print(f"Parsed {len(_papers_cache)} total papers from all queries")
        
        if len(_papers_cache) == 0:
            error_msg = "No papers found in RIS files. Check RIS file paths and content."
            print(f"ERROR: {error_msg}")
            _load_error = error_msg
            return
        
        # Load most-cited papers
        start = time.time()
        calculator.load_most_cited_papers()
        print(f"[TIMING] Load most-cited papers: {time.time() - start:.2f}s")
        
        # Load most-relevant papers
        start = time.time()
        calculator.load_most_relevant_papers()
        print(f"[TIMING] Load most-relevant papers: {time.time() - start:.2f}s")

        # Load Jon's curated list (standalone node)
        start = time.time()
        calculator.load_jons_list_papers()
        print(f"[TIMING] Load Jon's List papers: {time.time() - start:.2f}s")

        # Build hierarchy
        start = time.time()
        _hierarchy_cache = calculator.build_hierarchy()
        print(f"[TIMING] Build hierarchy: {time.time() - start:.2f}s")
        
        start = time.time()
        _visualization_cache = calculator.get_visualization_data(_hierarchy_cache)
        print(f"[TIMING] Build visualization: {time.time() - start:.2f}s")
        
        print(f"[TIMING] TOTAL LOAD TIME: {time.time() - start_total:.2f}s")
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

    # Direct URL fast path: L1 fields written by the new pipeline are full
    # https:// URLs (e.g. R2 CAS keys like pmid_12345678.pdf). Redirect
    # straight to them; the legacy internal-pdf:// resolver below cannot
    # handle this form.
    if paper.pdf_path.startswith(("http://", "https://")):
        print(f"[PDF DEBUG] Direct URL pdf_path, redirecting: {paper.pdf_path}")
        return redirect(paper.pdf_path)

    # Try Cloudflare R2 first if configured
    if R2_BUCKET_NAME:
        print(f"[PDF DEBUG] Paper ID: {paper_id}, pdf_path: {paper.pdf_path}")
        # Get all possible R2 URLs (tries both NLP_v4 and zotero_v3 prefixes)
        r2_urls = _pdf_resolver.get_all_r2_urls(paper.pdf_path)
        print(f"[PDF DEBUG] Generated {len(r2_urls)} R2 URLs: {r2_urls}")
        
        for r2_url in r2_urls:
            try:
                print(f"[PDF DEBUG] Checking R2 URL: {r2_url}")
                # Quick HEAD request to check if file exists
                response = requests.head(r2_url, timeout=5, allow_redirects=True)
                print(f"[PDF DEBUG] R2 HEAD response: status={response.status_code}, headers={dict(response.headers)}")
                if response.status_code == 200:
                    # Redirect to R2 - faster than proxying through our server
                    print(f"[PDF DEBUG] SUCCESS - Redirecting to R2: {r2_url}")
                    return redirect(r2_url)
                else:
                    print(f"[PDF DEBUG] R2 URL returned {response.status_code}: {r2_url}")
            except (requests.RequestException, requests.Timeout) as e:
                print(f"[PDF DEBUG] R2 check failed for {r2_url}: {type(e).__name__}: {e}")
                continue
        
        # If all R2 URLs failed, fall through to local filesystem
        print(f"[PDF DEBUG] All R2 URLs failed for paper {paper_id}, trying local filesystem")
    
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

    # Direct URL fast path (new pipeline writes full https:// L1 fields).
    if paper.pdf_path.startswith(("http://", "https://")):
        return jsonify({
            "available": True,
            "path": paper.pdf_path,
            "source": "direct_url"
        })

    # Check R2 first if configured
    if R2_BUCKET_NAME:
        r2_urls = _pdf_resolver.get_all_r2_urls(paper.pdf_path)
        for r2_url in r2_urls:
            try:
                response = requests.head(r2_url, timeout=3, allow_redirects=True)
                if response.status_code == 200:
                    return jsonify({
                        "available": True,
                        "path": paper.pdf_path,
                        "source": "R2"
                    })
            except (requests.RequestException, requests.Timeout):
                continue
    
    # Fallback to local filesystem check
    available = _pdf_resolver.is_pdf_available(paper.pdf_path)
    return jsonify({
        "available": available,
        "path": paper.pdf_path,
        "source": "local" if available else "none"
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


# ---------------------------------------------------------------------------
# Admin routes — active only when ADMIN_ENABLED=true in the environment.
# Set this locally (e.g. in a .env file or your shell); never set it on Render.
# ---------------------------------------------------------------------------
if os.environ.get("ADMIN_ENABLED", "false").lower() == "true":

    @app.route('/admin')
    def admin_page():
        """Serve the local admin search-and-pull page."""
        return send_file(
            str(Path(__file__).parent / 'templates' / 'admin.html')
        )

    @app.route('/api/catalog')
    def get_catalog():
        """List COMMON_SEARCH_TERMS entries that have slug + label (usable by the batch runner)."""
        catalog = []
        for name, info in COMMON_SEARCH_TERMS.items():
            if not isinstance(info, dict):
                continue
            slug = info.get("slug")
            label = info.get("label")
            query = info.get("query")
            if slug and label and query:
                catalog.append({
                    "name": name,
                    "query": query,
                    "slug": slug,
                    "label": label,
                })
        return jsonify(catalog)

    @app.route('/api/run_search', methods=['POST'])
    def run_search():
        """
        Launch auto_search_wrapper in the background for a single query.
        JSON body: {query, slug, label, extra_terms (optional)}
        Returns: {job_id, started_at, command_summary}
        """
        data = request.get_json(force=True) or {}
        base_query = (data.get("query") or "").strip()
        slug = (data.get("slug") or "").strip()
        label = (data.get("label") or "").strip()
        extra_terms = (data.get("extra_terms") or "").strip()

        if not base_query or not slug or not label:
            return jsonify({"error": "query, slug, and label are required"}), 400

        final_query = f"({base_query}) AND ({extra_terms})" if extra_terms else base_query

        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "automated_search" / "scripts" / "auto_search_wrapper.py"
        if not wrapper.is_file():
            return jsonify({"error": f"Wrapper not found: {wrapper}"}), 500

        cmd = [sys.executable, str(wrapper), "--query", final_query, "--slug", slug, "--label", label]
        job_id = uuid.uuid4().hex[:8]
        try:
            proc = subprocess.Popen(cmd, cwd=str(repo_root))
            _jobs[job_id] = proc
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        return jsonify({
            "job_id": job_id,
            "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "command_summary": f"auto_search_wrapper --slug {slug!r} --label {label!r}",
        })

    @app.route('/api/refresh_catalog', methods=['POST'])
    def refresh_catalog_route():
        """
        Launch refresh_catalog.py in the background (runs all catalog entries end-to-end).
        Returns: {job_id, started_at}
        """
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "automated_search" / "scripts" / "refresh_catalog.py"
        if not script.is_file():
            return jsonify({"error": f"refresh_catalog.py not found: {script}"}), 500

        cmd = [sys.executable, str(script)]
        job_id = uuid.uuid4().hex[:8]
        try:
            proc = subprocess.Popen(cmd, cwd=str(repo_root))
            _jobs[job_id] = proc
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        return jsonify({
            "job_id": job_id,
            "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "command_summary": "refresh_catalog.py (all catalog entries)",
        })

    @app.route('/api/job_status/<job_id>')
    def job_status(job_id):
        """Poll the status of a background job launched by /api/run_search or /api/refresh_catalog."""
        proc = _jobs.get(job_id)
        if proc is None:
            return jsonify({"error": "Unknown job ID"}), 404
        rc = proc.poll()
        if rc is None:
            return jsonify({"status": "running", "job_id": job_id})
        return jsonify({"status": "done", "job_id": job_id, "returncode": rc})


if __name__ == '__main__':
    # Load data on startup
    load_data()

    # Run Flask app
    port = int(os.getenv('PORT', 5001))  # Changed default to 5001
    # Disable debug mode in production (set FLASK_DEBUG=false in production)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)






