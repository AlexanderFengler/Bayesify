"""V5a — the validation report builder: it computes one watermarked report from (human, engine)
pairs, derives human coverage from the engine's own arithmetic, and excludes (not drops) bad papers.
Pure, in-memory; the CLI + fake data + on-disk firewall are V5b.
"""

from __future__ import annotations

import pathlib

from veribayes.core.rubric.loader import load_rubric
from veribayes.core.schema import EvidenceSpan, RelevanceLabel, ScoredResult, StepStatus
from veribayes.core.validation.human_report import (
    GoldOrigin,
    GoldProvenance,
    GoldTier,
    HumanReport,
    RaterRelationship,
    Rating,
    StepRating,
)
from veribayes.core.validation.report import build_report, to_calibration_payload, to_markdown

_FIX = pathlib.Path(__file__).parent / "fixtures" / "scored_result" / "empirical_mixed.json"
_RUBRIC = load_rubric()
_SPAN = EvidenceSpan(section_id="s01", quote="a cited span")


def _rating(sr: ScoredResult, rater_id: str, rel: RaterRelationship, *, flip: bool) -> Rating:
    """Mirror the engine's per-step verdict (so agreement is high); when ``flip``, nudge the first
    applicable step to create one real disagreement."""
    steps: list[StepRating] = []
    flipped = False
    for a in sr.step_assessments:
        if not a.applicable:
            steps.append(
                StepRating(
                    step_id=a.step_id,
                    applicable=False,
                    status=StepStatus.not_applicable,
                    confidence=0.8,
                )
            )
            continue
        status = a.status
        if flip and not flipped and status is not StepStatus.partial:
            status, flipped = StepStatus.partial, True
        present = status in (StepStatus.done_well, StepStatus.partial)
        steps.append(
            StepRating(
                step_id=a.step_id,
                applicable=True,
                status=status,
                confidence=0.85,
                evidence=[_SPAN] if present else [],
                rationale="rater note",
            )
        )
    assert sr.paper_class is not None
    return Rating(
        rater_id=rater_id,
        relationship=rel,
        relevance_label=RelevanceLabel.yes,
        relevance_rationale="fits a Bayesian model",
        paper_class_label=sr.paper_class.primary,
        gate_facts=sr.gate_facts,
        steps=steps,
    )


def _human(sr: ScoredResult, work_id: str, sha: str) -> HumanReport:
    return HumanReport(
        work_id=work_id,
        source_sha256=sha,
        version_label="v1",
        rubric_version=sr.rubric_version,
        tier=GoldTier.A,
        provenance=GoldProvenance(origin=GoldOrigin.fake_llm, authored_by="demo"),
        ratings=[
            _rating(sr, "r1", RaterRelationship.independent, flip=False),
            _rating(sr, "r2", RaterRelationship.prompt_author, flip=False),
        ],
        consensus=_rating(sr, "consensus", RaterRelationship.consensus, flip=True),
    )


def test_build_report_produces_one_watermarked_object() -> None:
    sr = ScoredResult.model_validate_json(_FIX.read_text())
    pairs = [(_human(sr, "w1", "aa"), sr), (_human(sr, "w2", "bb"), sr)]
    rep = build_report(
        pairs,
        _RUBRIC,
        engine_version="ev-test",
        is_demo=True,
        status="demo_fake_data",
        n_resamples=80,
    )
    assert rep.n_papers == 2 and rep.n_excluded == 0
    assert rep.status == "demo_fake_data" and rep.is_demo is True
    assert rep.status_kappa.value is not None
    assert rep.confusion  # the human×engine crosstab is populated
    assert rep.status_kappa.preliminary is True  # 2 papers < the 15-paper floor
    assert any("FAKE DATA" in c for c in rep.validity_caveats)
    # single-computation watermark: both renderers read the SAME object, so neither can disagree
    assert to_calibration_payload(rep)["status"] == "demo_fake_data"
    assert "FAKE DATA" in to_markdown(rep)


def test_human_coverage_is_derived_not_typed() -> None:
    # The human never authors a coverage number; the report carries coverage AGREEMENT, derived from
    # the consensus statuses via the engine's own arithmetic.
    assert "coverage" not in HumanReport.model_fields
    assert "quality_score" not in HumanReport.model_fields
    sr = ScoredResult.model_validate_json(_FIX.read_text())
    rep = build_report(
        [(_human(sr, "w1", "aa"), sr)],
        _RUBRIC,
        engine_version="ev",
        is_demo=True,
        status="demo_fake_data",
        n_resamples=40,
    )
    assert rep.coverage_icc.label.startswith("coverage")  # an agreement metric, not a typed value


def test_inadmissible_papers_are_excluded_not_dropped() -> None:
    sr = ScoredResult.model_validate_json(_FIX.read_text())
    good = _human(sr, "w1", "aa")
    # no consensus → inadmissible (must be excluded-and-counted, never silently dropped)
    bad = _human(sr, "w2", "bb").model_copy(update={"consensus": None})
    rep = build_report(
        [(good, sr), (bad, sr)],
        _RUBRIC,
        engine_version="ev",
        is_demo=True,
        status="demo_fake_data",
        n_resamples=40,
    )
    assert rep.n_papers == 1 and rep.n_excluded == 1
