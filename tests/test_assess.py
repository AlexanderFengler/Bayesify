"""e-assess (M5 slice 3): gating, grounded judge, adversarial refutation, absence-search.

Driven by a schema-aware fake (returns a StepJudgment for judge calls, a RefuterVerdict for refuter
calls) — no network. The live planted-evidence / decoy-negative evals are a separate merge gate.
"""

from __future__ import annotations

from datetime import datetime

from veribayes.core import assess as A
from veribayes.core.assess import RefuterVerdict, StepJudgment, derive_gate_facts
from veribayes.core.llm import LLMResponse
from veribayes.core.rubric.loader import load_rubric
from veribayes.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    InferenceMethod,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    PriorInformativeness,
    Relevance,
    RelevanceLabel,
    Section,
    SectionKind,
    Severity,
    SourceDoc,
    StepStatus,
)

_RUBRIC = load_rubric()
_WHEN = datetime(2026, 1, 1)


class _Fake:
    """Returns a judgment for StepJudgment calls and a verdict for RefuterVerdict calls. ``judge`` /
    ``refute`` are callables (step kwargs) -> model instance, or fixed instances."""

    def __init__(self, judge, refute=None) -> None:
        self._judge = judge
        self._refute = refute or RefuterVerdict(refuted=False, notes="genuinely absent")
        self.calls: list[dict] = []

    def complete(self, *, model, system, user, schema, max_tokens=1024):
        self.calls.append({"schema": schema.__name__, "user": user})
        if schema.__name__ == "StepJudgment":
            parsed = self._judge(user) if callable(self._judge) else self._judge
        else:
            parsed = self._refute(user) if callable(self._refute) else self._refute
        return LLMResponse(parsed=parsed, model=model, input_tokens=50, output_tokens=20)


def _parsed(*sections: tuple[SectionKind, str, str]) -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="t", source="upload", fetched_at=_WHEN)
    secs = [
        Section(id=f"s{i:02d}", kind=k, title=t, text=text)
        for i, (k, t, text) in enumerate(sections, start=1)
    ]
    return ParsedDoc(source=src, sections=secs, parser="t", parser_version="0")


def _ev(detector_id: str, kind: EvidenceKind, quote: str) -> Evidence:
    return Evidence(
        detector_id=detector_id,
        detector_version="0.1.0",
        kind=kind,
        span=EvidenceSpan(section_id="s01", page=1, quote=quote),
    )


_EMPIRICAL = PaperClass(
    primary=PaperClassLabel.empirical, confidence=0.9, rationale="real data", evidence_refs=[0]
)
_REL = Relevance(label=RelevanceLabel.yes, confidence=0.9, rationale="ok", evidence_refs=[0])


def _assess(parsed, evidence, judge, refute=None):
    client = _Fake(judge, refute)
    return (*A.assess(parsed, evidence, _REL, _EMPIRICAL, _RUBRIC, client=client), client)


# --- gate facts ----------------------------------------------------------------------------------


def test_gate_facts_from_evidence() -> None:
    ev = [
        _ev("method.mcmc", EvidenceKind.method_mention, "the NUTS sampler"),
        _ev("method.prior", EvidenceKind.method_mention, "a weakly-informative prior"),
        _ev("method.bayes_factor", EvidenceKind.method_mention, "Bayes factor of 12"),
    ]
    gf = derive_gate_facts(ev, _EMPIRICAL)
    assert gf.inference_method is InferenceMethod.hmc_nuts
    assert gf.prior_informativeness is PriorInformativeness.weakly_informative
    assert gf.bf_claimed is True


def test_gate_facts_analytic() -> None:
    ev = [_ev("method.analytic", EvidenceKind.method_mention, "conjugate prior")]
    gf = derive_gate_facts(ev, _EMPIRICAL)
    assert gf.inference_method is InferenceMethod.exact_analytic


def test_loo_detector_implies_multiple_models() -> None:
    # A PSIS-LOO / WAIC model-comparison detector firing is evidence of >=2 models, so S6 (model
    # comparison) stays applicable — not falsely N/A "only one model" on the very paper whose LOO
    # comparison the engine just detected.
    mcmc = [_ev("method.mcmc", EvidenceKind.method_mention, "NUTS")]
    assert derive_gate_facts(mcmc, _EMPIRICAL).n_models == 1  # nothing comparison-like → one model
    loo = derive_gate_facts(
        [_ev("diag.loo_waic", EvidenceKind.diagnostic_value, "PSIS-LOO model comparison")],
        _EMPIRICAL,
    )
    assert loo.n_models >= 2  # comparison detector → multi-model → S6 applicable


def test_trim_to_sentence_never_cuts_mid_word() -> None:
    short = "Step done; see §3."
    assert A._trim_to_sentence(short) == short  # under the limit → untouched

    # multi-sentence overflow → cut on a sentence boundary, no dangling fragment
    long = ("The caption shows the SBC histograms. " * 20).strip()
    out = A._trim_to_sentence(long, limit=120)
    assert len(out) <= 120 and out.endswith(".") and "…" not in out

    # a run-on with no terminator in-window → word-boundary cut + ellipsis, never mid-word
    out2 = A._trim_to_sentence("evidence " * 50, limit=50)
    assert len(out2) <= 51 and out2.endswith("…") and out2.replace("…", "").endswith("evidence")


# --- gating: N/A steps cost no LLM call ----------------------------------------------------------


