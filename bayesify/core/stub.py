"""The M1 stub engine.

Returns a fixed, hand-authored :class:`ScoredResult` — the canonical fixture the always-working app
demos behind (plans 02-mvp/g §M1). Every later component (a-f) lands by replacing a slice of this
stub; the API and the report UI are built and reviewed against it now.

The content models a plausible empirical comp-cog-sci paper (a hierarchical drift-diffusion model fit
to behavioural data) so the report has realistic shape: a mix of done-well / partial / missing /
N-A steps, an uncertainty-honest coverage range, dual grounding (evidence spans + literature
standards), and severity-tiered suggestions. It is **not** a real assessment — ``validation_ref`` is
``"unvalidated"`` and the report UI labels it a stub.
"""

from __future__ import annotations

from collections.abc import Iterable

from bayesify.core import schema as s
from bayesify.core.detectors import catalog_fingerprint
from bayesify.core.prompts import prompt_set_fingerprint
from bayesify.core.rubric import load_rubric
from bayesify.core.versioning import compute_engine_version

# Fold the real detector catalog and prompt set into the engine version (G1): a detector or prompt
# change now invalidates the result cache.
_ENGINE_VERSION = compute_engine_version(
    detector_catalog=catalog_fingerprint(), prompt_set=prompt_set_fingerprint()
).compact
_RUBRIC_VERSION = load_rubric().rubric_version  # the default (synthesis) rubric's version

# Public aliases — the real engine version / rubric version the screened pipeline (M4) stamps onto
# its results and short-circuits.
ENGINE_VERSION = _ENGINE_VERSION
RUBRIC_VERSION = _RUBRIC_VERSION


def _ev(
    detector_id: str, kind: s.EvidenceKind, section_id: str, page: int, quote: str
) -> s.Evidence:
    return s.Evidence(
        detector_id=detector_id,
        detector_version="stub",
        kind=kind,
        span=s.EvidenceSpan(section_id=section_id, page=page, quote=quote),
    )


def _std(
    source_id: str, citation: str, verified: bool, locator: str | None = None
) -> s.StandardRef:
    return s.StandardRef(source_id=source_id, citation=citation, verified=verified, locator=locator)


