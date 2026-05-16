# Monorepo + Server Clone Checklist

<!-- Purpose: step-by-step guide to move from visualizer-only git (nlp_lit_review)
     to a single cloneable repo at the project root, so the automated-search
     pipeline can run from either the laptop or a VPS/GPU server while Render
     continues to host the public website. Generated for operator use; not
     executed automatically. -->

**Target state**

- One GitHub repo (recommended name: **`nlp_lit_review`**) at the **project root**
  (current local folder: `/Users/jon/PRIME-AI/nlp_lit_review`; internal folder
  `visualizer_nlp_lit_review/` stays as-is).
- **Render** still hosts the public site; **Root Directory** = `visualizer_nlp_lit_review`.
- **Pipeline** (`automated_search/`, `admin_gui.py`) lives in the same repo.
- **PDFs** stay on Google Drive + R2 (not in git).
- Optional: a **VPS/GPU server** runs long Selenium/search jobs only; Render remains
  the public website host.

**Current state (verify before starting)**

- [ ] Git remote for visualizer: `https://github.com/jonmirsky/nlp_lit_review.git`
  (offloaded copy: `.../badjatia-hu-onedrive/NLP/lit_review/visualizer_nlp_lit_review_offloaded/.git`)
- [ ] `nlp_lit_review/` itself has **no** `.git` at root (only visualizer had git historically).
- [ ] Live site: https://nlp-lit-review.onrender.com (or your custom domain).
- [ ] rclone remotes `gdrive:` and `r2:` configured on the machine that runs the pipeline.

---

## Phase 0 — Decisions (do not skip)

- [ ] **Repo name on GitHub:** keep `nlp_lit_review` for the **whole** monorepo (recommended).
      Do **not** rename the GitHub repo to `visualizer_nlp_lit_review` unless the repo
      will remain visualizer-only.
- [ ] **Local parent folder name:** keep current `nlp_lit_review` unless you have a
      separate reason to rename it (cosmetic only; code uses paths relative to repo root).
- [ ] **Keep** subdirectory name `visualizer_nlp_lit_review/` (avoid mass path refactors).
- [ ] **Server strategy:** Render = website; laptop or VPS/GPU server = pipeline runner.
      This keeps the current Render deployment and adds a second place where the same
      search pipeline can be run after cloning the repo.

---

## Phase 1 — Prepare cloneable repo at `nlp_lit_review/` root

### 1.1 Backup

- [ ] Copy entire `nlp_lit_review/` tree to a safe backup (Time Machine / zip).
- [ ] Note latest good master RIS:
      `visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_*.txt`
- [ ] Export list of env vars you use:
      `NCBI_EMAIL`, `NCBI_API_KEY`, `LIT_REVIEW_PDF_REMOTE`,
      `LIT_REVIEW_GDRIVE_REMOTE`, `LIT_REVIEW_AUTO_R2_SYNC`, etc.

### 1.2 Put Git at repo root

Choose **one** approach. This is not a runtime migration from laptop to VPS; it is
only the Git restructuring needed so `git clone` on the server brings down both
the automated-search pipeline and the visualizer files Render needs.

**Option A — Move existing history (preserves visualizer commits)**

```bash
cd /Users/jon/PRIME-AI/nlp_lit_review

# Copy .git from offloaded visualizer (adjust path if yours differs)
cp -r "/Users/jon/Library/CloudStorage/OneDrive-UniversityofMarylandSchoolofMedicine/badjatia-hu-onedrive/NLP/lit_review/visualizer_nlp_lit_review_offloaded/.git" .

# Remove nested .git if it exists under visualizer (should not duplicate)
rm -rf visualizer_nlp_lit_review/.git

git status   # expect many "untracked" files at repo root (automated_search/, admin_gui.py, ...)
```

**Option B — Fresh root repo (simpler, loses old commit graph at root)**

```bash
cd /Users/jon/PRIME-AI/nlp_lit_review
git init
git remote add origin https://github.com/jonmirsky/nlp_lit_review.git
# First push may need --force only if you intend to replace GitHub history (dangerous)
```

- [ ] `git remote -v` shows `origin` → `https://github.com/jonmirsky/nlp_lit_review.git`
- [ ] Only **one** `.git` directory exists (at repo root).

### 1.3 Root `.gitignore`

Create **`/Users/jon/PRIME-AI/nlp_lit_review/.gitignore`** (merge rules from
subfolders). Minimum:

