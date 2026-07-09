"""Paper-title normalization helpers."""

from __future__ import annotations

import re


def normalize_paper_title(title: str | None) -> str | None:
    """Clean a best-effort paper title and sentence-case titles extracted in ALL CAPS."""
    if not title:
        return None
    cleaned = re.sub(r"\s+", " ", title).strip()
    if not cleaned:
        return None
    return _sentence_case(cleaned) if _is_all_caps_title(cleaned) else cleaned


def _is_all_caps_title(title: str) -> bool:
    letters = [ch for ch in title if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def _sentence_case(title: str) -> str:
    lowered = title.lower()
    chars = list(lowered)
    for i, ch in enumerate(chars):
        if ch.isalpha():
            chars[i] = ch.upper()
            break
    return "".join(chars)
