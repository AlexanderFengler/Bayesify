"""Score (component f) — turn per-step judgments into the profile + coverage + quality.

A **pure, deterministic** function (no LLM, no IO; enforced by an import-linter rule): identical
inputs yield byte-identical output, in rubric order. This is where B1's applicability gating becomes
arithmetic — N/A steps are excluded from the denominator and never penalise — and where the
post-badge scoring model lives: the per-step **profile** is primary, with **coverage** (an
uncertainty-honest range) and **quality** (weighted mean sub-score) as the two summary numbers.

All numbers come from the rubric's scoring block (``rubric/steps.yaml``, gate G5); nothing is
hardcoded. ``score`` re-derives applicability from ``paper_class`` + ``gate_facts`` via the shared
resolver and raises ``ContractError`` if it disagrees with the upstream ``applicable`` flags — it
trusts neither side blindly.
"""

from __future__ import annotations

from dataclasses import dataclass

from veribayes.core.rubric.applicability import step_applicability
from veribayes.core.rubric.models import RubricSpec
from veribayes.core.schema import (
    CostLedger,
    Coverage,
    GateFacts,
    PaperClass,
    Profile,
    Relevance,
    RelevanceLabel,
    ScoredResult,
    ScoreImpact,
    StepAssessment,
    StepProfile,
    StepStatus,
)


class ContractError(ValueError):
    """Malformed input, gate mismatch, or f invoked on an irrelevant paper. Carries the field."""


class RubricSpecError(ValueError):
    """The rubric is missing a table required to score this paper (e.g. no scoring block)."""


@dataclass(frozen=True)
class ScoreMeta:
    engine_version: str
    cost_ledger: CostLedger
    validation_ref: str = "unvalidated"


_PRESENT = (StepStatus.done_well, StepStatus.partial)


@dataclass(frozen=True)
class _Calc:
    """The minimal per-step facts the scoring arithmetic needs."""

    applicable: bool
    status: StepStatus
    weight: float
    confidence: float


def score(
    relevance: Relevance,
    paper_class: PaperClass,
    step_assessments: list[StepAssessment],
    gate_facts: GateFacts,
    rubric: RubricSpec,
    meta: ScoreMeta,
) -> ScoredResult:
    """Compute the ``ScoredResult``. Pure: no randomness, clock, or network."""
    if relevance.label is RelevanceLabel.no:
        raise ContractError("score() must not be called on an irrelevant paper (relevance=no)")
    if paper_class is None:  # type: ignore[redundant-expr]
        raise ContractError("paper_class is required to score a relevant paper")
    if rubric.scoring is None:
        raise RubricSpecError("rubric has no scoring block (gate G5)")
    if not step_assessments:
        raise ContractError("step_assessments is empty for a relevant paper")

    scoring = rubric.scoring
    by_id = {a.step_id: a for a in step_assessments}
    if len(by_id) != len(step_assessments):
        raise ContractError("duplicate step_id in step_assessments")

    profile_steps: list[StepProfile] = []
    calcs: list[tuple[str, _Calc]] = []
    for step in rubric.steps:  # canonical: rubric order
        assessment = by_id.get(step.id)
        if assessment is None:
            raise ContractError(f"no assessment for rubric step {step.id}")
        resolved = step_applicability(step, paper_class.primary, gate_facts)
        if resolved.applicable != assessment.applicable:
            raise ContractError(
                f"applicability mismatch on {step.id}: "
                f"rubric={resolved.applicable} vs upstream={assessment.applicable}"
            )
        if resolved.applicable and assessment.status is StepStatus.not_applicable:
            raise ContractError(f"{step.id} is applicable but status is not_applicable")

        weight = _weight(rubric, step.id, paper_class)
        sub = None if not resolved.applicable else scoring.sub_score[assessment.status.value]
        profile_steps.append(
            StepProfile(
                step_id=step.id,
                applicable=resolved.applicable,
                status=assessment.status,
                sub_score=sub,
                weight=weight,
                tier=resolved.tier,
            )
        )
        calcs.append(
            (step.id, _Calc(resolved.applicable, assessment.status, weight, assessment.confidence))
        )

    low_conf = scoring.low_confidence_threshold
    coverage, quality = _summaries([c for _, c in calcs], scoring.sub_score, low_conf)
    n_applicable = sum(1 for _, c in calcs if c.applicable)
    profile = Profile(
        steps=profile_steps,
        n_applicable=n_applicable,
        n_na=len(calcs) - n_applicable,
        n_uncertain=_uncertain(calcs, low_conf),
    )
    impacts = _score_impacts(calcs, scoring.sub_score, low_conf, coverage, quality)

    # step_assessments echo through in rubric order (canonical), all sub-fields untouched.
    ordered = [by_id[s.id] for s in rubric.steps]
    return ScoredResult(
        relevance=relevance,
        paper_class=paper_class,
        gate_facts=gate_facts,
        step_assessments=ordered,
        profile=profile,
        coverage=coverage,
        quality_score=quality,
        score_impacts=impacts,
        engine_version=meta.engine_version,
        rubric_version=rubric.rubric_version,
        rubric_profile=rubric.profile,
        cost_ledger=meta.cost_ledger,
        validation_ref=meta.validation_ref,
    )