def test_non_applicable_steps_make_no_llm_call() -> None:
    parsed = _parsed((SectionKind.body, "Methods", "We fit a model."))
    judge = StepJudgment(status="done_well", confidence=0.9)
    assessments, gate_facts, cost, client = _assess(parsed, [], judge)
    # S6 is N/A for an empirical paper with 1 model and no BF → no judge call for it
    s6 = next(a for a in assessments if a.step_id == "S6")
    assert s6.applicable is False and s6.status is StepStatus.not_applicable
    judged_steps = len([a for a in assessments if a.applicable])
    assert sum(1 for c in client.calls if c["schema"] == "StepJudgment") == judged_steps


# --- grounded judge → assessment -----------------------------------------------------------------


def test_done_well_maps_through_with_verified_quote_and_standard() -> None:
    parsed = _parsed(
        (SectionKind.abstract, "Abstract", "A hierarchical model with weakly-informative priors."),
        (SectionKind.body, "Methods", "All R-hat < 1.01 across 4 chains; no divergences."),
    )

    def judge(_user):
        return StepJudgment(
            status="done_well",
            confidence=0.9,
            evidence_quotes=["All R-hat < 1.01 across 4 chains"],  # verbatim in s02
            standard_ids=["barg2021"],  # a real candidate for S4
            did_well=["Reports R-hat for every parameter."],
        )

    assessments, _, _, _ = _assess(parsed, [], judge)
    s4 = next(a for a in assessments if a.step_id == "S4")
    assert s4.status is StepStatus.done_well
    quotes = [e for e in s4.evidence if e.kind is EvidenceKind.judge_quote]
    assert any("R-hat < 1.01" in e.span.quote for e in quotes)
    assert any(std.source_id == "barg2021" for std in s4.standards)
    assert s4.adversarial_verdict.challenged is False  # positive findings aren't challenged


def test_unverifiable_quote_is_dropped() -> None:
    parsed = _parsed((SectionKind.body, "Methods", "We fit a model."))

    def judge(_user):
        return StepJudgment(
            status="done_well", confidence=0.8, evidence_quotes=["NOT IN THE PAPER"]
        )

    assessments, _, _, _ = _assess(parsed, [], judge)
    s1 = next(a for a in assessments if a.step_id == "S1")
    assert not any(e.kind is EvidenceKind.judge_quote for e in s1.evidence)  # phantom quote dropped


def test_unknown_standard_id_is_rejected() -> None:
    parsed = _parsed((SectionKind.body, "Methods", "We fit a model."))

    def judge(_user):
        return StepJudgment(status="done_well", confidence=0.8, standard_ids=["not_a_real_source"])

    assessments, _, _, _ = _assess(parsed, [], judge)
    s1 = next(a for a in assessments if a.step_id == "S1")
    assert s1.standards == []


# --- severity derivation -------------------------------------------------------------------------


def test_missing_expected_step_yields_error_severity() -> None:
    parsed = _parsed((SectionKind.body, "Methods", "We fit a model."))

    def judge(_user):
        return StepJudgment(
            status="missing",
            confidence=0.9,
            suggestions=[A.JudgeSuggestion(text="Report R-hat", how_to="run it", ease="low")],
        )

    # S1 is "expected" for all classes; missing + expected → error severity (derived, not LLM-set)
    survived = RefuterVerdict(refuted=False, notes="absent")
    assessments, _, _, _ = _assess(parsed, [], judge, refute=survived)
    s1 = next(a for a in assessments if a.step_id == "S1")
    assert s1.status is StepStatus.missing
    assert s1.suggestions and s1.suggestions[0].severity is Severity.error


# --- adversarial refutation ----------------------------------------------------------------------


def test_missing_finding_always_carries_where_looked_and_is_challenged() -> None:
    parsed = _parsed((SectionKind.body, "Methods", "We fit a model with no checks."))
    judge = StepJudgment(status="missing", confidence=0.9)
    survived = RefuterVerdict(refuted=False, notes="searched supplements & captions; none")
    assessments, _, _, _ = _assess(parsed, [], judge, refute=survived)
    s1 = next(a for a in assessments if a.step_id == "S1")
    assert s1.status is StepStatus.missing
    assert any(e.kind is EvidenceKind.absence_search for e in s1.evidence)  # engine where-looked
    assert s1.adversarial_verdict.challenged is True and s1.adversarial_verdict.refuted is False


def test_refuted_absence_is_rescued_and_upgraded() -> None:
    parsed = _parsed(
        (SectionKind.body, "Methods", "Main text omits the check."),
        (SectionKind.supplement, "Supplement", "Posterior predictive checks are in Fig S3."),
    )
    judge = StepJudgment(status="missing", confidence=0.7)
    rescue = RefuterVerdict(
        refuted=True,
        notes="found in the supplement",
        rescuing_quote="Posterior predictive checks are in Fig S3.",
        upgraded_status="done_well",
    )
    assessments, _, _, _ = _assess(parsed, [], judge, refute=rescue)
    s5 = next(a for a in assessments if a.step_id == "S5")  # S5 = posterior predictive
    assert s5.status is StepStatus.done_well  # rescued
    assert s5.adversarial_verdict.refuted is True
    assert any(e.kind is EvidenceKind.judge_quote for e in s5.evidence)  # rescuing span appended
    assert not any(e.kind is EvidenceKind.absence_search for e in s5.evidence)  # no longer missing


def test_cost_ledger_meters_judge_and_refute_passes() -> None:
    parsed = _parsed((SectionKind.body, "Methods", "We fit a model."))
    judge = StepJudgment(status="missing", confidence=0.9)
    _, _, cost, _ = _assess(parsed, [], judge, refute=RefuterVerdict(refuted=False, notes="x"))
    stages = {(c.stage, c.pass_label) for c in cost}
    assert ("assess", "judge") in stages and ("assess", "refute") in stages