```gitignore
# Python / tooling
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
.env
.env.*

# OS / IDE
.DS_Store
.idea/
.vscode/
.cursor/

# Node (visualizer)
node_modules/
visualizer_nlp_lit_review/dist/
visualizer_nlp_lit_review/build/

# Pipeline run artifacts: local/server runtime output, not source of truth
automated_search/searches/
automated_search/.cache/
automated_search/.tmp_pdfs/
automated_search/found_papers/
automated_search/missing_papers/
archive/found_papers/
archive/found_papers/downloaded_papers/

# PDFs (R2 / Drive only)
visualizer_nlp_lit_review/pdfs_for_github/
**/pdfs_for_github/

# Local RIS backups; commit real pubmed_*.txt files deliberately
visualizer_nlp_lit_review/RIS_source_files/*.bak
visualizer_nlp_lit_review/RIS_source_files/*.bak[0-9]*
visualizer_nlp_lit_review/RIS_source_files/**/*.backup

# Secrets — never commit
*.pem
credentials.json
.rclone.conf
tokens.txt
```

- [ ] Keep `automated_search/searches/` untracked by default. If selected run metadata
      ever needs to be preserved, export or commit it deliberately rather than tracking
      every run folder.
- [ ] Decide whether large `RIS_source_files/pubmed_*.txt` stay in git (yes for Render deploy today).

### 1.4 First monorepo commit

```bash
cd /Users/jon/PRIME-AI/nlp_lit_review
git add .gitignore automated_search/ admin_gui.py run_visualizer.py \
  visualizer_nlp_lit_review/ \
  manual_database_search_results/   # optional: omit archive/ if huge
git status   # review: no .env, no searches/**/input.ris, no node_modules
git commit -m "Monorepo: add automated_search pipeline and admin GUI to nlp_lit_review"
git push -u origin main
```

- [ ] Push succeeds.
- [ ] GitHub shows `automated_search/`, `admin_gui.py`, and `visualizer_nlp_lit_review/` at repo root.

### 1.5 Retire split-git workflow

- [ ] Update or delete `visualizer_nlp_lit_review/NTF-MUST-READ-BEFORE-WORKING-ON-THIS-DIR`
      (no more “copy .git from OneDrive”).
- [ ] Stop using `visualizer_nlp_lit_review_offloaded` as the canonical git home (archive it).

---

## Phase 2 — Reconfigure Render (website)

Render must build from the **subdirectory**, not repo root.

- [ ] Render dashboard → Web Service → **Settings**
- [ ] **Root Directory:** `visualizer_nlp_lit_review`
- [ ] **Build Command** (unchanged):
      `pip install -r requirements_lit_review_visualizer.txt && npm install && npm run build`
- [ ] **Start Command** (unchanged):
      `gunicorn --bind 0.0.0.0:$PORT app:app`
- [ ] **Branch:** `main` (or your deploy branch)
- [ ] Trigger **Manual Deploy** after monorepo push.
- [ ] Site loads: https://nlp-lit-review.onrender.com
- [ ] `GET /api/reload` or restart works after you push a new `pubmed_*.txt`

**If deploy fails after monorepo push**

- [ ] Build log: confirm it `cd`s into `visualizer_nlp_lit_review` (Root Directory set).
- [ ] `requirements_lit_review_visualizer.txt` and `package.json` paths are under that subdir.
- [ ] `render.yaml` at `visualizer_nlp_lit_review/render.yaml` is picked up only if Render uses Blueprint from that root.

**Not affected by repo rename / monorepo**

- [ ] Cloudflare R2 bucket `nlp-lit-review-pdfs`
- [ ] `R2_PUBLIC_URL_BASE` in `config.py`
- [ ] rclone remotes on your laptop/server

---

## Phase 3 — Local developer workflow (after monorepo)

### Pipeline + GUI (from repo root)

```bash
cd /Users/jon/PRIME-AI/nlp_lit_review
export NCBI_EMAIL='you@example.com'
export LIT_REVIEW_PDF_REMOTE='gdrive:nlp_lit_review_1_papers/pdfs'
python3 admin_gui.py
```

### Visualizer locally

```bash
cd /Users/jon/PRIME-AI/nlp_lit_review
python3 run_visualizer.py
# or: cd visualizer_nlp_lit_review && python3 app.py
```

### Deploy new papers to live site

```bash
cd /Users/jon/PRIME-AI/nlp_lit_review
git add visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_<timestamp>.txt
git commit -m "Update master RIS after <run_id>"
git push
# wait for Render deploy; optional: curl https://nlp-lit-review.onrender.com/api/reload
```

- [ ] Document any server-specific paths in a personal note.

---

