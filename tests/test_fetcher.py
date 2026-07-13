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
    if "oa.example.org" in url or "repo.example.org" in url:
        return httpx.Response(200, content=PDF)
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
    assert "non-XML response from arXiv API" in str(exc.value)
    assert "direct PDF fallback failed" in str(exc.value)
    assert "direct PDF fallback did not work" in exc.value.user_message


def test_arxiv_http_error_is_fetch_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/query" in str(request.url):
            return httpx.Response(503, text="temporarily unavailable")
        return httpx.Response(404)

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), BlobStore(tmp_path))
    with pytest.raises(FetchFailedError) as exc:
        fetcher.fetch(parse_input("2011.01808"))
    assert "503 from arXiv API" in str(exc.value)
    assert "direct PDF fallback failed" in str(exc.value)


def test_arxiv_api_error_falls_back_to_direct_pdf(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/query" in url:
            return httpx.Response(503, text="temporarily unavailable")
        if "arxiv.org/pdf/" in url:
            return httpx.Response(200, content=PDF)
        return httpx.Response(404)

    fetcher = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), BlobStore(tmp_path))
    fs = fetcher.fetch(parse_input("2003.06281"))

    assert fs.source_doc.source == "arxiv"
    assert fs.source_doc.ids.arxiv_id == "2003.06281"
    assert fs.source_doc.version_label == "arXiv latest"
    assert fetcher._blobs.exists(fs.source_doc.sha256)


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
