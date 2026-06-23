"""V4 — the pure metric engine, pinned against hand-computed values.

No engine, no LLM, no network, no fake data — just labels in, statistics out.
"""

from __future__ import annotations

import pytest

from veribayes.core.schema import StepStatus as S
from veribayes.core.validation.metrics import (
    STATUS_ORDER,
    Rate,
    absence_fpr,
    absence_miss_rate,
    accuracy,
    binary_sens_spec,
    bootstrap_ci,
    cohen_kappa,
    confusion,
    gwet_ac,
    icc_a1,
    is_sufficient,
    percent_agreement,
    weighted_kappa,
    wilson_ci,
)

# --- basics + degenerate cases --------------------------------------------------------------------


def test_empty_and_degenerate() -> None:
    assert percent_agreement([]) is None
    assert cohen_kappa([]) is None
    assert Rate(0, 0).value is None
    assert Rate(1, 4).value == 0.25
    # one category, perfect agreement: chance agreement is 1, so κ is defined to 1.0 (not 0/0)
    assert cohen_kappa([(True, True)] * 5) == 1.0


# --- the κ-paradox: high agreement, skewed marginals → low κ, but high AC1 ------------------------


def test_kappa_paradox() -> None:
    # 98/100 agree, but almost everything is one category (True).
    pairs = [(True, True)] * 98 + [(True, False), (False, True)]
    assert percent_agreement(pairs) == pytest.approx(0.98)
    assert cohen_kappa(pairs) < 0.05  # κ collapses (here ≈ -0.01) despite 98% agreement
    assert gwet_ac(pairs) > 0.95  # AC1 stays high — the honest companion to κ on skewed marginals


# --- weighted (ordinal) κ credits near-misses -----------------------------------------------------


def test_weighted_kappa_beats_nominal_on_near_misses() -> None:
    # disagreements are all one step apart (adequate↔partial, missing↔partial), never far.
    pairs = (
        [(S.adequate, S.adequate)] * 4
        + [(S.partial, S.partial)] * 3
        + [(S.adequate, S.partial)] * 2
        + [(S.missing, S.partial)]
    )
    nominal = cohen_kappa(pairs)
    weighted = weighted_kappa(pairs, STATUS_ORDER, kind="linear")
    assert nominal == pytest.approx(0.4828, abs=0.001)
    assert weighted == pytest.approx(0.5161, abs=0.001)
    assert weighted > nominal  # near-misses are penalised less than far-misses


# --- absence-FPR + the two-stage decomposition ----------------------------------------------------


def test_absence_fpr_strict_and_broad_excludes_na() -> None:
    pairs = [
        (S.adequate, S.missing),  # engine cried 'missing' but it was present → strict + broad FP
        (S.partial, S.missing),  # present-ish → broad FP only
        (S.missing, S.missing),  # correct absence → not an FP
        (S.not_applicable, S.missing),  # engine-missing vs human-N/A → STAGE-1, excluded from FPR
    ]
    strict = absence_fpr(pairs, mode="strict")
    broad = absence_fpr(pairs, mode="broad")
    assert strict == Rate(1, 3)  # n=3, NOT 4 — the N/A cell is excluded (two-stage decomposition)
    assert broad == Rate(2, 3)
    assert strict.value == pytest.approx(1 / 3)


def test_absence_miss_rate_excludes_na() -> None:
    pairs = [
        (S.missing, S.adequate),  # human says missing, engine missed it → a miss
        (S.missing, S.partial),  # also a miss
        (S.missing, S.missing),  # caught
        (S.missing, S.not_applicable),  # engine-N/A vs human-missing → stage-1, excluded
    ]
    assert absence_miss_rate(pairs) == Rate(2, 3)


def test_confusion_crosstab() -> None:
    pairs = [(S.adequate, S.adequate), (S.adequate, S.partial), (S.missing, S.missing)]
    table = confusion(pairs)
    assert table["adequate"]["adequate"] == 1
    assert table["adequate"]["partial"] == 1
    assert table["missing"]["missing"] == 1


# --- scalar agreement -----------------------------------------------------------------------------


def test_accuracy_and_sens_spec() -> None:
    assert accuracy([("a", "a"), ("a", "b"), ("c", "c")]) == Rate(2, 3)
    # relevance: positive = 'is a Bayesian-workflow paper'
    sens, spec = binary_sens_spec([(True, True), (True, False), (False, False), (False, True)])
    assert sens == Rate(1, 2)  # 1 of 2 real papers caught
    assert spec == Rate(1, 2)  # 1 of 2 decoys correctly rejected


def test_icc_tracks_value_not_just_rank() -> None:
    # identical scores → ICC 1.0 (no rater bias, all variance is between papers)
    assert icc_a1([(0.8, 0.8), (0.5, 0.5), (0.9, 0.9)]) == pytest.approx(1.0)
    # close-but-not-identical, tracking the same value → high ICC
    assert icc_a1([(0.8, 0.82), (0.5, 0.48), (0.9, 0.91), (0.3, 0.35)]) > 0.95
    assert icc_a1([(0.5, 0.5)]) is None  # <2 papers


# --- uncertainty ----------------------------------------------------------------------------------


def test_wilson_ci_known_value() -> None:
    ci = wilson_ci(5, 10)
    assert ci is not None
    assert ci.lo == pytest.approx(0.2366, abs=0.001)
    assert ci.hi == pytest.approx(0.7634, abs=0.001)
    assert wilson_ci(0, 0) is None


def test_bootstrap_is_deterministic_and_brackets_the_estimate() -> None:
    # units = papers (cluster bootstrap); stat flattens to cells and computes % agreement.
    papers = [
        [(True, True), (True, True), (True, False)],
        [(True, True), (False, False)],
        [(True, True), (True, True)],
    ]

    def stat(units):
        cells = [c for paper in units for c in paper]
        return percent_agreement(cells)

    a = bootstrap_ci(papers, stat, seed=7, n_resamples=300)
    b = bootstrap_ci(papers, stat, seed=7, n_resamples=300)
    assert a is not None and a == b  # same seed → byte-identical interval (deterministic)
    point = stat(papers)
    assert a.lo <= point <= a.hi  # the interval brackets the point estimate
    assert bootstrap_ci([], stat, seed=7) is None


def test_is_sufficient_floor() -> None:
    assert is_sufficient(15, 15) is True
    assert is_sufficient(14, 15) is False
