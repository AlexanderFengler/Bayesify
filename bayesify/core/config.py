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

import importlib.util
import os
import shutil
from dataclasses import dataclass

# --- OA-provider config (M2 fetcher; verified terms 2026-06-13) ---
# OpenAlex moved to a metered API in Feb 2026: a free API key is recommended (single-DOI lookups
# stay free). Unpaywall requires a contact email parameter on every call. Both read from the
# environment so no secret is hard-coded; absence is tolerated (the fetcher skips that provider).


def openalex_api_key() -> str | None:
    return os.environ.get("OPENALEX_API_KEY") or None


def unpaywall_email() -> str | None:
    return os.environ.get("UNPAYWALL_EMAIL") or None


def anthropic_api_key() -> str | None:
    """The Anthropic API key for the LLM stages (screen/classify/assess). Absent → the app keeps
    full mode on the stub engine and the eval harness skips; local-only mode never needs it."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def claude_code_available() -> bool:
    """True if the Claude Agent SDK can run on the local Claude Code session: the ``claude`` CLI is
    on PATH and ``claude_agent_sdk`` is importable. This is the no-API-key path that bills the
    user's Claude subscription (Pro/Max)."""
    if shutil.which("claude") is None:
        return False
    return importlib.util.find_spec("claude_agent_sdk") is not None


def llm_backend() -> str:
    """Which backend full mode uses: ``"agent-sdk"`` (Claude subscription via Claude Code, no key),
    ``"api"`` (``ANTHROPIC_API_KEY``, pay-as-you-go), or ``"none"`` (→ stub fallback).

    Default preference is **subscription-first** (mirrors the hormuz translator): the Agent SDK when
    the ``claude`` CLI is available, else the API key. Override with ``BAYESIFY_LLM_BACKEND``.
    Caveat: the Agent SDK bills ``ANTHROPIC_API_KEY`` if it is set — unset it to use the plan,
    or set ``BAYESIFY_LLM_BACKEND=agent-sdk``."""
    override = os.environ.get("BAYESIFY_LLM_BACKEND")
    if override in ("agent-sdk", "api", "none"):
        return override
    if claude_code_available():
        return "agent-sdk"
    if anthropic_api_key():
        return "api"
    return "none"


# --- Pinned models (G1) ---------------------------------------------------------------------------
# Judge: the most capable model, for nuanced per-step methodology judgment (assess stage).
JUDGE_MODEL: str = "claude-opus-4-8"
# Screen/classify model. During M4 bring-up this is Opus 4.8 — guaranteed available on a Max plan
# via the Agent SDK, avoiding tier-availability surprises while we validate the subscription path.
# It can move back to the cheap Haiku tier (the C6 gate) later. Override: BAYESIFY_SCREEN_MODEL.
SCREEN_MODEL: str = os.environ.get("BAYESIFY_SCREEN_MODEL") or "claude-opus-4-8"


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
