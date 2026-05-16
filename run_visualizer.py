#!/usr/bin/env python3
"""
Run the Literature Review Flask app from the lit_review repo root.

Resolves visualizer_nlp_lit_review/app.py next to this script and runs it with
cwd set to visualizer_nlp_lit_review/ so template and static paths behave like
`cd visualizer_nlp_lit_review && python3 app.py`.

Inputs: this file must live at the repo root (parent of visualizer_nlp_lit_review/).
Outputs: none (delegates to app.py).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_DEBUG_LOG = Path("/Users/jon/PRIME-AI/lit_review/.cursor/debug-4a1f53.log")
_SESSION = "4a1f53"


def _agent_log(hypothesis_id: str, message: str, data: dict) -> None:
    # region agent log
    payload = {
        "sessionId": _SESSION,
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
        "location": "run_visualizer.py",
        "message": message,
        "data": data,
    }
    try:
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # endregion


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    viz_dir = repo_root / "visualizer_nlp_lit_review"
    app_py = viz_dir / "app.py"

    _agent_log(
        "H1",
        "run_visualizer entry",
        {
            "cwd": os.getcwd(),
            "repo_root": str(repo_root),
            "viz_dir": str(viz_dir),
            "app_py": str(app_py),
            "app_py_exists": app_py.is_file(),
        },
    )

    if not app_py.is_file():
        _agent_log(
            "H2",
            "app.py missing under repo root",
            {"expected_path": str(app_py)},
        )
        print(
            "ERROR: Flask app not found at:\n"
            f"  {app_py}\n\n"
            "This script must sit in the lit_review repo root (same folder as "
            "visualizer_nlp_lit_review/).\n"
            "If you use a minimal deploy folder, copy the full tree or run from "
            "the machine path that contains visualizer_nlp_lit_review/.\n\n"
            f"Your shell cwd was: {os.getcwd()}",
            file=sys.stderr,
        )
        return 1

    _agent_log(
        "H3",
        "spawning app.py with cwd=visualizer_nlp_lit_review",
        {"cwd": str(viz_dir)},
    )
    return subprocess.call([sys.executable, str(app_py), *sys.argv[1:]], cwd=str(viz_dir))


if __name__ == "__main__":
    raise SystemExit(main())
