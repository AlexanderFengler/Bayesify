"""Engine configuration — pinned model snapshots and token pricing.

Gate **G1** (2026-06-12 three-lens review): the judge model's identity must be pinned and must feed
``engine_version`` so a model change is a deliberate, cache-invalidating edit — never a silent
alias drift that detaches ``VALIDATION.md`` from the shipping instrument. This module is the single
place those IDs are declared; ``versioning.compute_engine_version`` folds ``model_ids()`` into the
engine version, and ``estimate_cost`` grounds the C6 cost ledger (and the ADV-10 cost envelope).

Model IDs and prices are the canonical Anthropic strings as of 2026-06 (per the claude-api
reference). Do **not** append date suffixes to the aliases — they are complete as-is. A model change
here MUST bump ``engine_version`` (it does, automatically) and invalidates the current
``VALIDATION.md`` per ``validation/protocol.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Pinned models (G1) ---------------------------------------------------------------------------
# Judge: the most capable model, for nuanced per-step methodology judgment (assess stage).
JUDGE_MODEL: str = "claude-opus-4-8"
# Screen tier: cheapest fast model, for the relevance gate + paper-type classifier (cheap-before-
# expensive, C6). Gates the costly assess stage.
SCREEN_MODEL: str = "claude-haiku-4-5"


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens."""

    input_per_mtok: float
    output_per_mtok: float


# Pricing as of 2026-06 (claude-api reference). Used only for the cost ledger's $ estimate; the
# authoritative spend is always the API's reported usage.
MODEL_PRICING: dict[str, ModelPrice] = {
    "claude-opus-4-8": ModelPrice(input_per_mtok=5.0, output_per_mtok=25.0),
    "claude-haiku-4-5": ModelPrice(input_per_mtok=1.0, output_per_mtok=5.0),
    # Kept for completeness / overrides; not used by default.
    "claude-sonnet-4-6": ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0),
    "claude-fable-5": ModelPrice(input_per_mtok=10.0, output_per_mtok=50.0),
}


def model_ids() -> tuple[str, ...]:
    """The pinned model IDs, sorted — folded into ``engine_version`` (G1)."""
    return tuple(sorted({JUDGE_MODEL, SCREEN_MODEL}))


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a call. Raises ``KeyError`` for an unpriced model (fail loud — an
    unpriced model usually means an unpinned one, which G1 forbids)."""
    price = MODEL_PRICING[model]
    return (
        input_tokens / 1_000_000 * price.input_per_mtok
        + output_tokens / 1_000_000 * price.output_per_mtok
    )
