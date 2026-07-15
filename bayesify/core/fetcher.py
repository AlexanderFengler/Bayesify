"""Fetch — resolve an identifier to an open-access PDF and build its ``SourceDoc`` (component a).

Built on top of ``ingest.parse_input``; the resolution chain follows ``02-mvp/a-ingest-fetch.md``:

1. **arXiv API** for arXiv IDs — authoritative metadata (version + license) then the PDF.
2. **OpenAlex** then **Unpaywall** for DOIs / OpenAlex IDs — best OA location + its license.
3. **Crossref** metadata as last resort, so a no-OA result still names the paper.

A **PMID / PMCID** is mapped to its DOI via NCBI's ID Converter and resolved through step 2 (with
the PubMed ids stamped on); a DOI-less PMCID falls back to Europe PMC's full-text PDF.

A pasted **URL** is fetched directly if it is already a PDF; otherwise it is treated as a
publisher/preprint landing page and its Highwire ``citation_*`` meta tags are mined for a
``citation_pdf_url`` (fetched directly) or a ``citation_doi`` (re-dispatched through step 2). One
publisher-agnostic path covers eLife, PsyArXiv/OSF, ScienceDirect, PMC, PLOS, … with no per-host
code.

Web-framework-free (stdlib + httpx + pydantic): Phase 3's acquisition step imports this unchanged.
The ``httpx.Client`` is **injected**, so tests run against a ``MockTransport`` with no live network,
and Phase-3 batch can pass a rate-limited/polite client.

Provider terms (verified 2026-06-13): OpenAlex single-entity lookups are free (a free API key is
recommended); Unpaywall requires a contact ``email``. The PDF bytes are governed by **each
location's own license**, captured here as ``FetchedSource.license`` so any later caching or
redistribution honors the host/publisher terms (gate G3) — never the index's CC0.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.etree.ElementTree import ParseError

import httpx

from bayesify.core import schema as s
from bayesify.core.cache import BlobStore
from bayesify.core.errors import (
    FetchFailedError,
    IdNotFoundError,
    NoOpenAccessError,
    NotAPdfError,
    UnrecognizedInputError,
)
from bayesify.core.ingest import ParsedIdentifier, parse_input
from bayesify.core.titles import normalize_paper_title

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
    NCBI_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"

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
        self._oa_key = openalex_api_key
        self._email = unpaywall_email

    # --- public entry -----------------------------------------------------------------------------

    def fetch(self, parsed: ParsedIdentifier) -> FetchedSource:
        if parsed.kind == "arxiv":
            return self._fetch_arxiv(parsed)
        if parsed.kind in ("doi", "openalex"):
            return self._fetch_doi_or_openalex(parsed)
        if parsed.kind == "pubmed":
            return self._fetch_pubmed(parsed)
        if parsed.kind == "url":
            return self._fetch_direct_url(parsed.value)
        raise FetchFailedError(f"cannot fetch identifier kind {parsed.kind!r}")

    # --- providers --------------------------------------------------------------------------------

    def _fetch_arxiv(self, parsed: ParsedIdentifier) -> FetchedSource:
        response = self._get(self.ARXIV_API, params={"id_list": parsed.value, "max_results": 1})
        if response.status_code >= 400:
            raise FetchFailedError(
                f"{response.status_code} from arXiv API",
                user_message="arXiv returned an error while looking up the paper.",
            )
        try:
            root = ET.fromstring(response.text)
        except ParseError as exc:
            content_type = response.headers.get("content-type", "unknown")
            preview = response.text[:200].replace("\n", " ").replace("\r", " ")
            raise FetchFailedError(
                "non-XML response from arXiv API; "
                f"content-type={content_type}; preview={preview!r}",
                user_message=(
                    "arXiv did not return metadata for this request. Try uploading the PDF, or "
                    "try the arXiv URL again later."
                ),
            ) from exc
        if root.tag != "{http://www.w3.org/2005/Atom}feed":
            preview = response.text[:200].replace("\n", " ").replace("\r", " ")
            raise FetchFailedError(
                f"unexpected response from arXiv API; root={root.tag!r}; preview={preview!r}",
                user_message=(
                    "arXiv did not return metadata for this request. Try uploading the PDF, or "
                    "try the arXiv URL again later."
                ),
            )
        entry = root.find("atom:entry", _ARXIV_NS)
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

    def _fetch_pubmed(self, parsed: ParsedIdentifier) -> FetchedSource:
        # NCBI's ID Converter maps a PMID/PMCID to its DOI (and the sibling id) in a single call.
        params = {"ids": parsed.value, "format": "json", "tool": "bayesify"}
        if self._email:  # NCBI asks for a contact email for politeness; reuse the Unpaywall one
            params["email"] = self._email
        record = _pubmed_record(self._get_json(self.NCBI_IDCONV, params=params, not_found_is=None))
        if not record or record.get("status") == "error":
            raise IdNotFoundError(
                f"PubMed id not found: {parsed.value}",
                user_message=f"No PubMed record found for {parsed.value}.",
            )
        pmid = record.get("pmid") or None
        pmcid = record.get("pmcid") or None
        # 1) With a DOI, resolve through the full OA chain (OpenAlex/Unpaywall/Crossref) — Unpaywall
        #    already indexes PMC-hosted copies — then stamp on the learned PubMed ids.
        if doi_id := _as_doi_id(record.get("doi")):
            fetched = self._fetch_doi_or_openalex(doi_id)
            fetched.source_doc.ids.pmid = pmid
            fetched.source_doc.ids.pmcid = pmcid
            return fetched
        # 2) No DOI, but an OA PMC copy may still exist — Europe PMC serves its full text directly.
        if pmcid:
            try:
                data = self._download(f"{self.EUROPEPMC}/{pmcid}/fullTextPDF")
            except (NotAPdfError, IdNotFoundError, FetchFailedError):
                data = None
            if data is not None:
                return self._store(
                    data,
                    ids=s.PaperIds(pmid=pmid, pmcid=pmcid),
                    version_label=f"PMC full text ({pmcid})",
                    source="pubmed",
                    license=None,
                )
        raise NoOpenAccessError(
            f"no open-access PDF for {parsed.value}",
            user_message=(
                f"No open-access PDF found for {parsed.value}. Upload the PDF to analyze it."
            ),
        )

    def _fetch_direct_url(self, url: str) -> FetchedSource:
        r = self._get(url)
        if r.status_code == 404:
            raise IdNotFoundError(f"404: {url}", user_message="That page could not be found.")
        if r.status_code >= 400:
            raise FetchFailedError(
                f"{r.status_code}: {url}", user_message="Could not fetch that URL."
            )
        if r.content[:5] == b"%PDF-":
            return self._store(
                r.content, ids=s.PaperIds(), version_label="fetched URL", source="url", license=None
            )
        # Not a direct PDF: treat it as a publisher/preprint landing page and mine the Highwire
        # ``citation_*`` meta tags that eLife, PsyArXiv/OSF, ScienceDirect, PMC, PLOS, Springer, …
        # all embed for Google Scholar. One mechanism, no per-publisher code or API keys.
        return self._resolve_landing_page(r)

    def _resolve_landing_page(self, response: httpx.Response) -> FetchedSource:
        meta = _extract_citation_meta(response.text)
        doi_id = _as_doi_id(meta.get("citation_doi"))
        title = _clean_title(meta.get("citation_title"))
        authors = list(meta.get("citation_author") or [])
        year = _year_prefix(meta.get("citation_date") or meta.get("citation_publication_date"))
        # 1) A ``citation_pdf_url`` is the publisher's own PDF — try it directly (resolving relative
        #    links against the landing page). If it's paywalled (HTML/error), fall back to the DOI.
        pdf_url = meta.get("citation_pdf_url")
        if pdf_url:
            try:
                data = self._download(urljoin(str(response.url), pdf_url))
            except (NotAPdfError, IdNotFoundError, FetchFailedError):
                data = None
            if data is not None:
                return self._store(
                    data,
                    ids=s.PaperIds(doi=doi_id.value if doi_id else None),
                    version_label="publisher PDF (landing page)",
                    source="url",
                    license=None,
                    title=title,
                    authors=authors,
                    year=year,
                )
        # 2) Re-dispatch the discovered DOI through the OA chain (OpenAlex/Unpaywall may hold a
        #    free copy even when the publisher's own PDF is locked).
        if doi_id:
            return self._fetch_doi_or_openalex(doi_id)
        raise NotAPdfError(
            f"not a PDF and no citation metadata at {response.url}",
            user_message=(
                "That page isn't a PDF and doesn't advertise one we can fetch. "
                "Try the direct PDF link, or the paper's DOI."
            ),
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
    """Collapse provider whitespace and normalize all-caps title styling."""
    return normalize_paper_title(title)


class _CitationMetaParser(HTMLParser):
    """Collect Highwire ``citation_*`` ``<meta>`` tags from a landing page (stdlib, no lxml).

    ``citation_author`` repeats once per author (order preserved); every other key keeps its first
    value. Attribute order is irrelevant — we read whichever of ``name``/``property`` is present.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, object] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        a = {k.lower(): v for k, v in attrs}
        name = (a.get("name") or a.get("property") or "").strip().lower()
        content = (a.get("content") or "").strip()
        if not name.startswith("citation_") or not content:
            return
        if name == "citation_author":
            authors = self.meta.setdefault("citation_author", [])
            if isinstance(authors, list):
                authors.append(content)
        else:
            self.meta.setdefault(name, content)


def _extract_citation_meta(html_text: str) -> dict[str, object]:
    """Parse a landing page's ``citation_*`` meta tags; never raises on malformed markup."""
    parser = _CitationMetaParser()
    try:
        parser.feed(html_text)
    except Exception:  # a broken page just yields whatever tags we parsed before the error
        pass
    return parser.meta


def _as_doi_id(raw: object) -> ParsedIdentifier | None:
    """Normalize an untrusted DOI string (a meta tag, a provider record) through ingest — the
    authoritative parser — to a ``doi`` ``ParsedIdentifier``, or None if it isn't a valid DOI."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = parse_input(raw)
    except UnrecognizedInputError:
        return None
    return parsed if parsed.kind == "doi" else None


def _year_prefix(date: str | None) -> int | None:
    """The leading 4-digit year of an ISO-ish date string (``2020-11-03T...``), else None."""
    head = (date or "")[:4]
    return int(head) if head.isdigit() else None


def _pubmed_record(resp: dict | None) -> dict:
    """The first record from an NCBI ID-Converter response (``{"records": [...]}``), or ``{}``."""
    records = (resp or {}).get("records") or []
    return records[0] if records else {}


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
