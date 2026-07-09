"""LLM title + author extraction (pre-grading metadata), driven by the fake LLM client."""

from __future__ import annotations

from datetime import datetime

from bayesify.core.extract import PaperMetadata, extract_metadata
from bayesify.core.schema import ParsedDoc, Section, SectionKind, SourceDoc
from bayesify.llm import FakeLLMClient


def _parsed(text: str) -> ParsedDoc:
    src = SourceDoc(
        sha256="a" * 64, version_label="t", source="upload", fetched_at=datetime(2026, 1, 1)
    )
    secs = [Section(id="s01", kind=SectionKind.body, title="B", text=text)]
    return ParsedDoc(source=src, sections=secs, parser="t", parser_version="0")


def test_extract_metadata_returns_title_and_authors() -> None:
    client = FakeLLMClient(
        PaperMetadata(title="A Hierarchical Model of X", authors=["Jane Q. Public", "John Doe"])
    )
    meta = extract_metadata(_parsed("A Hierarchical Model of X\nAuthors"), client=client, model="m")
    assert meta.title == "A Hierarchical Model of X"
    assert meta.authors == ["Jane Q. Public", "John Doe"]


def test_extract_metadata_strips_and_drops_blank_authors() -> None:
    client = FakeLLMClient(PaperMetadata(title="  T  ", authors=["  Ada  ", "", "   "]))
    meta = extract_metadata(_parsed("x"), client=client, model="m")
    assert meta.title == "T"
    assert meta.authors == ["Ada"]


def test_extract_metadata_blank_title_is_empty() -> None:
    # A blank title comes back empty (falsy) so the pipeline keeps the parse-time heuristic.
    client = FakeLLMClient(PaperMetadata(title="   "))
    meta = extract_metadata(_parsed("no clear title"), client=client, model="m")
    assert meta.title == ""
    assert meta.authors == []


def test_extract_metadata_forwards_the_page_image_to_the_client() -> None:
    client = FakeLLMClient(PaperMetadata(title="T", authors=[]))
    extract_metadata(_parsed("x"), client=client, model="m", page_image=b"PNGBYTES")
    assert client.calls[-1]["image"] == b"PNGBYTES"


def test_extract_metadata_omits_image_when_none() -> None:
    client = FakeLLMClient(PaperMetadata(title="T", authors=[]))
    extract_metadata(_parsed("x"), client=client, model="m")
    assert client.calls[-1]["image"] is None


def test_extract_metadata_prefers_opening_text_over_excerpt() -> None:
    # opening_text is raw page-1 (title + byline); the section excerpt starts at the abstract and
    # drops those lines — so the byline-bearing text must win.
    client = FakeLLMClient(PaperMetadata(title="Real Title", authors=["Jane Doe"]))
    extract_metadata(
        _parsed("ABSTRACT-ONLY body text"),
        client=client,
        model="m",
        opening_text="Real Title\nJane Doe and John Roe\nAbstract ...",
    )
    sent = client.calls[-1]["user"]
    assert "Real Title" in sent and "Jane Doe" in sent
    assert "ABSTRACT-ONLY" not in sent  # the excerpt was not used
