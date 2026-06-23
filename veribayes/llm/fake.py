"""Scripted in-memory LLM client for tests."""

from __future__ import annotations

from pydantic import BaseModel

from veribayes.llm.base import LLMError, LLMResponse


class FakeLLMClient:
    """A network-free LLM client with canned responses."""

    def __init__(
        self,
        *responses: object,
        input_tokens: int = 100,
        output_tokens: int = 20,
    ) -> None:
        self._responses: list[object] = list(responses)
        self._default_in = input_tokens
        self._default_out = output_tokens
        self.calls: list[dict] = []

    def complete[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 1024,
    ) -> LLMResponse[T]:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "user": user,
                "schema": schema.__name__,
                "max_tokens": max_tokens,
            }
        )
        if not self._responses:
            raise LLMError("FakeLLMClient: no more scripted responses")
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, tuple):
            parsed, in_tok, out_tok = item
            return LLMResponse(
                parsed=parsed, model=model, input_tokens=in_tok, output_tokens=out_tok
            )
        return LLMResponse(
            parsed=item, model=model, input_tokens=self._default_in, output_tokens=self._default_out
        )
