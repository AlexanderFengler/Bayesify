"""Anthropic API implementation of the provider-neutral LLM client."""

from __future__ import annotations

import threading

from pydantic import BaseModel

from bayesify.llm.base import LLMError, LLMResponse, LLMTransientError


class AnthropicClient:
    """LLM client backed by the Anthropic SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._sdk_client = None
        self._init_lock = threading.Lock()

    def _client(self):
        # Double-checked lock: the client is shared across the parallel assess fan-out, so the
        # lazy init must not race (two threads building, one SDK client silently discarded).
        if self._sdk_client is None:
            with self._init_lock:
                if self._sdk_client is None:
                    import anthropic

                    self._sdk_client = anthropic.Anthropic(api_key=self._api_key)
        return self._sdk_client

    def complete[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 1024,
    ) -> LLMResponse[T]:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise LLMError("the 'anthropic' SDK is not installed") from exc

        try:
            response = self._client().messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        except anthropic.APIError as exc:
            status = getattr(exc, "status_code", None)
            if status is None or status >= 500 or status == 429:
                raise LLMTransientError(str(exc)) from exc
            raise LLMError(str(exc)) from exc

        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("structured output did not parse against the schema")
        usage = response.usage
        return LLMResponse(
            parsed=parsed,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

