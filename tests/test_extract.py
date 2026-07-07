"""LLM title extraction (pre-grading metadata), driven by the fake LLM client."""

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


def test_extract_metadata_returns_the_title() -> None:
    client = FakeLLMClient(PaperMetadata(title="A Hierarchical Model of X"))
    parsed = _parsed("A Hierarchical Model of X\nAuthors")
    assert extract_metadata(parsed, client=client, model="m") == "A Hierarchical Model of X"


def test_extract_metadata_blank_title_is_none() -> None:
    # A blank title falls back to None so the caller keeps the parse-time heuristic.
    client = FakeLLMClient(PaperMetadata(title="   "))
    assert extract_metadata(_parsed("no clear title"), client=client, model="m") is None
