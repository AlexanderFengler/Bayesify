"""Shared pytest setup for the Bayesify suite."""

from __future__ import annotations

import os
from pathlib import Path

# Never load the developer's private bayesify.env during tests. The app loads it at startup (the
# TestClient lifespan calls `_load_env_file`), which would leak the local LLM backend, grading
# strategy, Atlas URI, etc. into os.environ and make env-sensitive tests non-hermetic. Point the
# loader at a path that does not exist so it is a no-op; the suite shapes the env explicitly below
# and per-test via monkeypatch. `setdefault` lets a developer/CI override deliberately.
os.environ.setdefault("BAYESIFY_ENV_FILE", str(Path(__file__).with_name("_no_such.env")))

# Pin the assess-stage fan-out to a single worker for the whole suite. `config.assess_concurrency()`
# is backend-aware and defaults to >1 on a dev machine where the `claude` CLI is present (backend
# resolves to "agent-sdk"); under real parallelism the order-dependent `FakeLLMClient` (it pops
# scripted responses in call order) would mis-map responses to racing steps. Tests that exercise the
# parallel path pass `concurrency=` to `assess()` explicitly, so this default does not bind them.
# `setdefault` lets CI or a developer override it deliberately.
os.environ.setdefault("BAYESIFY_ASSESS_CONCURRENCY", "1")

# Test runs should not depend on a developer's private bayesify.env. The production config remains
# env-only; the suite supplies explicit pins so engine_version/cache-key assertions are hermetic.
os.environ.setdefault("BAYESIFY_JUDGE_MODEL", "claude-opus-4-8")
os.environ.setdefault("BAYESIFY_SCREEN_MODEL", "claude-haiku-4-5")
os.environ.setdefault("BAYESIFY_CLASSIFY_MODEL", "claude-haiku-4-5")
os.environ.setdefault("BAYESIFY_REFUTER_MODEL", "claude-opus-4-8")
