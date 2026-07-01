"""Batched assess path: one judge call for all applicable rubric steps, one refuter call for all
negative findings.

This is an alternative to ``assess.assess`` for hosted/interactive use. It preserves the
deterministic parts of the original path (gate facts, applicability, quote verification, severity
derivation, score contracts) while reducing the LLM call count from O(steps) to two assess-stage
calls.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from bayesify.core import config
from bayesify.core.assess import (
    AssessError,
    RefuterVerdict,
    StepJudgment,
    _apply_refutation,
    _not_applicable_assessment,
    _scanned_section_ids,
    _step_evidence,
    _to_assessment,
    _wider_context,
    derive_gate_facts,
)
from bayesify.core.context import evidence_digest, excerpt_context
from bayesify.core.prompts import ASSESS_BATCH_JUDGE_SYSTEM, ASSESS_BATCH_REFUTE_SYSTEM
from bayesify.core.rubric.applicability import step_applicability_for_labels
from bayesify.core.rubric.models import RubricSpec, RubricStep
from bayesify.core.schema import (
    AdversarialVerdict,
    CostLedgerEntry,
    Evidence,
    GateFacts,
    PaperClass,
    StepAssessment,
    StepStatus,
)
from bayesify.llm import LLMClient, call_with_policy, ledger_entry


class BatchStepJudgment(StepJudgment):
    step_id: str


class BatchAssessJudgments(BaseModel):
    judgments: list[BatchStepJudgment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_unique_steps(self) -> BatchAssessJudgments:
        ids = [j.step_id for j in self.judgments]
        if len(ids) != len(set(ids)):
            raise ValueError("batch assessment returned duplicate step_id values")
        return self


class BatchRefuterVerdict(RefuterVerdict):
    step_id: str


class BatchRefuterVerdicts(BaseModel):
    verdicts: list[BatchRefuterVerdict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_unique_steps(self) -> BatchRefuterVerdicts:
        ids = [v.step_id for v in self.verdicts]
        if len(ids) != len(set(ids)):
            raise ValueError("batch refuter returned duplicate step_id values")
        return self


def assess_batch(
    parsed,
    evidence: list[Evidence],
    relevance,  # noqa: ARG001 - kept aligned with assess.assess
    paper_class: PaperClass,
    rubric: RubricSpec,
    *,
    client: LLMClient,
    model: str | None = None,
) -> tuple[list[StepAssessment], GateFacts, list[CostLedgerEntry]]:
    """Assess all applicable rubric steps with two LLM calls: judge batch, then refute batch."""
    model = model or config.judge_model()
    gate_facts = derive_gate_facts(evidence, paper_class)
    searched = _scanned_section_ids(parsed)
    plans = [
        (step, step_applicability_for_labels(step, paper_class.labels, gate_facts))
        for step in rubric.steps
    ]
    applicable = [(step, ap) for step, ap in plans if ap.applicable]

    cost: list[CostLedgerEntry] = []
    assessments_by_id: dict[str, StepAssessment] = {}
    if applicable:
        judge = call_with_policy(
            client,
            model=model,
            system=ASSESS_BATCH_JUDGE_SYSTEM,
            user=_build_batch_judge_user(applicable, parsed, evidence, rubric),
            schema=BatchAssessJudgments,
            max_tokens=5000,
        )
        cost.append(ledger_entry("assess", judge, pass_label="batch_judge"))
        judgments = _judgments_by_step(judge.parsed, [step.id for step, _ in applicable])
        for step, ap in applicable:
            step_ev = _step_evidence(step.id, evidence)
            assessments_by_id[step.id] = _to_assessment(
                step, ap, judgments[step.id], parsed, step_ev, searched, rubric
            )

    negative = [
        (step, assessments_by_id[step.id])
        for step, ap in applicable
        if assessments_by_id[step.id].status in (StepStatus.missing, StepStatus.partial)
    ]
    if negative:
        refute = call_with_policy(
            client,
            model=model,
            system=ASSESS_BATCH_REFUTE_SYSTEM,
            user=_build_batch_refuter_user(negative, parsed),
            schema=BatchRefuterVerdicts,
            max_tokens=3000,
        )
        cost.append(ledger_entry("assess", refute, pass_label="batch_refute"))
        verdicts = _verdicts_by_step(refute.parsed, [step.id for step, _ in negative])
        for step, assessment in negative:
            assessments_by_id[step.id] = _apply_refutation(
                assessment, verdicts[step.id], parsed
            )

    assessments: list[StepAssessment] = []
    for step, ap in plans:
        if ap.applicable:
            assessment = assessments_by_id[step.id]
            if assessment.adversarial_verdict is None:
                assessment = assessment.model_copy(
                    update={
                        "adversarial_verdict": AdversarialVerdict(
                            challenged=False, refuted=False
                        )
                    }
                )
            assessments.append(assessment)
        else:
            assessments.append(_not_applicable_assessment(step, ap))
    return assessments, gate_facts, cost


def _judgments_by_step(
    batch: BatchAssessJudgments, expected_ids: list[str]
) -> dict[str, BatchStepJudgment]:
    expected = set(expected_ids)
    found = {j.step_id: j for j in batch.judgments}
    extra = sorted(set(found) - expected)
    missing = sorted(expected - set(found))
    if extra or missing:
        raise AssessError(
            f"batch assessment step_id mismatch: missing={missing or 'none'}, "
            f"extra={extra or 'none'}"
        )
    return found


def _verdicts_by_step(
    batch: BatchRefuterVerdicts, expected_ids: list[str]
) -> dict[str, RefuterVerdict]:
    expected = set(expected_ids)
    found = {v.step_id: v for v in batch.verdicts if v.step_id in expected}
    return {
        step_id: found.get(
            step_id,
            RefuterVerdict(
                refuted=False,
                notes="Batch refuter returned no verdict for this step.",
            ),
        )
        for step_id in expected_ids
    }


def _build_batch_judge_user(
    applicable: list[tuple[RubricStep, object]],
    parsed,
    evidence: list[Evidence],
    rubric: RubricSpec,
) -> str:
    blocks = []
    for step, ap in applicable:
        thresholds = "\n".join(
            f"    - {name}: {threshold.value} ({threshold.source})"
            for name, threshold in step.thresholds.items()
        )
        candidates = "\n".join(
            f"    - {sid}: {rubric.citations.get(sid, sid)}" for sid in step.citations
        ) or "    (none)"
        blocks.append(
            "\n".join(
                [
                    f"STEP {step.id}: {step.name}",
                    f"  Applicability: {ap.reason}",
                    f"  ADEQUATE: {step.adequate}",
                    f"  MISSING: {step.missing}",
                    f"  THRESHOLDS:\n{thresholds}" if thresholds else "  THRESHOLDS: (none)",
                    f"  CANDIDATE STANDARDS:\n{candidates}",
                    f"  DETECTOR HITS:\n{evidence_digest(_step_evidence(step.id, evidence))}",
                ]
            )
        )
    return (
        "Return judgments for exactly these applicable rubric steps:\n\n"
        + "\n\n".join(blocks)
        + "\n\nALL DETECTOR HITS:\n"
        + evidence_digest(evidence)
        + "\n\nPAPER EXCERPTS:\n"
        + excerpt_context(parsed)
    )


def _build_batch_refuter_user(
    negative: list[tuple[RubricStep, StepAssessment]],
    parsed,
) -> str:
    blocks = []
    for step, assessment in negative:
        blocks.append(
            "\n".join(
                [
                    f"STEP {step.id}: {step.name}",
                    f"  First-pass status: {assessment.status.value}",
                    f"  ADEQUATE means: {step.adequate}",
                    "  First-pass rationale:",
                    "  "
                    + " ".join(
                        list(assessment.did_well)
                        + [suggestion.text for suggestion in assessment.suggestions]
                    )[:1200],
                ]
            )
        )
    return (
        "Return verdicts for exactly these challenged rubric steps:\n\n"
        + "\n\n".join(blocks)
        + "\n\nWIDER CONTEXT (includes supplements & captions):\n"
        + _wider_context(parsed)
    )
