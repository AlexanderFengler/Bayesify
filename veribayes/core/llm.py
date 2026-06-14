"""The LLM client seam — the keystone every LLM stage (screen, classify, assess) reuses.

A thin, **fakeable** interface so the pipeline depends on a `Protocol`, not the Anthropic SDK: unit
tests inject a ``FakeLLMClient`` with canned structured responses (no network, no API key), and real
cheap/judge-model calls go through ``AnthropicClient`` only in the eval harness and the running app.
Structured output is a pydantic ``schema`` the model must fill, so callers get a validated object,
never raw text to parse.

Two cross-cutting guarantees the pipeline relies on (d-screen-classify.md):
- **Fail closed.** A failed call raises a typed ``LLMError`` after bounded retries — it is never
  silently defaulted to a guessed answer. ``call_with_policy`` owns the retry/fail-closed policy.
- **Metered.** Every response carries token usage; ``ledger_entry`` turns it into a
  ``CostLedgerEntry`` priced via :mod:`veribayes.core.config` (the C6 cost ledger).

The concrete ``AnthropicClient`` lands with the eval harness (M4 slice 4); this module ships the
interface, the in-memory fake, and the policy/cost helpers so screen/classify can be built and
tested against the contract first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from veribayes.core import config
from veribayes.core.schema import CostLedgerEntry


class LLMError(Exception):
    """Terminal LLM failure — the caller must fail closed (never a defaulted/guessed answer)."""


class LLMTransientError(LLMError):
    """A retryable failure (network blip, 5xx, timeout). ``call_with_policy`` retries these."""


@dataclass(frozen=True)
class LLMResponse[T: BaseModel]:
    """A validated structured response plus the usage needed for the cost ledger."""

    parsed: T
    model: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    """The seam screen/classify/assess code against. Implementations return a validated ``schema``
    instance plus token usage, or raise ``LLMError`` / ``LLMTransientError``."""

    def complete[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 1024,
    ) -> LLMResponse[T]: ...


# --- policy ---------------------------------------------------------------------------------------


def call_with_policy[T: BaseModel](
    client: LLMClient,
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    max_tokens: int = 1024,
    retries: int = 2,
) -> LLMResponse[T]:
    """Call ``client.complete`` with bounded retries on transient failures, **failing closed**: once
    the retries are exhausted (or on any terminal ``LLMError``) it raises rather than returning a
    guess. ``retries`` is the number of *extra* attempts beyond the first."""
    last: LLMError | None = None
    for _attempt in range(retries + 1):
        try:
            return client.complete(
                model=model, system=system, user=user, schema=schema, max_tokens=max_tokens
            )
        except LLMTransientError as exc:
            last = exc
            continue
        # A terminal LLMError (e.g. unrepairable malformed output) is not retried — fail closed now.
    raise LLMError(f"LLM call failed after {retries + 1} attempt(s): {last}") from last


# --- cost ledger ----------------------------------------------------------------------------------


def ledger_entry(
    stage: str,
    response: LLMResponse,
    *,
    step_id: str | None = None,
    pass_label: str | None = None,
) -> CostLedgerEntry:
    """Price a response into a ``CostLedgerEntry`` (C6). ``estimate_cost`` raises for an unpriced —
    i.e. unpinned (G1) — model, so an accidental model swap fails loud."""
    cost = config.estimate_cost(response.model, response.input_tokens, response.output_tokens)
    return CostLedgerEntry(
        stage=stage,
        step_id=step_id,
        pass_label=pass_label,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=cost,
    )


# --- in-memory fake (tests) -----------------------------------------------------------------------


class FakeLLMClient:
    """A scripted, network-free ``LLMClient`` for unit tests.

    Pass the responses each ``complete`` call should yield, in order. An item may be: a pydantic
    model (returned with the default token counts); a ``(model_instance, in_tok, out_tok)`` tuple
    (explicit usage, for cost tests); or an ``Exception`` instance (raised, for retry/fail-closed
    tests). Every call's kwargs are recorded on ``.calls`` for assertions.
    """

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
