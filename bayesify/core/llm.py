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
  ``CostLedgerEntry`` priced via :mod:`bayesify.core.config` (the C6 cost ledger).

The concrete ``AnthropicClient`` lands with the eval harness (M4 slice 4); this module ships the
interface, the in-memory fake, and the policy/cost helpers so screen/classify can be built and
tested against the contract first.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from bayesify.core import config
from bayesify.core.schema import CostLedgerEntry


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


# --- real Anthropic client ------------------------------------------------------------------------


class AnthropicClient:
    """The real ``LLMClient`` backed by the Anthropic SDK. The SDK is imported lazily so importing
    this module stays cheap and core-light; only an actual call needs ``anthropic`` installed.

    Structured output uses ``messages.parse(..., output_format=schema)`` (per the claude-api
    reference), so the validated pydantic instance comes back as ``response.parsed_output``. API
    errors are mapped to ``LLMTransientError`` (connection/timeout/5xx/429 — retryable) or terminal
    ``LLMError`` (4xx and unparseable output), so ``call_with_policy`` retries the right ones.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._sdk_client = None  # cached anthropic.Anthropic (or a fake injected in tests)

    def _client(self):
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
                raise LLMTransientError(str(exc)) from exc  # connection/timeout/overloaded → retry
            raise LLMError(str(exc)) from exc  # 4xx (bad request/auth) → fail closed

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


# --- Claude Agent SDK client (runs on a Claude subscription, no API key) --------------------------


def _run_sync(coro_factory):
    """Run an async coroutine to completion from sync code. Safe in a worker thread (no running
    loop → ``asyncio.run``); if a loop is already running, run in a fresh thread."""
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


def _usage_tokens(usage: object) -> tuple[int, int]:
    def get(key: str) -> int:
        raw = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, 0)
        return int(raw or 0)

    if usage is None:
        return 0, 0
    return get("input_tokens"), get("output_tokens")


def _brace_json(text: str) -> dict | None:
    """Best-effort: parse the first balanced ``{...}`` object from text (fallback when the CLI did
    not return schema-bound ``structured_output``)."""
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


class AgentSDKClient:
    """An ``LLMClient`` backed by the **Claude Agent SDK** — runs on the user's Claude Code session,
    so it bills their **subscription** (Pro/Max) instead of API credits. Requires the ``claude`` CLI
    installed and logged in (``claude login``); the SDK is imported lazily.

    Mirrors the proven single-turn, tool-free, schema-bound pattern: ``output_format`` json-schema →
    ``ResultMessage.structured_output``, with a brace-matching text fallback. **Note:** if
    ``ANTHROPIC_API_KEY`` is set, the Agent SDK bills *that* key (API), not the subscription — unset
    it to use the plan.
    """

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
            import claude_agent_sdk as sdk
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise LLMError("the 'claude-agent-sdk' package is not installed") from exc

        # The CLI's schema-bound `output_format` needs an extra turn and some CLI versions reject
        # it, so by default we prompt for JSON and parse it ourselves (the hormuz-proven path).
        # max_turns has headroom for a thinking turn; allowed_tools=[] stops it looping. Opt into
        # native output_format with BAYESIFY_AGENT_OUTPUT_FORMAT=1.
        use_output_format = os.environ.get("BAYESIFY_AGENT_OUTPUT_FORMAT", "").strip().lower() in (
            "1", "true", "yes",
        )
        opts_kwargs: dict = dict(
            system_prompt=system,
            model=model,
            allowed_tools=[],
            max_turns=4,
            permission_mode="bypassPermissions",
        )
        prompt = user
        if use_output_format:
            opts_kwargs["output_format"] = {
                "type": "json_schema",
                "schema": schema.model_json_schema(),
            }
        else:
            prompt = (
                f"{user}\n\nRespond with ONLY a JSON object matching this JSON Schema — no prose, "
                f"no markdown fences:\n{json.dumps(schema.model_json_schema())}"
            )
        options = sdk.ClaudeAgentOptions(**opts_kwargs)

        async def _collect():
            chunks: list[str] = []
            result: dict = {"structured": None, "in": 0, "out": 0, "error": None}
            async for msg in sdk.query(prompt=prompt, options=options):
                if hasattr(msg, "structured_output") or hasattr(msg, "total_cost_usd"):
                    so = getattr(msg, "structured_output", None)
                    if isinstance(so, dict):
                        result["structured"] = so
                    result["in"], result["out"] = _usage_tokens(getattr(msg, "usage", None))
                    if getattr(msg, "is_error", False):
                        result["error"] = getattr(msg, "result", None) or "agent SDK error"
                elif hasattr(msg, "content"):
                    for block in msg.content:
                        text = getattr(block, "text", None)
                        if isinstance(text, str):
                            chunks.append(text)
            return "".join(chunks).strip(), result

        try:
            text, result = _run_sync(_collect)
        except Exception as exc:  # CLI launch / connection problems → retryable
            raise LLMTransientError(str(exc)) from exc

        if result["error"]:
            raise LLMError(f"agent SDK error: {result['error']}")
        # Parse/validation failures are transient — a fresh attempt often yields well-formed JSON.
        data = result["structured"] if result["structured"] is not None else _brace_json(text)
        if data is None:
            raise LLMTransientError(f"agent SDK returned no parseable JSON (got: {text[:200]!r})")
        try:
            parsed = schema.model_validate(data)
        except ValidationError as exc:
            raise LLMTransientError(f"agent SDK output failed schema validation: {exc}") from exc
        return LLMResponse(
            parsed=parsed, model=model, input_tokens=result["in"], output_tokens=result["out"]
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
