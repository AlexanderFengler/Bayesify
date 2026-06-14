"""Stage 4 + 5 composition: relevance gate, then (only if relevant) the paper-type classifier.

The C6 cost ordering lives here: screen runs first so a ``no`` short-circuits and never pays for the
classify call. Pure over the LLM-client seam, so it is unit-tested with the fake and reused by the
API job loop (and Phase 3's batch pipeline) unchanged.
"""

from __future__ import annotations

from veribayes.core import config
from veribayes.core.classify import classify
from veribayes.core.llm import LLMClient
from veribayes.core.schema import (
    CostLedgerEntry,
    Evidence,
    PaperClass,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
)
from veribayes.core.screen import screen


def screen_and_classify(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str = config.SCREEN_MODEL,
) -> tuple[Relevance, PaperClass | None, list[CostLedgerEntry]]:
    """Run the relevance gate, then the classifier only if the paper is not ``no``.

    Returns ``(relevance, paper_class_or_None, cost_entries)``. ``paper_class`` is ``None`` exactly
    when the gate short-circuited (``relevance.label == no``), in which case classify was not called
    and ``cost_entries`` holds the single screen entry.
    """
    relevance, screen_cost = screen(parsed, evidence, client=client, model=model)
    if relevance.label is RelevanceLabel.no:
        return relevance, None, [screen_cost]
    paper_class, classify_cost = classify(parsed, evidence, client=client, model=model)
    return relevance, paper_class, [screen_cost, classify_cost]
