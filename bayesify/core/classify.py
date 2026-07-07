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

from bayesify.core.context import build_user, validate_evidence_refs
from bayesify.core.prompts import CLASSIFY_SYSTEM
from bayesify.core.schema import CostLedgerEntry, Evidence, PaperClass, ParsedDoc
from bayesify.llm import LLMClient, call_with_policy, ledger_entry
from bayesify.llm import config as llm_config

# Wider than the screen gate's DEFAULT_MAX_CHARS (12k): the paper type / disciplines can depend on
# content in a later section (e.g. a secondary real-data analysis) that a 12k prefix cut would drop.
CLASSIFY_MAX_CHARS = 30_000


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
    return paper_class, ledger_entry("classify", response)
