"""Contract tests for the §4.3 stage types."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bayesify.core import schema as s


def _relevance(label: s.RelevanceLabel) -> s.Relevance:
    return s.Relevance(label=label, confidence=0.9, rationale="...", evidence_refs=[0, 1])


def test_sourcedoc_minimal_and_ids_default() -> None:
    doc = s.SourceDoc(
        sha256="a" * 64,
        version_label="uploaded PDF",
        source="upload",
        fetched_at=datetime(2026, 6, 13, tzinfo=UTC),
    )
    assert doc.ids.doi is None and doc.ids.arxiv_id is None


def test_evidence_kinds_include_detector_subset_and_absence_search() -> None:
    # Detectors emit everything except absence_search; e mints absence_search. Both belong to the
    # one shared enum (gate fix from the decomposition audit).
    values = {k.value for k in s.EvidenceKind}
    assert "method_mention" in values  # the relevance-floor family
    assert "absence_search" in values  # e's where-looked enumeration


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        s.GateFacts(inference_method="mcmc", n_models=2, bf_claimed=False, nonsense=1)  # type: ignore[call-arg]


def test_confidence_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        s.Relevance(label=s.RelevanceLabel.yes, confidence=1.5, rationale="x")


def test_scored_result_round_trip_is_byte_stable() -> None:
    result = s.ScoredResult(
        relevance=_relevance(s.RelevanceLabel.yes),
        paper_class=s.PaperClass(
            primary=s.PaperClassLabel.empirical,
            confidence=0.8,
            rationale="real data",
            evidence_refs=[0],
        ),
        gate_facts=s.GateFacts(
            inference_method=s.InferenceMethod.hmc_nuts,
            n_models=1,
            bf_claimed=False,
            prior_informativeness=s.PriorInformativeness.weakly_informative,
        ),
        step_assessments=[
            s.StepAssessment(
                step_id="S4",
                applicable=True,
                applicability_reason="HMC/NUTS sampler used",
                status=s.StepStatus.adequate,
                confidence=0.85,
                evidence=[
                    s.Evidence(
                        detector_id="diag.rhat_value",
                        detector_version="0.1.0",
                        kind=s.EvidenceKind.diagnostic_value,
                        value={"metric": "rhat", "op": "<", "number": 1.01},
                        span=s.EvidenceSpan(section_id="s07", page=8, quote="all R-hat < 1.01"),
                    )
                ],
                standards=[
                    s.StandardRef(
                        source_id="barg2021",
                        citation="Kruschke 2021. BARG.",
                        verified=True,
                        locator="Step 2.B-C",
                    )
                ],
                did_well=["Reports R-hat and ESS for every parameter (Fig 3)."],
                suggestions=[],
                adversarial_verdict=s.AdversarialVerdict(challenged=False, refuted=False),
            )
        ],
        profile=s.Profile(
            steps=[
                s.StepProfile(
                    step_id="S4",
                    applicable=True,
                    status=s.StepStatus.adequate,
                    sub_score=1.0,
                    weight=1.0,
                    tier=s.ExpectationTier.expected,
                )
            ],
            n_applicable=1,
            n_na=0,
            n_uncertain=0,
        ),
        coverage=s.Coverage(present=1, applicable=1, strict=1.0, lenient=1.0),
        quality_score=1.0,
        engine_version="pkg=0.1.0;prompts=none;detectors=none;models=claude-haiku-4-5+claude-opus-4-8",
        rubric_version="0.1-draft",
    )
    dumped = result.model_dump_json()
    reparsed = s.ScoredResult.model_validate_json(dumped)
    assert reparsed.model_dump_json() == dumped  # exact round-trip (meta-research view contract)


def test_short_circuit_nulls_scores_and_requires_no_label() -> None:
    result = s.ScoredResult.short_circuit(
        relevance=_relevance(s.RelevanceLabel.no),
        engine_version="ev",
        rubric_version="0.1-draft",
    )
    assert result.paper_class is None
    assert result.gate_facts is None
    assert result.profile is None
    assert result.coverage is None
    assert result.quality_score is None
    assert result.step_assessments == []


def test_short_circuit_carries_its_reason() -> None:
    # not-Bayesian (default) keeps the 'no' label; a review piece keeps relevance=yes + paper_class.
    nb = s.ScoredResult.short_circuit(
        relevance=_relevance(s.RelevanceLabel.no), engine_version="ev", rubric_version="0.1-draft"
    )
    assert nb.not_applicable_reason == "not_bayesian" and not nb.step_assessments
    rev = s.ScoredResult.short_circuit(
        relevance=_relevance(s.RelevanceLabel.yes),
        reason="not_an_application",
        engine_version="ev",
        rubric_version="0.1-draft",
    )
    assert rev.not_applicable_reason == "not_an_application"
    assert rev.relevance.label is s.RelevanceLabel.yes and not rev.step_assessments
