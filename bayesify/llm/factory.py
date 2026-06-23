"""Factory for choosing the configured LLM provider."""

from __future__ import annotations

from bayesify.core import config
from bayesify.llm.anthropic import AnthropicClient
from bayesify.llm.base import LLMClient, LLMError
from bayesify.llm.claude_agent import AgentSDKClient
from bayesify.llm.openai import OpenAIClient


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

