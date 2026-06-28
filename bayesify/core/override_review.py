"""Override-review pass — the global, LLM-judged correction layer (display-time, post-grading).

Mirrors the adversarial refuter ([assess.py], judge -> refute). For each applicable step that has
candidate overrides in the bank, an LLM judges whether any past trusted correction is *relevant* to
THIS step's grade (evidence/context similarity) and, if so, proposes a slight, conservative (at most
one-level) correction linking back to the override + its source paper. The result is re-scored via
the engine's own f-score arithmetic, so coverage/quality stay consistent.

Robust + cheap: a step with no candidates costs no LLM call. It is NOT part of ``grade_parsed`` —
it runs only in the API/display path, so the validation harness keeps measuring the raw engine and
the blind calibration is never contaminated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from bayesify.core import config
from bayesify.core.prompts import OVERRIDE_REVIEW_SYSTEM
from bayesify.core.rubric.models import RubricSpec, RubricStep
from bayesify.core.schema import CostLedgerEntry, ScoredResult, StepAssessment, StepStatus
from bayesify.core.score import ScoreMeta, score
from bayesify.llm import LLMClient, call_with_policy, ledger_entry

_ORDER = (StepStatus.missing, StepStatus.partial, StepStatus.adequate)  # gradeable, low -> high
_BY_VALUE = {s.value: s for s in _ORDER}


@dataclass(frozen=True)
class BankOverride:
    """One bank entry (a past trusted correction) as the review pass sees it."""

    step_id: str
    original_status: str
    corrected_status: str
    rationale: str = ""
    engine_rationale: str = ""
    paper_title: str = ""
    author: str = ""
    evidence_quotes: list[str] = field(default_factory=list)


class ReviewVerdict(BaseModel):
    """The override-review LLM's structured output for one step."""

    model_config = ConfigDict(extra="forbid")

    relevant: bool = False
    corrected_status: str | None = None  # "missing"|"partial"|"adequate"; null if not relevant
    used_override: int | None = None  # index into the candidate list
    justification: str = ""


class AppliedCorrection(BaseModel):
    """Provenance for one applied correction — what the report shows (a tooltip to the source paper)
    plus how much it moved the two summary numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    from_status: StepStatus
    to_status: StepStatus
    coverage_delta: float
    quality_delta: float
    override_author: str
    override_rationale: str
    source_paper_title: str
    justification: str  # the review LLM's reason for applying it


def review_overrides(
    result: ScoredResult,
    bank: dict[str, list[BankOverride]],
    rubric: RubricSpec,
    *,
    client: LLMClient,
    model: str = config.JUDGE_MODEL,
) -> tuple[ScoredResult, list[AppliedCorrection], list[CostLedgerEntry]]:
    """Run the relevance+correction pass over the steps that have candidate overrides. Returns the
    (possibly corrected) result + provenance + the LLM cost ledger. A no-op when nothing applies;
    one LLM call per step-with-candidates, none when ``bank`` is empty."""
    if result.paper_class is None or not result.step_assessments:
        return result, [], []
    by_id = {a.step_id: a for a in result.step_assessments}
    steps = {st.id: st for st in rubric.steps}
    changes: dict[str, StepStatus] = {}
    provenance: dict[str, tuple[BankOverride, str]] = {}
    cost: list[CostLedgerEntry] = []

    for step_id, candidates in bank.items():
        a = by_id.get(step_id)
        if a is None or not a.applicable or not candidates:
            continue
        resp = call_with_policy(
            client,
            model=model,
            system=OVERRIDE_REVIEW_SYSTEM,
            user=_build_user(a, steps.get(step_id), candidates),
            schema=ReviewVerdict,
            max_tokens=600,
        )
        cost.append(ledger_entry("override_review", resp, step_id=step_id, pass_label="review"))
        v = resp.parsed
        target = _BY_VALUE.get(v.corrected_status or "")
        if not v.relevant or target is None or target is a.status:
            continue
        nudged = _one_level_toward(a.status, target)
        if nudged is a.status:
            continue
        idx = v.used_override if v.used_override is not None else 0
        ov = candidates[idx] if 0 <= idx < len(candidates) else candidates[0]
        changes[step_id] = nudged
        provenance[step_id] = (ov, v.justification)

    if not changes:
        return result, [], cost

    meta = ScoreMeta(
        engine_version=result.engine_version,
        cost_ledger=result.cost_ledger,
        validation_ref=result.validation_ref,
    )
    base = result.step_assessments

    def rescore(overrides: dict[str, StepStatus]) -> ScoredResult:
        new = [
            a.model_copy(update={"status": overrides[a.step_id]}) if a.step_id in overrides else a
            for a in base
        ]
        return score(result.relevance, result.paper_class, new, result.gate_facts, rubric, meta)

    corrected = rescore(changes)
    base_cov = result.coverage.strict if result.coverage else 0.0
    base_q = result.quality_score or 0.0
    applied: list[AppliedCorrection] = []
    for step_id, to_status in changes.items():
        one = rescore({step_id: to_status})  # marginal effect of this one correction
        ov, justification = provenance[step_id]
        applied.append(
            AppliedCorrection(
                step_id=step_id,
                from_status=by_id[step_id].status,
                to_status=to_status,
                coverage_delta=(one.coverage.strict if one.coverage else 0.0) - base_cov,
                quality_delta=(one.quality_score or 0.0) - base_q,
                override_author=ov.author,
                override_rationale=ov.rationale,
                source_paper_title=ov.paper_title,
                justification=justification,
            )
        )
    return corrected, applied, cost


def _one_level_toward(current: StepStatus, target: StepStatus) -> StepStatus:
    """Move ``current`` one level toward ``target`` (missing<partial<adequate) — the nudge stays
    slight. Returns ``current`` unchanged if either is not a gradeable status."""
    if current not in _ORDER or target not in _ORDER:
        return current
    ci, ti = _ORDER.index(current), _ORDER.index(target)
    if ti > ci:
        return _ORDER[ci + 1]
    if ti < ci:
        return _ORDER[ci - 1]
    return current


def _build_user(
    assessment: StepAssessment, step: RubricStep | None, candidates: list[BankOverride]
) -> str:
    reasoning = " ".join(
        list(assessment.did_well) + [s.text for s in assessment.suggestions]
    ).strip() or "(no reasoning recorded)"
    quotes = (
        "; ".join(e.span.quote for e in assessment.evidence if e.span and e.span.quote) or "(none)"
    )
    criteria = (
        f"ADEQUATE means: {step.adequate}\nDONE POORLY means: {step.missing}\n" if step else ""
    )
    bank = "\n".join(
        f"  [{i}] paper: {c.paper_title or '(untitled)'} | engine: {c.original_status} -> "
        f"expert: {c.corrected_status}\n      expert rationale: {c.rationale}\n"
        f"      engine reasoning then: {c.engine_rationale[:400]}\n"
        f"      quotes: {'; '.join(c.evidence_quotes[:3]) or '(none)'}"
        for i, c in enumerate(candidates)
    )
    return (
        f"RUBRIC STEP {assessment.step_id}\n{criteria}\n"
        f"CURRENT GRADE: {assessment.status.value} (confidence {assessment.confidence:.0%})\n"
        f"CURRENT REASONING: {reasoning}\n"
        f"CURRENT EVIDENCE QUOTES: {quotes}\n\n"
        f"BANK OF PAST EXPERT CORRECTIONS ON THIS STEP:\n{bank}\n\n"
        "Is any bank entry relevant to the current grade? If so, give its index + corrected_status."
    )
