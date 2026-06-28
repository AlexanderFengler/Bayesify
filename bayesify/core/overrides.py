"""Apply trusted expert corrections as a deterministic overlay on a scored result (display-time).

A trusted disagreement swaps one step's status; we re-run the SAME f-score arithmetic so coverage,
quality, the profile, and the score-impacts all stay consistent — exactly as if the engine had
produced that status. Pure: no IO, no LLM (the trusted-override lookup happens in the API layer).

Deliberately NOT called from ``engine.grade_parsed``: the validation harness keeps measuring the raw
engine output, so the blind calibration is never contaminated by these non-blind corrections.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from bayesify.core.rubric.models import RubricSpec
from bayesify.core.schema import ScoredResult, StepStatus
from bayesify.core.score import ScoreMeta, score


@dataclass(frozen=True)
class TrustedOverride:
    """One trusted per-step correction to apply (the engine-facing subset of a stored Override)."""

    step_id: str
    corrected_status: StepStatus
    author: str = ""
    rationale: str = ""
    recorded_at: str | None = None


class AppliedCorrection(BaseModel):
    """Provenance for one correction that actually changed an applicable step — what the report
    shows: the engine's status, the trusted status it became, who/why, and how much it moved the
    summary numbers (its own marginal coverage/quality delta vs the raw engine result)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    from_status: StepStatus
    to_status: StepStatus
    author: str
    rationale: str
    recorded_at: str | None
    coverage_delta: float
    quality_delta: float


def apply_step_overrides(
    result: ScoredResult, overrides: list[TrustedOverride], rubric: RubricSpec
) -> tuple[ScoredResult, list[AppliedCorrection]]:
    """Return ``(corrected_result, applied)``. Overrides that don't change an *applicable* step's
    status are ignored (a no-op, an unknown step, or an attempt to re-gate to not_applicable). When
    nothing changes, the original result is returned unchanged with an empty ``applied`` list."""
    if result.paper_class is None or not result.step_assessments:
        return result, []
    by_step = {o.step_id: o for o in overrides}
    base = result.step_assessments
    base_status = {a.step_id: a.status for a in base}

    changes: dict[str, StepStatus] = {}
    for a in base:
        o = by_step.get(a.step_id)
        if o is None or not a.applicable:
            continue
        if o.corrected_status is StepStatus.not_applicable or o.corrected_status is a.status:
            continue  # can't re-gate via an overlay; a no-op changes nothing
        changes[a.step_id] = o.corrected_status
    if not changes:
        return result, []

    meta = ScoreMeta(
        engine_version=result.engine_version,
        cost_ledger=result.cost_ledger,
        validation_ref=result.validation_ref,
    )

    def rescore(status_by_step: dict[str, StepStatus]) -> ScoredResult:
        new_steps = [
            a.model_copy(update={"status": status_by_step[a.step_id]})
            if a.step_id in status_by_step
            else a
            for a in base
        ]
        return score(
            result.relevance, result.paper_class, new_steps, result.gate_facts, rubric, meta
        )

    corrected = rescore(changes)
    base_cov = result.coverage.strict if result.coverage else 0.0
    base_q = result.quality_score or 0.0
    applied = []
    for step_id, to_status in changes.items():
        one = rescore({step_id: to_status})  # marginal effect of this one correction alone
        o = by_step[step_id]
        applied.append(
            AppliedCorrection(
                step_id=step_id,
                from_status=base_status[step_id],
                to_status=to_status,
                author=o.author,
                rationale=o.rationale,
                recorded_at=o.recorded_at,
                coverage_delta=(one.coverage.strict if one.coverage else 0.0) - base_cov,
                quality_delta=(one.quality_score or 0.0) - base_q,
            )
        )
    return corrected, applied
