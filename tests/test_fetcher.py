"""Fetcher resolution chain — fully offline via httpx MockTransport."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from bayesify.core.cache import BlobStore
from bayesify.core.errors import FetchFailedError, IdNotFoundError, NoOpenAccessError, NotAPdfError
from bayesify.core.fetcher import Fetcher, _clean_title
from bayesify.core.ingest import parse_input

PDF = b"%PDF-1.5\n%mock pdf\n"

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2011.01808v3</id>
    <title>Bayesian Workflow</title>
    <published>2020-11-03T00:00:00Z</published>
    <author><name>Andrew Gelman</name></author>
    <author><name>Aki Vehtari</name></author>
    <arxiv:license>http://creativecommons.org/licenses/by/4.0/</arxiv:license>
  </entry>
</feed>"""
ARXIV_ERR = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Error</title></entry></feed>"""

OA_WITH = {
    "id": "https://openalex.org/W1",
    "ids": {"openalex": "https://openalex.org/W1", "doi": "https://doi.org/10.1038/withpdf"},
    "title": "OA Paper",
    "publication_year": 2021,
    "authorships": [
        {"author": {"display_name": "Andrew Gelman"}},
        {"author": {"display_name": "Aki Vehtari"}},
    ],
    "best_oa_location": {
        "pdf_url": "https://oa.example.org/paper.pdf",
        "license": "cc-by",
        "version": "publishedVersion",
    },
}
OA_NO = {
    "id": "https://openalex.org/W2",
    "ids": {"openalex": "https://openalex.org/W2"},
    "title": "Repo Paper",
    "best_oa_location": None,
}
OA_NOOA = {"id": "https://openalex.org/W3", "title": "Locked Paper", "best_oa_location": None}
UW_WITH = {
    "best_oa_location": {
        "url_for_pdf": "https://repo.example.org/p.pdf",
        "license": "cc-by-nc",
        "version": "acceptedVersion",
    }
}

# A publisher landing page whose Highwire meta tags advertise a directly-fetchable PDF (relative
# href, to exercise urljoin) plus a DOI, title, authors, and date.
ELIFE_LANDING = """<html><head>
  <meta name="citation_title" content="A Landing Page Paper">
  <meta name="citation_author" content="Jane Roe">
  <meta name="citation_author" content="John Doe">
  <meta name="citation_date" content="2022/05/01">
  <meta name="citation_doi" content="10.7554/eLife.00001">
  <meta name="citation_pdf_url" content="/paper.pdf">
