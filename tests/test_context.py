"""Shared cheap-model context builders (used by screen + classify)."""

from __future__ import annotations

from datetime import datetime

import pytest

from bayesify.core.context import (
    build_user,
    evidence_digest,
    excerpt_context,
    validate_evidence_refs,
)
from bayesify.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    ParsedDoc,
    Section,
    SectionKind,
    SourceDoc,
)

_WHEN = datetime(2026, 1, 1)


def _parsed(*sections: tuple[SectionKind, str, str]) -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="t", source="upload", fetched_at=_WHEN)
    secs = [
        Section(id=f"s{i:02d}", kind=k, title=title, text=text)
        for i, (k, title, text) in enumerate(sections, start=1)
    ]
    return ParsedDoc(source=src, sections=secs, parser="test", parser_version="0")


def _ev(detector_id: str, kind: EvidenceKind, quote: str) -> Evidence:
    return Evidence(
        detector_id=detector_id,
        detector_version="0.1.0",
        kind=kind,
        span=EvidenceSpan(section_id="s01", page=1, quote=quote),
    )


def test_excerpt_excludes_references_and_supplements() -> None:
    parsed = _parsed(
        (SectionKind.abstract, "Abstract", "We fit a Bayesian model."),
        (SectionKind.body, "Methods", "MCMC with Stan."),
        (SectionKind.references, "References", "Gelman 2020. Bayesian Workflow."),
        (SectionKind.supplement, "Supp", "Extra sampler detail."),
    )
    ctx = excerpt_context(parsed)
    assert "Bayesian model" in ctx and "MCMC with Stan" in ctx
    assert "Gelman 2020" not in ctx  # references excluded (A3)
    assert "Extra sampler detail" not in ctx  # supplements excluded


def test_excerpt_truncates_to_budget() -> None:
    parsed = _parsed((SectionKind.body, "Body", "x" * 50_000))
    assert len(excerpt_context(parsed, max_chars=1000)) <= 1000


def test_evidence_digest_indexes_hits() -> None:
    digest = evidence_digest([_ev("software.stan", EvidenceKind.software_mention, "in Stan")])
    assert digest.startswith("[0] software.stan")
    assert "in Stan" in digest
    assert evidence_digest([]) == "(no deterministic detector hits)"


def test_build_user_combines_excerpts_and_hits() -> None:
    parsed = _parsed((SectionKind.abstract, "Abstract", "A Bayesian model in Stan."))
    user = build_user(parsed, [_ev("software.stan", EvidenceKind.software_mention, "in Stan")])
    assert "PAPER EXCERPTS" in user and "DETECTOR HITS" in user
    assert "Bayesian model in Stan" in user and "[0] software.stan" in user


def test_validate_evidence_refs_accepts_in_range_and_empty() -> None:
    evidence = [_ev("software.stan", EvidenceKind.software_mention, "in Stan")]
    validate_evidence_refs([0], evidence, where="relevance")  # in range
    validate_evidence_refs([], evidence, where="relevance")  # empty is fine (caller enforces >=1)


def test_validate_evidence_refs_rejects_out_of_range() -> None:
    evidence = [_ev("software.stan", EvidenceKind.software_mention, "in Stan")]  # only [0] exists
    with pytest.raises(ValueError, match="evidence_refs"):
        validate_evidence_refs([0, 5], evidence, where="relevance")
    with pytest.raises(ValueError, match="evidence_refs"):
        validate_evidence_refs([-1], evidence, where="relevance")
