"""Cost-ledger pricing (C6 / ADV-10 envelope)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from bayesify.api import config as api_config
from bayesify.api.env import load_env_file
from bayesify.llm import config as llm_config


def test_config_modules_do_not_load_env_files(monkeypatch) -> None:
    env_file = _env_file()
    try:
        env_file.write_text("BAYESIFY_SHOULD_NOT_LOAD=1\n", encoding="utf-8")
        monkeypatch.setenv("BAYESIFY_ENV_FILE", str(env_file))
        monkeypatch.delenv("BAYESIFY_SHOULD_NOT_LOAD", raising=False)

        api_config.mongodb_database()
        llm_config.llm_backend()

        assert "BAYESIFY_SHOULD_NOT_LOAD" not in os.environ
    finally:
        env_file.unlink(missing_ok=True)


def test_api_env_loader_reads_env_file_once(monkeypatch) -> None:
    env_file = _env_file()
    try:
        env_file.write_text(
            "export BAYESIFY_TEST_LOADED='yes'\nBAYESIFY_ALREADY_SET=file\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("BAYESIFY_ENV_FILE", str(env_file))
        monkeypatch.setenv("BAYESIFY_ALREADY_SET", "process")
        monkeypatch.delenv("BAYESIFY_TEST_LOADED", raising=False)

        loaded = load_env_file()

        assert loaded.keys == ("BAYESIFY_TEST_LOADED",)
        assert os.environ["BAYESIFY_TEST_LOADED"] == "yes"
        assert os.environ["BAYESIFY_ALREADY_SET"] == "process"
    finally:
        env_file.unlink(missing_ok=True)


def _env_file() -> Path:
    return Path(f".pytest-env-{uuid.uuid4().hex}.env")


def test_estimate_cost_uses_per_mtok_pricing() -> None:
    # 1M input @ $5 + 1M output @ $25 on the judge = $30.
    cost = llm_config.estimate_cost("claude-opus-4-8", 1_000_000, 1_000_000)
    assert cost == pytest.approx(30.0)


def test_trusted_tokens_parses_name_token_pairs(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_TRUSTED_TOKENS", " alice:tok1, bob:tok2 ,bad,empty: ")
    # token -> name; whitespace trimmed, malformed/empty entries dropped.
    assert api_config.trusted_tokens() == {"tok1": "alice", "tok2": "bob"}


def test_trusted_tokens_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_TRUSTED_TOKENS", raising=False)
    assert api_config.trusted_tokens() == {}


def test_cheap_tier_exists_in_pricing() -> None:
    # The C6 cheap-before-expensive gate relies on a cheaper screen tier existing in the table.
    # This asserts the pricing fact, not which model the gate currently uses.
    tokens = (500_000, 500_000)
    haiku = llm_config.estimate_cost("claude-haiku-4-5", *tokens)
    opus = llm_config.estimate_cost("claude-opus-4-8", *tokens)
    assert haiku < opus


def test_unpriced_model_fails_loud() -> None:
    # An unpriced model usually means an unpinned one, which G1 forbids — fail, don't guess $0.
    with pytest.raises(KeyError):
        llm_config.estimate_cost("some-unpinned-model", 100, 100)


def test_zero_tokens_zero_cost() -> None:
    assert llm_config.estimate_cost(llm_config.judge_model(), 0, 0) == 0.0


# --- MongoDB / Atlas configuration ----------------------------------------------------------------


def test_mongodb_uri_accepts_atlas_style_alias(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_MONGODB_URI", raising=False)
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify")
    assert (
        api_config.mongodb_uri()
        == "mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify"
    )


def test_mongodb_uri_prefers_bayesify_override(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_URI", "mongodb://localhost:27018")
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pass@example.mongodb.net")
    assert api_config.mongodb_uri() == "mongodb://localhost:27018"


def test_mongodb_database_accepts_common_aliases(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_MONGODB_DB", raising=False)
    monkeypatch.setenv("MONGODB_DATABASE", "atlas_db")
    assert api_config.mongodb_database() == "atlas_db"


def test_mongodb_server_api_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_SERVER_API", "0")
    assert api_config.mongodb_server_api() is None


# --- LLM backend selection (subscription-first) ---------------------------------------------------


def test_backend_respects_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_LLM_BACKEND", "api")
    monkeypatch.setattr(llm_config, "claude_code_available", lambda: True)  # would otherwise win
    assert llm_config.llm_backend() == "api"


def test_backend_prefers_subscription_when_cli_present(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm_config, "claude_code_available", lambda: True)
    assert llm_config.llm_backend() == "agent-sdk"


def test_backend_falls_back_to_api_key(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_config, "claude_code_available", lambda: False)
    assert llm_config.llm_backend() == "api"


def test_backend_falls_back_to_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(llm_config, "claude_code_available", lambda: False)
    assert llm_config.llm_backend() == "openai"


def test_backend_none_when_no_credentials(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_config, "claude_code_available", lambda: False)
    assert llm_config.llm_backend() == "none"
