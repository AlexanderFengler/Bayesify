"""Paper-type classifier (M4 slice 3), driven by the fake LLM client (no network)."""

from __future__ import annotations

from datetime import datetime

import pytest

from bayesify.core import classify as C
from bayesify.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    Section,
    SectionKind,
    SourceDoc,
)
from bayesify.llm import FakeLLMClient, LLMError, LLMTransientError
from bayesify.llm import config as llm_config

_WHEN = datetime(2026, 1, 1)


def _parsed(text: str) -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="t", source="upload", fetched_at=_WHEN)
    secs = [Section(id="s01", kind=SectionKind.body, title="Body", text=text)]
    return ParsedDoc(source=src, sections=secs, parser="test", parser_version="0")


def _ev() -> Evidence:
    return Evidence(
        detector_id="software.stan",
        detector_version="0.1.0",
        kind=EvidenceKind.software_mention,
        span=EvidenceSpan(section_id="s01", page=1, quote="in Stan"),
    )


def test_classify_returns_paperclass_and_meters_cost() -> None:
    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.85,
        rationale="fits real data",
        evidence_refs=[0],
    )
    client = FakeLLMClient(canned)
    cls, entry = C.classify(_parsed("We fit a model to real RT data."), [_ev()], client=client)

    assert cls.labels == [PaperClassLabel.data_analysis]
    assert entry.stage == "classify" and entry.model == llm_config.classify_model()
    assert client.calls[0]["schema"] == "PaperClass"
    assert "DETECTOR HITS" in client.calls[0]["user"]


def test_classify_supports_multi_label_paper_types() -> None:
    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.data_analysis],
        confidence=0.7,
        rationale="new prior + a real-data application section",
        evidence_refs=[0],
    )
    cls, _ = C.classify(
        _parsed("We propose a new prior and apply it."), [_ev()], client=FakeLLMClient(canned)
    )
    assert cls.labels == [PaperClassLabel.method_development, PaperClassLabel.data_analysis]


def test_classify_fails_closed() -> None:
    client = FakeLLMClient(LLMTransientError("a"), LLMTransientError("b"), LLMTransientError("c"))
    with pytest.raises(LLMError):
        C.classify(_parsed("text"), [_ev()], client=client)


def test_classify_rejects_out_of_range_evidence_ref() -> None:
    # Only one detector hit (index 0) was shown; a ref to index 3 is a hallucinated citation.
    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.85,
        rationale="fits real data",
        evidence_refs=[3],
    )
    with pytest.raises(ValueError, match="evidence_refs"):
        C.classify(_parsed("We fit a model."), [_ev()], client=FakeLLMClient(canned))
