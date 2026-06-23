"""M7 slice 3 — real-engine pairing: grade a gold-set paper with the SAME engine the app ships,
on the exact rated bytes (sha256-pinned), and hard-fail if the rated document isn't available.
"""

from __future__ import annotations

import fitz
import pytest

from veribayes.core.cache import BlobStore
from veribayes.core.engine import grade_document
from veribayes.core.rubric.loader import load_rubric
from veribayes.core.schema import Relevance, RelevanceLabel, ScoredResult
from veribayes.core.validation import harness
from veribayes.core.validation.harness import (
    FixtureEngineSource,
    GoldsetVersionMismatch,
    LiveEngineSource,
)
from veribayes.core.validation.human_report import (
    GoldOrigin,
    GoldProvenance,
    GoldTier,
    HumanReport,
    RaterRelationship,
    Rating,
)

_RUBRIC = load_rubric()


def _no() -> Relevance:
    return Relevance(label=RelevanceLabel.no, confidence=0.9, rationale="not Bayesian")


def _canned() -> ScoredResult:
    return ScoredResult.short_circuit(relevance=_no(), engine_version="ev", rubric_version="rv")


def _no_rating(rid: str, rel: RaterRelationship) -> Rating:
    return Rating(
        rater_id=rid,
        relationship=rel,
        relevance_label=RelevanceLabel.no,
        relevance_rationale="not Bayesian",
    )


def _hr(work_id: str, sha: str, tier: GoldTier = GoldTier.B) -> HumanReport:
    return HumanReport(
        work_id=work_id,
        source_sha256=sha,
        version_label="v1",
        rubric_version="rv",
        tier=tier,
        provenance=GoldProvenance(origin=GoldOrigin.fake_llm),
        ratings=[
            _no_rating("r1", RaterRelationship.independent),
            _no_rating("r2", RaterRelationship.independent),
        ],
        consensus=_no_rating("consensus", RaterRelationship.consensus),
    )


# --- engine sources -------------------------------------------------------------------------------


def test_live_engine_source_grades_the_pinned_bytes(tmp_path) -> None:
    blobs = BlobStore(tmp_path / "blobs")
    sha = blobs.put(b"the exact rated document")
    canned = _canned()
    seen: dict[str, bytes] = {}

    def grade_fn(data: bytes) -> ScoredResult:
        seen["data"] = data
        return canned

    result = LiveEngineSource(blobs, grade_fn)(_hr("w1", sha))
    assert result is canned
    assert seen["data"] == b"the exact rated document"  # graded the bytes the rater rated


def test_live_engine_source_hard_fails_when_doc_absent(tmp_path) -> None:
    blobs = BlobStore(tmp_path / "blobs")
    src = LiveEngineSource(blobs, lambda data: _canned())
    with pytest.raises(GoldsetVersionMismatch):  # never grade a substitute document
        src(_hr("w1", "0" * 64))


def test_fixture_engine_source_pairs_by_work_id(tmp_path) -> None:
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "w1.json").write_text(_canned().model_dump_json())
    src = FixtureEngineSource(engine_dir)
    assert src(_hr("w1", "sha")).relevance.label is RelevanceLabel.no
    assert src(_hr("w2", "sha")) is None  # missing fixture → no pair (demo tolerates)


def test_build_uses_the_injected_engine_source(tmp_path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "w1.json").write_text(_hr("w1", "sha").model_dump_json())
    report = harness.build(
        goldset_dir=gold,
        engine_source=lambda h: _canned(),
        treat_as_real=False,
        n_resamples=20,
    )
    assert report.n_papers == 1 and report.is_demo  # the custom source paired the one paper


def test_engine_runs_two_grades_tier_a_twice(tmp_path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "a.json").write_text(_hr("a", "sa", tier=GoldTier.A).model_dump_json())
    (gold / "b.json").write_text(_hr("b", "sb", tier=GoldTier.B).model_dump_json())
    calls: dict[str, int] = {}

    def src(h: HumanReport) -> ScoredResult:
        calls[h.work_id] = calls.get(h.work_id, 0) + 1
        return _canned()

    harness.build(
        goldset_dir=gold, engine_source=src, engine_runs=2, treat_as_real=False, n_resamples=10
    )
    assert calls["a"] == 2  # Tier A graded twice → test-retest
    assert calls["b"] == 1  # Tier B once


# --- the shared engine (grade_document == the app's engine) ---------------------------------------


class _FakeLLM:
    """Schema-aware fake driving the full grade path, no real LLM (mirrors test_api._full_fake)."""

    def complete(self, *, model, system, user, schema, max_tokens=1024):
        from veribayes.core.assess import RefuterVerdict, StepJudgment
        from veribayes.core.llm import LLMResponse
        from veribayes.core.schema import PaperClass, PaperClassLabel, Relevance, RelevanceLabel

        name = schema.__name__
        if name == "Relevance":
            p = Relevance(
                label=RelevanceLabel.yes, confidence=0.9, rationale="ok", evidence_refs=[0]
            )
        elif name == "PaperClass":
            p = PaperClass(
                primary=PaperClassLabel.empirical, confidence=0.8, rationale="r", evidence_refs=[0]
            )
        elif name == "StepJudgment":
            p = StepJudgment(status="adequate", confidence=0.9)
        else:
            p = RefuterVerdict(refuted=False, notes="absent")
        return LLMResponse(parsed=p, model=model, input_tokens=10, output_tokens=5)


def _pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    return doc.tobytes()


_HDDM = _pdf(
    [
        "A hierarchical drift-diffusion model of decision making",
        "We fit it with Bayesian inference in Stan using the NUTS sampler;",
        "convergence checked with R-hat and bulk-ESS; posterior predictive checks pass.",
    ]
)


def test_grade_document_runs_the_full_engine(tmp_path) -> None:
    blobs = BlobStore(tmp_path / "blobs")
    sr = grade_document(
        _HDDM,
        blobs=blobs,
        client=_FakeLLM(),
        rubric=_RUBRIC,
        engine_version="ev",
        rubric_version="rv",
    )
    assert sr.relevance.label is RelevanceLabel.yes
    assert sr.paper_class is not None and len(sr.step_assessments) == 10  # graded end-to-end
