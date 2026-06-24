"""Paper-type classifier — component d, stage 5 (runs only after a non-``no`` relevance gate).

Assigns every evidence-supported paper-class label. The label set drives rubric-step applicability
downstream (B1): data-analysis papers, method/model/software
development papers, numerical/theoretical analyses, and reviews can have different expectations.
This component only *produces* the class; the applicability rules live in
``rubric/steps.yaml`` and are applied by e-assess / f-score.

Like the relevance gate it runs on the cheap model (C6) over the same bounded context, fails closed
on LLM error, and meters its single call into the cost ledger (stage tag ``classify``).
"""

from __future__ import annotations

from bayesify.core import config
from bayesify.core.context import build_user
from bayesify.core.prompts import CLASSIFY_SYSTEM
from bayesify.core.schema import CostLedgerEntry, Evidence, PaperClass, ParsedDoc
from bayesify.llm import LLMClient, call_with_policy, ledger_entry


def classify(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str = config.SCREEN_MODEL,
) -> tuple[PaperClass, CostLedgerEntry]:
    """Classify the paper type. Returns the ``PaperClass`` and its cost entry; raises ``LLMError``
    (fail closed) if the cheap-model call cannot complete."""
    user = build_user(parsed, evidence)
    response = call_with_policy(
        client, model=model, system=CLASSIFY_SYSTEM, user=user, schema=PaperClass, max_tokens=600
    )
    return response.parsed, ledger_entry("classify", response)