## Phase 4 — Clone to a separate pipeline server (optional)

Use when you want Entrez + V4/Selenium searches to run off your laptop. Render
continues to host the public website.

### 4.1 Server prerequisites

- [ ] Ubuntu/Debian (or similar) VPS/GPU server with sufficient RAM for Selenium + Chrome.
- [ ] `python3`, `pip`, `git`, `rclone`, Google Chrome + chromedriver (or Chromium).
- [ ] rclone configured with same `gdrive:` and `r2:` remotes (or copy `rclone.conf` securely).
- [ ] Do not expose the admin GUI to the public internet. Prefer CLI in `tmux`/`screen`
      unless you intentionally configure a private desktop session.

### 4.2 Clone monorepo

```bash
git clone https://github.com/jonmirsky/nlp_lit_review.git
cd nlp_lit_review
pip install -r automated_search/requirements.txt
```

### 4.3 Environment (persist in `~/.profile` or systemd unit)

```bash
export NCBI_EMAIL='...'
export NCBI_API_KEY='...'                    # optional
export LIT_REVIEW_PDF_REMOTE='gdrive:nlp_lit_review_1_papers/pdfs'
export LIT_REVIEW_GDRIVE_REMOTE='gdrive:nlp_lit_review_1_papers/pdfs'
export LIT_REVIEW_AUTO_R2_SYNC='1'
# export LIT_REVIEW_ENTREZ_INSECURE_SSL='1'  # only if needed on that network
```

### 4.4 Run pipeline on server

- [ ] Batch: `python3 automated_search/scripts/refresh_catalog.py`
- [ ] Single search: `python3 automated_search/scripts/auto_search_wrapper.py --query '<PubMed query>' --slug '<slug>' --label '(<label>)'`
- [ ] GUI over SSH/X11/VNC only if you explicitly need it; otherwise use CLI.
- [ ] Long runs: `tmux` or `screen` so disconnect does not kill V4.

### 4.5 Publish results back to Render

```bash
git status
git add visualizer_nlp_lit_review/RIS_source_files/pubmed_NLP_v4_<timestamp>.txt
git commit -m "Update master RIS after server run"
git push
```

- [ ] Render deploys the updated visualizer from `visualizer_nlp_lit_review`.
- [ ] PDF links still hit R2 URLs from `config.py`; PDFs themselves are not committed.

### 4.6 Render vs pipeline runner split

| Workload | Where |
|----------|--------|
| Public visualizer | Render |
| Refresh catalog / V4 | VPS/GPU server or laptop |
| R2 sync | End of wrapper on whichever machine runs pipeline |

---

## Phase 5 — Verification matrix

| Check | Pass? |
|-------|-------|
| `git pull` at repo root updates both `automated_search/` and `visualizer_nlp_lit_review/` | [ ] |
| `refresh_catalog.py --dry-run` lists catalog entries | [ ] |
| One wrapper smoke run writes under `automated_search/searches/` | [ ] |
| Merge creates new `visualizer_nlp_lit_review/RIS_source_files/pubmed_*.txt` | [ ] |
| `git push` + Render deploy shows new papers on live site | [ ] |
| PDF open on site (R2 URL) for a newly downloaded paper | [ ] |
| `python3 -m pytest automated_search/tests/ -v` at repo root | [ ] |

---

## Phase 6 — Docs and cleanup (after stable)

- [ ] Update `automated_search/docs/AI_summary_of_pipeline_5_18_2026.txt` §16 if deploy paths changed.
- [ ] Update `visualizer_nlp_lit_review/README.md` “push from repo root” instructions.
- [ ] Fix `prepare_pdfs_for_github.py` GitHub URL if you renamed the repo.
- [ ] Remove obsolete `.git` copies on OneDrive after 30 days stable.

---

---

## Rollback

- [ ] Restore backup zip of `nlp_lit_review/`.
- [ ] Restore `.git` to offloaded visualizer-only layout if push went wrong.
- [ ] Render: point Root Directory back and redeploy last known-good commit.

---

## Quick reference — path constants in code

These assume repo root contains **both** siblings (do not flatten without code changes):

| Component | Path from repo root |
|-----------|---------------------|
| Catalog config | `visualizer_nlp_lit_review/config.py` |
| Master RIS | `visualizer_nlp_lit_review/RIS_source_files/` |
| Wrapper | `automated_search/scripts/auto_search_wrapper.py` |
| Admin GUI | `admin_gui.py` |
| Run searches | `automated_search/searches/` |

---

*Last updated: 2026-05-18. Operator checklist — execute steps manually in order.*
