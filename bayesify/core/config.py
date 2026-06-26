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

ANTHROPIC_JUDGE_MODEL = "claude-opus-4-8"
ANTHROPIC_SCREEN_MODEL = "claude-opus-4-8"
OPENAI_JUDGE_MODEL = "gpt-5.5"
OPENAI_SCREEN_MODEL = "gpt-5.4-mini"


def openalex_api_key() -> str | None:
    return os.environ.get("OPENALEX_API_KEY") or None


def unpaywall_email() -> str | None:
    return os.environ.get("UNPAYWALL_EMAIL") or None


def anthropic_api_key() -> str | None:
    """The Anthropic API key for the LLM stages (screen/classify/assess). Absent → the app keeps
    full mode on the stub engine and the eval harness skips; local-only mode never needs it."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def openai_api_key() -> str | None:
    """The OpenAI API key for the LLM stages when ``BAYESIFY_LLM_BACKEND=openai``."""
    return os.environ.get("OPENAI_API_KEY") or None


def mongodb_uri() -> str:
    """MongoDB connection URI for report persistence scaffolding."""
    return (
        os.environ.get("BAYESIFY_MONGODB_URI")
        or os.environ.get("MONGODB_URI")
        or "mongodb://localhost:27017"
    )


def mongodb_database() -> str:
    """MongoDB database name for report persistence scaffolding."""
    return (
        os.environ.get("BAYESIFY_MONGODB_DB")
        or os.environ.get("MONGODB_DATABASE")
        or os.environ.get("MONGO_DATABASE")
        or "bayesify"
    )


def mongodb_server_api() -> str | None:
    """MongoDB Stable API version for hosted clusters such as Atlas."""
    value = os.environ.get("BAYESIFY_MONGODB_SERVER_API", "1").strip()
    return None if value.lower() in ("", "0", "false", "no") else value


def mongodb_autostart() -> bool:
    """Whether the API may start a local ``mongod`` process when using a localhost URI."""
    return os.environ.get("BAYESIFY_MONGODB_AUTOSTART", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def claude_code_available() -> bool:
    """True if the Claude Agent SDK can run on the local Claude Code session: the ``claude`` CLI is
    on PATH and ``claude_agent_sdk`` is importable. This is the no-API-key path that bills the
    user's Claude subscription (Pro/Max)."""
    if shutil.which("claude") is None:
        return False
    return importlib.util.find_spec("claude_agent_sdk") is not None


def llm_backend() -> str:
    """Select the LLM backend for full mode.

    Returns ``"agent-sdk"`` (Claude subscription), ``"api"`` (Anthropic API), ``"openai"``
    (OpenAI API), or ``"none"`` (stub fallback). Override with ``BAYESIFY_LLM_BACKEND``.
    """
    override = (os.environ.get("BAYESIFY_LLM_BACKEND") or "").strip().lower()
    aliases = {
        "anthropic": "api",
        "anthropic-api": "api",
        "claude-api": "api",
        "openai-api": "openai",
    }
    override = aliases.get(override, override)
    if override in ("agent-sdk", "api", "openai", "none"):
        return override
    if claude_code_available():
        return "agent-sdk"
    if anthropic_api_key():
        return "api"
    if openai_api_key():
        return "openai"
    return "none"


def _default_judge_model() -> str:
    return OPENAI_JUDGE_MODEL if llm_backend() == "openai" else ANTHROPIC_JUDGE_MODEL


def _default_screen_model() -> str:
    return OPENAI_SCREEN_MODEL if llm_backend() == "openai" else ANTHROPIC_SCREEN_MODEL


JUDGE_MODEL: str = os.environ.get("BAYESIFY_JUDGE_MODEL") or _default_judge_model()
SCREEN_MODEL: str = os.environ.get("BAYESIFY_SCREEN_MODEL") or _default_screen_model()


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
    "gpt-5.5": ModelPrice(input_per_mtok=5.0, output_per_mtok=30.0),
    "gpt-5.4": ModelPrice(input_per_mtok=2.5, output_per_mtok=15.0),
    "gpt-5.4-mini": ModelPrice(input_per_mtok=0.75, output_per_mtok=4.5),
    "gpt-5.4-nano": ModelPrice(input_per_mtok=0.2, output_per_mtok=1.25),
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
