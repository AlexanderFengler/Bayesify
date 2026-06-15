"""V0 — the human-report contract: round-trip, the honesty primitives, the engine-free firewall,
per-step grounding, and structural admissibility.

Pure contract tests: no engine, no LLM, no network.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from pydantic import ValidationError

from veribayes.core.schema import (
    EvidenceSpan,
    GateFacts,
    PaperClassLabel,
    RelevanceLabel,
    StepStatus,
)
from veribayes.core.validation import human_report as hr
from veribayes.core.validation.human_report import (
    GoldOrigin,
    GoldProvenance,
    GoldTier,
    HumanReport,
    MissingSubtag,
    RaterRelationship,
    Rating,
    StepRating,
)

_SPAN = EvidenceSpan(section_id="s01", quote="we fit a hierarchical model in Stan")


def _step(step_id: str = "S1", status: StepStatus = StepStatus.done_well, **over) -> StepRating:
    base: dict = dict(
        step_id=step_id,
        applicable=status is not StepStatus.not_applicable,
        status=status,
        confidence=0.9,
        evidence=[_SPAN] if status in (StepStatus.done_well, StepStatus.partial) else [],
        rationale="" if status is StepStatus.not_applicable else "the paper does this",
    )
    base.update(over)
    return StepRating(**base)


def _rating(rater_id: str, relationship: RaterRelationship, **over) -> Rating:
    base: dict = dict(
        rater_id=rater_id,
        relationship=relationship,
        relevance_label=RelevanceLabel.yes,
        relevance_rationale="clearly Bayesian",
        paper_class_label=PaperClassLabel.empirical,
        gate_facts=GateFacts(),
        steps=[_step("S1"), _step("S2", status=StepStatus.missing)],
    )
    base.update(over)
    return Rating(**base)


def _report(**over) -> HumanReport:
    base: dict = dict(
        work_id="w1",
        source_sha256="deadbeef",
        version_label="arXiv v1",
        rubric_version="0.1-draft",
        tier=GoldTier.A,
        provenance=GoldProvenance(origin=GoldOrigin.fake_llm, authored_by="claude-demo"),
        ratings=[
            _rating("r1", RaterRelationship.independent),
            _rating("r2", RaterRelationship.prompt_author),
        ],
        consensus=_rating("consensus", RaterRelationship.consensus),
    )
    base.update(over)
    return HumanReport(**base)


# --- round-trip + honesty primitives --------------------------------------------------------------


def test_human_report_round_trips() -> None:
    r = _report()
    again = HumanReport.model_validate_json(r.model_dump_json())
    assert again == r


def test_origin_is_required_no_default() -> None:
    # The load-bearing honesty firewall: a record can't exist without declaring who authored it.
    with pytest.raises(ValidationError):
        GoldProvenance()  # type: ignore[call-arg]
    assert "origin" in GoldProvenance.model_fields
    assert GoldProvenance.model_fields["origin"].is_required()


# --- the validity firewall (engine-free, no narrative fields) -------------------------------------


def test_step_rating_has_no_engine_only_fields() -> None:
    # Their absence is load-bearing: a human must not be handed the engine's narrative framing.
    engine_only = {"did_well", "suggestions", "standards", "adversarial_verdict"}
    assert engine_only.isdisjoint(StepRating.model_fields)


def test_human_report_module_is_engine_free() -> None:
    # AST (not substring) so the docstring's own mentions of these names don't false-trip.
    tree = ast.parse(pathlib.Path(hr.__file__).read_text())
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            referenced.update(a.name for a in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    assert "ScoredResult" not in referenced
    assert "StepAssessment" not in referenced


# --- per-step grounding ---------------------------------------------------------------------------


def test_present_status_requires_evidence_span() -> None:
    with pytest.raises(ValidationError):
        _step("S1", status=StepStatus.done_well, evidence=[])


def test_missing_status_needs_no_span_but_needs_rationale() -> None:
    _step("S3", status=StepStatus.missing, evidence=[])  # absence: nothing to quote — allowed
    with pytest.raises(ValidationError):
        _step("S3", status=StepStatus.missing, evidence=[], rationale="")


def test_applicable_status_invariant() -> None:
    with pytest.raises(ValidationError):  # N/A status but applicable=True
        StepRating(step_id="S4", applicable=True, status=StepStatus.not_applicable, confidence=0.5)
    with pytest.raises(ValidationError):  # applicable=False but a substantive status
        StepRating(step_id="S4", applicable=False, status=StepStatus.missing, confidence=0.5)


def test_missing_subtag_only_when_missing() -> None:
    _step("S2", status=StepStatus.missing, missing_subtag=MissingSubtag.not_reported_suspected)
    with pytest.raises(ValidationError):
        _step("S1", status=StepStatus.done_well, missing_subtag=MissingSubtag.not_done)


# --- rating short-circuit + envelope --------------------------------------------------------------


def test_relevance_no_is_a_short_circuit() -> None:
    Rating(
        rater_id="r1",
        relationship=RaterRelationship.independent,
        relevance_label=RelevanceLabel.no,
        relevance_rationale="not a Bayesian paper",
    )
    with pytest.raises(ValidationError):  # 'no' must not carry steps
        Rating(
            rater_id="r1",
            relationship=RaterRelationship.independent,
            relevance_label=RelevanceLabel.no,
            relevance_rationale="not Bayesian",
            steps=[_step("S1")],
        )


def test_relevant_rating_requires_class_and_gate_facts() -> None:
    with pytest.raises(ValidationError):
        _rating("r1", RaterRelationship.independent, paper_class_label=None)
    with pytest.raises(ValidationError):
        _rating("r1", RaterRelationship.independent, gate_facts=None)


def test_consensus_must_be_consensus_relationship() -> None:
    with pytest.raises(ValidationError):
        _report(consensus=_rating("consensus", RaterRelationship.independent))
    with pytest.raises(ValidationError):  # ratings must not contain a consensus rater
        _report(ratings=[_rating("c", RaterRelationship.consensus)])


# --- admissibility --------------------------------------------------------------------------------


def test_admissible_happy_path() -> None:
    assert _report().validate_admissible() == []


def test_admissibility_flags_structural_gaps() -> None:
    too_few = _report(ratings=[_rating("r1", RaterRelationship.independent)])
    assert any("2-3 raters" in v for v in too_few.validate_admissible())

    no_indep = _report(
        ratings=[
            _rating("r1", RaterRelationship.prompt_author),
            _rating("r2", RaterRelationship.engine_dev),
        ]
    )
    violations = no_indep.validate_admissible()
    assert any("independent" in v for v in violations)
    assert any("engine/prompt developers" in v for v in violations)

    no_consensus = _report(consensus=None)
    assert any("consensus" in v for v in no_consensus.validate_admissible())


def test_publication_gate_rejects_fake_draft_unseeded() -> None:
    # The fake demo report is fine for the demo path but must fail the real-publication gate.
    r = _report(
        provenance=GoldProvenance(
            origin=GoldOrigin.fake_llm, rating_guide_version="draft:abc", selection_seed=None
        )
    )
    violations = r.validate_admissible(for_publication=True)
    assert any("blind_human" in v for v in violations)
    assert any("selection_seed" in v for v in violations)
    assert any("frozen rating guide" in v for v in violations)
