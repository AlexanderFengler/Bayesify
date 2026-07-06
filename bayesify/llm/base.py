"""Shared LLM interface, retry policy, token accounting, and cost ledger helpers."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from bayesify.core.schema import CostLedgerEntry
from bayesify.llm import config as llm_config


class LLMError(Exception):
    """Terminal LLM failure; callers fail closed rather than guessing."""


class LLMTransientError(LLMError):
    """A retryable failure such as a timeout, overload, 429, or malformed transient output."""


@dataclass(frozen=True)
class LLMResponse[T: BaseModel]:
    """A validated structured response plus usage for the cost ledger."""

    parsed: T
    model: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    """Provider-neutral contract used by screen/classify/assess."""

    def complete[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 1024,
    ) -> LLMResponse[T]: ...


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
    """Call an LLM client with bounded retries on transient failures."""
    last: LLMError | None = None
    for _attempt in range(retries + 1):
        try:
            return client.complete(
                model=model, system=system, user=user, schema=schema, max_tokens=max_tokens
            )
        except LLMTransientError as exc:
            last = exc
            continue
    raise LLMError(f"LLM call failed after {retries + 1} attempt(s): {last}") from last


def ledger_entry(
    stage: str,
    response: LLMResponse,
    *,
    step_id: str | None = None,
    pass_label: str | None = None,
) -> CostLedgerEntry:
    """Price a response into the engine cost ledger."""
    cost = llm_config.estimate_cost(response.model, response.input_tokens, response.output_tokens)
    return CostLedgerEntry(
        stage=stage,
        step_id=step_id,
        pass_label=pass_label,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=cost,
    )


def run_sync(coro_factory):
    """Run an async coroutine from sync code, including when a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    import threading

    box: dict = {}

    def _runner() -> None:
        box["value"] = asyncio.run(coro_factory())

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()
    return box["value"]


def usage_tokens(usage: object) -> tuple[int, int]:
    """Read provider usage objects that expose either response or completion token names."""

    def get(*keys: str) -> int:
        for key in keys:
            raw = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
            if raw is not None:
                return int(raw or 0)
        return 0

    if usage is None:
        return 0, 0
    return get("input_tokens", "prompt_tokens"), get("output_tokens", "completion_tokens")


def brace_json(text: str) -> dict | None:
    """Best-effort parse of the first balanced JSON object from a text response."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start : i + 1])
                except ValueError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None

