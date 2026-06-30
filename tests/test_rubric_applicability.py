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
    assert sc.sub_score == {"adequate": 1.0, "partial": 0.5, "missing": 0.0}
    assert 0.0 < sc.low_confidence_threshold < 1.0
    assert sc.mixing_rule == "max"


# --- S4: analytic posterior → N/A ----------------------------------------------------------------


def test_s4_not_applicable_for_analytic_posterior() -> None:
    ap = _ap(
        "S4", PaperClassLabel.method_development, inference_method=InferenceMethod.exact_analytic
    )
    assert ap.applicable is False and ap.tier is ExpectationTier.none
    assert "analytic" in ap.reason.lower()


def test_s4_expected_when_a_sampler_is_used() -> None:
    ap = _ap("S4", PaperClassLabel.data_analysis, inference_method=InferenceMethod.hmc_nuts)
    assert ap.applicable is True and ap.tier is ExpectationTier.expected


# --- S6: model comparison gate -------------------------------------------------------------------


def test_s6_na_for_single_model_without_bf() -> None:
    ap = _ap("S6", PaperClassLabel.data_analysis, n_models=1, bf_claimed=False)
    assert ap.applicable is False


def test_s6_expected_with_two_models() -> None:
    ap = _ap("S6", PaperClassLabel.data_analysis, n_models=2)
    assert ap.applicable is True and ap.tier is ExpectationTier.expected


def test_s6_expected_when_bf_claimed() -> None:
    ap = _ap("S6", PaperClassLabel.data_analysis, n_models=1, bf_claimed=True)
    assert ap.applicable is True and ap.tier is ExpectationTier.expected


# --- S8: sensitivity escalation ------------------------------------------------------------------


def test_s8_recommended_for_empirical_by_default() -> None:
    ap = _ap("S8", PaperClassLabel.data_analysis)  # default priors, no BF
    assert ap.applicable is True and ap.tier is ExpectationTier.recommended


def test_s8_escalates_to_expected_under_informative_priors() -> None:
    ap = _ap(
        "S8", PaperClassLabel.data_analysis, prior_informativeness=PriorInformativeness.informative
    )
    assert ap.tier is ExpectationTier.expected


def test_s8_escalates_to_expected_under_bf_claim() -> None:
    ap = _ap("S8", PaperClassLabel.data_analysis, bf_claimed=True)
    assert ap.tier is ExpectationTier.expected


# --- ungated steps: tier follows the class -------------------------------------------------------


def test_s1_expected_for_every_graded_class() -> None:
    # `review` papers short-circuit (the rubric doesn't apply); a forced grade is advisory, so steps
    # are not "expected" for it — the per-step rubric is expected only for the graded classes.
    for pc in (
        PaperClassLabel.model_development,
        PaperClassLabel.method_development,
        PaperClassLabel.software_development,
        PaperClassLabel.data_analysis,
        PaperClassLabel.numerical_analysis,
        PaperClassLabel.theoretical_analysis,
    ):
        assert _ap("S1", pc).tier is ExpectationTier.expected


def test_s5_expected_for_empirical_recommended_otherwise() -> None:
    assert _ap("S5", PaperClassLabel.data_analysis).tier is ExpectationTier.expected
    assert _ap("S5", PaperClassLabel.numerical_analysis).tier is ExpectationTier.recommended


# --- S3/S8: method_development demoted to recommended (the 0.2-draft tier change) -----------------


def test_s3_recommended_for_method_development() -> None:
    # Demoted essential → recommended: a methods paper's illustrative data work isn't held to a
    # substantive prior-predictive check by default. Still APPLICABLE (stays in coverage/quality);
    # only the suggestion severity softens — a tier move never changes the score.
    ap = _ap("S3", PaperClassLabel.method_development)
    assert ap.applicable is True and ap.tier is ExpectationTier.recommended


def test_s8_recommended_for_method_development_by_default() -> None:
    ap = _ap("S8", PaperClassLabel.method_development)  # default priors, no BF
    assert ap.applicable is True and ap.tier is ExpectationTier.recommended


def test_s8_method_development_still_escalates_under_informative_priors() -> None:
    # The demotion only softens the DEFAULT expectation; the evidence gate still re-escalates S8.
    ap = _ap(
        "S8",
        PaperClassLabel.method_development,
        prior_informativeness=PriorInformativeness.weakly_informative,
    )
    assert ap.tier is ExpectationTier.expected


def test_s3_s8_still_essential_for_other_development_classes() -> None:
    # The demotion is scoped to method_development; model/software/theoretical stay expected.
    for pc in (
        PaperClassLabel.model_development,
        PaperClassLabel.software_development,
        PaperClassLabel.theoretical_analysis,
    ):
        assert _ap("S3", pc).tier is ExpectationTier.expected
        assert _ap("S8", pc).tier is ExpectationTier.expected