</head><body>eLife article</body></html>"""
# A landing page that advertises only a DOI — resolution must re-dispatch through the OA chain.
DOIONLY_LANDING = (
    '<html><head><meta name="citation_doi" content="https://doi.org/10.1038/withpdf">'
    "</head><body>preprint</body></html>"
)
# A landing page whose own PDF is paywalled (returns HTML) but whose DOI has a green-OA copy.
LOCKED_PDF_LANDING = (
    '<html><head><meta name="citation_pdf_url" content="https://elsevier.example.org/locked.pdf">'
    '<meta name="citation_doi" content="10.1038/nopdf"></head><body>ScienceDirect</body></html>'
)
NOMETA_LANDING = "<html><head><title>Nothing here</title></head><body>no meta</body></html>"


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "/api/query" in url:
        return httpx.Response(200, text=ARXIV_ERR if "9999.99999" in url else ARXIV_FEED)
    if "arxiv.org/pdf/" in url:
        return httpx.Response(200, content=PDF)
    if "api.openalex.org/works/" in url:
        if "withpdf" in url:
            return httpx.Response(200, json=OA_WITH)
        if "nopdf" in url:
            return httpx.Response(200, json=OA_NO)
        if "locked" in url:
            return httpx.Response(200, json=OA_NOOA)
        return httpx.Response(404)
    if "api.unpaywall.org/v2/" in url:
        return httpx.Response(200, json=UW_WITH if "nopdf" in url else {"best_oa_location": None})
    if "api.crossref.org/works/" in url:
        return httpx.Response(200, json={"message": {"title": ["Locked Paper"]}})
    if "api.crossref.org/works" in url:  # PII search: match on alternative-id, not the top hit
        items = [
            {"DOI": "10.1000/wrong", "alternative-id": ["S9999999999999999"]},
            {"DOI": "10.1038/withpdf", "alternative-id": ["S2213158221000012"]},
        ]
        return httpx.Response(200, json={"message": {"items": items if "S2213" in url else []}})
    if "idconv" in url:  # NCBI ID Converter: PMID/PMCID -> DOI (+ sibling ids)
        if "14699080" in url:  # a PMID that carries a DOI with an OA copy
            record = {"pmid": 14699080, "pmcid": "PMC1193645", "doi": "10.1038/withpdf"}  # int pmid
        elif "PMC7777777" in url:  # a PMCID with no DOI but an OA full text
            record = {"pmcid": "PMC7777777"}
        elif "PMC0000000" in url:  # an id the converter rejects
            record = {"pmcid": "PMC0000000", "status": "error", "errmsg": "invalid article id"}
        else:
            return httpx.Response(200, json={"records": []})
        return httpx.Response(200, json={"records": [record]})
    if "europepmc" in url and "PMC7777777" in url:
        return httpx.Response(200, content=PDF)
    if "osf.io/download/bfsgr" in url:  # OSF/PsyArXiv download endpoint serves the PDF by GUID
        return httpx.Response(200, content=PDF)
    if "osf.io/download/" in url:  # unknown GUID
        return httpx.Response(404, json={"message": "Not found"})
    if "blocked.example.org" in url:  # a publisher that bot-blocks server-side fetches
        return httpx.Response(403, text="<html>Access Denied</html>")
    if "oa.example.org" in url or "repo.example.org" in url:
        return httpx.Response(200, content=PDF)
    if "elsevier.example.org/locked.pdf" in url:  # a "PDF" link that's really a paywall page
        return httpx.Response(200, content=b"<html>paywall</html>")
    if "elife.example.org/paper.pdf" in url:
        return httpx.Response(200, content=PDF)
    if "elife.example.org/landing" in url:
        return httpx.Response(200, text=ELIFE_LANDING, headers={"content-type": "text/html"})
    if "psyarxiv.example.org/landing" in url:
        return httpx.Response(200, text=DOIONLY_LANDING, headers={"content-type": "text/html"})
    if "sciencedirect.example.org/landing" in url:
        return httpx.Response(200, text=LOCKED_PDF_LANDING, headers={"content-type": "text/html"})
    if "nometa.example.org/landing" in url:
        return httpx.Response(200, text=NOMETA_LANDING, headers={"content-type": "text/html"})
    if "paywall.example.org" in url:
        return httpx.Response(200, content=b"<html>paywall</html>")
    return httpx.Response(404)


@pytest.fixture
def fetcher(tmp_path: Path) -> Fetcher:
    client = httpx.Client(transport=httpx.MockTransport(_handler))
    return Fetcher(
        client, BlobStore(tmp_path), openalex_api_key=None, unpaywall_email="test@example.org"
    )


def test_arxiv_fetch_captures_version_and_license(fetcher: Fetcher) -> None:
    fs = fetcher.fetch(parse_input("2011.01808"))
    assert fs.source_doc.source == "arxiv"
    assert fs.source_doc.version_label == "arXiv v3"  # learned from the API, not the bare id
    assert fs.source_doc.ids.arxiv_id == "2011.01808"
    assert "creativecommons.org/licenses/by" in (fs.license or "")
    assert fs.authors == ["Andrew Gelman", "Aki Vehtari"] and fs.year == 2020  # provider metadata
    assert fetcher._blobs.exists(fs.source_doc.sha256)


def test_clean_title_sentence_cases_all_caps_provider_title() -> None:
    assert _clean_title("  BAYESIAN\nWORKFLOW FOR COGNITIVE MODELS  ") == (
        "Bayesian workflow for cognitive models"
    )
    assert _clean_title("Bayesian Workflow") == "Bayesian Workflow"


def test_arxiv_unknown_id_raises(fetcher: Fetcher) -> None:
    with pytest.raises(IdNotFoundError):
        fetcher.fetch(parse_input("9999.99999"))


def test_arxiv_non_xml_response_is_fetch_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/query" in str(request.url):
            return httpx.Response(
                200,
                text="<html>blocked</html>",
                headers={"content-type": "text/html"},
            )
        return httpx.Response(404)

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), BlobStore(tmp_path))
    with pytest.raises(FetchFailedError) as exc:
        fetcher.fetch(parse_input("2011.01808"))
    assert "unexpected response from arXiv API" in str(exc.value)
    assert "arXiv did not return metadata" in exc.value.user_message


def test_arxiv_http_error_is_fetch_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/query" in str(request.url):
            return httpx.Response(503, text="temporarily unavailable")
        return httpx.Response(404)

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), BlobStore(tmp_path))
    with pytest.raises(FetchFailedError) as exc:
        fetcher.fetch(parse_input("2011.01808"))
    assert "503 from arXiv API" in str(exc.value)


def test_doi_resolved_via_openalex(fetcher: Fetcher) -> None:
    fs = fetcher.fetch(parse_input("10.1038/withpdf"))
    assert fs.source_doc.source == "openalex"
    assert fs.license == "cc-by"
    assert fs.source_doc.ids.doi == "10.1038/withpdf"
    assert fs.source_doc.ids.openalex_id == "W1"  # learned during resolution
    assert fs.authors == ["Andrew Gelman", "Aki Vehtari"] and fs.year == 2021  # provider metadata


def test_doi_falls_through_openalex_to_unpaywall(fetcher: Fetcher) -> None:
    fs = fetcher.fetch(parse_input("10.1038/nopdf"))
    assert fs.source_doc.source == "unpaywall"
    assert fs.license == "cc-by-nc"
    assert "acceptedVersion" in fs.source_doc.version_label


def test_no_open_access_names_the_paper(fetcher: Fetcher) -> None:
    with pytest.raises(NoOpenAccessError) as exc:
        fetcher.fetch(parse_input("10.1038/locked"))
    assert "Locked Paper" in exc.value.user_message  # so the UI can offer a manual upload


def test_html_payload_is_rejected_as_not_pdf(fetcher: Fetcher) -> None:
    with pytest.raises(NotAPdfError):
        fetcher.fetch(parse_input("https://paywall.example.org/x"))


def test_direct_pdf_url(fetcher: Fetcher) -> None:
    fs = fetcher.fetch(parse_input("https://oa.example.org/direct.pdf"))
    assert fs.source_doc.source == "url"
    assert fetcher._blobs.exists(fs.source_doc.sha256)


def test_landing_page_citation_pdf_url_is_fetched(fetcher: Fetcher) -> None:
    # An eLife-style landing page: mine citation_pdf_url (relative, urljoin-resolved) + metadata.
    fs = fetcher.fetch(parse_input("https://elife.example.org/landing/00001"))
    assert fs.source_doc.source == "url"
    assert fs.source_doc.version_label == "publisher PDF (landing page)"
    assert fs.source_doc.ids.doi == "10.7554/elife.00001"  # normalized (lowercased) from the tag
    assert fs.title == "A Landing Page Paper"
    assert fs.authors == ["Jane Roe", "John Doe"] and fs.year == 2022
    assert fetcher._blobs.exists(fs.source_doc.sha256)


def test_landing_page_doi_only_redispatches_to_oa_chain(fetcher: Fetcher) -> None:
    # No citation_pdf_url — the discovered DOI must flow through OpenAlex.
    fs = fetcher.fetch(parse_input("https://psyarxiv.example.org/landing/xyz"))
    assert fs.source_doc.source == "openalex"
    assert fs.source_doc.ids.doi == "10.1038/withpdf"
    assert fs.license == "cc-by"


def test_landing_page_locked_pdf_falls_back_to_doi(fetcher: Fetcher) -> None:
    # citation_pdf_url is a paywall page; fall through to the DOI's green-OA copy (Unpaywall).
    fs = fetcher.fetch(parse_input("https://sciencedirect.example.org/landing/pii"))
    assert fs.source_doc.source == "unpaywall"
    assert "acceptedVersion" in fs.source_doc.version_label


def test_landing_page_without_citation_meta_raises(fetcher: Fetcher) -> None:
    with pytest.raises(NotAPdfError):
        fetcher.fetch(parse_input("https://nometa.example.org/landing"))


def test_pubmed_pmid_resolves_via_doi_and_stamps_ids(fetcher: Fetcher) -> None:
    # PMID -> DOI (NCBI ID Converter) -> OA chain, with the learned PubMed ids stamped on.
    fs = fetcher.fetch(parse_input("PMID: 14699080"))
    assert fs.source_doc.source == "openalex"
    assert fs.source_doc.ids.doi == "10.1038/withpdf"
    assert fs.source_doc.ids.pmid == "14699080"
    assert fs.source_doc.ids.pmcid == "PMC1193645"


def test_pubmed_pmcid_without_doi_falls_back_to_europepmc(fetcher: Fetcher) -> None:
    fs = fetcher.fetch(parse_input("PMC7777777"))
    assert fs.source_doc.source == "pubmed"
    assert fs.source_doc.ids.pmcid == "PMC7777777"
    assert "PMC full text" in fs.source_doc.version_label
    assert fetcher._blobs.exists(fs.source_doc.sha256)


def test_pubmed_unknown_id_raises(fetcher: Fetcher) -> None:
    with pytest.raises(IdNotFoundError):
        fetcher.fetch(parse_input("PMC0000000"))


def test_osf_preprint_url_downloads_pdf_by_guid(fetcher: Fetcher) -> None:
    # OSF's SPA has no citation meta; resolve the versioned GUID via the download endpoint.
    fs = fetcher.fetch(parse_input("https://osf.io/preprints/psyarxiv/bfsgr_v1"))
    assert fs.source_doc.source == "osf"
    assert fs.source_doc.version_label == "OSF preprint (bfsgr_v1)"
    assert fetcher._blobs.exists(fs.source_doc.sha256)


def test_osf_unknown_guid_raises(fetcher: Fetcher) -> None:
    with pytest.raises(IdNotFoundError):
        fetcher.fetch(parse_input("https://osf.io/zzzzz/"))


def test_bot_blocked_publisher_suggests_doi(fetcher: Fetcher) -> None:
    with pytest.raises(FetchFailedError) as exc:
        fetcher.fetch(parse_input("https://blocked.example.org/article/1"))
    assert "Try the article's DOI" in exc.value.user_message


def test_elsevier_pii_url_resolves_via_crossref_to_oa_copy(fetcher: Fetcher) -> None:
    # ScienceDirect bot-blocks its page; identify the paper by PII -> CrossRef DOI -> OA chain.
    fs = fetcher.fetch(
        parse_input("https://www.sciencedirect.com/science/article/pii/S2213158221000012?via%3Dihub")
    )
    assert fs.source_doc.source == "openalex"  # a copy fetched from a non-blocked host
    assert fs.source_doc.ids.doi == "10.1038/withpdf"  # matched on alternative-id, not the top hit


def test_elsevier_pii_not_in_crossref_raises(fetcher: Fetcher) -> None:
    with pytest.raises(IdNotFoundError):
        fetcher.fetch(parse_input("https://www.sciencedirect.com/science/article/pii/S0000000000000000"))
