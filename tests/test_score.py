"""f-score (M5 slice 2): golden tables, scoring invariants (Hypothesis), and contract errors.

Pure component — driven by hand-built StepAssessment[] fixtures, never a live chain.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bayesify.core.rubric.applicability import step_applicability_for_labels
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import (
    CostLedger,
    ExpectationTier,
    GateFacts,
    InferenceMethod,
    PaperClass,
    PaperClassLabel,
    PriorInformativeness,
    Relevance,
    RelevanceLabel,
    StepAssessment,
    StepStatus,
)
from bayesify.core.score import (
    ContractError,
    ScoreMeta,
    StepCalc,
    coverage_quality_from_weighted_steps,
    score,
)

_RUBRIC = load_rubric()
_META = ScoreMeta(engine_version="ev", cost_ledger=CostLedger())
_SUB = _RUBRIC.scoring.sub_score
_LOW = _RUBRIC.scoring.low_confidence_threshold


def _facts(**over) -> GateFacts:
    base = dict(
        inference_method=InferenceMethod.mcmc,
        n_models=1,
        bf_claimed=False,
        prior_informativeness=PriorInformativeness.default,
    )
    base.update(over)
    return GateFacts(**base)


def _assessments(
    paper_classes: list[PaperClassLabel],
    gate_facts: GateFacts,
    statuses: dict[str, StepStatus] | None = None,
    *,
    confidence: float = 0.9,
) -> list[StepAssessment]:
    """A full, applicability-consistent StepAssessment list (one per rubric step). Applicable steps
    default to adequate unless overridden; N/A steps get not_applicable."""
    statuses = statuses or {}
    out = []
    for step in _RUBRIC.steps:
        ap = step_applicability_for_labels(step, paper_classes, gate_facts)
        status = (
            statuses.get(step.id, StepStatus.adequate)
            if ap.applicable
            else StepStatus.not_applicable
        )
        out.append(
            StepAssessment(
                step_id=step.id,
                applicable=ap.applicable,
                applicability_reason=ap.reason,
                status=status,
                confidence=confidence,
            )
        )
    return out


def _relevance(label=RelevanceLabel.yes) -> Relevance:
    refs = [] if label is RelevanceLabel.no else [0]
    return Relevance(label=label, confidence=0.9, rationale="ok", evidence_refs=refs)


_EMPIRICAL = PaperClass(
    labels=[PaperClassLabel.data_analysis], confidence=0.9, rationale="real data", evidence_refs=[0]
)


def _score(paper_class, gate_facts, statuses=None, *, confidence=0.9, relevance=None):
    return score(
        relevance or _relevance(),
        paper_class,
        _assessments(paper_class.labels, gate_facts, statuses, confidence=confidence),
        gate_facts,
        _RUBRIC,
        _META,
    )


# --- golden tables -------------------------------------------------------------------------------


def test_all_adequate_is_full_coverage_and_quality() -> None:
    r = _score(_EMPIRICAL, _facts())
    assert r.coverage.strict == 1.0 and r.coverage.lenient == 1.0
    assert r.coverage.present == r.coverage.applicable == r.profile.n_applicable
    assert r.quality_score == pytest.approx(1.0)


def test_high_confidence_absence_lowers_coverage_without_a_range() -> None:
    r = _score(_EMPIRICAL, _facts(), {"S5": StepStatus.missing}, confidence=0.95)
    n = r.coverage.applicable
    assert r.coverage.strict == pytest.approx((n - 1) / n)
    assert r.coverage.strict == r.coverage.lenient  # high-confidence absence: no range
    assert r.profile.n_uncertain == 0


def test_low_confidence_absence_widens_the_range_instead() -> None:
    r = _score(_EMPIRICAL, _facts(), {"S5": StepStatus.missing}, confidence=0.3)
    assert r.coverage.strict < r.coverage.lenient  # uncertain → honest range
    assert r.profile.n_uncertain == 1


def test_na_step_is_excluded_from_the_denominator() -> None:
    # analytic posterior → S4 N/A; quality/coverage identical to the same paper minus S4.
    analytic = _score(_EMPIRICAL, _facts(inference_method=InferenceMethod.exact_analytic))
    s4 = next(s for s in analytic.profile.steps if s.step_id == "S4")
    assert s4.applicable is False and s4.sub_score is None
    assert analytic.quality_score == pytest.approx(1.0)  # all-adequate minus an N/A step
    assert analytic.coverage.applicable == analytic.profile.n_applicable


def test_bf_claim_escalates_s8_to_expected_tier() -> None:
    r = _score(_EMPIRICAL, _facts(bf_claimed=True))
    s8 = next(s for s in r.profile.steps if s.step_id == "S8")
    assert s8.tier is ExpectationTier.expected  # gate G6 escalation, even for an empirical paper


def test_score_is_byte_identical_across_runs() -> None:
    a = _score(_EMPIRICAL, _facts())
    b = _score(_EMPIRICAL, _facts())
    assert a.model_dump_json() == b.model_dump_json()


# --- score-impact reachability -------------------------------------------------------------------


def test_every_score_impact_is_reachable() -> None:
    statuses = {"S5": StepStatus.missing, "S9": StepStatus.partial}
    base = _score(_EMPIRICAL, _facts(), statuses, confidence=0.95)
    for impact in base.score_impacts:
        upgraded = dict(statuses)
        upgraded[impact.step_id] = StepStatus.adequate
        after = _score(_EMPIRICAL, _facts(), upgraded, confidence=0.95)
        assert after.coverage.strict - base.coverage.strict == pytest.approx(impact.coverage_delta)
        assert after.quality_score - base.quality_score == pytest.approx(impact.quality_delta)
    assert any(i.step_id == "S5" for i in base.score_impacts)  # the missing step is upgradable


# --- contract errors -----------------------------------------------------------------------------


def test_irrelevant_paper_raises() -> None:
    with pytest.raises(ContractError):
        _score(_EMPIRICAL, _facts(), relevance=_relevance(RelevanceLabel.no))


def test_empty_assessments_raises() -> None:
    with pytest.raises(ContractError):
        score(_relevance(), _EMPIRICAL, [], _facts(), _RUBRIC, _META)


def test_missing_step_assessment_raises() -> None:
    full = _assessments([PaperClassLabel.data_analysis], _facts())
    with pytest.raises(ContractError):
        score(_relevance(), _EMPIRICAL, full[:-1], _facts(), _RUBRIC, _META)  # drop S10


def test_applicability_mismatch_raises() -> None:
    full = _assessments([PaperClassLabel.data_analysis], _facts())
    # flip S1 (always applicable) to applicable=False → disagrees with the resolver
    bad = [
        a.model_copy(update={"applicable": False, "status": StepStatus.not_applicable})
        if a.step_id == "S1"
        else a
        for a in full
    ]
    with pytest.raises(ContractError):
        score(_relevance(), _EMPIRICAL, bad, _facts(), _RUBRIC, _META)


# --- property tests over the scoring arithmetic --------------------------------------------------

_STATUSES = [StepStatus.adequate, StepStatus.partial, StepStatus.missing]
_ORDER = {StepStatus.missing: 0, StepStatus.partial: 1, StepStatus.adequate: 2}


@st.composite
def _calc(draw) -> StepCalc:
    applicable = draw(st.booleans())
    status = draw(st.sampled_from(_STATUSES)) if applicable else StepStatus.not_applicable
    weight = draw(st.floats(min_value=0.1, max_value=5.0))
    confidence = draw(st.floats(min_value=0.0, max_value=1.0))
    return StepCalc(applicable, status, weight, confidence)


_calcs = st.lists(_calc(), min_size=0, max_size=12)


@given(_calcs)
def test_uncertainty_honesty(calcs) -> None:
    cov, _ = coverage_quality_from_weighted_steps(calcs, _SUB, _LOW)
    if cov is not None:
        assert cov.strict <= cov.lenient + 1e-9
        no_uncertain = all(
            not (c.applicable and c.status is StepStatus.missing and c.confidence < _LOW)
            for c in calcs
        )
        if no_uncertain:
            assert cov.strict == pytest.approx(cov.lenient)


@given(_calcs)
def test_na_step_never_penalises(calcs) -> None:
    cov, q = coverage_quality_from_weighted_steps(calcs, _SUB, _LOW)
    na = StepCalc(False, StepStatus.not_applicable, 1.0, 1.0)
    cov2, q2 = coverage_quality_from_weighted_steps([*calcs, na], _SUB, _LOW)
    # adding an N/A step changes nothing about coverage/quality
    assert (cov is None) == (cov2 is None)
    if cov is not None:
        assert cov2.strict == pytest.approx(cov.strict)
        assert cov2.lenient == pytest.approx(cov.lenient)
        assert q2 == pytest.approx(q)


@given(_calcs, st.integers(min_value=0, max_value=11))
def test_upgrading_a_step_never_lowers_scores(calcs, idx) -> None:
    if not calcs:
        return
    i = idx % len(calcs)
    c = calcs[i]
    if not c.applicable or c.status is StepStatus.adequate:
        return
    better = StepStatus.partial if c.status is StepStatus.missing else StepStatus.adequate
    base_cov, base_q = coverage_quality_from_weighted_steps(calcs, _SUB, _LOW)
    up = list(calcs)
    up[i] = StepCalc(True, better, c.weight, c.confidence)
    up_cov, up_q = coverage_quality_from_weighted_steps(up, _SUB, _LOW)
    assert up_cov.strict >= base_cov.strict - 1e-9
    assert up_q >= base_q - 1e-9
