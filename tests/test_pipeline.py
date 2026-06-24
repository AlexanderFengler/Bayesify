"""Stage 4+5 composition (M4 slice 4): C6 ordering — 'no' short-circuits, skipping classify."""

from __future__ import annotations

from datetime import datetime

from bayesify.core.llm import FakeLLMClient
from bayesify.core.pipeline import screen_and_classify
from bayesify.core.schema import (
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
    Section,
    SectionKind,
    SourceDoc,
)

_WHEN = datetime(2026, 1, 1)


def _parsed() -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="t", source="upload", fetched_at=_WHEN)
    secs = [Section(id="s01", kind=SectionKind.body, title="B", text="text")]
    return ParsedDoc(source=src, sections=secs, parser="test", parser_version="0")


def test_no_short_circuits_and_skips_classify() -> None:
    # Only one scripted response: if classify were called the fake would raise (exhausted).
    client = FakeLLMClient(
        Relevance(label=RelevanceLabel.no, confidence=0.9, rationale="not Bayesian")
    )
    rel, cls, costs = screen_and_classify(_parsed(), [], client=client)

    assert rel.label is RelevanceLabel.no
    assert cls is None  # classify skipped
    assert len(costs) == 1 and costs[0].stage == "screen"
    assert len(client.calls) == 1  # classify never called


def test_relevant_runs_both_stages() -> None:
    client = FakeLLMClient(
        Relevance(
            label=RelevanceLabel.yes, confidence=0.9, rationale="Bayesian", evidence_refs=[0]
        ),
        PaperClass(
            labels=[PaperClassLabel.data_analysis],
            confidence=0.8,
            rationale="real data",
            evidence_refs=[0],
        ),
    )
    rel, cls, costs = screen_and_classify(_parsed(), [], client=client)

    assert rel.label is RelevanceLabel.yes
    assert cls is not None and cls.labels == [PaperClassLabel.data_analysis]
    assert [c.stage for c in costs] == ["screen", "classify"]
