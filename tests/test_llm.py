"""The LLM client seam (M4 slice 1): the fake, the retry/fail-closed policy, and cost metering.

No network and no API key — this is the contract screen/classify build against.
"""

from __future__ import annotations

import sys

import pytest
from pydantic import BaseModel

from bayesify.llm import (
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


def test_ledger_entry_unpriced_model_records_zero_cost() -> None:
    # An unpriced model records a 0.0-cost entry instead of raising, so a completed (billed) run is
    # never destroyed just because we can't price the model.
    resp = LLMResponse(
        parsed=_Answer(label="x"), model="not-a-pinned-model", input_tokens=1, output_tokens=1
    )
    entry = ledger_entry("screen", resp)
    assert entry.model == "not-a-pinned-model" and entry.cost_usd == 0.0


# --- real AnthropicClient (SDK injected; no network) ----------------------------------------------


def test_anthropic_client_maps_parsed_output_and_usage() -> None:
    from types import SimpleNamespace

    from bayesify.llm import AnthropicClient

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
    # reasoning models spend max_output_tokens on reasoning too, so the client pads the answer
    # budget with headroom (here default max_tokens=1024) — otherwise a small budget starves output.
    from bayesify.llm import openai as openai_mod

    assert calls["max_output_tokens"] == 1024 + openai_mod._REASONING_HEADROOM_TOKENS


def test_factory_builds_openai_client() -> None:
    from bayesify.llm import OpenAIClient, make_llm_client

    assert isinstance(make_llm_client("openai"), OpenAIClient)


# --- AgentSDKClient (claude-agent-sdk query monkeypatched; no CLI/session) ---


def _agent_complete(monkeypatch, messages):
    import claude_agent_sdk as sdk

    from bayesify.llm import AgentSDKClient

    async def fake_query(*, prompt, options):
        for m in messages:
            yield m

    monkeypatch.setattr(sdk, "query", fake_query)
    return AgentSDKClient().complete(model="claude-haiku-4-5", system="s", user="u", schema=_Answer)


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
            [
                SimpleNamespace(
                    structured_output=None,
                    usage=None,
                    is_error=True,
                    result="boom",
                    total_cost_usd=0.0,
                )
            ],
        )


# --- multimodal seam (page-1 image for metadata extraction) ---------------------------------------


def test_call_with_policy_forwards_image_only_when_set() -> None:
    # The policy passes `image` only when non-None, so text-only fakes/clients whose complete()
    # predates the kwarg keep working — only the multimodal path sends one.
    client = FakeLLMClient(_Answer(label="a"), _Answer(label="b"))
    _call(client)
    assert client.calls[-1]["image"] is None
    _call(client, image=b"PNGBYTES")
    assert client.calls[-1]["image"] == b"PNGBYTES"


def test_anthropic_client_attaches_page_image_as_base64_block() -> None:
    import base64
    from types import SimpleNamespace

    from bayesify.llm import AnthropicClient

    captured: dict = {}

    class _Msgs:
        def parse(self, **kw):
            captured.update(kw)
            return SimpleNamespace(
                parsed_output=_Answer(label="yes"),
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    client = AnthropicClient(api_key="sk-fake")
    client._sdk_client = SimpleNamespace(messages=_Msgs())

    # No image -> the content stays a bare string (unchanged behaviour).
    client.complete(model="claude-haiku-4-5", system="s", user="u", schema=_Answer)
    assert captured["messages"][0]["content"] == "u"

    # With an image -> a text block + a base64 PNG image block.
    client.complete(model="claude-haiku-4-5", system="s", user="u", schema=_Answer, image=b"PNG")
    content = captured["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "u"}
    assert content[1]["type"] == "image"
    assert content[1]["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(content[1]["source"]["data"]) == b"PNG"


def test_openai_client_attaches_page_image_as_data_uri(monkeypatch) -> None:
    import base64
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
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    class _OpenAI:
        def __init__(self, *, api_key=None):
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI, APIError=APIError))
    client = OpenAIClient(api_key="sk-fake")
    client.complete(model="gpt-5.4-mini", system="s", user="u", schema=_Answer, image=b"PNG")

    user_msg = calls["input"][1]
    assert user_msg["role"] == "user"
    parts = user_msg["content"]
    assert parts[0] == {"type": "input_text", "text": "u"}
    assert parts[1]["type"] == "input_image"
    b64 = base64.standard_b64encode(b"PNG").decode()
    assert parts[1]["image_url"] == f"data:image/png;base64,{b64}"


def test_agentsdk_sends_image_via_streaming_input(monkeypatch) -> None:
    # The Agent SDK is not text-only: with an image it switches from a string prompt to the SDK's
    # streaming-input form, carrying the same base64 image block the API backends use.
    import base64
    from types import SimpleNamespace

    import claude_agent_sdk as sdk

    from bayesify.llm import AgentSDKClient

    captured: dict = {}

    async def fake_query(*, prompt, options):
        captured["is_str"] = isinstance(prompt, str)
        if not isinstance(prompt, str):
            captured["messages"] = [m async for m in prompt]
        yield SimpleNamespace(
            structured_output={"label": "yes"},
            usage={"input_tokens": 1, "output_tokens": 1},
            is_error=False,
            result=None,
            total_cost_usd=0.0,
        )

    monkeypatch.setattr(sdk, "query", fake_query)
    resp = AgentSDKClient().complete(
        model="claude-haiku-4-5", system="s", user="u", schema=_Answer, image=b"PNG"
    )
    assert resp.parsed.label == "yes"
    assert captured["is_str"] is False  # streaming input, not a bare string
    content = captured["messages"][0]["message"]["content"]
    assert content[0]["type"] == "text" and "u" in content[0]["text"]
    assert content[1]["type"] == "image" and content[1]["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(content[1]["source"]["data"]) == b"PNG"


def test_agentsdk_uses_string_prompt_without_image(monkeypatch) -> None:
    from types import SimpleNamespace

    import claude_agent_sdk as sdk

    from bayesify.llm import AgentSDKClient

    captured: dict = {}

    async def fake_query(*, prompt, options):
        captured["is_str"] = isinstance(prompt, str)
        yield SimpleNamespace(
            structured_output={"label": "no"},
            usage={"input_tokens": 1, "output_tokens": 1},
            is_error=False,
            result=None,
            total_cost_usd=0.0,
        )

    monkeypatch.setattr(sdk, "query", fake_query)
    AgentSDKClient().complete(model="claude-haiku-4-5", system="s", user="u", schema=_Answer)
    assert captured["is_str"] is True  # a text-only call stays a plain string prompt
