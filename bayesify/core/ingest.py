"""Ingest — turn user input into a canonical ``SourceDoc`` (component a, network-free core).

This module owns input classification and identifier normalization (authoritative; the frontend's
guess is only a hint), plus ``ingest_upload`` for dropped PDFs. The live provider-fetch resolution
chain (arXiv API -> OpenAlex/Unpaywall -> Crossref) is built on top of ``parse_input`` in a later
increment; it is deliberately not in this file so the classification/normalization logic stays
network-free and trivially testable.

DOIs are lowercased; arXiv/OpenAlex IDs are normalized to their canonical form. Version suffixes are
split off and kept as a hint (a new arXiv version is a different document and must not replay a
stale cache entry — see ``cache.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from bayesify.core import schema as s
from bayesify.core.cache import BlobStore
from bayesify.core.errors import NotAPdfError, UnrecognizedInputError

# --- identifier patterns --------------------------------------------------------------------------
_ARXIV_NEW = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5})(v\d+)?$", re.IGNORECASE)
_ARXIV_OLD = re.compile(r"^(?:arxiv:)?([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$", re.IGNORECASE)
_ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?]+?)(?:\.pdf)?$", re.IGNORECASE)
_DOI_BARE = re.compile(r"^(?:doi:)?(10\.\d{4,9}/\S+)$", re.IGNORECASE)
_DOI_URL = re.compile(r"doi\.org/(10\.\d{4,9}/\S+)$", re.IGNORECASE)
_OPENALEX = re.compile(r"^(?:https?://openalex\.org/)?(W\d+)$", re.IGNORECASE)
# PubMed: a bare PMCID is unambiguous (the ``PMC`` prefix); a bare PMID would collide with any stray
# integer, so it needs an explicit ``PMID:`` marker or a pubmed.ncbi URL.
_PMCID = re.compile(r"^(?:pmcid:\s*)?(PMC\d+)$", re.IGNORECASE)
_PMID = re.compile(r"^pmid:\s*(\d+)$", re.IGNORECASE)
_PMC_URL = re.compile(r"ncbi\.nlm\.nih\.gov/(?:pmc/articles|articles)/(PMC\d+)", re.IGNORECASE)
_PMID_URL = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", re.IGNORECASE)
# OSF (and the preprint servers it hosts: PsyArXiv, SocArXiv, …) is a JS-rendered SPA, so its
# landing pages carry no server-side citation tags — but a 5-char GUID (optionally ``_v\d`` version)
# resolves to a PDF via the download endpoint. Match the ``/preprints/<provider>/<guid>`` and bare
# ``osf.io/<guid>`` forms; the 5-char width keeps path words like ``preprints`` from matching.
_OSF_PREPRINT = re.compile(r"osf\.io/preprints/[^/?#]+/([a-z0-9]{5}(?:_v\d+)?)", re.IGNORECASE)
_OSF_GUID = re.compile(r"osf\.io/([a-z0-9]{5}(?:_v\d+)?)/?(?:[?#]|$)", re.IGNORECASE)
# Elsevier bot-blocks its landing pages, but the PII in a ScienceDirect/linkinghub URL is indexed by
# CrossRef as an ``alternative-id`` — so we capture it and later resolve it to a DOI to find a copy
# hosted elsewhere, rather than scraping the (blocked) page.
_ELSEVIER_PII = re.compile(
    r"(?:sciencedirect\.com/science/article/(?:abs/)?pii|linkinghub\.elsevier\.com/retrieve/pii)"
    r"/([A-Z0-9]+)",
    re.IGNORECASE,
)
_URL = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedIdentifier:
    kind: str  # "arxiv" | "doi" | "openalex" | "pubmed" | "osf" | "pii" | "url"
    value: str  # normalized (pubmed: PMID/"PMC…"; osf: lowercase GUID; pii: uppercase Elsevier PII)
    version_hint: str | None = None  # e.g. "v2" for an explicitly-versioned arXiv id


def _split_arxiv(match: re.Match) -> ParsedIdentifier:
    base, version = match.group(1), match.group(2)
    return ParsedIdentifier("arxiv", base.lower() if "/" in base else base, version)


def parse_input(raw: str) -> ParsedIdentifier:
    """Classify and normalize a pasted identifier or URL. Raises ``UnrecognizedInputError`` rather
    than guessing when nothing matches."""
    v = raw.strip()
    if not v:
        raise UnrecognizedInputError(
            "empty input", user_message="Please paste an identifier or URL."
        )

    if m := _ARXIV_URL.search(v):
        inner = m.group(1)
        if mm := (_ARXIV_NEW.match(inner) or _ARXIV_OLD.match(inner)):
            return _split_arxiv(mm)
    for pat in (_ARXIV_NEW, _ARXIV_OLD):
        if m := pat.match(v):
            return _split_arxiv(m)
    if m := (_DOI_URL.search(v) or _DOI_BARE.match(v)):
        return ParsedIdentifier("doi", m.group(1).lower())
    if m := _OPENALEX.match(v):
        return ParsedIdentifier("openalex", m.group(1).upper())
    if m := (_PMC_URL.search(v) or _PMCID.match(v)):
        return ParsedIdentifier("pubmed", m.group(1).upper())  # canonical "PMC…"
    if m := (_PMID_URL.search(v) or _PMID.match(v)):
        return ParsedIdentifier("pubmed", m.group(1))  # bare PMID digits
    if m := (_OSF_PREPRINT.search(v) or _OSF_GUID.search(v)):
        return ParsedIdentifier("osf", m.group(1).lower())
    if m := _ELSEVIER_PII.search(v):
        return ParsedIdentifier("pii", m.group(1).upper())
    if _URL.match(v):
        return ParsedIdentifier("url", v)
    raise UnrecognizedInputError(
        f"unrecognized input: {raw!r}",
        user_message="That doesn't look like an arXiv ID, DOI, OpenAlex ID, PMID/PMCID, or URL.",
    )


def to_paper_ids(parsed: ParsedIdentifier) -> s.PaperIds:
    """Map a parsed identifier into the ``SourceDoc.ids`` shape (URLs carry no canonical id yet)."""
    if parsed.kind == "arxiv":
        return s.PaperIds(arxiv_id=parsed.value)
    if parsed.kind == "doi":
        return s.PaperIds(doi=parsed.value)
    if parsed.kind == "openalex":
        return s.PaperIds(openalex_id=parsed.value)
    if parsed.kind == "pubmed":
        if parsed.value.upper().startswith("PMC"):
            return s.PaperIds(pmcid=parsed.value)
        return s.PaperIds(pmid=parsed.value)
    return s.PaperIds()


def ingest_upload(
    blob_store: BlobStore, data: bytes, *, filename: str | None = None
) -> s.SourceDoc:
    """Store a dropped PDF content-addressed and build its ``SourceDoc``. Rejects non-PDF bytes."""
    if data[:5] != b"%PDF-":
        raise NotAPdfError(
            "uploaded bytes are not a PDF",
            user_message="That file doesn't look like a PDF.",
        )
    sha256 = blob_store.put(data)
    return s.SourceDoc(
        sha256=sha256,
        ids=s.PaperIds(),
        version_label=f"uploaded PDF ({filename})" if filename else "uploaded PDF",
        source="upload",
        fetched_at=datetime.now(UTC),
    )