# --- arithmetic (shared by score() and the score-impact what-ifs) --------------------------------


def _weight(rubric: RubricSpec, step_id: str, paper_class: PaperClass) -> float:
    scoring = rubric.scoring
    assert scoring is not None

    def w(cls: str | None) -> float:
        if cls is None:
            return scoring.weight_default
        return scoring.weights.get(cls, {}).get(step_id, scoring.weight_default)

    primary = w(paper_class.primary.value)
    if paper_class.secondary is not None and scoring.mixing_rule == "max":
        return max(primary, w(paper_class.secondary.value))
    return primary


def _uncertain(calcs: list[tuple[str, _Calc]], low_conf: float) -> int:
    return sum(
        1
        for _, c in calcs
        if c.applicable and c.status is StepStatus.missing and c.confidence < low_conf
    )


def _summaries(
    calcs: list[_Calc], sub_score: dict[str, float], low_conf: float
) -> tuple[Coverage | None, float | None]:
    applicable = [c for c in calcs if c.applicable]
    n = len(applicable)
    if n == 0:  # not gradable — no division; coverage/quality are null
        return None, None
    present = sum(1 for c in applicable if c.status in _PRESENT)
    uncertain = sum(
        1 for c in applicable if c.status is StepStatus.missing and c.confidence < low_conf
    )
    coverage = Coverage(
        present=present,
        applicable=n,
        strict=present / n,  # uncertain absences counted absent
        lenient=(present + uncertain) / n,  # counted present
    )
    total_w = sum(c.weight for c in applicable)
    quality = (
        sum(c.weight * sub_score[c.status.value] for c in applicable) / total_w
        if total_w
        else None
    )
    return coverage, quality


def _score_impacts(
    calcs: list[tuple[str, _Calc]],
    sub_score: dict[str, float],
    low_conf: float,
    base_cov: Coverage | None,
    base_q: float | None,
) -> list[ScoreImpact]:
    """For each applicable step not already at ``done_well``, the verified coverage/quality gain of
    upgrading it to ``done_well`` — computed by re-running the arithmetic, so every delta is
    reachable by construction (never speculative)."""
    if base_cov is None or base_q is None:
        return []
    impacts: list[ScoreImpact] = []
    plain = [c for _, c in calcs]
    for i, (step_id, c) in enumerate(calcs):
        if not c.applicable or c.status is StepStatus.done_well:
            continue
        hypo = list(plain)
        hypo[i] = _Calc(True, StepStatus.done_well, c.weight, c.confidence)
        cov2, q2 = _summaries(hypo, sub_score, low_conf)
        assert cov2 is not None and q2 is not None
        impacts.append(
            ScoreImpact(
                step_id=step_id,
                from_status=c.status,
                to_status=StepStatus.done_well,
                # exact (not rounded): every delta is reachable by re-scoring with this upgrade.
                coverage_delta=cov2.strict - base_cov.strict,
                quality_delta=q2 - base_q,
            )
        )
    return impacts
