"""M7 slice 1 — automated consensus from blind ratings (the adjudication-UI replacement).

Strict-majority per step; no majority → the cell is dropped + counted; no paper-level majority →
consensus is None (the paper is excluded-and-counted downstream). Pure, deterministic.
"""

from __future__ import annotations

from bayesify.core.schema import (
    EvidenceSpan,
    GateFacts,
    PaperClassLabel,
    RelevanceLabel,
    StepStatus,
)
from bayesify.core.validation.consensus import assemble_human_report, consensus_from_ratings
from bayesify.core.validation.human_report import (
    GoldOrigin,
    GoldTier,
    RaterRelationship,
    Rating,
    StepRating,
)

S = StepStatus
_SPAN_A = EvidenceSpan(section_id="s01", quote="span A")
_SPAN_B = EvidenceSpan(section_id="s02", quote="span B")


def _sr(
    step_id: str, status: StepStatus, *, conf: float = 0.9, span: EvidenceSpan = _SPAN_A
) -> StepRating:
    na = status is S.not_applicable
    return StepRating(
        step_id=step_id,
        applicable=not na,
        status=status,
        confidence=conf,
        evidence=[span] if status in (S.adequate, S.partial) else [],
        rationale="" if na else "rater note",
    )


def _rating(
    rid: str,
    steps: list[StepRating],
    *,
    rel: RelevanceLabel = RelevanceLabel.yes,
    cls: PaperClassLabel | None = PaperClassLabel.empirical,
    relationship: RaterRelationship = RaterRelationship.independent,
) -> Rating:
    no = rel is RelevanceLabel.no
    return Rating(
        rater_id=rid,
        relationship=relationship,
        relevance_label=rel,
        relevance_rationale="r",
        paper_class_label=None if no else cls,
        gate_facts=None if no else GateFacts(),
        steps=[] if no else steps,
    )


def _byid(rating: Rating) -> dict[str, StepRating]:
    return {s.step_id: s for s in rating.steps}


# --- per-step majority ----------------------------------------------------------------------------


def test_unanimous_agreement_passes_through() -> None:
    r1 = _rating("r1", [_sr("S1", S.adequate), _sr("S2", S.missing)])
    r2 = _rating("r2", [_sr("S1", S.adequate), _sr("S2", S.missing)])
    res = consensus_from_ratings([r1, r2])
    assert res.no_consensus_steps == []
    steps = _byid(res.consensus)
    assert steps["S1"].status is S.adequate and steps["S2"].status is S.missing


def test_strict_majority_of_three() -> None:
    raters = [
        _rating("r1", [_sr("S1", S.adequate)]),
        _rating("r2", [_sr("S1", S.adequate)]),
        _rating("r3", [_sr("S1", S.partial)]),
    ]
    res = consensus_from_ratings(raters)
    assert _byid(res.consensus)["S1"].status is S.adequate  # 2 of 3
    assert res.no_consensus_steps == []


def test_two_rater_status_disagreement_is_no_consensus() -> None:
    r1 = _rating("r1", [_sr("S1", S.adequate), _sr("S2", S.adequate)])
    r2 = _rating("r2", [_sr("S1", S.partial), _sr("S2", S.adequate)])  # split on S1, agree on S2
    res = consensus_from_ratings([r1, r2])
    assert res.no_consensus_steps == ["S1"]
    steps = _byid(res.consensus)
    assert "S1" not in steps  # dropped — the engine comparison skips it
    assert steps["S2"].status is S.adequate


def test_applicability_split_is_no_consensus() -> None:
    r1 = _rating("r1", [_sr("S4", S.adequate)])  # applicable
    r2 = _rating("r2", [_sr("S4", S.not_applicable)])  # N/A
    res = consensus_from_ratings([r1, r2])
    assert res.no_consensus_steps == ["S4"]
    assert res.consensus.steps == []


def test_majority_not_applicable() -> None:
    r1 = _rating("r1", [_sr("S4", S.not_applicable)])
    r2 = _rating("r2", [_sr("S4", S.not_applicable)])
    res = consensus_from_ratings([r1, r2])
    s4 = _byid(res.consensus)["S4"]
    assert s4.applicable is False and s4.status is S.not_applicable


def test_present_consensus_unions_evidence_and_is_contract_valid() -> None:
    # two raters agree adequate but cite different spans → consensus cites both; a valid StepRating
    r1 = _rating("r1", [_sr("S1", S.adequate, conf=0.8, span=_SPAN_A)])
    r2 = _rating("r2", [_sr("S1", S.adequate, conf=1.0, span=_SPAN_B)])
    s1 = _byid(consensus_from_ratings([r1, r2]).consensus)["S1"]
    assert {sp.quote for sp in s1.evidence} == {"span A", "span B"}
    assert s1.confidence == 0.9  # mean of the agreeing raters
    assert s1.rationale  # required for a present status; synthesized


# --- paper-level majority -------------------------------------------------------------------------


def test_relevance_no_majority_short_circuits() -> None:
    r1 = _rating("r1", [], rel=RelevanceLabel.no)
    r2 = _rating("r2", [], rel=RelevanceLabel.no)
    res = consensus_from_ratings([r1, r2])
    assert res.consensus.relevance_label is RelevanceLabel.no
    assert res.consensus.steps == [] and res.consensus.paper_class_label is None


def test_no_relevance_consensus_yields_none() -> None:
    r1 = _rating("r1", [_sr("S1", S.adequate)], rel=RelevanceLabel.yes)
    r2 = _rating("r2", [], rel=RelevanceLabel.no)
    assert consensus_from_ratings([r1, r2]).consensus is None


def test_no_paper_class_consensus_yields_none() -> None:
    r1 = _rating("r1", [_sr("S1", S.adequate)], cls=PaperClassLabel.empirical)
    r2 = _rating("r2", [_sr("S1", S.adequate)], cls=PaperClassLabel.methodological)
    assert consensus_from_ratings([r1, r2]).consensus is None


# --- assembly -------------------------------------------------------------------------------------


def test_assemble_human_report_is_admissible() -> None:
    ratings = [
        _rating("r1", [_sr("S1", S.adequate)], relationship=RaterRelationship.independent),
        _rating("r2", [_sr("S1", S.adequate)], relationship=RaterRelationship.prompt_author),
    ]
    hr = assemble_human_report(
        work_id="w1",
        source_sha256="sha",
        version_label="v1",
        rubric_version="0.1-draft",
        tier=GoldTier.A,
        ratings=ratings,
        origin=GoldOrigin.fake_llm,
    )
    assert hr is not None
    assert hr.consensus is not None and hr.consensus.relationship is RaterRelationship.consensus
    assert hr.ratings == ratings  # originals retained
    assert hr.validate_admissible() == []


def test_assemble_returns_none_without_consensus() -> None:
    ratings = [
        _rating("r1", [], rel=RelevanceLabel.yes, cls=PaperClassLabel.empirical),
        _rating("r2", [], rel=RelevanceLabel.no),
    ]
    hr = assemble_human_report(
        work_id="w1",
        source_sha256="sha",
        version_label="v1",
        rubric_version="0.1-draft",
        tier=GoldTier.A,
        ratings=ratings,
        origin=GoldOrigin.fake_llm,
    )
    assert hr is None
