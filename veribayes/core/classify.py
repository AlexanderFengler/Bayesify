"""Paper-type classifier — component d, stage 5 (runs only after a non-``no`` relevance gate).

Assigns one of ``empirical`` / ``numerical_experiment`` / ``methodological`` (primary, with an
optional evidence-supported secondary). The class drives rubric-step applicability downstream (B1):
SBC near-mandatory for methodological work, predictive checks on real data central for empirical
work. This component only *produces* the class; the applicability rules live in
``rubric/steps.yaml`` and are applied by e-assess / f-score.

Like the relevance gate it runs on the cheap model (C6) over the same bounded context, fails closed
on LLM error, and meters its single call into the cost ledger (stage tag ``classify``).
"""

from __future__ import annotations

from veribayes.core import config
from veribayes.core.context import build_user
from veribayes.core.llm import LLMClient, call_with_policy, ledger_entry
from veribayes.core.prompts import CLASSIFY_SYSTEM
from veribayes.core.schema import CostLedgerEntry, Evidence, PaperClass, ParsedDoc


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
