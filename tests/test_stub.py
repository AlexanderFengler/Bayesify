"""The M1 stub engine result."""

from __future__ import annotations

from bayesify.core import schema as s
from bayesify.core.stub import build_stub_result


def test_stub_is_schema_valid_and_round_trips() -> None:
    r = build_stub_result()
    assert s.ScoredResult.model_validate_json(r.model_dump_json()) == r


def test_stub_coverage_and_quality() -> None:
    r = build_stub_result()
    assert r.coverage is not None and r.profile is not None
    # 8 applicable steps (S6, S7 are N/A); 6 present (adequate|partial); 1 uncertain (low-conf S3).
    assert r.coverage.applicable == 8
    assert r.coverage.present == 6
    assert r.profile.n_na == 2
    assert r.profile.n_uncertain == 1
    # strict counts the uncertain absence as absent; lenient as present.
    assert r.coverage.strict < r.coverage.lenient
    assert r.quality_score == 0.625


def test_stub_carries_dual_grounding_and_severities() -> None:
    r = build_stub_result()
    s4 = next(a for a in r.step_assessments if a.step_id == "S4")
    assert s4.evidence and s4.standards  # grounded in the paper AND the literature
    s8 = next(a for a in r.step_assessments if a.step_id == "S8")
    assert any(sug.severity is s.Severity.error for sug in s8.suggestions)


def test_stub_engine_version_pins_models() -> None:
    from bayesify.llm import config as llm_config

    r = build_stub_result()
    assert llm_config.judge_model() in r.engine_version
    assert llm_config.screen_model() in r.engine_version
    assert llm_config.classify_model() in r.engine_version
    assert llm_config.refuter_model() in r.engine_version


def test_engine_version_is_computed_after_env_is_loaded(monkeypatch) -> None:
    import importlib

    import bayesify.core.stub as stub

    for name in (
        "BAYESIFY_JUDGE_MODEL",
        "BAYESIFY_SCREEN_MODEL",
        "BAYESIFY_CLASSIFY_MODEL",
        "BAYESIFY_REFUTER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    stub = importlib.reload(stub)
    assert stub.ENGINE_VERSION.endswith(";models=")

    monkeypatch.setenv("BAYESIFY_JUDGE_MODEL", "gpt-5.4")
    monkeypatch.setenv("BAYESIFY_SCREEN_MODEL", "gpt-5.4-nano")
    monkeypatch.setenv("BAYESIFY_CLASSIFY_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("BAYESIFY_REFUTER_MODEL", "gpt-5.5")

    current = stub.engine_version()
    assert current.endswith(";models=gpt-5.4+gpt-5.4-mini+gpt-5.4-nano+gpt-5.5")
    assert stub.build_stub_result().engine_version == current

    monkeypatch.setenv("BAYESIFY_JUDGE_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("BAYESIFY_SCREEN_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("BAYESIFY_CLASSIFY_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("BAYESIFY_REFUTER_MODEL", "claude-opus-4-8")
    importlib.reload(stub)
