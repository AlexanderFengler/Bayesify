"""Sentence-aligned verbatim quotes.

Every ``EvidenceSpan.quote`` must be a verbatim substring of its section (hard guarantee — UI
highlighting and grounding checks slice on it), but until now nothing chose GOOD endpoints for that
substring: detector spans were a ±30-char window and judge quotes were whatever fragment the model
excerpted, so the report's "In the paper" sections read as mid-sentence shards. This module picks
sentence boundaries instead — same guarantee, readable endpoints.
"""

from __future__ import annotations

import re

# A terminator ends a sentence only when followed by whitespace (so decimals like "R-hat < 1.01"
# never split) and not preceded by a common scientific abbreviation or a single-letter initial.
_TERMINATORS = ".!?"
_ABBREV_RE = re.compile(
    r"(?:\b(?:al|e\.g|i\.e|cf|vs|resp|etc|Fig|Figs|Eq|Eqs|Sec|Secs|Tab|Tabs|Ref|Refs|Dr|Prof|No)"
    r"|\b[A-Z])\.$"
)

# Default cap: roughly two long scientific sentences — long enough for coherence, short enough that
# "In the paper" stays scannable.
MAX_QUOTE_CHARS = 360


def _is_boundary(text: str, i: int) -> bool:
    """True when ``text[i]`` terminates a sentence: a terminator followed by whitespace (or the end
    of the text), not part of an abbreviation/initial."""
    if text[i] not in _TERMINATORS:
        return False
    if i + 1 < len(text) and not text[i + 1].isspace():
        return False
    return _ABBREV_RE.search(text[max(0, i - 11) : i + 1]) is None


def _sentence_start(text: str, pos: int) -> int:
    """Index of the first character of the sentence containing ``pos``."""
    for i in range(min(pos, len(text)) - 1, -1, -1):
        if _is_boundary(text, i):
            j = i + 1
            while j < len(text) and text[j].isspace():
                j += 1
            return min(j, pos)
    return 0


def _sentence_end(text: str, pos: int) -> int:
    """Index just past the terminator of the sentence containing ``pos`` (or ``len(text)``)."""
    if pos > 0 and pos <= len(text) and _is_boundary(text, pos - 1):
        return pos  # the span already ends exactly on a sentence terminator
    for i in range(min(pos, len(text)), len(text)):
        if _is_boundary(text, i):
            return i + 1
    return len(text)


def sentence_span(text: str, start: int, end: int, *, max_chars: int = MAX_QUOTE_CHARS) -> str:
    """The sentence(s) of ``text`` enclosing ``[start, end)`` — a verbatim substring that always
    contains the match. When the enclosing sentence overruns ``max_chars``, fall back to a
    word-boundary window (preferring to keep the sentence OPENING, which reads far better than a
    mid-sentence start), still containing the match."""
    left = _sentence_start(text, start)
    right = _sentence_end(text, max(end, start))
    if right - left <= max_chars:
        return text[left:right].strip()

    # Overlong sentence: start at the sentence opening when the match still fits in that window;
    # otherwise slide right just enough to contain the match.
    lo = left if end - left <= max_chars else max(left, end - max_chars)
    hi = min(right, lo + max_chars)
    # Snap to word boundaries without ever excluding the match (the old detector-window discipline).
    while lo < start and not (lo == 0 or text[lo - 1].isspace()):
        lo += 1
    while hi > end and not (hi == len(text) or text[hi].isspace()):
        hi -= 1
    return text[lo:hi].strip()
