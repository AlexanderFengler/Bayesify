"""Compatibility re-export for the LLM seam.

New code should import from :mod:`bayesify.llm`. This module remains so older tests, scripts, and
downstream imports of ``bayesify.core.llm`` keep working while the provider layer grows.
"""

from bayesify.llm import (
    AgentSDKClient,
    AnthropicClient,
    FakeLLMClient,
    LLMClient,
    LLMError,
    LLMResponse,
    LLMTransientError,
    OpenAIClient,
    call_with_policy,
    ledger_entry,
    make_llm_client,
)

__all__ = [
    "AgentSDKClient",
    "AnthropicClient",
    "FakeLLMClient",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "LLMTransientError",
    "OpenAIClient",
    "call_with_policy",
    "ledger_entry",
    "make_llm_client",
]
