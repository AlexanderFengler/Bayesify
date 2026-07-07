"""Relevance gate (M4 slice 2): context discipline, the detector floor, and fail-closed behaviour.

No real LLM — the gate is driven with a scripted FakeLLMClient returning canned Relevance objects.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from bayesify.core import screen as S
from bayesify.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
    Section,
    SectionKind,
    SourceDoc,
)
from bayesify.llm import FakeLLMClient, LLMError, LLMTransientError
from bayesify.llm import config as llm_config

_WHEN = datetime(2026, 1, 1)


def _parsed(*sections: tuple[SectionKind, str, str]) -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="t", source="upload", fetched_at=_WHEN)
    secs = [
        Section(id=f"s{i:02d}", kind=k, title=title, text=text)
        for i, (k, title, text) in enumerate(sections, start=1)
    ]
    return ParsedDoc(source=src, sections=secs, parser="test", parser_version="0")


def _ev(detector_id: str, kind: EvidenceKind, quote: str = "q") -> Evidence:
    return Evidence(
        detector_id=detector_id,
        detector_version="0.1.0",
        kind=kind,
        span=EvidenceSpan(section_id="s01", page=1, quote=quote),
    )


# --- the happy path -------------------------------------------------------------------------------


def test_screen_returns_relevance_and_meters_cost() -> None:
    parsed = _parsed((SectionKind.abstract, "Abstract", "A Bayesian model fit with Stan."))
    evidence = [_ev("software.stan", EvidenceKind.software_mention)]
    canned = Relevance(
        label=RelevanceLabel.yes, confidence=0.9, rationale="clearly Bayesian", evidence_refs=[0]
    )
    client = FakeLLMClient(canned)

    rel, entry = S.screen(parsed, evidence, client=client)

    assert rel.label is RelevanceLabel.yes
    assert entry.stage == "screen" and entry.model == llm_config.screen_model()
    assert client.calls[0]["schema"] == "Relevance"
    assert "DETECTOR HITS" in client.calls[0]["user"]  # evidence digest reached the prompt


def test_screen_repairs_relevant_label_without_evidence_refs() -> None:
    parsed = _parsed((SectionKind.abstract, "Abstract", "A Bayesian model fit with Stan."))
    evidence = [_ev("software.stan", EvidenceKind.software_mention)]
    client = FakeLLMClient(
        S.ScreenRelevance(
            label=RelevanceLabel.yes,
            confidence=0.9,
            rationale="clearly Bayesian",
            evidence_refs=[],
        )
    )

    rel, _ = S.screen(parsed, evidence, client=client)

    assert rel.label is RelevanceLabel.yes
    assert rel.evidence_refs == [0]
    assert "Grounding repair" in rel.rationale


def test_screen_downgrades_uncited_relevant_label_without_bayesian_evidence() -> None:
    parsed = _parsed((SectionKind.abstract, "Abstract", "Data and code are available."))
    evidence = [_ev("open.github", EvidenceKind.open_science)]
    client = FakeLLMClient(
        S.ScreenRelevance(
            label=RelevanceLabel.yes,
            confidence=0.7,
            rationale="Bayesian-looking paper",
            evidence_refs=[],
        )
    )

    rel, _ = S.screen(parsed, evidence, client=client)

    assert rel.label is RelevanceLabel.no
    assert rel.evidence_refs == []
    assert "downgraded to 'no'" in rel.rationale


# --- detector floor -------------------------------------------------------------------------------


def test_floor_corrects_no_when_two_bayesian_families_present() -> None:
    # Two independent families (software + diagnostic) → a 'no' is not supported.
    evidence = [
        _ev("software.stan", EvidenceKind.software_mention),
        _ev("diag.rhat", EvidenceKind.diagnostic_value),
    ]
    client = FakeLLMClient(
        Relevance(label=RelevanceLabel.no, confidence=0.6, rationale="looked frequentist to me")
    )
    rel, _ = S.screen(_parsed((SectionKind.body, "B", "text")), evidence, client=client)

    assert rel.label is RelevanceLabel.partial  # corrected
    assert rel.evidence_refs  # floor populated refs so the partial is well-formed
    assert "Detector floor" in rel.rationale


def test_floor_leaves_no_when_under_two_families() -> None:
    # A single family (just an open-science GitHub link is not even Bayesian) → no correction.
    evidence = [_ev("open.github", EvidenceKind.open_science)]
    client = FakeLLMClient(
        Relevance(
            label=RelevanceLabel.no, confidence=0.95, rationale="searched priors/MCMC: none found"
        )
    )
    rel, _ = S.screen(_parsed((SectionKind.body, "B", "text")), evidence, client=client)
    assert rel.label is RelevanceLabel.no


def test_floor_does_not_touch_yes_or_partial() -> None:
    evidence = [
        _ev("software.stan", EvidenceKind.software_mention),
        _ev("diag.rhat", EvidenceKind.diagnostic_value),
    ]
    canned = Relevance(
        label=RelevanceLabel.yes, confidence=0.9, rationale="Bayesian", evidence_refs=[0]
    )
    rel, _ = S.screen(
        _parsed((SectionKind.body, "B", "text")), evidence, client=FakeLLMClient(canned)
    )
    assert rel.label is RelevanceLabel.yes
    assert "Detector floor" not in rel.rationale


# --- fail closed ----------------------------------------------------------------------------------


def test_screen_fails_closed_on_persistent_llm_error() -> None:
    client = FakeLLMClient(LLMTransientError("x"), LLMTransientError("y"), LLMTransientError("z"))
    with pytest.raises(LLMError):
        S.screen(_parsed((SectionKind.body, "B", "text")), [], client=client)


def test_screen_rejects_out_of_range_evidence_ref() -> None:
    # The model cites index 99 but only one detector hit (index 0) was shown — a hallucinated
    # citation that would become a dangling ref in the report. Reject it (fail loud).
    evidence = [_ev("software.stan", EvidenceKind.software_mention)]
    canned = Relevance(
        label=RelevanceLabel.yes, confidence=0.9, rationale="Bayesian", evidence_refs=[99]
    )
    with pytest.raises(ValueError, match="evidence_refs"):
        S.screen(_parsed((SectionKind.body, "B", "text")), evidence, client=FakeLLMClient(canned))
