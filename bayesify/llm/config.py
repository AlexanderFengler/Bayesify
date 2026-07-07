"""LLM provider selection, model pins, and token pricing."""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass


class LLMConfigError(RuntimeError):
    """Required LLM runtime configuration is missing or invalid."""


def anthropic_api_key() -> str | None:
    """The Anthropic API key for the LLM stages."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def openai_api_key() -> str | None:
    """The OpenAI API key for the LLM stages when ``BAYESIFY_LLM_BACKEND=openai``."""
    return os.environ.get("OPENAI_API_KEY") or None


def claude_code_available() -> bool:
    """True when the local Claude Code session can run the Claude Agent SDK backend."""
    if shutil.which("claude") is None:
        return False
    return importlib.util.find_spec("claude_agent_sdk") is not None


def llm_backend() -> str:
    """Select the LLM backend for full mode."""
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


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise LLMConfigError(f"{name} must be set; model selection is env-only")
    return value


def judge_model() -> str:
    return _required_env("BAYESIFY_JUDGE_MODEL")


def screen_model() -> str:
    return _required_env("BAYESIFY_SCREEN_MODEL")


def classify_model() -> str:
    return _required_env("BAYESIFY_CLASSIFY_MODEL")


def refuter_model() -> str:
    return _required_env("BAYESIFY_REFUTER_MODEL")


def model_ids() -> tuple[str, ...]:
    """The pinned model IDs, sorted and folded into ``engine_version``."""
    return tuple(sorted({judge_model(), screen_model(), classify_model(), refuter_model()}))


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens."""

    input_per_mtok: float
    output_per_mtok: float


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


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a call. Raises ``KeyError`` for an unpriced model."""
    price = MODEL_PRICING[model]
    return (
        input_tokens / 1_000_000 * price.input_per_mtok
        + output_tokens / 1_000_000 * price.output_per_mtok
    )
