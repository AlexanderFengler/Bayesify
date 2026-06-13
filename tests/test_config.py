"""Cost-ledger pricing (C6 / ADV-10 envelope)."""

from __future__ import annotations

import pytest

from veribayes.core import config


def test_estimate_cost_uses_per_mtok_pricing() -> None:
    # 1M input @ $5 + 1M output @ $25 on the judge = $30.
    cost = config.estimate_cost("claude-opus-4-8", 1_000_000, 1_000_000)
    assert cost == pytest.approx(30.0)


def test_screen_tier_is_cheaper_than_judge() -> None:
    tokens = (500_000, 500_000)
    judge = config.estimate_cost(config.JUDGE_MODEL, *tokens)
    screen = config.estimate_cost(config.SCREEN_MODEL, *tokens)
    assert screen < judge


def test_unpriced_model_fails_loud() -> None:
    # An unpriced model usually means an unpinned one, which G1 forbids — fail, don't guess $0.
    with pytest.raises(KeyError):
        config.estimate_cost("some-unpinned-model", 100, 100)


def test_zero_tokens_zero_cost() -> None:
    assert config.estimate_cost(config.JUDGE_MODEL, 0, 0) == 0.0
