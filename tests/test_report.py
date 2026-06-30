"""Report-derived views (M6 slice 1): D2 fix-list ordering, D3 praise lint, JSON round-trip."""

from __future__ import annotations

import json
from pathlib import Path

from bayesify.core.report import fix_list, uncited_praise
from bayesify.core.schema import (
    CostLedger,
    Coverage,
    Ease,
    ExpectationTier,
    PaperClass,
    PaperClassLabel,
    Profile,
    Relevance,
    RelevanceLabel,
    ScoredResult,
    Severity,
    StepAssessment,
    StepProfile,
    StepStatus,
    Suggestion,
)

_FIX = Path(__file__).parent / "fixtures" / "scored_result" / "empirical_mixed.json"


def _sugg(severity: Severity, ease: Ease, text: str) -> Suggestion:
    return Suggestion(severity=severity, text=text, how_to="...", ease=ease)


def _result(step_assessments, profile_steps) -> ScoredResult:
    return ScoredResult(
        relevance=Relevance(
            label=RelevanceLabel.yes, confidence=0.9, rationale="x", evidence_refs=[0]
        ),
        paper_class=PaperClass(
            labels=[PaperClassLabel.data_analysis], confidence=0.9, rationale="x", evidence_refs=[0]
        ),
        step_assessments=step_assessments,
        profile=Profile(
            steps=profile_steps, n_applicable=len(profile_steps), n_na=0, n_uncertain=0
        ),
        coverage=Coverage(present=1, applicable=len(profile_steps), strict=0.5, lenient=0.5),
        quality_score=0.5,
        engine_version="ev",
        rubric_version="0.1-draft",
        cost_ledger=CostLedger(),
    )


def _assessment(step_id: str, suggestions) -> StepAssessment:
    return StepAssessment(
        step_id=step_id,
        applicable=True,
        applicability_reason="",
        status=StepStatus.missing,
        confidence=0.9,
        suggestions=suggestions,
    )


def _profile(step_id: str, weight: float) -> StepProfile:
    return StepProfile(
        step_id=step_id,
        applicable=True,
        status=StepStatus.missing,
        sub_score=0.0,
        weight=weight,
        tier=ExpectationTier.expected,
    )


# --- D2 ordering: severity → step weight → ease --------------------------------------------------


def test_fix_list_orders_by_severity_then_weight_then_ease() -> None:
    # deliberately shuffled across steps; each (step, suggestion) has a known rank key.
    result = _result(
        step_assessments=[
            _assessment("S1", [_sugg(Severity.info, Ease.low, "info-low")]),
            _assessment("S2", [_sugg(Severity.error, Ease.high, "error-high-w1")]),
            _assessment("S3", [_sugg(Severity.error, Ease.high, "error-high-w2")]),
            _assessment("S4", [_sugg(Severity.warning, Ease.low, "warn-low")]),
            _assessment("S5", [_sugg(Severity.error, Ease.low, "error-low-w1")]),
        ],
        profile_steps=[
            _profile("S1", 1.0),
            _profile("S2", 1.0),
            _profile("S3", 2.0),  # heavier
            _profile("S4", 1.0),
            _profile("S5", 1.0),
        ],
    )
    order = [f.text for f in fix_list(result)]
    assert order == [
        "error-high-w2",  # error, weight 2.0
        "error-low-w1",   # error, weight 1.0, ease low (easy win before...)
        "error-high-w1",  # error, weight 1.0, ease high
        "warn-low",       # warning
        "info-low",       # info last
    ]


def test_fix_list_carries_score_impact() -> None:
    result = ScoredResult.model_validate_json(_FIX.read_text(encoding="utf-8"))
    fixes = fix_list(result)
    assert fixes  # the fixture has suggestions
    s5 = next(f for f in fixes if f.step_id == "S5")  # missing expected step
    assert s5.severity is Severity.error
    assert s5.coverage_delta > 0  # bringing a missing step to adequate lifts coverage


# --- D3 praise lint ------------------------------------------------------------------------------


def test_uncited_praise_is_flagged() -> None:
    cited = StepAssessment(
        step_id="S1", applicable=True, applicability_reason="", status=StepStatus.adequate,
        confidence=0.9, did_well=['Reports R-hat (§s02).'],
    )
    generic = StepAssessment(
        step_id="S4", applicable=True, applicability_reason="", status=StepStatus.adequate,
        confidence=0.9, did_well=["The analysis is rigorous and well done."],
    )
    result = _result([cited, generic], [_profile("S1", 1.0), _profile("S4", 1.0)])
    flagged = uncited_praise(result)
    assert ("S4", "The analysis is rigorous and well done.") in flagged
    assert all(step_id != "S1" for step_id, _ in flagged)  # the cited entry passes


def test_recorded_fixture_has_only_cited_praise() -> None:
    result = ScoredResult.model_validate_json(_FIX.read_text(encoding="utf-8"))
    assert uncited_praise(result) == []  # the committed fixture must model good (cited) praise


# --- meta-research JSON round-trips exactly ------------------------------------------------------


def test_scored_result_round_trips_byte_identical() -> None:
    text = _FIX.read_text(encoding="utf-8")
    result = ScoredResult.model_validate_json(text)
    assert json.loads(result.model_dump_json()) == json.loads(text)  # parse(report.json) == result
