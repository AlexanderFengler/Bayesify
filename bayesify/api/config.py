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


def resend_api_key() -> str | None:
    """Resend API key for the About-us contact form. Absent → the form is disabled (503)."""
    return os.environ.get("RESEND_API_KEY") or None


def contact_to_email() -> str | None:
    """Where contact-form messages are delivered. Absent → the form is disabled (503)."""
    return os.environ.get("CONTACT_TO_EMAIL") or None


def contact_from_email() -> str:
    """The verified sender address the contact email is sent *from* (must be a Resend-verified
    domain in production; `onboarding@resend.dev` works for testing to the account owner only)."""
    return os.environ.get("CONTACT_FROM_EMAIL") or "onboarding@resend.dev"
