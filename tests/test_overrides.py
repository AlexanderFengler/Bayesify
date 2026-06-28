"""The trusted-override overlay (Phase 2): ``apply_step_overrides`` swaps a step's status and
re-scores via the engine's own f-score, returning the corrected result + per-correction provenance.
Pure — no IO, no LLM."""

from __future__ import annotations

import pathlib

from bayesify.core.overrides import TrustedOverride, apply_step_overrides
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import ScoredResult, StepStatus

_FIX = pathlib.Path(__file__).parent / "fixtures" / "scored_result" / "empirical_mixed.json"
_RUBRIC = load_rubric()


def _result() -> ScoredResult:
    return ScoredResult.model_validate_json(_FIX.read_text(encoding="utf-8"))


def test_overlay_flips_status_and_rescores() -> None:
    result = _result()
    target = next(
        a for a in result.step_assessments if a.applicable and a.status is StepStatus.missing
    )
    ov = TrustedOverride(
        step_id=target.step_id,
        corrected_status=StepStatus.adequate,
        author="alice",
        rationale="supp",
    )
    corrected, applied = apply_step_overrides(result, [ov], _RUBRIC)

    new = next(a for a in corrected.step_assessments if a.step_id == target.step_id)
    assert new.status is StepStatus.adequate  # the step now reads the corrected status
    assert (corrected.quality_score or 0) > (result.quality_score or 0)  # re-scored upward
    assert len(applied) == 1
    c = applied[0]
    assert c.step_id == target.step_id
    assert c.from_status is StepStatus.missing and c.to_status is StepStatus.adequate
    assert c.author == "alice" and c.rationale == "supp"
    assert c.quality_delta > 0 and c.coverage_delta > 0  # how much this one correction moved them


def test_overlay_ignores_noops_unknown_and_na_steps() -> None:
    result = _result()
    applicable = next(a for a in result.step_assessments if a.applicable)
    overrides = [
        TrustedOverride(step_id=applicable.step_id, corrected_status=applicable.status),  # no-op
        TrustedOverride(step_id="S99", corrected_status=StepStatus.adequate),  # unknown step
    ]
    corrected, applied = apply_step_overrides(result, overrides, _RUBRIC)
    assert applied == [] and corrected is result  # nothing changed → the same object is returned

    na = next((a for a in result.step_assessments if not a.applicable), None)
    if na is not None:  # an N/A step can't be re-gated by an overlay
        _, applied2 = apply_step_overrides(
            result,
            [TrustedOverride(step_id=na.step_id, corrected_status=StepStatus.adequate)],
            _RUBRIC,
        )
        assert applied2 == []
