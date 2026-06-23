"""Typed ingest/fetch errors.

Each carries a ``user_message`` that the API/UI can render as-is. Errors never write to the blob
store or alias table (the caller decides what to persist). See ``plans/02-mvp/a-ingest-fetch.md``.
"""

from __future__ import annotations


class IngestError(Exception):
    """Base for everything ingest can refuse. ``user_message`` is safe to show a user."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class UnrecognizedInputError(IngestError):
    """The pasted string matches no accepted identifier or URL form."""


class IdNotFoundError(IngestError):
    """A resolver returned 404 — the identifier does not exist."""


class NoOpenAccessError(IngestError):
    """The paper exists but no open-access copy was found; suggest uploading the PDF."""


class FetchFailedError(IngestError):
    """Network or 5xx failure after bounded retries."""


class NotAPdfError(IngestError):
    """The fetched payload is not a PDF (e.g. an HTML paywall page)."""


class UnparseableDocument(IngestError):
    """A PDF that cannot be turned into a ``ParsedDoc`` (component b). ``reason`` is a stable code:
    ``no_text_layer`` (scanned, OCR off in v0), ``corrupt_pdf``, ``encrypted``."""

    def __init__(self, reason: str, *, user_message: str | None = None) -> None:
        super().__init__(f"unparseable document: {reason}", user_message=user_message)
        self.reason = reason
