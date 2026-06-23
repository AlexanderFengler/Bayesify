"""Factory for choosing the configured LLM provider."""

from __future__ import annotations

from veribayes.core import config
from veribayes.llm.anthropic import AnthropicClient
from veribayes.llm.base import LLMClient, LLMError
from veribayes.llm.claude_agent import AgentSDKClient
from veribayes.llm.openai import OpenAIClient


def make_llm_client(backend: str | None = None) -> LLMClient:
    """Build the configured provider client for full-mode jobs."""
    selected = backend or config.llm_backend()
    if selected == "agent-sdk":
        return AgentSDKClient()
    if selected == "api":
        return AnthropicClient(api_key=config.anthropic_api_key())
    if selected == "openai":
        return OpenAIClient(api_key=config.openai_api_key())
    raise LLMError(f"no LLM client is configured for backend {selected!r}")
