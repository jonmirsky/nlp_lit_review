"""
Configure urllib SSL for Bio.Entrez (NCBI) requests.

Inputs:
- Environment variables (see apply_entrez_ssl_settings docstring).

Outputs:
- Installs a process-wide urllib opener with the chosen SSL context (call once per process
  before Entrez.esearch / efetch).
"""

from __future__ import annotations

import os
import ssl
import sys
import urllib.request
from pathlib import Path


def apply_entrez_ssl_settings() -> None:
    """Install urllib HTTPS handler for Entrez based on environment.

    Priority:
    1. ``LIT_REVIEW_ENTREZ_INSECURE_SSL=1`` — disable verification (university SSL inspection).
    2. ``LIT_REVIEW_SSL_CA_BUNDLE`` or ``SSL_CERT_FILE`` — path to a PEM CA bundle.
    3. ``certifi`` default bundle (helps stock macOS python.org installs).
    4. System default SSL context.
    """
    insecure = os.environ.get("LIT_REVIEW_ENTREZ_INSECURE_SSL", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    ca_bundle = (
        os.environ.get("LIT_REVIEW_SSL_CA_BUNDLE", "").strip()
        or os.environ.get("SSL_CERT_FILE", "").strip()
    )

    if insecure:
        print(
            "WARNING: LIT_REVIEW_ENTREZ_INSECURE_SSL is set; SSL verification is OFF for "
            "NCBI Entrez. Use only on networks you trust.",
            file=sys.stderr,
            flush=True,
        )
        ctx = ssl._create_unverified_context()
    elif ca_bundle and Path(ca_bundle).is_file():
        ctx = ssl.create_default_context(cafile=ca_bundle)
    else:
        try:
            import certifi  # type: ignore[import-not-found]

            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()

    handler = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(handler)
    urllib.request.install_opener(opener)


def ssl_error_hint(exc: BaseException) -> str:
    """Human-readable hint when Entrez fails with certificate errors."""
    return (
        "NCBI Entrez SSL verification failed (common on macOS or university networks).\n\n"
        "Try one of:\n"
        "  1. Run Apple's certificate installer for your Python, e.g.\n"
        "     /Applications/Python 3.11/Install Certificates.command\n"
        "  2. Set LIT_REVIEW_SSL_CA_BUNDLE to your institution's root CA .pem file\n"
        "  3. In the admin GUI, check 'Insecure SSL for NCBI' (or export "
        "LIT_REVIEW_ENTREZ_INSECURE_SSL=1)\n\n"
        f"Original error: {exc}"
    )
