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


def test_registry_lists_synthesis_first_and_includes_gelman_and_schad() -> None:
    infos = available_rubrics()
    ids = [r.id for r in infos]
    assert ids[0] == "synthesis"  # default first
    assert {"gelman", "schad"} <= set(ids)  # the contained rubrics are registered
    syn = next(r for r in infos if r.id == "synthesis")
    assert syn.label and syn.summary and syn.rubric_version == "0.1-draft"


def test_gelman_is_a_self_contained_single_source_rubric() -> None:
    g = load_rubric("gelman")
    assert g.profile == "gelman" and g.rubric_version == "0.1-gelman"
    assert [s.id for s in g.steps] == [f"G{i}" for i in range(1, 11)]  # its own stages, not S1..S10
    assert g.sources == ["gelman2020"]  # single source...
    assert all(not s.citations for s in g.steps)  # ...so no per-step "Standard applied"
    assert g.label and g.summary  # carries a preamble


def test_schad_is_a_self_contained_single_source_rubric() -> None:
    s = load_rubric("schad")
    assert s.profile == "schad" and s.rubric_version == "0.1-schad"
    assert [st.id for st in s.steps] == [f"SC{i}" for i in range(1, 8)]  # its own SC1..SC7 stages
    assert s.sources == ["schad2021"]  # single source...
    assert all(not st.citations for st in s.steps)  # ...so no per-step "Standard applied"
    assert s.label and s.summary  # carries a preamble


def test_unknown_rubric_raises() -> None:
    with pytest.raises(RubricProfileError):
        load_rubric(profile="does_not_exist")
