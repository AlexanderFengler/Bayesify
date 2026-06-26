"""Cost-ledger pricing (C6 / ADV-10 envelope)."""

from __future__ import annotations

import pytest

from bayesify.core import config


def test_estimate_cost_uses_per_mtok_pricing() -> None:
    # 1M input @ $5 + 1M output @ $25 on the judge = $30.
    cost = config.estimate_cost("claude-opus-4-8", 1_000_000, 1_000_000)
    assert cost == pytest.approx(30.0)


def test_cheap_tier_exists_in_pricing() -> None:
    # The C6 cheap-before-expensive gate relies on a cheaper screen tier existing in the table.
    # (SCREEN_MODEL is temporarily Opus during M4 bring-up; this asserts the pricing fact, not which
    # model the gate currently uses.)
    tokens = (500_000, 500_000)
    haiku = config.estimate_cost("claude-haiku-4-5", *tokens)
    opus = config.estimate_cost("claude-opus-4-8", *tokens)
    assert haiku < opus


def test_unpriced_model_fails_loud() -> None:
    # An unpriced model usually means an unpinned one, which G1 forbids — fail, don't guess $0.
    with pytest.raises(KeyError):
        config.estimate_cost("some-unpinned-model", 100, 100)


def test_zero_tokens_zero_cost() -> None:
    assert config.estimate_cost(config.JUDGE_MODEL, 0, 0) == 0.0


# --- MongoDB / Atlas configuration ----------------------------------------------------------------


def test_mongodb_uri_accepts_atlas_style_alias(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_MONGODB_URI", raising=False)
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify")
    assert config.mongodb_uri() == "mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify"


def test_mongodb_uri_prefers_bayesify_override(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_URI", "mongodb://localhost:27018")
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pass@example.mongodb.net")
    assert config.mongodb_uri() == "mongodb://localhost:27018"


def test_mongodb_database_accepts_common_aliases(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_MONGODB_DB", raising=False)
    monkeypatch.setenv("MONGODB_DATABASE", "atlas_db")
    assert config.mongodb_database() == "atlas_db"


def test_mongodb_server_api_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_SERVER_API", "0")
    assert config.mongodb_server_api() is None


# --- LLM backend selection (subscription-first) ---------------------------------------------------


def test_backend_respects_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_LLM_BACKEND", "api")
    monkeypatch.setattr(config, "claude_code_available", lambda: True)  # would otherwise win
    assert config.llm_backend() == "api"


def test_backend_prefers_subscription_when_cli_present(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config, "claude_code_available", lambda: True)
    assert config.llm_backend() == "agent-sdk"


def test_backend_falls_back_to_api_key(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config, "claude_code_available", lambda: False)
    assert config.llm_backend() == "api"


def test_backend_falls_back_to_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config, "claude_code_available", lambda: False)
    assert config.llm_backend() == "openai"


def test_backend_none_when_no_credentials(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config, "claude_code_available", lambda: False)
    assert config.llm_backend() == "none"
