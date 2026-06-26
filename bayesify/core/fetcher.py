"""Fetch — resolve an identifier to an open-access PDF and build its ``SourceDoc`` (component a).

Built on top of ``ingest.parse_input``; the resolution chain follows ``02-mvp/a-ingest-fetch.md``:

1. **arXiv API** for arXiv IDs — authoritative metadata (version + license) then the PDF.
2. **OpenAlex** then **Unpaywall** for DOIs / OpenAlex IDs — best OA location + its license.
3. **Crossref** metadata as last resort, so a no-OA result still names the paper.

Web-framework-free (stdlib + httpx + pydantic): Phase 3's acquisition step imports this unchanged.
The ``httpx.Client`` is **injected**, so tests run against a ``MockTransport`` with no live network,
and Phase-3 batch can pass a rate-limited/polite client.

Provider terms (verified 2026-06-13): OpenAlex single-entity lookups are free (a free API key is
recommended); Unpaywall requires a contact ``email``. The PDF bytes are governed by **each
location's own license**, captured here as ``FetchedSource.license`` so any later caching or
redistribution honors the host/publisher terms (gate G3) — never the index's CC0.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from bayesify.core import config
from bayesify.core import schema as s
from bayesify.core.cache import BlobStore
from bayesify.core.errors import (
    FetchFailedError,
    IdNotFoundError,
    NoOpenAccessError,
    NotAPdfError,
)
from bayesify.core.ingest import ParsedIdentifier

_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_TIMEOUT = httpx.Timeout(30.0)


@dataclass
class FetchedSource:
    """A fetched, content-addressed document plus the license that governs its bytes."""

    source_doc: s.SourceDoc
    license: str | None  # the fetched copy's own license (cc-by / cc0 / publisher / None=unknown)
    is_oa: bool = True
    title: str | None = None  # the paper title from the provider metadata (the "webpage"), if known
    authors: list[str] = field(default_factory=list)  # author names from the provider metadata
    year: int | None = None  # publication year from the provider metadata


class Fetcher:
    ARXIV_API = "https://export.arxiv.org/api/query"
    ARXIV_PDF = "https://arxiv.org/pdf"
    OPENALEX_WORKS = "https://api.openalex.org/works"
    UNPAYWALL = "https://api.unpaywall.org/v2"
    CROSSREF = "https://api.crossref.org/works"

    def __init__(
        self,
        client: httpx.Client,
        blob_store: BlobStore,
        *,
        openalex_api_key: str | None = None,
        unpaywall_email: str | None = None,
    ) -> None:
        self._client = client
        self._blobs = blob_store
        self._oa_key = (
            openalex_api_key if openalex_api_key is not None else config.openalex_api_key()
        )
        self._email = unpaywall_email if unpaywall_email is not None else config.unpaywall_email()

    # --- public entry -----------------------------------------------------------------------------

    def fetch(self, parsed: ParsedIdentifier) -> FetchedSource:
        if parsed.kind == "arxiv":
            return self._fetch_arxiv(parsed)
        if parsed.kind in ("doi", "openalex"):
            return self._fetch_doi_or_openalex(parsed)
        if parsed.kind == "url":
            return self._fetch_direct_url(parsed.value)
        raise FetchFailedError(f"cannot fetch identifier kind {parsed.kind!r}")

    # --- providers --------------------------------------------------------------------------------

    def _fetch_arxiv(self, parsed: ParsedIdentifier) -> FetchedSource:
        feed = self._get(self.ARXIV_API, params={"id_list": parsed.value, "max_results": 1}).text
        entry = ET.fromstring(feed).find("atom:entry", _ARXIV_NS)
        if entry is None or (entry.findtext("atom:title", "", _ARXIV_NS) or "").strip() == "Error":
            raise IdNotFoundError(
                f"arXiv id not found: {parsed.value}",
                user_message=f"No arXiv paper found for {parsed.value}.",
            )
        id_url = entry.findtext("atom:id", "", _ARXIV_NS)  # http://arxiv.org/abs/2011.01808v3
        version = parsed.version_hint or _arxiv_version(id_url)
        license_url = entry.findtext("arxiv:license", default=None, namespaces=_ARXIV_NS)
        title = entry.findtext("atom:title", "", _ARXIV_NS)  # paper title from arXiv metadata
        authors = [
            (n.text or "").strip()
            for n in entry.findall("atom:author/atom:name", _ARXIV_NS)
            if (n.text or "").strip()
        ]
        year = _year_prefix(entry.findtext("atom:published", "", _ARXIV_NS))  # "2020-11-03T..."
        data = self._download(f"{self.ARXIV_PDF}/{parsed.value}{version}")
        return self._store(
            data,
            ids=s.PaperIds(arxiv_id=parsed.value),
            version_label=f"arXiv {version}",
            source="arxiv",
            license=license_url,
            title=title,
            authors=authors,
            year=year,
        )

    def _fetch_doi_or_openalex(self, parsed: ParsedIdentifier) -> FetchedSource:
        ref = f"doi:{parsed.value}" if parsed.kind == "doi" else parsed.value
        # 1) OpenAlex.
        params = {"api_key": self._oa_key} if self._oa_key else {}
        resp = self._get_json(
            f"{self.OPENALEX_WORKS}/{ref}", params=params, not_found_is=IdNotFoundError
        )
        ids = _ids_from_openalex(resp)
        title = resp.get("title") or resp.get("display_name")  # the paper title from OpenAlex
        authors = _openalex_authors(resp)
        year = resp.get("publication_year")  # an int, or None
        loc = resp.get("best_oa_location") or resp.get("primary_location") or {}
        pdf_url = loc.get("pdf_url")
        if pdf_url:
            data = self._download(pdf_url)
            return self._store(
                data,
                ids=ids,
                version_label=f"{loc.get('version') or 'OA'} (OpenAlex)",
                source="openalex",
                license=loc.get("license"),
                title=title,
                authors=authors,
                year=year,
            )
        # 2) Unpaywall (needs an email; skip if not configured).
        if parsed.kind == "doi" and self._email:
            uw = self._get_json(
                f"{self.UNPAYWALL}/{parsed.value}",
                params={"email": self._email},
                not_found_is=None,
            )
            uloc = (uw or {}).get("best_oa_location") or {}
            updf = uloc.get("url_for_pdf")
            if updf:
                data = self._download(updf)
                return self._store(
                    data,
                    ids=s.PaperIds(doi=parsed.value, openalex_id=ids.openalex_id),
                    version_label=f"{uloc.get('version') or 'OA'} (Unpaywall)",
                    source="unpaywall",
                    license=uloc.get("license"),
                    title=title or self._crossref_title(parsed.value),
                    authors=authors,
                    year=year,
                )
        # 3) No OA copy — name the paper so the UI can invite a manual upload.
        title = resp.get("title") or self._crossref_title(parsed.value)
        raise NoOpenAccessError(
            f"no open-access PDF for {ref}",
            user_message=(
                f'No open-access PDF found for "{title}". Upload the PDF to analyze it.'
                if title
                else f"No open-access PDF found for {ref}. Upload the PDF to analyze it."
            ),
        )

    def _fetch_direct_url(self, url: str) -> FetchedSource:
        data = self._download(url)
        return self._store(
            data, ids=s.PaperIds(), version_label="fetched URL", source="url", license=None
        )

    def _crossref_title(self, doi: str) -> str | None:
        cr = self._get_json(f"{self.CROSSREF}/{doi}", not_found_is=None)
        titles = ((cr or {}).get("message") or {}).get("title") or []
        return titles[0] if titles else None

    # --- http helpers -----------------------------------------------------------------------------

    def _get(self, url: str, *, params: dict | None = None) -> httpx.Response:
        try:
            r = self._client.get(url, params=params, follow_redirects=True, timeout=_TIMEOUT)
        except httpx.HTTPError as exc:
            raise FetchFailedError(
                f"request failed: {url}", user_message="Network error fetching the paper."
            ) from exc
        return r

    def _get_json(self, url: str, *, params: dict | None = None, not_found_is) -> dict | None:
        r = self._get(url, params=params)
        if r.status_code == 404:
            if not_found_is is None:
                return None
            raise not_found_is(f"not found: {url}", user_message="That identifier was not found.")
        if r.status_code >= 400:
            raise FetchFailedError(
                f"{r.status_code} from {url}",
                user_message="The metadata provider returned an error.",
            )
        return r.json()

    def _download(self, url: str) -> bytes:
        r = self._get(url)
        if r.status_code == 404:
            raise IdNotFoundError(f"404: {url}", user_message="The paper file could not be found.")
        if r.status_code >= 400:
            raise FetchFailedError(
                f"{r.status_code}: {url}", user_message="Could not download the paper."
            )
        data = r.content
        if data[:5] != b"%PDF-":
            raise NotAPdfError(
                f"not a PDF: {url}",
                user_message="The fetched file is not a PDF (it may be a paywall page).",
            )
        return data

    def _store(
        self,
        data: bytes,
        *,
        ids: s.PaperIds,
        version_label: str,
        source: str,
        license: str | None,
        title: str | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> FetchedSource:
        sha = self._blobs.put(data)
        doc = s.SourceDoc(
            sha256=sha,
            ids=ids,
            version_label=version_label,
            source=source,
            fetched_at=datetime.now(UTC),
        )
        return FetchedSource(
            source_doc=doc,
            license=license,
            is_oa=True,
            title=_clean_title(title),
            authors=authors or [],
            year=year,
        )


def _clean_title(title: str | None) -> str | None:
    """Collapse whitespace (arXiv/crossref titles carry newlines); drop empties."""
    if not title:
        return None
    cleaned = re.sub(r"\s+", " ", title).strip()
    return cleaned or None


def _year_prefix(date: str | None) -> int | None:
    """The leading 4-digit year of an ISO-ish date string (``2020-11-03T...``), else None."""
    head = (date or "")[:4]
    return int(head) if head.isdigit() else None


def _openalex_authors(resp: dict) -> list[str]:
    """Author display names from an OpenAlex work's ``authorships`` (in order)."""
    names = [(a.get("author") or {}).get("display_name") for a in resp.get("authorships") or []]
    return [n.strip() for n in names if n and n.strip()]


def _arxiv_version(id_url: str) -> str:
    # id_url like http://arxiv.org/abs/2011.01808v3 -> "v3"; default v1 if unversioned.
    tail = id_url.rsplit("/", 1)[-1]
    idx = tail.rfind("v")
    return tail[idx:] if idx != -1 and tail[idx + 1 :].isdigit() else "v1"


def _ids_from_openalex(resp: dict) -> s.PaperIds:
    ids = resp.get("ids") or {}
    doi = ids.get("doi") or resp.get("doi")
    if doi:
        doi = doi.replace("https://doi.org/", "").lower()
    oa = (ids.get("openalex") or resp.get("id") or "").rsplit("/", 1)[-1] or None
    return s.PaperIds(doi=doi, openalex_id=oa)
