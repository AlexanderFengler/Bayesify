"""Gate G1: engine_version composition + model pinning."""

from __future__ import annotations

from bayesify.core.versioning import compute_engine_version
from bayesify.llm import config as llm_config


def test_default_engine_version_folds_in_pinned_models() -> None:
    ev = compute_engine_version()
    # G1: all LLM role model IDs are part of engine_version, so a model change can't silently
    # replay a cached result.
    assert llm_config.judge_model() in ev.compact
    assert llm_config.screen_model() in ev.compact
    assert llm_config.classify_model() in ev.compact
    assert llm_config.refuter_model() in ev.compact
    assert ev.prompt_set_hash == "none"  # no prompts at M1
    assert ev.detector_catalog_hash == "none"  # no detectors at M1


def test_engine_version_is_deterministic() -> None:
    assert compute_engine_version().compact == compute_engine_version().compact


def test_model_change_changes_engine_version() -> None:
    a = compute_engine_version(model_ids=("claude-opus-4-8", "claude-haiku-4-5"))
    b = compute_engine_version(model_ids=("claude-sonnet-4-6", "claude-haiku-4-5"))
    assert a.compact != b.compact  # a model swap MUST bump engine_version (cache + VALIDATION.md)


def test_prompt_and_detector_hashes_change_when_contents_change() -> None:
    base = compute_engine_version(prompt_set="v1", detector_catalog="cat1")
    diff_prompt = compute_engine_version(prompt_set="v2", detector_catalog="cat1")
    diff_detect = compute_engine_version(prompt_set="v1", detector_catalog="cat2")
    assert base.compact != diff_prompt.compact
    assert base.compact != diff_detect.compact


def test_model_ids_are_sorted_and_deduped() -> None:
    ids = llm_config.model_ids()
    assert list(ids) == sorted(set(ids))
