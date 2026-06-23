"""The LLM client seam (M4 slice 1): the fake, the retry/fail-closed policy, and cost metering.

No network and no API key — this is the contract screen/classify build against.
"""

from __future__ import annotations

import sys

import pytest
from pydantic import BaseModel

from bayesify.core.llm import (
    FakeLLMClient,
    LLMError,
    LLMResponse,
    LLMTransientError,
    call_with_policy,
    ledger_entry,
)


class _Answer(BaseModel):
    label: str


def _call(client, **over):
    kw = dict(model="claude-haiku-4-5", system="sys", user="usr", schema=_Answer)
    kw.update(over)
    return call_with_policy(client, **kw)


# --- fake client ----------------------------------------------------------------------------------


def test_fake_returns_scripted_response_and_records_call() -> None:
    client = FakeLLMClient(_Answer(label="yes"))
    resp = client.complete(model="claude-haiku-4-5", system="s", user="u", schema=_Answer)
    assert isinstance(resp, LLMResponse)
    assert resp.parsed.label == "yes"
    assert resp.model == "claude-haiku-4-5"
    assert client.calls[0]["schema"] == "_Answer" and client.calls[0]["user"] == "u"


def test_fake_exhausted_raises() -> None:
    client = FakeLLMClient()  # nothing scripted
    with pytest.raises(LLMError):
        client.complete(model="claude-haiku-4-5", system="s", user="u", schema=_Answer)


# --- retry / fail-closed policy -------------------------------------------------------------------


def test_policy_retries_transient_then_succeeds() -> None:
    client = FakeLLMClient(LLMTransientError("blip"), _Answer(label="partial"))
    resp = _call(client)  # default retries=2 → one transient tolerated
    assert resp.parsed.label == "partial"
    assert len(client.calls) == 2  # failed once, then succeeded


def test_policy_fails_closed_after_exhausting_retries() -> None:
    client = FakeLLMClient(
        LLMTransientError("1"), LLMTransientError("2"), LLMTransientError("3"), _Answer(label="yes")
    )
    with pytest.raises(LLMError):
        _call(client, retries=2)  # 3 attempts, all transient → raise, never a guess
    assert len(client.calls) == 3


def test_policy_does_not_retry_terminal_error() -> None:
    client = FakeLLMClient(LLMError("malformed and unrepairable"), _Answer(label="yes"))
    with pytest.raises(LLMError):
        _call(client)
    assert len(client.calls) == 1  # terminal error → fail closed immediately, no retry


# --- cost ledger ----------------------------------------------------------------------------------


def test_ledger_entry_prices_usage() -> None:
    client = FakeLLMClient((_Answer(label="yes"), 1_000_000, 1_000_000))
    resp = _call(client)
    entry = ledger_entry("screen", resp)
    assert entry.stage == "screen" and entry.model == "claude-haiku-4-5"
    assert entry.input_tokens == 1_000_000 and entry.output_tokens == 1_000_000
    # haiku pricing: $1/Mtok in + $5/Mtok out = $6.00 for 1M each
    assert entry.cost_usd == pytest.approx(6.0)


def test_ledger_entry_carries_step_and_pass_labels() -> None:
    resp = _call(FakeLLMClient(_Answer(label="yes")))
    entry = ledger_entry("classify", resp, step_id="S4", pass_label="primary")
    assert entry.step_id == "S4" and entry.pass_label == "primary"


def test_ledger_entry_unpriced_model_fails_loud() -> None:
    resp = LLMResponse(
        parsed=_Answer(label="x"), model="not-a-pinned-model", input_tokens=1, output_tokens=1
    )
    with pytest.raises(KeyError):
        ledger_entry("screen", resp)


# --- real AnthropicClient (SDK injected; no network) ----------------------------------------------


def test_anthropic_client_maps_parsed_output_and_usage() -> None:
    from types import SimpleNamespace

    from bayesify.core.llm import AnthropicClient

    class _Msgs:
        def parse(self, **kw):
            return SimpleNamespace(
                parsed_output=_Answer(label="yes"),
                usage=SimpleNamespace(input_tokens=11, output_tokens=4),
            )

    client = AnthropicClient(api_key="sk-fake")
    client._sdk_client = SimpleNamespace(messages=_Msgs())  # bypass real SDK construction
    resp = client.complete(model="claude-haiku-4-5", system="s", user="u", schema=_Answer)
    assert resp.parsed.label == "yes" and resp.input_tokens == 11 and resp.output_tokens == 4


def test_openai_client_maps_parsed_output_and_usage(monkeypatch) -> None:
    from types import SimpleNamespace

    from bayesify.llm import OpenAIClient

    calls: dict = {}

    class APIError(Exception):
        status_code = 500

    class _Responses:
        def parse(self, **kw):
            calls.update(kw)
            return SimpleNamespace(
                output_parsed=_Answer(label="yes"),
                usage=SimpleNamespace(input_tokens=13, output_tokens=7),
            )

    class _OpenAI:
        def __init__(self, *, api_key=None):
            self.api_key = api_key
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI, APIError=APIError))
    client = OpenAIClient(api_key="sk-fake")
    resp = client.complete(model="gpt-5.4-mini", system="s", user="u", schema=_Answer)
    assert resp.parsed.label == "yes"
    assert resp.input_tokens == 13 and resp.output_tokens == 7
    assert calls["text_format"] is _Answer
    assert calls["store"] is False


def test_factory_builds_openai_client() -> None:
    from bayesify.llm import OpenAIClient, make_llm_client

    assert isinstance(make_llm_client("openai"), OpenAIClient)


# --- AgentSDKClient (claude-agent-sdk query monkeypatched; no CLI/session) ---


def _agent_complete(monkeypatch, messages):
    import claude_agent_sdk as sdk

    from bayesify.core.llm import AgentSDKClient

    async def fake_query(*, prompt, options):
        for m in messages:
            yield m

    monkeypatch.setattr(sdk, "query", fake_query)
    return AgentSDKClient().complete(
        model="claude-haiku-4-5", system="s", user="u", schema=_Answer
    )


def test_agentsdk_maps_structured_output(monkeypatch) -> None:
    from types import SimpleNamespace

    resp = _agent_complete(
        monkeypatch,
        [
            SimpleNamespace(content=[SimpleNamespace(text="(prose, ignored)")]),
            SimpleNamespace(
                structured_output={"label": "yes"},
                usage={"input_tokens": 12, "output_tokens": 4},
                is_error=False,
                result=None,
                total_cost_usd=0.0,
            ),
        ],
    )
    assert resp.parsed.label == "yes" and resp.input_tokens == 12 and resp.output_tokens == 4


def test_agentsdk_falls_back_to_brace_json(monkeypatch) -> None:
    from types import SimpleNamespace

    resp = _agent_complete(
        monkeypatch,
        [
            SimpleNamespace(content=[SimpleNamespace(text='here: {"label": "no"} done')]),
            SimpleNamespace(usage=None, is_error=False, result=None, total_cost_usd=0.0),
        ],
    )
    assert resp.parsed.label == "no"


def test_agentsdk_raises_on_error(monkeypatch) -> None:
    from types import SimpleNamespace

    with pytest.raises(LLMError):
        _agent_complete(
            monkeypatch,
            [SimpleNamespace(structured_output=None, usage=None, is_error=True, result="boom",
                             total_cost_usd=0.0)],
        )
