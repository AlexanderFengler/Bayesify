"""Shared pytest setup for the Bayesify suite."""

from __future__ import annotations

import os

# Pin the assess-stage fan-out to a single worker for the whole suite. `config.assess_concurrency()`
# is backend-aware and defaults to >1 on a dev machine where the `claude` CLI is present (backend
# resolves to "agent-sdk"); under real parallelism the order-dependent `FakeLLMClient` (it pops
# scripted responses in call order) would mis-map responses to racing steps. Tests that exercise the
# parallel path pass `concurrency=` to `assess()` explicitly, so this default does not bind them.
# `setdefault` lets CI or a developer override it deliberately.
os.environ.setdefault("BAYESIFY_ASSESS_CONCURRENCY", "1")
