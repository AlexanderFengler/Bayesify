"""Provider-neutral LLM clients and helpers.

The public seam lives here rather than in ``veribayes.core`` so additional providers can be added
without turning the core package into a provider grab bag.
"""

from veribayes.llm.anthropic import AnthropicClient
from veribayes.llm.base import (
    LLMClient,
    LLMError,
    LLMResponse,
    LLMTransientError,
    call_with_policy,
    ledger_entry,
)
from veribayes.llm.claude_agent import AgentSDKClient
from veribayes.llm.factory import make_llm_client
from veribayes.llm.fake import FakeLLMClient
from veribayes.llm.openai import OpenAIClient

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
