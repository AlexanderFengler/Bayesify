"""Deterministic rubric applicability + expectation tier (B1 / gate G6).

``step_applicability`` is the single shared resolver: given a rubric step, the paper class, and the
evidence-derived ``GateFacts``, it decides whether the step applies and at what expectation tier
(expected / recommended / none). Both e-assess (which steps to judge) and f-score (gating + tier ->
severity) call it, so the two stages can never disagree on applicability — and f re-runs it to
cross-check e's flags (the f-score DoD).
"""

from __future__ import annotations

from dataclasses import dataclass

from bayesify.core.rubric.models import RubricStep
from bayesify.core.schema import ExpectationTier, GateFacts, PaperClassLabel, PriorInformativeness

_INFORMATIVE = {PriorInformativeness.informative, PriorInformativeness.weakly_informative}


@dataclass(frozen=True)
class StepApplicability:
    applicable: bool
    tier: ExpectationTier
    reason: str


def step_applicability(
    step: RubricStep, paper_class: PaperClassLabel, gate_facts: GateFacts
) -> StepApplicability:
    """Resolve one step's applicability + tier for a paper. N/A steps are excluded from scoring;
    an escalated step is ``expected`` (tier-1) regardless of class (G6)."""
    gate = step.gate
    pc = paper_class.value

    # 1. Gate-driven not-applicable (excluded from the denominator; never penalised).
    na_reason = step.na_when or "Not applicable."
    if gate is not None:
        if gate.na_when_inference and gate_facts.inference_method.value in gate.na_when_inference:
            return StepApplicability(False, ExpectationTier.none, na_reason)
        single_model_no_bf = gate_facts.n_models <= 1 and not gate_facts.bf_claimed
        if gate.na_when_single_model_no_bf and single_model_no_bf:
            return StepApplicability(False, ExpectationTier.none, na_reason)

    # 2. Expectation tier: evidence escalation (G6) wins, else the per-class tier.
    escalation = _escalation_reason(gate, gate_facts)
    if escalation is not None:
        return StepApplicability(True, ExpectationTier.expected, escalation)
    if pc in step.essential_for:
        return StepApplicability(True, ExpectationTier.expected, f"Expected for {pc} papers.")
    if pc in step.recommended_for:
        return StepApplicability(True, ExpectationTier.recommended, f"Recommended for {pc} papers.")
    return StepApplicability(True, ExpectationTier.none, f"Optional for {pc} papers.")


def _escalation_reason(gate, gate_facts: GateFacts) -> str | None:
    if gate is None:
        return None
    if gate.essential_when_bf_claimed and gate_facts.bf_claimed:
        return "Expected: a Bayes-factor claim is made."
    if (
        gate.essential_when_models_gte is not None
        and gate_facts.n_models >= gate.essential_when_models_gte
    ):
        return f"Expected: {gate_facts.n_models} models are compared."
    if gate.essential_when_prior_informative and gate_facts.prior_informativeness in _INFORMATIVE:
        return "Expected: (weakly-)informative priors are used."
    return None
