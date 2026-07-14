"""Core analysis-engine configuration."""

from __future__ import annotations

import os

from bayesify.llm import config as llm_config


class ConfigError(RuntimeError):
    """Required runtime configuration is missing or invalid."""


def assess_concurrency() -> int:
    """Worker threads for the assess stage's per-step judge/refute fan-out."""
    default = {"api": 4, "openai": 4, "agent-sdk": 6}.get(llm_config.llm_backend(), 1)
    try:
        return max(1, int(os.environ.get("BAYESIFY_ASSESS_CONCURRENCY", str(default))))
    except ValueError:
        return default


def grading_strategy() -> str:
    """How full-mode grading should call the LLM."""
    value = os.environ.get("BAYESIFY_GRADING_STRATEGY", "batch").strip().lower()
    aliases = {
        "batched": "batch",
        "batch-assess": "batch",
        "batch_assess": "batch",
        "classic": "per-step",
        "per_step": "per-step",
        "perstep": "per-step",
    }
    value = aliases.get(value, value)
    return value if value in ("per-step", "batch") else "batch"


def assess_context_chars() -> int:
    """Character budget for assessment-stage paper context."""
    try:
        return max(1_000, int(os.environ.get("BAYESIFY_ASSESS_CONTEXT_CHARS", "500000")))
    except ValueError:
        return 500_000


def classify_context_chars() -> int:
    """Character budget for classifier-stage paper context."""
    try:
        return max(30_000, int(os.environ.get("BAYESIFY_CLASSIFY_CONTEXT_CHARS", "200000")))
    except ValueError:
        return 200_000
