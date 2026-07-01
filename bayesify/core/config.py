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
from pathlib import Path


class ConfigError(RuntimeError):
    """Required runtime configuration is missing or invalid."""


def load_env_file() -> None:
    """Load ``bayesify.env`` without overriding variables already set by the process/host."""
    path = Path(os.environ.get("BAYESIFY_ENV_FILE", "bayesify.env"))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip().removeprefix("export ").lstrip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


load_env_file()


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


def trusted_tokens() -> dict[str, str]:
    """Shared-secret token -> author name for **trusted** reviewers, parsed from
    ``BAYESIFY_TRUSTED_TOKENS`` (e.g. ``"alice:tok1,bob:tok2"``). A disagreement carrying one of
    these tokens may affect production grading; any other is advisory-only. Unset = no trusted
    reviewers. A small-team shared secret (assume HTTPS), not per-user crypto."""
    tokens: dict[str, str] = {}
    for entry in os.environ.get("BAYESIFY_TRUSTED_TOKENS", "").split(","):
        name, sep, token = entry.partition(":")
        name, token = name.strip(), token.strip()
        if sep and name and token:
            tokens[token] = name
    return tokens


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


def assess_concurrency() -> int:
    """Worker threads for the assess stage's per-step judge/refute fan-out.

    The per-step chains are independent, so this only overlaps the I/O-bound LLM calls to cut
    wall-clock — call count, tokens, and outputs are unchanged. Defaults are backend-aware: the
    agent-SDK (Claude subscription) path handled parallel ``claude`` sessions well in testing, the
    rate-limited HTTP backends use a lower default, and ``none`` stays serial. Override with
    ``BAYESIFY_ASSESS_CONCURRENCY``; clamped to >= 1 (1 = sequential).
    """
    default = {"api": 4, "openai": 4, "agent-sdk": 6}.get(llm_backend(), 1)
    try:
        return max(1, int(os.environ.get("BAYESIFY_ASSESS_CONCURRENCY", str(default))))
    except ValueError:
        return default


def grading_strategy() -> str:
    """How full-mode grading should call the LLM.

    ``"per-step"`` is the original path: one judge call per applicable rubric step plus one refuter
    call per negative finding. ``"batch"`` keeps the same screen/classify calls, then judges all
    applicable steps in one call and refutes all negative findings in one call.
    """
    value = os.environ.get("BAYESIFY_GRADING_STRATEGY", "per-step").strip().lower()
    aliases = {
        "batched": "batch",
        "batch-assess": "batch",
        "batch_assess": "batch",
        "classic": "per-step",
        "per_step": "per-step",
        "perstep": "per-step",
    }
    value = aliases.get(value, value)
    return value if value in ("per-step", "batch") else "per-step"


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} must be set; model selection is env-only")
    return value


def judge_model() -> str:
    return _required_env("BAYESIFY_JUDGE_MODEL")


def screen_model() -> str:
    return _required_env("BAYESIFY_SCREEN_MODEL")


def classify_model() -> str:
    return _required_env("BAYESIFY_CLASSIFY_MODEL")


def refuter_model() -> str:
    return _required_env("BAYESIFY_REFUTER_MODEL")


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
    return tuple(sorted({judge_model(), screen_model(), classify_model(), refuter_model()}))


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a call. Raises ``KeyError`` for an unpriced model (fail loud — an
    unpriced model usually means an unpinned one, which G1 forbids)."""
    price = MODEL_PRICING[model]
    return (
        input_tokens / 1_000_000 * price.input_per_mtok
        + output_tokens / 1_000_000 * price.output_per_mtok
    )
