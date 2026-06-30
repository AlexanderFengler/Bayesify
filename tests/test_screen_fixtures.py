"""Deterministic guard over the labeled screen/classify fixture set (no LLM).

Validates the fixtures are well-formed and internally consistent with the detector floor, and that
screen/classify flow over real detector Evidence[] without corrupting a correct label. The actual
accuracy measurement is the live eval harness (tests/eval/, M4 slice 4) and, for release, the
validation protocol (M7).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bayesify.core import classify as C
from bayesify.core import screen as S
from bayesify.core.detectors import run_detectors
from bayesify.core.llm import FakeLLMClient
from bayesify.core.schema import (
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
)

_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "screen" / "cases.json").read_text(encoding="utf-8")
)
_IDS = [c["id"] for c in _CASES]


def _parsed(case: dict) -> ParsedDoc:
    return ParsedDoc.model_validate(case["parsed"])


# --- set-level coverage (d-screen-classify.md minimums) -------------------------------------------


def test_fixture_set_meets_coverage_minimums() -> None:
    rel = [c for c in _CASES if c["expect_relevance"] == "yes"]
    part = [c for c in _CASES if c["expect_relevance"] == "partial"]
    dec = [c for c in _CASES if c["expect_relevance"] == "no"]
    assert len(rel) >= 9 and len(part) >= 3 and len(dec) >= 4
    labels = {label for c in rel for label in c["expect_labels"]}
    assert {"data_analysis", "numerical_analysis", "method_development"} <= labels
    assert any(len(c["expect_labels"]) > 1 for c in rel)  # at least one mixed case


# --- detector-floor consistency (the real invariant) ----------------------------------------------


@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_floor_consistency(case: dict) -> None:
    families = S._bayes_families(run_detectors(_parsed(case)))
    if case["expect_relevance"] == "no":
        # A non-Bayesian decoy must surface zero Bayesian evidence families, so the gate can
        # legitimately return 'no' and the floor never interferes. (dec2 also proves a 'Bayes'
        # mention confined to the reference list produces no hits.)
        assert families == set(), f"{case['id']}: decoy leaked Bayesian families {families}"
    else:
        assert families, f"{case['id']}: relevant/partial case has no Bayesian evidence"


# --- pass-through: screen/classify don't corrupt a correct label over real evidence ---------------


@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_screen_preserves_correct_label(case: dict) -> None:
    parsed = _parsed(case)
    evidence = run_detectors(parsed)
    label = RelevanceLabel(case["expect_relevance"])
    refs = [0] if label is not RelevanceLabel.no and evidence else []
    canned = Relevance(label=label, confidence=0.9, rationale="fixture", evidence_refs=refs)
    rel, entry = S.screen(parsed, evidence, client=FakeLLMClient(canned))
    assert rel.label is label
    assert entry.stage == "screen"


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c["expect_labels"]],
    ids=[c["id"] for c in _CASES if c["expect_labels"]],
)
def test_classify_returns_expected_class(case: dict) -> None:
    parsed = _parsed(case)
    evidence = run_detectors(parsed)
    labels = [PaperClassLabel(label) for label in case["expect_labels"]]
    canned = PaperClass(
        labels=labels,
        confidence=0.8,
        rationale="fixture",
        evidence_refs=[0],
    )
    cls, _ = C.classify(parsed, evidence, client=FakeLLMClient(canned))
    assert cls.labels == labels
