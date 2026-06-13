"""Rubric loader + profile filtering (G5 shape pin; PR-#1 rubric profiles)."""

from __future__ import annotations

import pytest

from veribayes.core.rubric import RubricProfileError, load_rubric
from veribayes.core.rubric.loader import DEFAULT_RUBRIC_PATH


def test_loads_the_real_rubric_with_ten_steps() -> None:
    spec = load_rubric()
    assert spec.rubric_version == "0.1-draft"
    ids = [s.id for s in spec.steps]
    assert ids == [f"S{i}" for i in range(1, 11)]
    assert spec.profile == "synthesis"


def test_default_path_points_at_repo_rubric() -> None:
    assert DEFAULT_RUBRIC_PATH.name == "steps.yaml"
    assert DEFAULT_RUBRIC_PATH.exists()


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


def test_schad2021_profile_keeps_only_steps_grounded_in_that_source() -> None:
    spec = load_rubric(profile="schad2021")
    assert spec.profile == "schad2021"
    # In the current rubric only S1 and S3 cite schad2021 (S6/S7/S8 cite schad2022_bf, a *different*
    # source — exact-match, not substring, is the correct behaviour).
    assert sorted(s.id for s in spec.steps) == ["S1", "S3"]
    assert set(spec.citations) == {"schad2021"}


def test_source_profile_drops_thresholds_not_attributed_to_the_source() -> None:
    # betancourt_workflow grounds several S4 thresholds but S4 also carries vehtari2021/wambs2017
    # thresholds; the source-pure profile keeps only betancourt_workflow's.
    spec = load_rubric(profile="betancourt_workflow")
    s4 = next((s for s in spec.steps if s.id == "S4"), None)
    assert s4 is not None
    assert s4.thresholds  # at least one survives
    assert all(t.source == "betancourt_workflow" for t in s4.thresholds.values())


def test_unknown_profile_raises() -> None:
    with pytest.raises(RubricProfileError):
        load_rubric(profile="does_not_exist")
