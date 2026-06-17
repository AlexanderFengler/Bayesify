"""Rubric loader + registry — self-contained rubric files; ``synthesis`` is the default."""

from __future__ import annotations

import pytest

from veribayes.core.rubric import RubricProfileError, available_rubrics, load_rubric


def test_loads_the_synthesis_rubric_with_ten_steps() -> None:
    spec = load_rubric()
    assert spec.rubric_version == "0.1-draft"
    assert spec.profile == "synthesis"
    assert [s.id for s in spec.steps] == [f"S{i}" for i in range(1, 11)]
    assert spec.label and spec.summary  # carries a label + preamble for the picker / report


def test_every_step_citation_resolves_to_a_known_source() -> None:
    spec = load_rubric()
    for step in spec.steps:
        for src in step.citations:
            assert src in spec.citations, f"{step.id} cites unknown source {src!r}"


def test_thresholds_carry_verified_status() -> None:
    spec = load_rubric()
    s4 = spec.step("S4")
    # The honest verified/unverified split must survive loading (project transparency rule).
    assert s4.thresholds["rhat_historical"].verified is True
    assert s4.thresholds["rhat_modern"].verified is False


def test_registry_lists_synthesis_first() -> None:
    infos = available_rubrics()
    ids = [r.id for r in infos]
    assert "synthesis" in ids and ids[0] == "synthesis"  # the default is listed first
    syn = next(r for r in infos if r.id == "synthesis")
    assert syn.label and syn.summary and syn.rubric_version == "0.1-draft"


def test_unknown_rubric_raises() -> None:
    with pytest.raises(RubricProfileError):
        load_rubric(profile="does_not_exist")
