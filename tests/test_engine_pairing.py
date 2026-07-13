"""M7 slice 3 — real-engine pairing: grade a gold-set paper with the SAME engine the app ships,
on the exact rated bytes (sha256-pinned), and hard-fail if the rated document isn't available.
"""

from __future__ import annotations

from datetime import datetime

import fitz
import pytest

from bayesify.core.cache import BlobStore
from bayesify.core.engine import grade_document, grade_parsed
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
    ScoredResult,
    Section,
    SectionKind,
    SourceDoc,
)
from bayesify.core.validation import harness
from bayesify.core.validation.harness import (
    FixtureEngineSource,
    GoldsetVersionMismatch,
    LiveEngineSource,
)
from bayesify.core.validation.human_report import (
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


def _fake_batch(name: str, user: str, status: str = "adequate"):
    """Batch-schema responses for the fakes (grade_parsed dispatches to assess_batch by default);
    step ids are parsed from the batch prompt, mirroring test_assess_batch."""
    import re

    from bayesify.core.assess_batch import (
        BatchAssessJudgments,
        BatchRefuterVerdict,
        BatchRefuterVerdicts,
        BatchStepJudgment,
    )

    ids = re.findall(r"^STEP (S\d+):", user, re.M)
    if name == "BatchAssessJudgments":
        return BatchAssessJudgments(
            judgments=[BatchStepJudgment(step_id=s, status=status, confidence=0.9) for s in ids]
        )
    return BatchRefuterVerdicts(
        verdicts=[BatchRefuterVerdict(step_id=s, refuted=False, notes="absent") for s in ids]
    )


def _classifier_facts():
    """Checklist facts mapping deterministically to [data_analysis]; the quote carries the label's
    cue words so it survives without matching the fixture text, and Stan implies mcmc."""
    from bayesify.core.schema import (
        ClassifierFacts,
        ClassifierMethodFacts,
        ClassifierPaperTypeFacts,
    )

    no = {"answer": "no", "confidence": "low", "evidence": ""}
    pt = {name: dict(no) for name in ClassifierPaperTypeFacts.model_fields}
    pt["uses_bayesian_model_on_real_data"] = {
        "answer": "yes",
        "confidence": "high",
        "evidence": "we fit the model to real data",
    }
    me = {name: dict(no) for name in ClassifierMethodFacts.model_fields}
    return ClassifierFacts(paper_type=pt, methods=me, software=["Stan"], disciplines=[])


class _FakeLLM:
    """Schema-aware fake driving the full grade path, no real LLM (mirrors test_api._full_fake)."""

    def complete(self, *, model, system, user, schema, max_tokens=1024, image=None):
        from bayesify.core.assess import RefuterVerdict, StepJudgment
        from bayesify.core.schema import Relevance, RelevanceLabel
        from bayesify.llm import LLMResponse

        name = schema.__name__
        if name == "Relevance":
            p = Relevance(
                label=RelevanceLabel.yes, confidence=0.9, rationale="ok", evidence_refs=[0]
            )
        elif name == "ClassifierFacts":
            p = _classifier_facts()
        elif name == "StepJudgment":
            p = StepJudgment(status="adequate", confidence=0.9)
        elif name in ("BatchAssessJudgments", "BatchRefuterVerdicts"):
            p = _fake_batch(name, user)
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


# --- grade_parsed is the single composition: escape hatch + progress events live here now ---------


class _NoGateLLM:
    """Like _FakeLLM but the gate says 'no' (downstream still grades, for the override path)."""

    def complete(self, *, model, system, user, schema, max_tokens=1024, image=None):
        from bayesify.core.assess import RefuterVerdict, StepJudgment
        from bayesify.llm import LLMResponse

        name = schema.__name__
        if name == "Relevance":
            p = Relevance(label=RelevanceLabel.no, confidence=0.9, rationale="looks frequentist")
        elif name == "ClassifierFacts":
            p = _classifier_facts()
        elif name == "StepJudgment":
            p = StepJudgment(status="adequate", confidence=0.9)
        elif name in ("BatchAssessJudgments", "BatchRefuterVerdicts"):
            p = _fake_batch(name, user)
        else:
            p = RefuterVerdict(refuted=False, notes="absent")
        return LLMResponse(parsed=p, model=model, input_tokens=10, output_tokens=5)


def _parsed_doc() -> ParsedDoc:
    src = SourceDoc(
        sha256="a" * 64, version_label="t", source="upload", fetched_at=datetime(2026, 1, 1)
    )
    secs = [Section(id="s01", kind=SectionKind.body, title="B", text="We fit a model in Stan.")]
    return ParsedDoc(source=src, sections=secs, parser="t", parser_version="0")


def _one_hit() -> list[Evidence]:
    return [
        Evidence(
            detector_id="software.stan",
            detector_version="0.1.0",
            kind=EvidenceKind.software_mention,
            span=EvidenceSpan(section_id="s01", page=1, quote="in Stan"),
        )
    ]


def _grade(client, **over):
    return grade_parsed(
        _parsed_doc(), _one_hit(), client=client, rubric=_RUBRIC,
        engine_version="ev", rubric_version="rv", **over,
    )


def test_grade_parsed_short_circuits_a_no_without_override() -> None:
    sr = _grade(_NoGateLLM())
    assert sr.relevance.label is RelevanceLabel.no
    assert not sr.step_assessments  # short-circuited, not graded


def test_grade_parsed_relevance_override_grades_a_short_circuited_paper() -> None:
    # The escape hatch now lives in the shared engine, so the harness path can reproduce it too.
    sr = _grade(_NoGateLLM(), relevance_override="partial")
    assert sr.relevance.label is RelevanceLabel.partial and sr.relevance.overridden
    assert "[User override:" in sr.relevance.rationale
    assert sr.paper_class is not None and len(sr.step_assessments) == 10  # graded end-to-end


def test_grade_parsed_emits_stage_events_in_order() -> None:
    events: list[tuple[str, str]] = []
    _grade(_FakeLLM(), on_stage=lambda stage, state: events.append((stage, state)))
    assert events == [
        ("screen", "running"), ("screen", "done"),
        ("classify", "done"),
        ("assess", "running"), ("assess", "done"),
        ("score", "running"), ("score", "done"),
    ]


def test_grade_parsed_reveals_paper_class_once_for_a_graded_paper() -> None:
    seen: list[PaperClass] = []
    _grade(_FakeLLM(), on_paper_class=seen.append)
    assert len(seen) == 1 and seen[0].labels == [PaperClassLabel.data_analysis]


def test_grade_parsed_does_not_reveal_paper_class_when_screened_out() -> None:
    seen: list[PaperClass] = []
    _grade(_NoGateLLM(), on_paper_class=seen.append)
    assert seen == []  # a rejected paper never reaches the classify-done reveal
