"""V5b — the harness + the honesty firewall. The demo dry-run produces a watermarked report; fake
data can never reach the real goldset or the public VALIDATION.md.
"""

from __future__ import annotations

import pytest

from veribayes.core.rubric.loader import load_rubric
from veribayes.core.validation.demo_data import build_demo_dataset, write_demo_dataset
from veribayes.core.validation.harness import (
    FakeDataInPublicReport,
    FakeDataInRealGoldset,
    decide_status,
    guard_public_emit,
    run,
)
from veribayes.core.validation.human_report import GoldOrigin, HumanReport
from veribayes.core.validation.report import build_report

_RUBRIC = load_rubric()


def _blindify(humans: list[HumanReport]) -> list[HumanReport]:
    """Re-stamp fabricated reports as blind_human (to simulate a real goldset)."""
    blind = GoldOrigin.blind_human
    return [
        h.model_copy(update={"provenance": h.provenance.model_copy(update={"origin": blind})})
        for h in humans
    ]


def test_demo_run_is_watermarked(tmp_path) -> None:
    g, e, o = tmp_path / "gold", tmp_path / "engine", tmp_path / "out"
    assert write_demo_dataset(str(g), str(e)) == 5

    rep = run(goldset_dir=g, engine_dir=e, out_dir=o, treat_as_real=False, seed=1)

    assert rep.is_demo and rep.status == "demo_fake_data" and rep.n_papers == 5
    assert (o / "VALIDATION.demo.md").exists()
    assert not (o / "VALIDATION.md").exists()  # the public report is NEVER written from demo data
    assert list(o.glob("*.json"))  # the report JSON (the /api/calibration payload)
    # the seeded absence-FPR paper flows through (engine 'missing' on S5, human saw it)
    assert rep.absence_fpr_strict.x == 1 and rep.absence_fpr_strict.n == 1
    md = (o / "VALIDATION.demo.md").read_text()
    assert "FAKE DATA" in md
    # the Tier-C analytic paper is reported as a case, not pooled into the rates
    assert "Tier-C special cases" in md and "demo-analytic" in md
    assert rep.tier_counts.get("C") == 1 and len(rep.tier_c_cases) == 1


def test_fake_data_in_real_goldset_raises() -> None:
    humans = [p.human for p in build_demo_dataset()]  # origin=fake_llm
    with pytest.raises(FakeDataInRealGoldset):
        decide_status(humans, treat_as_real=True)


def test_public_emit_blocked_for_demo() -> None:
    pairs = [(p.human, p.engine) for p in build_demo_dataset()]
    rep = build_report(
        pairs, _RUBRIC, engine_version="ev", is_demo=True, status="demo_fake_data", n_resamples=40
    )
    with pytest.raises(FakeDataInPublicReport):
        guard_public_emit(rep)


def test_real_blind_path_is_development_set_and_publishable() -> None:
    papers = build_demo_dataset()
    humans = _blindify([p.human for p in papers])
    is_demo, status = decide_status(humans, treat_as_real=True)
    assert is_demo is False and status == "development_set"
    pairs = list(zip(humans, [p.engine for p in papers], strict=True))
    rep = build_report(
        pairs, _RUBRIC, engine_version="ev", is_demo=False, status="development_set", n_resamples=40
    )
    guard_public_emit(rep)  # must NOT raise — real, non-demo data may produce VALIDATION.md
