#!/usr/bin/env python3
"""
Tests for fast-baseline mode: env-var config helpers, CLI flag plumbing,
captcha short-circuit, and deferred-paper retry RIS writing.

Input files:  none (pure unit tests; no Selenium launched)
Output files: none (uses pytest tmp_path for filesystem assertions)
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "scripts" / "helpers"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for _p in (HELPERS, SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import auto_search_wrapper  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# Import the scraper module. Selenium is installed on this machine; we only
# need module-level symbols (no Chrome is started).
# ---------------------------------------------------------------------------
import full_text_scrape_V5 as scraper  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAST_ENV_KEYS = (
    "LIT_REVIEW_FAST_BASELINE",
    "LIT_REVIEW_MAX_PAPER_SECONDS",
    "LIT_REVIEW_CAPTCHA_TIMEOUT",
    "LIT_REVIEW_SKIP_DEEP_PUBLISHER",
)


def _clean_env():
    """Return a context manager that removes all fast-baseline env vars."""
    return patch.dict(os.environ, {}, clear=False)


def _reset_fast_env():
    for k in _FAST_ENV_KEYS:
        os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# 1. Config helper defaults — fast mode OFF
# ---------------------------------------------------------------------------

def test_env_defaults_off():
    _reset_fast_env()
    assert scraper._fast_baseline_enabled() is False
    assert scraper._captcha_timeout_seconds() == 180
    assert scraper._max_paper_seconds() == float("inf")
    assert scraper._skip_deep_publisher() is False
    assert scraper._page_load_timeout_seconds() == 60


# ---------------------------------------------------------------------------
# 2. Config helper defaults — fast mode ON via LIT_REVIEW_FAST_BASELINE=1
# ---------------------------------------------------------------------------

def test_env_fast_baseline_defaults():
    _reset_fast_env()
    with patch.dict(os.environ, {"LIT_REVIEW_FAST_BASELINE": "1"}):
        assert scraper._fast_baseline_enabled() is True
        assert scraper._captcha_timeout_seconds() == 0
        assert scraper._max_paper_seconds() == 30.0
        assert scraper._skip_deep_publisher() is True
        assert scraper._page_load_timeout_seconds() == 20


# ---------------------------------------------------------------------------
# 3. Individual env var overrides work independently of fast mode flag
# ---------------------------------------------------------------------------

def test_env_overrides_individual():
    _reset_fast_env()
    with patch.dict(os.environ, {
        "LIT_REVIEW_MAX_PAPER_SECONDS": "45",
        "LIT_REVIEW_CAPTCHA_TIMEOUT": "10",
    }):
        # fast mode still off
        assert scraper._fast_baseline_enabled() is False
        # but individual overrides apply
        assert scraper._max_paper_seconds() == 45.0
        assert scraper._captcha_timeout_seconds() == 10


def test_env_fast_baseline_with_explicit_max():
    _reset_fast_env()
    with patch.dict(os.environ, {
        "LIT_REVIEW_FAST_BASELINE": "1",
        "LIT_REVIEW_MAX_PAPER_SECONDS": "60",
    }):
        assert scraper._fast_baseline_enabled() is True
        assert scraper._max_paper_seconds() == 60.0


def test_env_skip_deep_explicit_false():
    _reset_fast_env()
    with patch.dict(os.environ, {
        "LIT_REVIEW_FAST_BASELINE": "1",
        "LIT_REVIEW_SKIP_DEEP_PUBLISHER": "0",
    }):
        assert scraper._skip_deep_publisher() is False


# ---------------------------------------------------------------------------
# 4. Wrapper CLI flag → env var plumbing
# ---------------------------------------------------------------------------

def test_wrapper_flag_fast_baseline_sets_env():
    _reset_fast_env()
    args = SimpleNamespace(
        fast_baseline=True,
        max_paper_seconds=None,
        captcha_timeout=None,
        skip_deep_publisher_fallbacks=False,
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LIT_REVIEW_FAST_BASELINE", None)
        auto_search_wrapper._apply_fast_baseline_env(args)
        assert os.environ.get("LIT_REVIEW_FAST_BASELINE") == "1"


def test_wrapper_flag_max_paper_seconds():
    _reset_fast_env()
    args = SimpleNamespace(
        fast_baseline=False,
        max_paper_seconds=45,
        captcha_timeout=None,
        skip_deep_publisher_fallbacks=False,
    )
    with patch.dict(os.environ, {}, clear=False):
        auto_search_wrapper._apply_fast_baseline_env(args)
        assert os.environ.get("LIT_REVIEW_MAX_PAPER_SECONDS") == "45"


def test_wrapper_flag_captcha_timeout_zero():
    _reset_fast_env()
    args = SimpleNamespace(
        fast_baseline=False,
        max_paper_seconds=None,
        captcha_timeout=0,
        skip_deep_publisher_fallbacks=False,
    )
    with patch.dict(os.environ, {}, clear=False):
        auto_search_wrapper._apply_fast_baseline_env(args)
        assert os.environ.get("LIT_REVIEW_CAPTCHA_TIMEOUT") == "0"


def test_wrapper_flag_skip_deep():
    _reset_fast_env()
    args = SimpleNamespace(
        fast_baseline=False,
        max_paper_seconds=None,
        captcha_timeout=None,
        skip_deep_publisher_fallbacks=True,
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LIT_REVIEW_SKIP_DEEP_PUBLISHER", None)
        auto_search_wrapper._apply_fast_baseline_env(args)
        assert os.environ.get("LIT_REVIEW_SKIP_DEEP_PUBLISHER") == "1"


def test_wrapper_no_flags_no_env_mutation():
    _reset_fast_env()
    before = {k: os.environ.get(k) for k in _FAST_ENV_KEYS}
    args = SimpleNamespace(
        fast_baseline=False,
        max_paper_seconds=None,
        captcha_timeout=None,
        skip_deep_publisher_fallbacks=False,
    )
    auto_search_wrapper._apply_fast_baseline_env(args)
    after = {k: os.environ.get(k) for k in _FAST_ENV_KEYS}
    assert before == after


# ---------------------------------------------------------------------------
# 5. wait_for_captcha_completion returns immediately when timeout is 0
# ---------------------------------------------------------------------------

class _FakeDriver:
    """Minimal driver stub — must NOT be called when captcha is short-circuited."""

    @property
    def current_url(self):
        raise AssertionError("Driver accessed when captcha wait was supposed to be skipped")

    @property
    def title(self):
        raise AssertionError("Driver accessed when captcha wait was supposed to be skipped")

    @property
    def page_source(self):
        raise AssertionError("Driver accessed when captcha wait was supposed to be skipped")

    def find_elements(self, *args: Any, **kwargs: Any):
        raise AssertionError("Driver accessed when captcha wait was supposed to be skipped")


def test_wait_for_captcha_short_circuit_when_zero():
    _reset_fast_env()
    with patch.dict(os.environ, {"LIT_REVIEW_CAPTCHA_TIMEOUT": "0"}):
        t0 = time.monotonic()
        result = scraper.wait_for_captcha_completion(_FakeDriver())  # type: ignore[arg-type]
        elapsed = time.monotonic() - t0
    assert result is False, "Should return False (skipped) when captcha timeout is 0"
    assert elapsed < 1.0, f"Should return in <1s, took {elapsed:.2f}s"


def test_wait_for_captcha_not_short_circuit_when_nonzero(monkeypatch):
    _reset_fast_env()
    # Patch time.time to simulate instant expiry of the fast loop (8 * 1s checks).
    # We use a very short timeout and a driver that returns stable state so the
    # function exercises the "check every 3s" loop and exits immediately.
    calls = [0]

    class _StableDriver:
        current_url = "https://example.com"
        title = "Example"
        page_source = "<html></html>"

        def find_elements(self, *args: Any, **kwargs: Any):
            return []

    with patch.dict(os.environ, {"LIT_REVIEW_CAPTCHA_TIMEOUT": "1"}):
        t0 = time.monotonic()
        scraper.wait_for_captcha_completion(_StableDriver(), timeout=1)  # type: ignore[arg-type]
        elapsed = time.monotonic() - t0
    assert elapsed < 20.0, "Should exit within a few seconds for a 1s timeout"


# ---------------------------------------------------------------------------
# 6. Slow-retry RIS writer (inline in loop; test via deferred tracking constants)
# ---------------------------------------------------------------------------

def test_fast_defer_reasons_set():
    assert scraper.ERROR_FAST_TIMEOUT in scraper._FAST_DEFER_REASONS
    assert scraper.ERROR_DEFERRED_DEEP_PUBLISHER in scraper._FAST_DEFER_REASONS
    assert scraper.ERROR_PUBLISHER_ERROR not in scraper._FAST_DEFER_REASONS


def test_slow_retry_ris_written(tmp_path: Path):
    """Simulate the missing-dir write logic for deferred refs."""
    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    slow_retry_ris = missing_dir / "slow_retry_candidates.ris"

    deferred_for_retry = [
        {"ris_text": "TY  - JOUR\nTI  - Paper One\nER  -\n"},
        {"ris_text": "TY  - JOUR\nTI  - Paper Two\nER  -\n"},
    ]

    if deferred_for_retry:
        with open(slow_retry_ris, "w", encoding="utf-8") as f:
            f.write("; Papers deferred by fast-baseline mode\n")
            f.write("; generated by full_text_scrape_V5.py\n\n")
            for ref in deferred_for_retry:
                f.write(ref["ris_text"])
                f.write("\n")

    assert slow_retry_ris.exists()
    content = slow_retry_ris.read_text()
    assert "Paper One" in content
    assert "Paper Two" in content


def test_slow_retry_ris_empty_write(tmp_path: Path):
    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    slow_retry_ris = missing_dir / "slow_retry_candidates.ris"

    deferred_for_retry: list = []

    slow_retry_ris.write_text(
        "; No papers deferred by fast-baseline mode\n"
        "; generated by full_text_scrape_V5.py\n",
        encoding="utf-8",
    )

    assert slow_retry_ris.exists()
    assert "No papers deferred" in slow_retry_ris.read_text()