def _assessments() -> list[s.StepAssessment]:
    return [
        s.StepAssessment(
            step_id="S1",
            applicable=True,
            applicability_reason="Essential for all paper types.",
            status=s.StepStatus.adequate,
            confidence=0.9,
            evidence=[
                _ev(
                    "workflow.model_spec",
                    s.EvidenceKind.workflow_signal,
                    "s03",
                    4,
                    "We model single-trial RTs with a hierarchical drift-diffusion model (HDDM).",
                ),
            ],
            standards=[_std("gelman2020", "Gelman et al. 2020, Bayesian Workflow", verified=True)],
            did_well=[
                "The generative model is stated explicitly (§3.1) and its drift/boundary parameters "
                "are tied to the experimental manipulation — exactly what S1 asks for.",
            ],
            suggestions=[],
            adversarial_verdict=s.AdversarialVerdict(challenged=False, refuted=False),
        ),
        s.StepAssessment(
            step_id="S2",
            applicable=True,
            applicability_reason="Priors are non-trivial (hierarchical model).",
            status=s.StepStatus.partial,
            confidence=0.8,
            evidence=[
                _ev(
                    "method.prior_mention",
                    s.EvidenceKind.method_mention,
                    "s03",
                    5,
                    "Group-level priors were weakly informative (Normal(0, 1) on standardized scales).",
                ),
            ],
            standards=[
                _std("barg2021", "Kruschke 2021, BARG", verified=True, locator="Step 1"),
                _std("wambs2017", "Depaoli & van de Schoot 2017, WAMBS", verified=True),
            ],
            did_well=["All priors are listed in Table 1 with their distributional forms."],
            suggestions=[
                s.Suggestion(
                    severity=s.Severity.warning,
                    text="Priors are stated but their choice is not justified against domain knowledge.",
                    how_to="Add one sentence per prior explaining the scale (e.g. why Normal(0,1) is "
                    "weakly informative on the standardized drift rate). Cite a source for any "
                    "informative prior.",
                    ease=s.Ease.low,
                ),
            ],
            adversarial_verdict=s.AdversarialVerdict(challenged=False, refuted=False),
        ),
        s.StepAssessment(
            step_id="S3",
            applicable=True,
            applicability_reason="Recommended for empirical work; small-data hierarchical model.",
            status=s.StepStatus.missing,
            confidence=0.45,  # low confidence → contributes to the uncertainty range, not a hard absence
            evidence=[
                s.Evidence(
                    detector_id="assess.where_looked",
                    detector_version="stub",
                    kind=s.EvidenceKind.absence_search,
                    span=s.EvidenceSpan(
                        section_id="s03", page=5, quote="searched Methods, Results, and Supplement"
                    ),
                ),
            ],
            standards=[
                _std(
                    "gabry2019",
                    "Gabry et al. 2019, Visualization in Bayesian workflow",
                    verified=True,
                )
            ],
            did_well=[],
            suggestions=[
                s.Suggestion(
                    severity=s.Severity.info,
                    text="No prior predictive check found — but it may live in an unparsed figure or "
                    "supplement (low confidence).",
                    how_to="Simulate datasets from the prior before fitting and confirm implied RTs are "
                    "plausible (e.g. not negative, within human range).",
                    ease=s.Ease.medium,
                ),
            ],
            adversarial_verdict=s.AdversarialVerdict(
                challenged=True,
                refuted=False,
                notes="Refutation pass searched the supplement and figure captions; no prior predictive "
                "check found, but parsing of Fig S2 was incomplete — hence low confidence.",
            ),
        ),
        s.StepAssessment(
            step_id="S4",
            applicable=True,
            applicability_reason="MCMC/NUTS inference used.",
            status=s.StepStatus.adequate,
            confidence=0.92,
            evidence=[
                _ev(
                    "diag.rhat_value",
                    s.EvidenceKind.diagnostic_value,
                    "s05",
                    8,
                    "All R-hat < 1.01 and bulk-ESS > 1500 for every parameter.",
                ),
                _ev(
                    "diag.divergences",
                    s.EvidenceKind.diagnostic_value,
                    "s05",
                    8,
                    "No divergent transitions were observed across 4 chains.",
                ),
            ],
            standards=[
                _std("barg2021", "Kruschke 2021, BARG", verified=True, locator="Step 2.B-C"),
                _std("vehtari2021", "Vehtari et al. 2021, Improved R-hat", verified=False),
            ],
            did_well=[
                "Reports both convergence (R-hat) and resolution (ESS) for every parameter, and states "
                "the divergence count — the two-diagnostic standard BARG requires.",
            ],
            suggestions=[],
            adversarial_verdict=s.AdversarialVerdict(challenged=False, refuted=False),
        ),
        s.StepAssessment(
            step_id="S5",
            applicable=True,
            applicability_reason="Essential for empirical data analysis.",
            status=s.StepStatus.partial,
            confidence=0.75,
            evidence=[
                _ev(
                    "workflow.ppc",
                    s.EvidenceKind.workflow_signal,
                    "s06",
                    10,
                    "Posterior predictive RT distributions are overlaid on the data in Fig 4.",
                ),
            ],
            standards=[_std("gabry2019", "Gabry et al. 2019", verified=True)],
            did_well=["A graphical posterior predictive check (Fig 4) is shown."],
            suggestions=[
                s.Suggestion(
                    severity=s.Severity.warning,
                    text="The PPC is shown but discrepancies in the tails are not discussed.",
                    how_to="Comment on the systematic under-fit of slow RTs visible in Fig 4, and say "
                    "whether it affects the conclusions.",
                    ease=s.Ease.low,
                ),
            ],
            adversarial_verdict=s.AdversarialVerdict(challenged=False, refuted=False),
        ),
        s.StepAssessment(
            step_id="S6",
            applicable=False,
            applicability_reason="Only one model is entertained and no Bayes factor is reported.",
            status=s.StepStatus.not_applicable,
            confidence=0.85,
            adversarial_verdict=None,
        ),
        s.StepAssessment(
            step_id="S7",
            applicable=False,
            applicability_reason="Routine empirical fit of a standard model with reliable self-diagnostics.",
            status=s.StepStatus.not_applicable,
            confidence=0.7,
            adversarial_verdict=None,
        ),
        s.StepAssessment(
            step_id="S8",
            applicable=True,
            applicability_reason="Weakly-informative priors used; sensitivity is expected.",
            status=s.StepStatus.missing,
            confidence=0.85,
            evidence=[
                s.Evidence(
                    detector_id="assess.where_looked",
                    detector_version="stub",
                    kind=s.EvidenceKind.absence_search,
                    span=s.EvidenceSpan(
                        section_id="s07",
                        page=12,
                        quote="searched Methods, Results, Discussion, and Supplement",
                    ),
                ),
            ],
            standards=[_std("wambs2017", "WAMBS-v2, point 9", verified=True)],
            did_well=[],
            suggestions=[
                s.Suggestion(
                    severity=s.Severity.error,
                    text="No prior-sensitivity analysis, despite weakly-informative priors on the "
                    "group-level scales.",
                    how_to="Re-fit under at least one alternative prior (e.g. a wider scale) and report "
                    "whether the substantive conclusions change. Report it regardless of outcome.",
                    ease=s.Ease.medium,
                ),
            ],
            adversarial_verdict=s.AdversarialVerdict(
                challenged=True,
                refuted=False,
                notes="Refutation pass found no sensitivity analysis in any parsed section.",
            ),
        ),
        s.StepAssessment(
            step_id="S9",
            applicable=True,
            applicability_reason="Essential for all paper types.",
            status=s.StepStatus.adequate,
            confidence=0.88,
            evidence=[
                _ev(
                    "open_science.code",
                    s.EvidenceKind.open_science,
                    "s08",
                    14,
                    "Data and analysis code are available at https://osf.io/xxxxx.",
                ),
                _ev(
                    "sampler.config",
                    s.EvidenceKind.sampler_config,
                    "s05",
                    8,
                    "4 chains, 2000 warmup + 2000 sampling iterations, seed fixed.",
                ),
            ],
            standards=[_std("barg2021", "Kruschke 2021, BARG", verified=True, locator="Step 6")],
            did_well=[
                "Software + versions, full sampler settings, and an OSF link to data and code are all "
                "reported — the paper is reproducible.",
            ],
            suggestions=[],
            adversarial_verdict=s.AdversarialVerdict(challenged=False, refuted=False),
        ),
        s.StepAssessment(
            step_id="S10",
            applicable=True,
            applicability_reason="Essential for all paper types.",
            status=s.StepStatus.adequate,
            confidence=0.86,
            evidence=[
                _ev(
                    "workflow.posterior_summary",
                    s.EvidenceKind.workflow_signal,
                    "s06",
                    11,
                    "We report posterior means and 95% credible intervals for all effects.",
                ),
            ],
            standards=[_std("barg2021", "Kruschke 2021, BARG", verified=True, locator="Step 3")],
            did_well=[
                "Effects are reported with 95% credible intervals and no over-claiming beyond the posterior."
            ],
            suggestions=[],
            adversarial_verdict=s.AdversarialVerdict(challenged=False, refuted=False),
        ),
    ]


