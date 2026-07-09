"""Paper-type classifier — component d, stage 5 (runs only after a non-``no`` relevance gate).

Assigns every evidence-supported paper-class label. The label set drives rubric-step applicability
downstream (B1): data-analysis papers, method/model/software
development papers, numerical/theoretical analyses, and reviews can have different expectations.
This component only *produces* the class; the applicability rules live in
``rubric/steps.yaml`` and are applied by e-assess / f-score.

Like the relevance gate it runs on the cheap model (C6), fails closed on LLM error, and meters its
single call into the cost ledger (stage tag ``classify``). Its context is wider than the screen
gate's, so a secondary or late-section real-data analysis is not truncated away before the model
sees it.
"""

from __future__ import annotations

import logging

from bayesify.core.context import build_user, validate_evidence_refs
from bayesify.core.prompts import CLASSIFY_SYSTEM
from bayesify.core.schema import (
    CostLedgerEntry,
    Evidence,
    InferenceMethod,
    PaperClass,
    ParsedDoc,
)
from bayesify.llm import LLMClient, call_with_policy, ledger_entry
from bayesify.llm import config as llm_config

_log = logging.getLogger("bayesify.core.classify")

# Wider than the screen gate's DEFAULT_MAX_CHARS (12k): the paper type / disciplines can depend on
# content in a later section (e.g. a secondary real-data analysis) that a 12k prefix cut would drop.
CLASSIFY_MAX_CHARS = 30_000

# Each method chip must be corroborated by a detector hit, the same grounding the labels get via
# evidence_refs — otherwise a hallucinated in-vocab method (the "SMC?!" report) shows as fact. smc/
# abc/laplace_inla detectors were added to the catalog specifically so this mapping is total.
_METHOD_DETECTOR: dict[InferenceMethod, str] = {
    InferenceMethod.mcmc: "method.mcmc",
    InferenceMethod.hmc_nuts: "method.mcmc",  # NUTS/HMC live in the method.mcmc pattern
    InferenceMethod.variational: "method.variational",
    InferenceMethod.sbi: "method.sbi",
    InferenceMethod.smc: "method.smc",
    InferenceMethod.abc: "method.abc",
    InferenceMethod.laplace_inla: "method.laplace_inla",
    InferenceMethod.exact_analytic: "method.analytic",
}


def classify(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str | None = None,
) -> tuple[PaperClass, CostLedgerEntry]:
    """Classify the paper type. Returns the ``PaperClass`` and its cost entry; raises ``LLMError``
    (fail closed) if the cheap-model call cannot complete."""
    model = model or llm_config.classify_model()
    user = build_user(parsed, evidence, max_chars=CLASSIFY_MAX_CHARS)
    response = call_with_policy(
        client, model=model, system=CLASSIFY_SYSTEM, user=user, schema=PaperClass, max_tokens=800
    )
    paper_class = response.parsed
    # A3: reject a hallucinated citation before it becomes a dangling ref. Guarded on `evidence`
    # because the only zero-evidence caller is the forced rerun escape hatch (which grades without
    # grounding by design); the normal relevance gate only reaches classify when evidence exists.
    if evidence:
        validate_evidence_refs(paper_class.evidence_refs, evidence, where="paper_class")
        _ground_methods(paper_class, evidence)
    return paper_class, ledger_entry("classify", response)


def _ground_methods(paper_class: PaperClass, evidence: list[Evidence]) -> None:
    """Drop any ``methods_used`` entry with no corroborating detector hit — the same grounding the
    labels get via ``evidence_refs``, applied to the (otherwise ungrounded) method chips. Mutates
    ``paper_class`` in place. Precision-first: a real method the catalog missed loses its chip, but
    a hallucinated in-vocab method can no longer surface as fact. Skipped when evidence is empty."""
    fired = {e.detector_id for e in evidence}
    kept: list[InferenceMethod] = []
    dropped: list[InferenceMethod] = []
    for m in paper_class.methods_used:
        (kept if _METHOD_DETECTOR.get(m) in fired else dropped).append(m)
    if dropped:
        _log.warning(
            "classifier named methods with no corroborating detector hit (dropped): %s",
            [m.value for m in dropped],
        )
        paper_class.methods_used = kept
