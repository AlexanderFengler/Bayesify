"""Immutable API-layer defaults.

This is intentionally separate from ``bayesify.core.config``: these values configure the web/API
transport, not the analysis engine.
"""

from __future__ import annotations

import os
from types import MappingProxyType

API_CONFIG = MappingProxyType(
    {
        "title": "Bayesify API",
        "version": "0.1.0",
        "cors": MappingProxyType(
            {
                "allow_origins": ("http://localhost:5173", "http://127.0.0.1:5173"),
                "allow_methods": ("*",),
                "allow_headers": ("*",),
            }
        ),
    }
)


def openalex_api_key() -> str | None:
    return os.environ.get("OPENALEX_API_KEY") or None


def unpaywall_email() -> str | None:
    return os.environ.get("UNPAYWALL_EMAIL") or None


def trusted_tokens() -> dict[str, str]:
    tokens: dict[str, str] = {}
    for entry in os.environ.get("BAYESIFY_TRUSTED_TOKENS", "").split(","):
        name, sep, token = entry.partition(":")
        name, token = name.strip(), token.strip()
        if sep and name and token:
            tokens[token] = name
    return tokens


def override_review_timeout_s() -> float:
    try:
        return max(0.0, float(os.environ.get("BAYESIFY_OVERRIDE_REVIEW_TIMEOUT_S", "8")))
    except ValueError:
        return 8.0
