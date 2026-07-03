"""Factory for choosing the configured LLM provider."""

from __future__ import annotations

from bayesify.llm import config as llm_config
from bayesify.llm.anthropic import AnthropicClient
from bayesify.llm.base import LLMClient, LLMError
from bayesify.llm.claude_agent import AgentSDKClient
from bayesify.llm.openai import OpenAIClient


def make_llm_client(backend: str | None = None) -> LLMClient:
    """Build the configured provider client for full-mode jobs."""
    selected = backend or llm_config.llm_backend()
    if selected == "agent-sdk":
        return AgentSDKClient()
    if selected == "api":
        return AnthropicClient(api_key=llm_config.anthropic_api_key())
    if selected == "openai":
        return OpenAIClient(api_key=llm_config.openai_api_key())
    raise LLMError(f"no LLM client is configured for backend {selected!r}")

