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


def _method_ev(detector_id: str) -> Evidence:
    return Evidence(
        detector_id=detector_id,
        detector_version="0.1.0",
        kind=EvidenceKind.method_mention,
        span=EvidenceSpan(section_id="s01", page=1, quote="m"),
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


def test_classify_keeps_methods_grounded_by_a_detector_hit() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits real data",
        evidence_refs=[0],
        methods_used=[InferenceMethod.hmc_nuts, InferenceMethod.sbi, InferenceMethod.smc],
    )
    # hmc_nuts grounds on method.mcmc, sbi on method.sbi, smc on method.smc — all present, so all
    # three survive.
    evidence = [
        _ev(),
        _method_ev("method.mcmc"),
        _method_ev("method.sbi"),
        _method_ev("method.smc"),
    ]
    cls, _ = C.classify(
        _parsed("We fit with NUTS, SBI, SMC."), evidence, client=FakeLLMClient(canned)
    )
    assert cls.methods_used == [InferenceMethod.hmc_nuts, InferenceMethod.sbi, InferenceMethod.smc]


def test_classify_drops_methods_with_no_detector_hit(caplog) -> None:
    import logging

    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="r",
        evidence_refs=[0],
        methods_used=[InferenceMethod.mcmc, InferenceMethod.smc],
    )
    # Only method.mcmc fired; the hallucinated smc has no corroborating detector hit -> dropped.
    evidence = [_ev(), _method_ev("method.mcmc")]
    with caplog.at_level(logging.WARNING, logger="bayesify.core.classify"):
        cls, _ = C.classify(_parsed("mcmc yes, smc no"), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.mcmc]
    assert any("smc" in r.getMessage() for r in caplog.records)


def test_classify_skips_method_grounding_without_evidence() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="r",
        evidence_refs=[0],
        methods_used=[InferenceMethod.smc],
    )
    # The forced-rerun escape hatch grades without grounding (evidence == []): methods pass through.
    cls, _ = C.classify(_parsed("x"), [], client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.smc]


def test_paperclass_methods_used_drops_unknown_unstated_and_dupes() -> None:
    # A stray/hallucinated method token is filtered (mode="before"), not a hard failure; "unstated"
    # and duplicates are dropped by the after-validator, so one bad word never fails the whole call.
    from bayesify.core.schema import InferenceMethod

    pc = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="r",
        evidence_refs=[0],
        methods_used=["mcmc", "nuts", "mcmc", "unstated"],  # "nuts" not in vocab; dup + unstated
    )
    assert pc.methods_used == [InferenceMethod.mcmc]


def test_paperclass_methods_used_logs_dropped(caplog) -> None:
    # Out-of-vocab tokens are dropped (not fatal) AND logged, so an untracked method surfaces.
    import logging

    from bayesify.core.schema import InferenceMethod

    with caplog.at_level(logging.WARNING, logger="bayesify.core.schema"):
        pc = PaperClass(
            labels=[PaperClassLabel.data_analysis],
            confidence=0.8,
            rationale="r",
            evidence_refs=[0],
            methods_used=["mcmc", "particle_filter"],
        )
    assert pc.methods_used == [InferenceMethod.mcmc]
    assert any("particle_filter" in r.getMessage() for r in caplog.records)