_SUBSCORE = {s.StepStatus.adequate: 1.0, s.StepStatus.partial: 0.5, s.StepStatus.missing: 0.0}
_TIER = {  # which steps are tier-1 "expected" for an empirical paper (drives severity, not a verdict)
    "S1": s.ExpectationTier.expected,
    "S2": s.ExpectationTier.expected,
    "S3": s.ExpectationTier.recommended,
    "S4": s.ExpectationTier.expected,
    "S5": s.ExpectationTier.expected,
    "S8": s.ExpectationTier.recommended,
    "S9": s.ExpectationTier.expected,
    "S10": s.ExpectationTier.expected,
}
_LOW_CONFIDENCE = 0.5  # below this, an absence is "uncertain" (widens the coverage range)


def build_stub_result(mode: str = "full") -> s.ScoredResult:
    assessments = _assessments()
    applicable = [a for a in assessments if a.applicable]
    n_na = len(assessments) - len(applicable)

    profile_steps: list[s.StepProfile] = []
    present = 0
    uncertain = 0
    quality_num = 0.0
    for a in assessments:
        sub = None if not a.applicable else _SUBSCORE[a.status]
        profile_steps.append(
            s.StepProfile(
                step_id=a.step_id,
                applicable=a.applicable,
                status=a.status,
                sub_score=sub,
                weight=1.0,
                tier=_TIER.get(a.step_id, s.ExpectationTier.none),
            )
        )
        if not a.applicable:
            continue
        quality_num += sub or 0.0
        if a.status in (s.StepStatus.adequate, s.StepStatus.partial):
            present += 1
        elif a.status is s.StepStatus.missing and a.confidence < _LOW_CONFIDENCE:
            uncertain += 1

    n_app = len(applicable)
    coverage = s.Coverage(
        present=present,
        applicable=n_app,
        strict=present / n_app,
        lenient=(present + uncertain) / n_app,
    )

    return s.ScoredResult(
        relevance=s.Relevance(
            label=s.RelevanceLabel.yes,
            confidence=0.95,
            rationale="The paper fits a hierarchical Bayesian model (HDDM) to behavioural data with "
            "MCMC inference — squarely a Bayesian-workflow paper.",
            evidence_refs=[0, 1],
        ),
        paper_class=s.PaperClass(
            primary=s.PaperClassLabel.empirical,
            confidence=0.88,
            rationale="Fits a Bayesian model to real observed data to draw substantive conclusions.",
            evidence_refs=[0],
        ),
        gate_facts=s.GateFacts(
            inference_method=s.InferenceMethod.mcmc,
            n_models=1,
            bf_claimed=False,
            prior_informativeness=s.PriorInformativeness.weakly_informative,
        ),
        step_assessments=assessments,
        profile=s.Profile(
            steps=profile_steps, n_applicable=n_app, n_na=n_na, n_uncertain=uncertain
        ),
        coverage=coverage,
        quality_score=round(quality_num / n_app, 3),
        score_impacts=[
            s.ScoreImpact(
                step_id="S8",
                from_status=s.StepStatus.missing,
                to_status=s.StepStatus.adequate,
                coverage_delta=1 / n_app,
                quality_delta=round(1.0 / n_app, 3),
            ),
            s.ScoreImpact(
                step_id="S5",
                from_status=s.StepStatus.partial,
                to_status=s.StepStatus.adequate,
                coverage_delta=0.0,
                quality_delta=round(0.5 / n_app, 3),
            ),
        ],
        engine_version=_ENGINE_VERSION,
        rubric_version=_RUBRIC_VERSION,
        rubric_profile="synthesis",
        cost_ledger=s.CostLedger(
            entries=[
                s.CostLedgerEntry(
                    stage="screen",
                    model="claude-haiku-4-5",
                    input_tokens=4200,
                    output_tokens=180,
                    cost_usd=0.0051,
                ),
                s.CostLedgerEntry(
                    stage="classify",
                    model="claude-haiku-4-5",
                    input_tokens=3900,
                    output_tokens=210,
                    cost_usd=0.0049,
                ),
                s.CostLedgerEntry(
                    stage="assess",
                    model="claude-opus-4-8",
                    input_tokens=38000,
                    output_tokens=4200,
                    cost_usd=0.295,
                ),
            ],
            total_tokens=50690,
            total_cost_usd=0.305,
        ),
        validation_ref="unvalidated",
    )


def cost_ledger(entries: Iterable[s.CostLedgerEntry]) -> s.CostLedger:
    """Roll a sequence of cost entries into a ``CostLedger`` with totals."""
    items = list(entries)
    return s.CostLedger(
        entries=items,
        total_tokens=sum(e.input_tokens + e.output_tokens for e in items),
        total_cost_usd=round(sum(e.cost_usd for e in items), 6),
    )
