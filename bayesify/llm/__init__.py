"""Provider-neutral LLM clients and helpers.

The public seam lives here rather than in ``bayesify.core`` so additional providers can be added
without turning the core package into a provider grab bag.
"""

from bayesify.llm.anthropic import AnthropicClient
from bayesify.llm.base import (
    LLMClient,
    LLMError,
    LLMResponse,
    LLMTransientError,
    call_with_policy,
    ledger_entry,
)
from bayesify.llm.claude_agent import AgentSDKClient
from bayesify.llm.factory import make_llm_client
from bayesify.llm.fake import FakeLLMClient
from bayesify.llm.openai import OpenAIClient

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

