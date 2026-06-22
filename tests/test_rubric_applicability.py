"""Rubric machine-half (G5/G6): the scoring block loads, and step_applicability gates correctly."""

from __future__ import annotations

from bayesify.core.rubric.applicability import step_applicability
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import (
    ExpectationTier,
    GateFacts,
    InferenceMethod,
    PaperClassLabel,
    PriorInformativeness,
)

_RUBRIC = load_rubric()


def _facts(**over) -> GateFacts:
    base = dict(
        inference_method=InferenceMethod.mcmc,
        n_models=1,
        bf_claimed=False,
        prior_informativeness=PriorInformativeness.unstated,
    )
    base.update(over)
    return GateFacts(**base)


def _ap(step_id: str, paper_class: PaperClassLabel, **facts):
    return step_applicability(_RUBRIC.step(step_id), paper_class, _facts(**facts))


# --- scoring block -------------------------------------------------------------------------------


def test_scoring_block_loads() -> None:
    sc = _RUBRIC.scoring
    assert sc is not None
    assert sc.sub_score == {"done_well": 1.0, "partial": 0.5, "missing": 0.0}
    assert 0.0 < sc.low_confidence_threshold < 1.0
    assert sc.mixing_rule == "max"


# --- S4: analytic posterior → N/A ----------------------------------------------------------------


def test_s4_not_applicable_for_analytic_posterior() -> None:
    ap = _ap("S4", PaperClassLabel.methodological, inference_method=InferenceMethod.exact_analytic)
    assert ap.applicable is False and ap.tier is ExpectationTier.none
    assert "analytic" in ap.reason.lower()


def test_s4_expected_when_a_sampler_is_used() -> None:
    ap = _ap("S4", PaperClassLabel.empirical, inference_method=InferenceMethod.hmc_nuts)
    assert ap.applicable is True and ap.tier is ExpectationTier.expected


# --- S6: model comparison gate -------------------------------------------------------------------


def test_s6_na_for_single_model_without_bf() -> None:
    ap = _ap("S6", PaperClassLabel.empirical, n_models=1, bf_claimed=False)
    assert ap.applicable is False


def test_s6_expected_with_two_models() -> None:
    ap = _ap("S6", PaperClassLabel.empirical, n_models=2)
    assert ap.applicable is True and ap.tier is ExpectationTier.expected


def test_s6_expected_when_bf_claimed() -> None:
    ap = _ap("S6", PaperClassLabel.empirical, n_models=1, bf_claimed=True)
    assert ap.applicable is True and ap.tier is ExpectationTier.expected


# --- S8: sensitivity escalation ------------------------------------------------------------------


def test_s8_recommended_for_empirical_by_default() -> None:
    ap = _ap("S8", PaperClassLabel.empirical)  # default priors, no BF
    assert ap.applicable is True and ap.tier is ExpectationTier.recommended


def test_s8_escalates_to_expected_under_informative_priors() -> None:
    ap = _ap(
        "S8", PaperClassLabel.empirical, prior_informativeness=PriorInformativeness.informative
    )
    assert ap.tier is ExpectationTier.expected


def test_s8_escalates_to_expected_under_bf_claim() -> None:
    assert _ap("S8", PaperClassLabel.empirical, bf_claimed=True).tier is ExpectationTier.expected


# --- ungated steps: tier follows the class -------------------------------------------------------


def test_s1_expected_for_every_graded_class() -> None:
    # `review` papers short-circuit (the rubric doesn't apply); a forced grade is advisory, so steps
    # are not "expected" for it — the per-step rubric is expected only for the graded classes.
    for pc in (
        PaperClassLabel.empirical,
        PaperClassLabel.numerical_experiment,
        PaperClassLabel.methodological,
    ):
        assert _ap("S1", pc).tier is ExpectationTier.expected


def test_s5_expected_for_empirical_recommended_otherwise() -> None:
    assert _ap("S5", PaperClassLabel.empirical).tier is ExpectationTier.expected
    assert _ap("S5", PaperClassLabel.numerical_experiment).tier is ExpectationTier.recommended
