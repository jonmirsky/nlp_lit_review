#!/usr/bin/env python3
"""
Standalone desktop GUI for the literature review search pipeline.

Inputs:
- visualizer_nlp_lit_review/config.py (reads COMMON_SEARCH_TERMS for catalog dropdown)
- automated_search/scripts/auto_search_wrapper.py (spawned by Search and Pull)
- automated_search/scripts/refresh_catalog.py (spawned by Refresh Catalog)
- visualizer_nlp_lit_review/RIS_source_files/pubmed_*.txt (paper search for Jon's List)

Outputs:
- Appends selected paper stubs to
  visualizer_nlp_lit_review/RIS_source_files/manual_groupings/jons_list.txt.
- Pipeline outputs come from spawned scripts (see their own docstrings).

Usage:
    python3 admin_gui.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, scrolledtext, ttk
from typing import Any


# ── Repo layout ─────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = REPO_ROOT / "visualizer_nlp_lit_review" / "config.py"
RIS_PARSER_PATH = REPO_ROOT / "visualizer_nlp_lit_review" / "ris_parser.py"
RIS_SOURCE_DIR = REPO_ROOT / "visualizer_nlp_lit_review" / "RIS_source_files"
MANUAL_GROUPINGS_DIR = RIS_SOURCE_DIR / "manual_groupings"
JONS_LIST_PATH = MANUAL_GROUPINGS_DIR / "jons_list.txt"
CUSTOM_QUERY_REGISTRY_PATH = MANUAL_GROUPINGS_DIR / "custom_queries.json"
HELPERS_DIR = REPO_ROOT / "automated_search" / "scripts" / "helpers"
WRAPPER_PATH = REPO_ROOT / "automated_search" / "scripts" / "auto_search_wrapper.py"
REFRESH_PATH = REPO_ROOT / "automated_search" / "scripts" / "refresh_catalog.py"
REQUIREMENTS_PATH = REPO_ROOT / "automated_search" / "requirements.txt"

# Pipeline runtime dependencies (import_name, pip_name). Checked at GUI startup
# and offered as a one-click install so the user never sees a
# `ModuleNotFoundError` mid-run.
RUNTIME_DEPS: list[tuple[str, str]] = [
    ("Bio", "biopython"),
]


# ── Catalog loader (same approach as refresh_catalog.py) ────────────────────
def _load_catalog() -> list[dict[str, str]]:
    if not CONFIG_PATH.is_file():
        return []
    spec = importlib.util.spec_from_file_location("viz_config", CONFIG_PATH)
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return []
    terms = getattr(mod, "COMMON_SEARCH_TERMS", {})
    entries = []
    for name, info in terms.items():
        if not isinstance(info, dict):
            continue
        if info.get("slug") and info.get("label") and info.get("query"):
            entries.append({
                "name": name,
                "query": info["query"],
                "slug": info["slug"],
                "label": info["label"],
            })
    return entries


def _load_ris_parser_class() -> Any | None:
    if not RIS_PARSER_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("viz_ris_parser", RIS_PARSER_PATH)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return getattr(mod, "RISParser", None)


def _find_newest_master_ris() -> Path | None:
    if not RIS_SOURCE_DIR.is_dir():
        return None
    candidates = [
        p for p in RIS_SOURCE_DIR.glob("pubmed*.txt")
        if p.is_file()
        and ".bak" not in p.name
        and not p.name.endswith(".backup")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _normalize_lookup_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _paper_lookup_key(paper: Any) -> str:
    doi = _normalize_lookup_text(getattr(paper, "doi", ""))
    if doi:
        return f"doi:{doi}"
    return f"title:{_normalize_lookup_text(getattr(paper, 'title', ''))}"


def _ris_value(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _query_name_from_label(label: str, slug: str = "") -> str:
    raw = slug or label
    raw = raw.replace("(", " ").replace(")", " ")
    name = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_")
    return name or "Custom_Query"


def _latest_resume_decision() -> Any | None:
    if str(HELPERS_DIR) not in sys.path:
        sys.path.insert(0, str(HELPERS_DIR))
    try:
        from resume_latest import latest_resume_decision  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        return latest_resume_decision()
    except Exception:
        return None


# ── GUI ──────────────────────────────────────────────────────────────────────
class AdminGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Lit Review Pipeline")
        self.root.resizable(True, True)
        self.root.minsize(920, 760)

        self._catalog: list[dict[str, str]] = _load_catalog()
        self._papers: list[Any] = []
        self._filtered_papers: list[Any] = []
        self._selected_paper: Any | None = None
        self._label_manually_edited = False
        self._proc: subprocess.Popen | None = None
        self._job_active = False
        self._log_queue: queue.Queue[str | None] = queue.Queue()

        self._build_ui()
        self._populate_catalog()
        self._load_paper_index()
        self._ensure_buttons_ready()
        self._poll_log()
        # Defer dep check until after window is shown so the dialog is modal
        # over the GUI, not in front of a black background.
        self.root.after(200, self._check_runtime_deps)

    # ── Runtime-dependency check (biopython, etc.) ───────────────────────────
    def _missing_deps(self) -> list[tuple[str, str]]:
        missing: list[tuple[str, str]] = []
        for import_name, pip_name in RUNTIME_DEPS:
            if importlib.util.find_spec(import_name) is None:
                missing.append((import_name, pip_name))
        return missing

    def _check_runtime_deps(self) -> None:
        missing = self._missing_deps()
        if not missing:
            return
        pip_names = [p for _, p in missing]
        msg = (
            "The pipeline needs these Python packages, which aren't installed:\n\n"
            f"    {', '.join(pip_names)}\n\n"
            "Install them now with:\n"
            f"    {sys.executable} -m pip install --user {' '.join(pip_names)}\n\n"
            "Click Yes to install now (writes to your user site-packages, no sudo)."
        )
        if not messagebox.askyesno("Install missing dependencies?", msg):
            self._log_line(
                f"\n[WARNING] Missing dependencies: {', '.join(pip_names)}.\n"
                "Pipeline runs will fail until they are installed.\n"
            )
            return
        self._install_deps(pip_names)

    def _install_deps(self, pip_names: list[str]) -> None:
        cmd = [sys.executable, "-u", "-m", "pip", "install", "--user", *pip_names]
        self._log_line(f"\n▶  Installing: {' '.join(pip_names)}\n")
        self._status_var.set("⏳  Installing dependencies…")
        self.root.update_idletasks()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if proc.stdout:
                self._log_line(proc.stdout)
            if proc.stderr:
                self._log_line(proc.stderr)
            if proc.returncode == 0:
                self._log_line(f"✓ Installed {', '.join(pip_names)} successfully.\n")
                self._status_var.set("Ready.")
            else:
                self._log_line(f"✗ Install failed (exit {proc.returncode}).\n")
                self._status_var.set("Install failed — see log.")
        except Exception as exc:
            self._log_line(f"✗ Install error: {exc}\n")
            self._status_var.set("Install failed — see log.")

    # ── UI construction ──────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        PADX, PADY = 12, 6

        # ── Top frame: catalog + database ───────────────────────────────────
        top = ttk.LabelFrame(self.root, text="Search settings", padding=10)
        top.pack(fill="x", padx=PADX, pady=(PADY * 2, PADY))

        # Row 0: catalog selector
        ttk.Label(top, text="Catalog entry:").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        self._catalog_var = tk.StringVar()
        self._catalog_combo = ttk.Combobox(top, textvariable=self._catalog_var,
                                           state="readonly", width=38)
        self._catalog_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        self._catalog_combo.bind("<<ComboboxSelected>>", self._on_catalog_change)

        # Row 1: database
        ttk.Label(top, text="Database:").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        self._db_var = tk.StringVar(value="pubmed")
        db_combo = ttk.Combobox(top, textvariable=self._db_var, state="readonly", width=20,
                                values=["pubmed"])
        db_combo.grid(row=1, column=1, sticky="w", padx=4, pady=3)

        top.columnconfigure(1, weight=1)

        # ── Middle frame: query + label + slug ──────────────────────────────
        mid = ttk.LabelFrame(self.root, text="Query", padding=10)
        mid.pack(fill="both", expand=False, padx=PADX, pady=PADY)

        # Base query (read-only when catalog entry selected)
        ttk.Label(mid, text="Base query:").grid(row=0, column=0, sticky="nw", padx=4, pady=3)
        self._base_query_text = tk.Text(mid, height=4, wrap="word", state="disabled",
                                        bg="#f0f0f0", relief="solid", borderwidth=1)
        self._base_query_text.grid(row=0, column=1, columnspan=2, sticky="ew", padx=4, pady=3)

        # Additional terms
        ttk.Label(mid, text="Additional terms:").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        self._extra_var = tk.StringVar()
        self._extra_entry = ttk.Entry(mid, textvariable=self._extra_var, width=50)
        self._extra_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=3)
        self._extra_entry.bind("<KeyRelease>", self._on_extra_change)
        ttk.Label(mid, text='ANDed with base: (base) AND (extra)',
                  foreground="#888").grid(row=2, column=1, columnspan=2, sticky="w", padx=4)

        # Label
        ttk.Label(mid, text="Label (→ visualizer node):").grid(row=3, column=0, sticky="w", padx=4, pady=3)
        self._label_var = tk.StringVar()
        self._label_entry = ttk.Entry(mid, textvariable=self._label_var, width=50)
        self._label_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=4, pady=3)
        self._label_entry.bind("<KeyRelease>", self._on_label_edit)
        ttk.Label(mid, text="Exact string stamped into RN field → becomes a branch node in the visualizer.",
                  foreground="#888").grid(row=4, column=1, columnspan=2, sticky="w", padx=4)

        # Slug
        ttk.Label(mid, text="Slug:").grid(row=5, column=0, sticky="w", padx=4, pady=3)
        self._slug_var = tk.StringVar()
        self._slug_entry = ttk.Entry(mid, textvariable=self._slug_var, width=30)
        self._slug_entry.grid(row=5, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(mid, text="Used for run folder name.",
                  foreground="#888").grid(row=5, column=2, sticky="w", padx=4)

        mid.columnconfigure(1, weight=1)

        # ── Env vars frame ───────────────────────────────────────────────────
        env_frame = ttk.LabelFrame(self.root, text="Environment", padding=10)
        env_frame.pack(fill="x", padx=PADX, pady=PADY)

        ttk.Label(env_frame, text="NCBI_EMAIL:").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        self._email_var = tk.StringVar(value=os.environ.get("NCBI_EMAIL", ""))
        ttk.Entry(env_frame, textvariable=self._email_var, width=42).grid(
            row=0, column=1, sticky="ew", padx=4, pady=3)

        ttk.Label(env_frame, text="LIT_REVIEW_PDF_REMOTE:").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        self._pdf_remote_var = tk.StringVar(
            value=os.environ.get("LIT_REVIEW_PDF_REMOTE", "gdrive:nlp_lit_review_1_papers/pdfs"))
        ttk.Entry(env_frame, textvariable=self._pdf_remote_var, width=42).grid(
            row=1, column=1, sticky="ew", padx=4, pady=3)

        ttk.Label(env_frame, text="NCBI_API_KEY (optional):").grid(row=2, column=0, sticky="w", padx=4, pady=3)
        self._api_key_var = tk.StringVar(value=os.environ.get("NCBI_API_KEY", ""))
        ttk.Entry(env_frame, textvariable=self._api_key_var, show="*", width=42).grid(
            row=2, column=1, sticky="ew", padx=4, pady=3)

        self._insecure_ssl_var = tk.BooleanVar(
            value=os.environ.get("LIT_REVIEW_ENTREZ_INSECURE_SSL", "").strip().lower()
            in ("1", "true", "yes"),
        )
        ttk.Checkbutton(
            env_frame,
            text="Insecure SSL for NCBI (needed on some university / hospital networks)",
            variable=self._insecure_ssl_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=4, pady=(6, 3))

        env_frame.columnconfigure(1, weight=1)

        # ── Jon's List curation ─────────────────────────────────────────────
        jons_frame = ttk.LabelFrame(self.root, text="Jon's List", padding=10)
        jons_frame.pack(fill="both", expand=False, padx=PADX, pady=PADY)

        jons_top = ttk.Frame(jons_frame)
        jons_top.pack(fill="x")

        ttk.Label(jons_top, text="Find paper:").pack(side="left", padx=(0, 6))
        self._jons_search_var = tk.StringVar()
        self._jons_search_entry = ttk.Entry(jons_top, textvariable=self._jons_search_var, width=48)
        self._jons_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._jons_search_entry.bind("<KeyRelease>", self._on_jons_search)

        self._btn_reload_papers = ttk.Button(jons_top, text="Reload Papers", command=self._load_paper_index)
        self._btn_reload_papers.pack(side="left", padx=(0, 8))

        self._btn_add_jons = ttk.Button(
            jons_top,
            text="Add to Jon's List",
            command=self._add_selected_to_jons_list,
            state="disabled",
        )
        self._btn_add_jons.pack(side="left")

        tree_frame = ttk.Frame(jons_frame)
        tree_frame.pack(fill="both", expand=True, pady=(8, 0))

        columns = ("year", "title", "doi")
        self._jons_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=7,
            selectmode="browse",
        )
        self._jons_tree.heading("year", text="Year")
        self._jons_tree.heading("title", text="Title")
        self._jons_tree.heading("doi", text="DOI")
        self._jons_tree.column("year", width=70, anchor="center", stretch=False)
        self._jons_tree.column("title", width=560, anchor="w")
        self._jons_tree.column("doi", width=220, anchor="w")
        self._jons_tree.bind("<<TreeviewSelect>>", self._on_jons_select)
        self._jons_tree.pack(side="left", fill="both", expand=True)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._jons_tree.yview)
        self._jons_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side="right", fill="y")

        self._jons_status_var = tk.StringVar(value="Loading papers...")
        ttk.Label(jons_frame, textvariable=self._jons_status_var, foreground="#555").pack(
            fill="x", pady=(6, 0)
        )

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self.root, padding=(PADX, PADY))
        btn_frame.pack(fill="x")

        btn_row = ttk.Frame(btn_frame)
        btn_row.pack(fill="x")

        self._btn_search = ttk.Button(btn_row, text="Search and Pull",
                                      command=self._run_search)
        self._btn_search.pack(side="left", padx=(0, 8), pady=4)

        self._btn_refresh = ttk.Button(btn_row, text="Refresh Catalog",
                                       command=self._run_refresh)
        self._btn_refresh.pack(side="left", padx=(0, 8), pady=4)

        self._btn_resume = ttk.Button(btn_row, text="Resume Latest", command=self._run_resume_latest)
        self._btn_resume.pack(side="left", padx=(0, 8), pady=4)

        self._btn_stop = ttk.Button(btn_row, text="Stop", command=self._stop_proc,
                                    state="disabled")
        self._btn_stop.pack(side="left", padx=(0, 8), pady=4)

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(btn_frame, textvariable=self._status_var,
                  foreground="#555").pack(fill="x", padx=4, pady=(0, 4))

        # ── Log output ───────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self.root, text="Output", padding=6)
        log_frame.pack(fill="both", expand=True, padx=PADX, pady=(PADY, PADX))

        self._log = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="word",
                                              bg="#1e1e1e", fg="#d4d4d4",
                                              font=("Menlo", 11), relief="flat")
        self._log.pack(fill="both", expand=True)

        btn_clear = ttk.Button(log_frame, text="Clear log", command=self._clear_log)
        btn_clear.pack(anchor="e", pady=(4, 0))

    # ── Catalog helpers ──────────────────────────────────────────────────────
    def _populate_catalog(self) -> None:
        names = ["— Custom —"] + [e["name"] for e in self._catalog]
        self._catalog_combo["values"] = names
        if self._catalog:
            self._catalog_combo.current(1)
            self._on_catalog_change()
        else:
            self._catalog_combo.current(0)

    def _current_entry(self) -> dict[str, str] | None:
        name = self._catalog_var.get()
        return next((e for e in self._catalog if e["name"] == name), None)

    def _on_catalog_change(self, _event=None) -> None:
        self._label_manually_edited = False
        entry = self._current_entry()
        self._base_query_text.config(state="normal")
        self._base_query_text.delete("1.0", "end")
        if entry:
            self._base_query_text.insert("1.0", entry["query"])
            self._base_query_text.config(state="disabled", bg="#f0f0f0")
            self._slug_var.set(entry["slug"])
            self._slug_entry.config(state="disabled")
        else:
            self._base_query_text.config(state="normal", bg="white")
            self._slug_var.set("")
            self._slug_entry.config(state="normal")
        self._sync_label()

    def _on_extra_change(self, _event=None) -> None:
        if not self._label_manually_edited:
            self._sync_label()

    def _on_label_edit(self, _event=None) -> None:
        self._label_manually_edited = True

    def _sync_label(self) -> None:
        entry = self._current_entry()
        extra = self._extra_var.get().strip()
        if entry:
            self._label_var.set(f"{entry['label']} AND {extra}" if extra else entry["label"])

    # ── Jon's List helpers ──────────────────────────────────────────────────
    def _load_paper_index(self) -> None:
        parser_cls = _load_ris_parser_class()
        master_ris = _find_newest_master_ris()
        if parser_cls is None:
            self._papers = []
            self._filtered_papers = []
            self._selected_paper = None
            self._jons_status_var.set(f"RIS parser not found: {RIS_PARSER_PATH}")
            self._refresh_jons_tree()
            return
        if master_ris is None:
            self._papers = []
            self._filtered_papers = []
            self._selected_paper = None
            self._jons_status_var.set(f"No pubmed*.txt master RIS found in {RIS_SOURCE_DIR}")
            self._refresh_jons_tree()
            return
        try:
            self._papers = parser_cls(str(master_ris)).parse()
        except Exception as exc:
            self._papers = []
            self._filtered_papers = []
            self._selected_paper = None
            self._jons_status_var.set(f"Could not load master RIS: {exc}")
            self._refresh_jons_tree()
            return
        self._filtered_papers = []
        self._selected_paper = None
        self._btn_add_jons.config(state="disabled")
        self._jons_status_var.set(
            f"Loaded {len(self._papers)} papers from {master_ris.name}. Type to search."
        )
        self._refresh_jons_tree()

    def _on_jons_search(self, _event=None) -> None:
        query = _normalize_lookup_text(self._jons_search_var.get())
        if not query:
            self._filtered_papers = []
            self._selected_paper = None
            self._btn_add_jons.config(state="disabled")
            self._jons_status_var.set(f"Loaded {len(self._papers)} papers. Type to search.")
            self._refresh_jons_tree()
            return

        terms = query.split()
        matches = []
        for paper in self._papers:
            haystack = " ".join([
                _normalize_lookup_text(getattr(paper, "title", "")),
                _normalize_lookup_text(getattr(paper, "abstract", "")),
                _normalize_lookup_text(getattr(paper, "doi", "")),
                _normalize_lookup_text(" ".join(getattr(paper, "authors", []) or [])),
                _normalize_lookup_text(str(getattr(paper, "year", "") or "")),
            ])
            if all(term in haystack for term in terms):
                matches.append(paper)
            if len(matches) >= 250:
                break

        self._filtered_papers = matches
        self._selected_paper = None
        self._btn_add_jons.config(state="disabled")
        suffix = "showing first 250" if len(matches) == 250 else f"{len(matches)} found"
        self._jons_status_var.set(f"Search: {suffix}. Select one paper, then Add to Jon's List.")
        self._refresh_jons_tree()

    def _refresh_jons_tree(self) -> None:
        for item_id in self._jons_tree.get_children():
            self._jons_tree.delete(item_id)

        for idx, paper in enumerate(self._filtered_papers):
            title = _ris_value(getattr(paper, "title", ""))
            doi = _ris_value(getattr(paper, "doi", ""))
            year = _ris_value(getattr(paper, "year", ""))
            self._jons_tree.insert("", "end", iid=str(idx), values=(year, title, doi))

    def _on_jons_select(self, _event=None) -> None:
        selected = self._jons_tree.selection()
        if not selected:
            self._selected_paper = None
            self._btn_add_jons.config(state="disabled")
            return
        idx = int(selected[0])
        if idx < 0 or idx >= len(self._filtered_papers):
            self._selected_paper = None
            self._btn_add_jons.config(state="disabled")
            return
        self._selected_paper = self._filtered_papers[idx]
        self._btn_add_jons.config(state="normal")

    def _existing_jons_list_keys(self) -> set[str]:
        parser_cls = _load_ris_parser_class()
        if parser_cls is None or not JONS_LIST_PATH.is_file():
            return set()
        try:
            papers = parser_cls(str(JONS_LIST_PATH)).parse()
        except Exception:
            return set()
        return {_paper_lookup_key(paper) for paper in papers if _paper_lookup_key(paper) != "title:"}

    def _add_selected_to_jons_list(self) -> None:
        paper = self._selected_paper
        if paper is None:
            messagebox.showwarning("No paper selected", "Search for a paper and select one row first.")
            return

        title = _ris_value(getattr(paper, "title", ""))
        doi = _ris_value(getattr(paper, "doi", ""))
        year = _ris_value(getattr(paper, "year", ""))
        paper_id = _ris_value(getattr(paper, "id", ""))
        if not title and not doi:
            messagebox.showwarning(
                "Cannot add paper",
                "Selected paper has neither title nor DOI, so Jon's List cannot match it later.",
            )
            return

        key = _paper_lookup_key(paper)
        if key in self._existing_jons_list_keys():
            messagebox.showinfo("Already in Jon's List", "That paper is already in Jon's List.")
            return

        MANUAL_GROUPINGS_DIR.mkdir(parents=True, exist_ok=True)
        needs_leading_newline = JONS_LIST_PATH.exists() and JONS_LIST_PATH.stat().st_size > 0
        lines = []
        if needs_leading_newline:
            lines.append("")
        lines.extend([
            "TY  - JOUR",
        ])
        if title:
            lines.append(f"TI  - {title}")
        if doi:
            lines.append(f"DO  - {doi}")
        if year:
            lines.append(f"PY  - {year}")
        if paper_id:
            lines.append(f"ID  - {paper_id}")
        lines.append("ER  -")

        try:
            with open(JONS_LIST_PATH, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as exc:
            messagebox.showerror("Could not update Jon's List", str(exc))
            return

        self._jons_status_var.set(f"Added to Jon's List: {title or doi}")
        self._log_line(f"\n[Jon's List] Added: {title or doi}\n")
        messagebox.showinfo(
            "Added to Jon's List",
            "Added the selected paper to Jon's List.\n\n"
            "Commit and push jons_list.txt when you want this reflected on Render.",
        )

    def _register_custom_query_node(self, *, query: str, slug: str, label: str, source_db: str) -> None:
        MANUAL_GROUPINGS_DIR.mkdir(parents=True, exist_ok=True)
        if CUSTOM_QUERY_REGISTRY_PATH.is_file():
            try:
                with open(CUSTOM_QUERY_REGISTRY_PATH, "r", encoding="utf-8") as f:
                    registry = json.load(f)
            except Exception:
                registry = {}
        else:
            registry = {}

        entries = registry.get("queries", [])
        if not isinstance(entries, list):
            entries = []

        name = _query_name_from_label(label, slug)
        new_entry = {
            "name": name,
            "query": query,
            "slug": slug,
            "label": label,
            "source_db": source_db,
        }

        replaced = False
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            if entry.get("label") == label or entry.get("slug") == slug or entry.get("name") == name:
                entries[idx] = new_entry
                replaced = True
                break
        if not replaced:
            entries.append(new_entry)

        registry["queries"] = entries
        with open(CUSTOM_QUERY_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
            f.write("\n")

        self._log_line(f"[Visualizer] Registered custom query node: {name} ({label})\n")

    # ── Subprocess execution ─────────────────────────────────────────────────
    @staticmethod
    def _python_cmd(script: Path, *args: str) -> list[str]:
        """Build an unbuffered python command so GUI log updates in real time."""
        return [sys.executable, "-u", str(script), *args]

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        if self._email_var.get().strip():
            env["NCBI_EMAIL"] = self._email_var.get().strip()
        if self._pdf_remote_var.get().strip():
            env["LIT_REVIEW_PDF_REMOTE"] = self._pdf_remote_var.get().strip()
        if self._api_key_var.get().strip():
            env["NCBI_API_KEY"] = self._api_key_var.get().strip()
        if self._insecure_ssl_var.get():
            env["LIT_REVIEW_ENTREZ_INSECURE_SSL"] = "1"
        else:
            env.pop("LIT_REVIEW_ENTREZ_INSECURE_SSL", None)
        return env

    def _validate_search(self) -> tuple[bool, str]:
        if not self._base_query_text.get("1.0", "end").strip():
            return False, "Base query is empty."
        if not self._slug_var.get().strip():
            return False, "Slug is required."
        if not self._label_var.get().strip():
            return False, "Label is required."
        return True, ""

    def _run_search(self) -> None:
        ok, msg = self._validate_search()
        if not ok:
            messagebox.showwarning("Missing fields", msg)
            return
        if not WRAPPER_PATH.is_file():
            messagebox.showerror("Not found", f"auto_search_wrapper.py not found:\n{WRAPPER_PATH}")
            return

        base_q = self._base_query_text.get("1.0", "end").strip()
        extra = self._extra_var.get().strip()
        final_q = f"({base_q}) AND ({extra})" if extra else base_q
        slug = self._slug_var.get().strip()
        label = self._label_var.get().strip()
        source_db = self._db_var.get().strip() or "pubmed"

        if self._current_entry() is None:
            try:
                self._register_custom_query_node(
                    query=final_q,
                    slug=slug,
                    label=label,
                    source_db=source_db,
                )
            except Exception as exc:
                messagebox.showerror("Could not register visualizer node", str(exc))
                return

        cmd = self._python_cmd(
            WRAPPER_PATH,
            "--query", final_q,
            "--slug", slug,
            "--label", label,
            "--source-db", source_db,
        )
        self._spawn(cmd, label=f"Search and Pull — {slug}")

    def _run_refresh(self) -> None:
        if not REFRESH_PATH.is_file():
            messagebox.showerror("Not found", f"refresh_catalog.py not found:\n{REFRESH_PATH}")
            return
        cmd = self._python_cmd(REFRESH_PATH)
        self._spawn(cmd, label="Refresh Catalog")

    def _run_resume_latest(self) -> None:
        decision = _latest_resume_decision()
        if decision is None:
            messagebox.showerror("Resume unavailable", "Could not inspect latest run state.")
            return
        if not decision.can_resume:
            self._log_line(f"\n[Resume Latest] {decision.reason}\n")
            messagebox.showinfo("Nothing to resume", decision.reason)
            self._ensure_buttons_ready()
            return
        cmd = self._python_cmd(WRAPPER_PATH, "--resume-latest")
        self._spawn(cmd, label=f"Resume Latest — {decision.run.run_id}")

    def _is_job_running(self) -> bool:
        if not self._job_active:
            return False
        if self._proc is None:
            return False
        if self._proc.poll() is not None:
            return False
        return True

    def _set_job_ui(self, running: bool, label: str = "") -> None:
        self._job_active = running
        if running:
            self._btn_search.config(state="disabled")
            self._btn_refresh.config(state="disabled", text="Refresh Catalog (running…)")
            self._btn_resume.config(state="disabled", text="Resume Latest (running…)")
            self._btn_stop.config(state="normal")
            self._status_var.set(f"Running: {label}…")
        else:
            self._ensure_buttons_ready()

    def _ensure_buttons_ready(self) -> None:
        """Re-enable action buttons (e.g. after job end or on startup)."""
        self._job_active = False
        self._proc = None
        self._btn_search.config(state="normal")
        self._btn_refresh.config(state="normal", text="Refresh Catalog")
        decision = _latest_resume_decision()
        if decision is not None and decision.can_resume:
            self._btn_resume.config(state="normal", text="Resume Latest")
        else:
            self._btn_resume.config(state="disabled", text="Resume Latest")
        self._btn_stop.config(state="disabled")
        if self._status_var.get().startswith("Running:") or "Installing" in self._status_var.get():
            self._status_var.set("Ready.")

    def _spawn(self, cmd: list[str], label: str) -> None:
        if self._is_job_running():
            messagebox.showwarning(
                "Already running",
                "A pipeline job is already running.\n\n"
                "Check the Output log below, or press Stop to cancel it first.",
            )
            return

        self._log_line(f"\n{'─'*60}\n▶  {label}\n{'─'*60}\n")
        self._set_job_ui(True, label)
        self.root.update_idletasks()

        env = self._build_env()
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except Exception as exc:
            self._log_line(f"ERROR launching process: {exc}\n")
            self._ensure_buttons_ready()
            return

        threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self) -> None:
        rc = -1
        try:
            if self._proc and self._proc.stdout:
                for line in self._proc.stdout:
                    self._log_queue.put(line)
            if self._proc:
                rc = self._proc.wait()
        except Exception as exc:
            self._log_queue.put(f"\nERROR reading process output: {exc}\n")
        finally:
            self._log_queue.put(f"\n{'─'*60}\nDone (exit {rc})\n{'─'*60}\n")
            self._log_queue.put(None)

    def _stop_proc(self) -> None:
        if not self._is_job_running() or not self._proc:
            self._ensure_buttons_ready()
            return
        try:
            os.killpg(self._proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, AttributeError):
            self._proc.terminate()
        self._log_line("\n[Stopped by user]\n")

    # ── Log helpers ──────────────────────────────────────────────────────────
    def _poll_log(self) -> None:
        try:
            while True:
                item = self._log_queue.get_nowait()
                if item is None:
                    self._reset_buttons()
                else:
                    self._log_line(item)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    def _log_line(self, text: str) -> None:
        self._log.config(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.config(state="disabled")

    def _clear_log(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _reset_buttons(self) -> None:
        self._ensure_buttons_ready()


# ── Entry point ──────────────────────────────────────────────────────────────
def main() -> None:
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.5)
    except tk.TclError:
        pass
    AdminGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
