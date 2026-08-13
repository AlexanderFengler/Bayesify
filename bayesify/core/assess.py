"""Assess (component e, stage 6) — the grounded + adversarial per-step judge.

For each applicable rubric step an LLM judge, conditioned on the mapped detector evidence and the
relevant excerpts (never a vacuum), produces a grounded ``StepAssessment``; then an adversarial
refuter attacks every negative finding (``missing``/``partial``) over a *wider* slice (supplements,
captions, synonym wordings) before anything is reported — A3's dual grounding and A4's
anti-false-absence guarantee. Non-applicable steps cost zero LLM calls.

e also mints the ``GateFacts`` (from ``PaperClass`` + detector evidence) that f-score consumes, and
the engine-constructed ``absence_search`` where-looked enumeration on every ``missing`` finding.

The step→detector map and per-step synonym lists live here as v0 constants; they belong in
``rubric/steps.yaml`` at the v1 freeze (noted, not blocking).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from bayesify.core import config
from bayesify.core.context import assessment_context, evidence_digest
from bayesify.core.prompts import ASSESS_JUDGE_SYSTEM, ASSESS_REFUTE_SYSTEM
from bayesify.core.quotes import sentence_span
from bayesify.core.rubric.applicability import step_applicability_for_labels
from bayesify.core.rubric.models import RubricSpec, RubricStep
from bayesify.core.schema import (
    AdversarialVerdict,
    CostLedgerEntry,
    Ease,
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    ExpectationTier,
    GateFacts,
    InferenceMethod,
    PaperClass,
    PriorInformativeness,
    Section,
    Severity,
    StandardRef,
    StepAssessment,
    StepStatus,
    Suggestion,
)
from bayesify.llm import LLMClient, call_with_policy, ledger_entry
from bayesify.llm import config as llm_config


class AssessError(RuntimeError):
    """A per-step judgment could not be produced (bad status, exhausted retries). Fail loud."""


# --- LLM structured-output schemas (internal to e; mapped onto the StepAssessment contract) ------


class JudgeSuggestion(BaseModel):
    text: str
    how_to: str = ""
    ease: str = "medium"  # low | medium | high


class StepJudgment(BaseModel):
    status: str  # adequate | partial | missing
    confidence: float = 0.5
    rationale: str = ""
    evidence_quotes: list[str] = Field(default_factory=list)  # verbatim substrings of the excerpts
    standard_ids: list[str] = Field(default_factory=list)  # chosen from the candidate ids
    did_well: list[str] = Field(default_factory=list)
    suggestions: list[JudgeSuggestion] = Field(default_factory=list)


class RefuterVerdict(BaseModel):
    refuted: bool = False
    notes: str = ""
    rescuing_quote: str | None = None
    upgraded_status: str | None = None  # partial | adequate when refuted


_STEP_DETECTORS: dict[str, list[str]] = {
    "S1": ["software.", "method."],
    "S2": ["method.prior"],
    "S3": ["workflow.prior_predictive"],
    "S4": ["diag.", "sampler.chains", "sampler.iterations", "sampler.warmup", "method.mcmc",
           "method.variational"],
    "S5": ["workflow.posterior_predictive"],
    "S6": ["diag.loo_waic", "diag.pareto_k", "method.bayes_factor"],
    "S7": ["workflow.sbc", "workflow.recovery"],
    "S8": ["workflow.sensitivity"],
    "S9": ["open.", "sampler.seed", "software."],
    "S10": ["method.credible_interval", "method.posterior"],
}
_STEP_SYNONYMS: dict[str, list[str]] = {
    "S3": ["prior predictive", "prior simulation", "prior pushforward"],
    "S5": ["posterior predictive", "PPC", "retrodictive check", "model-fit check"],
    "S7": ["simulation-based calibration", "SBC", "parameter recovery", "rank histogram"],
    "S8": ["sensitivity analysis", "robustness check", "alternative prior"],
}

_STATUS = {s.value: s for s in (StepStatus.adequate, StepStatus.partial, StepStatus.missing)}
_RANK = {StepStatus.missing: 0, StepStatus.partial: 1, StepStatus.adequate: 2}
_NEGATIVE = (StepStatus.missing, StepStatus.partial)

# Detectors that imply the posterior was sampled or approximated, not closed-form. They override a
# stray "conjugate prior"/"analytic posterior" mention so a mixed-method paper is not misread as
# exact_analytic, which would wrongly gate S4 (R-hat/ESS) N/A.
_SAMPLING_EVIDENCE = frozenset(
    {
        "method.mcmc",
        "method.variational",
        "diag.rhat",
        "diag.ess",
        "diag.divergences",
        "diag.trace_plot",
        "diag.rank_plot",
        "diag.treedepth",
        "diag.bfmi",
        "diag.mcse",
        "sampler.chains",
        "sampler.iterations",
        "sampler.warmup",
    }
)


def derive_gate_facts(evidence: list[Evidence], paper_class: PaperClass) -> GateFacts:
    """Best-effort, deterministic facts that drive applicability gates (G6). n_models is not
    reliably countable from text in v0, so it defaults to 1 — EXCEPT when a model-comparison
    detector (PSIS-LOO / WAIC / Pareto-k) fired, which is reliable evidence that >=2 models were
    entertained; without this S6 (model comparison) is falsely marked N/A ('only one model') on the
    very paper whose LOO comparison the engine detected. BF / prior / inference come from detectors.
    """
    ids = {e.detector_id for e in evidence}
    classifier_inference = _inference_from_paper_class(paper_class)
    if classifier_inference is not InferenceMethod.unstated:
        inference = classifier_inference
    elif "method.analytic" in ids and not (ids & _SAMPLING_EVIDENCE):
        inference = InferenceMethod.exact_analytic
    elif "method.variational" in ids:
        inference = InferenceMethod.variational
    elif "method.mcmc" in ids:
        inference = InferenceMethod.mcmc
    else:
        inference = InferenceMethod.unstated
    compared_models = "diag.loo_waic" in ids or "diag.pareto_k" in ids
    return GateFacts(
        inference_method=inference,
        n_models=2 if compared_models else 1,
        bf_claimed="method.bayes_factor" in ids,
        prior_informativeness=_prior_informativeness(evidence),
    )


def _inference_from_paper_class(paper_class: PaperClass) -> InferenceMethod:
    # Prefer context-aware classifier answers over mention-based detectors. Keep this order aligned
    # with the older detector precedence for applicability gates that expect a single method.
    for method in (
        InferenceMethod.exact_analytic,
        InferenceMethod.variational,
        InferenceMethod.mcmc,
        InferenceMethod.sbi,
        InferenceMethod.abc,
        InferenceMethod.smc,
        InferenceMethod.laplace_inla,
        InferenceMethod.map,
        InferenceMethod.em,
    ):
        if method in paper_class.methods_used:
            return method
    if InferenceMethod.hmc_nuts in paper_class.methods_used:
        return InferenceMethod.mcmc
    return InferenceMethod.unstated


def _prior_informativeness(evidence: list[Evidence]) -> PriorInformativeness:
    quotes = " ".join(e.span.quote.lower() for e in evidence if e.detector_id == "method.prior")
    if not quotes:
        return PriorInformativeness.unstated
    if "weakly" in quotes:
        return PriorInformativeness.weakly_informative
    if "non-informative" in quotes or "noninformative" in quotes or "flat" in quotes:
        return PriorInformativeness.none
    if "informative" in quotes:
        return PriorInformativeness.informative
    if "default" in quotes:
        return PriorInformativeness.default
    return PriorInformativeness.unstated


def assess(
    parsed,
    evidence: list[Evidence],
    relevance,  # noqa: ARG001 — only yes/partial reach here; kept for the documented contract
    paper_class: PaperClass,
    rubric: RubricSpec,
    *,
    client: LLMClient,
    model: str | None = None,
    refuter_model: str | None = None,
    concurrency: int | None = None,
) -> tuple[list[StepAssessment], GateFacts, list[CostLedgerEntry]]:
    """Produce one ``StepAssessment`` per rubric step, plus the minted ``GateFacts`` and cost ledger
    entries. Raises ``AssessError`` if the judge returns an unparseable status (fail loud).

    Each applicable step is judged (and adversarially refuted) independently of every other step —
    they share only the read-only paper + evidence — so the per-step work (``_assess_one_step``) is
    fanned out across up to ``concurrency`` worker threads to overlap the I/O-bound LLM calls.
    ``concurrency`` defaults to ``config.assess_concurrency()`` (``None``); ``1`` is the strictly
    sequential path. This is a pure latency optimization: assessments and ledger entries are always
    reassembled in rubric-step order, so the result is byte-identical to the serial run.
    """
    model = model or llm_config.judge_model()
    refuter_model = refuter_model or llm_config.refuter_model()
    gate_facts = derive_gate_facts(evidence, paper_class)
    searched = _scanned_section_ids(parsed)  # paper-level; identical for every step

    # Applicability is deterministic and LLM-free; resolve it up front so the only thing that fans
    # out is the independent (and expensive) per-step judge/refute work.
    plans = [
        (step, step_applicability_for_labels(step, paper_class.labels, gate_facts))
        for step in rubric.steps
    ]
    applicable = [(step, ap) for step, ap in plans if ap.applicable]

    def run(item):
        step, ap = item
        return _assess_one_step(
            step,
            ap,
            parsed,
            evidence,
            searched,
            rubric,
            client=client,
            model=model,
            refuter_model=refuter_model,
        )

    k = concurrency if concurrency is not None else config.assess_concurrency()
    workers = min(k, len(applicable))
    if workers <= 1:
        graded = [run(item) for item in applicable]  # strictly sequential — the original path
    else:
        # ThreadPoolExecutor (stdlib) keeps the engine web-free and nests fine inside the API's
        # asyncio.to_thread(grade_parsed). map() returns in input order and, on with-block exit,
        # waits for in-flight calls before re-raising the first failure (fail loud, like the loop).
        with ThreadPoolExecutor(max_workers=workers) as pool:
            graded = list(pool.map(run, applicable))

    # Reassemble in rubric-step order regardless of completion order; N/A steps cost no LLM call.
    assessments: list[StepAssessment] = []
    cost: list[CostLedgerEntry] = []
    graded_iter = iter(graded)
    for step, ap in plans:
        if ap.applicable:
            assessment, step_cost = next(graded_iter)
            assessments.append(assessment)
            cost.extend(step_cost)
        else:
            assessments.append(_not_applicable_assessment(step, ap))

    return assessments, gate_facts, cost


def _not_applicable_assessment(step: RubricStep, ap) -> StepAssessment:
    """The zero-LLM-cost assessment for a step gated N/A for this paper class."""
    return StepAssessment(
        step_id=step.id,
        applicable=False,
        applicability_reason=ap.reason,
        status=StepStatus.not_applicable,
        confidence=1.0,
        adversarial_verdict=AdversarialVerdict(challenged=False, refuted=False),
    )


def _assess_one_step(
    step: RubricStep,
    ap,
    parsed,
    evidence: list[Evidence],
    searched: list[str],
    rubric: RubricSpec,
    *,
    client: LLMClient,
    model: str,
    refuter_model: str,
) -> tuple[StepAssessment, list[CostLedgerEntry]]:
    """Judge one applicable step, then (A4) adversarially refute it if the finding is negative.

    Self-contained over shared state — reads only ``parsed``/``evidence`` and returns this step's
    assessment plus its (judge[, refute]) ledger entries in order — so the caller may run these
    concurrently across steps. Raises ``AssessError`` on a bad judge status.
    """
    cost: list[CostLedgerEntry] = []
    step_ev = _step_evidence(step.id, evidence)
    judge = call_with_policy(
        client,
        model=model,
        system=ASSESS_JUDGE_SYSTEM,
        user=_build_judge_user(step, parsed, step_ev, rubric),
        schema=StepJudgment,
        max_tokens=1500,
    )
    cost.append(ledger_entry("assess", judge, step_id=step.id, pass_label="judge"))
    assessment = _to_assessment(step, ap, judge.parsed, parsed, step_ev, searched, rubric)

    if assessment.status in _NEGATIVE:  # A4: adversarially challenge every negative finding
        refute = call_with_policy(
            client,
            model=refuter_model,
            system=ASSESS_REFUTE_SYSTEM,
            user=_build_refuter_user(step, parsed, assessment),
            schema=RefuterVerdict,
            max_tokens=800,
        )
        cost.append(ledger_entry("assess", refute, step_id=step.id, pass_label="refute"))
        assessment = _apply_refutation(assessment, refute.parsed, parsed)
    else:
        assessment = assessment.model_copy(
            update={"adversarial_verdict": AdversarialVerdict(challenged=False, refuted=False)}
        )
    return assessment, cost


def _build_judge_user(
    step: RubricStep, parsed, step_ev: list[Evidence], rubric: RubricSpec
) -> str:
    thresholds = "\n".join(f"  - {n}: {t.value} ({t.source})" for n, t in step.thresholds.items())
    candidates = "\n".join(
        f"  - {sid}: {rubric.citations.get(sid, sid)}" for sid in step.citations
    ) or "  (none)"
    return (
        f"RUBRIC STEP {step.id}: {step.name}\n"
        f"ADEQUATE: {step.adequate}\n"
        f"MISSING: {step.missing}\n"
        + (f"THRESHOLDS:\n{thresholds}\n" if thresholds else "")
        + f"\nCANDIDATE STANDARDS (cite by id only):\n{candidates}\n\n"
        f"DETECTOR HITS for this step:\n{evidence_digest(step_ev)}\n\n"
        f"PAPER EXCERPTS:\n{assessment_context(parsed, max_chars=config.assess_context_chars())}"
    )


def _build_refuter_user(step: RubricStep, parsed, assessment: StepAssessment) -> str:
    synonyms = ", ".join(_STEP_SYNONYMS.get(step.id, [])) or "(none)"
    wider = assessment_context(parsed, max_chars=config.assess_context_chars())
    return (
        f"RUBRIC STEP {step.id}: {step.name}\n"
        f"The first pass judged this '{assessment.status.value}'.\n"
        f"ADEQUATE means: {step.adequate}\n"
        f"Alternative wordings to search for: {synonyms}\n\n"
        f"WIDER CONTEXT (includes supplements & captions):\n{wider}"
    )


def _scanned_section_ids(parsed) -> list[str]:
    return [s.id for s in parsed.sections if s.kind.value != "references" and s.text]


def _step_evidence(step_id: str, evidence: list[Evidence]) -> list[Evidence]:
    prefixes = _STEP_DETECTORS.get(step_id, [])
    return [e for e in evidence if any(e.detector_id.startswith(p) for p in prefixes)]


def _to_assessment(
    step: RubricStep,
    ap,
    judgment: StepJudgment,
    parsed,
    step_ev: list[Evidence],
    searched: list[str],
    rubric: RubricSpec,
) -> StepAssessment:
    status = _STATUS.get(judgment.status)
    if status is None:
        raise AssessError(f"{step.id}: judge returned an invalid status {judgment.status!r}")

    evidence = _dedupe_spans(
        list(step_ev) + _judge_quote_evidence(judgment.evidence_quotes, parsed.sections)
    )
    if status is StepStatus.missing:
        evidence.append(_absence_search(searched, parsed))

    suggestions = [
        Suggestion(
            severity=_severity(ap.tier, status),
            text=s.text,
            how_to=s.how_to,
            ease=_ease(s.ease),
        )
        for s in judgment.suggestions
    ]
    return StepAssessment(
        step_id=step.id,
        applicable=True,
        applicability_reason=ap.reason,
        status=status,
        confidence=_clamp(judgment.confidence),
        evidence=evidence,
        standards=_resolve_standards(step, judgment.standard_ids, rubric),
        did_well=[d for d in judgment.did_well if d.strip()],
        suggestions=suggestions,
        adversarial_verdict=None,  # set by the caller (positive) or _apply_refutation (negative)
    )


def _trim_to_sentence(text: str, limit: int = 400) -> str:
    """Trim to <= ``limit`` chars WITHOUT cutting mid-word: prefer the last sentence terminator in
    the window, else the last word boundary (marked with an ellipsis). Replaces a blind character
    slice that produced dangling fragments — a safety net under the prompt's own brevity request."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    window = text[:limit]
    end = max(window.rfind("."), window.rfind("!"), window.rfind("?"))
    if end >= limit // 2:  # a sentence ends reasonably far in → cut there, keep the terminator
        return window[: end + 1]
    cut = window.rfind(" ")
    return (window[:cut] if cut > 0 else window) + "…"


def _apply_refutation(
    assessment: StepAssessment, verdict: RefuterVerdict, parsed
) -> StepAssessment:
    notes = _trim_to_sentence(verdict.notes)
    if not verdict.refuted:
        survived = AdversarialVerdict(challenged=True, refuted=False, notes=notes)
        return assessment.model_copy(update={"adversarial_verdict": survived})

    new_status = _STATUS.get(verdict.upgraded_status or "") or _bump(assessment.status)
    if _RANK[new_status] <= _RANK[assessment.status]:
        new_status = _bump(assessment.status)  # a refutation must not downgrade

    evidence = [e for e in assessment.evidence if e.kind is not EvidenceKind.absence_search]
    if verdict.rescuing_quote:
        evidence = _dedupe_spans(
            evidence + _judge_quote_evidence([verdict.rescuing_quote], parsed.sections)
        )
    suggestions = [] if new_status is StepStatus.adequate else assessment.suggestions
    return assessment.model_copy(
        update={
            "status": new_status,
            "evidence": evidence,
            "suggestions": suggestions,
            "adversarial_verdict": AdversarialVerdict(challenged=True, refuted=True, notes=notes),
        }
    )


def _severity(tier: ExpectationTier, status: StepStatus) -> Severity:
    if status is StepStatus.missing:
        if tier is ExpectationTier.expected:
            return Severity.error
        return Severity.warning if tier is ExpectationTier.recommended else Severity.info
    if status is StepStatus.partial:
        return Severity.warning if tier is ExpectationTier.expected else Severity.info
    return Severity.info


def _ease(value: str) -> Ease:
    try:
        return Ease(value.strip().lower())
    except ValueError:
        return Ease.medium


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _bump(status: StepStatus) -> StepStatus:
    return StepStatus.partial if status is StepStatus.missing else StepStatus.adequate


def _dedupe_spans(evidence: list[Evidence]) -> list[Evidence]:
    """Collapse evidence items whose (section, quote) span is identical, keeping the first.
    Sentence-aligned quotes (#90) made distinct detectors on one sentence — and judge quotes
    expanded onto it — render as verbatim repeats in "In the paper" (#91). Display-level identity
    only: the global Evidence[] and evidence_refs are untouched."""
    seen: set[tuple[str, str]] = set()
    out: list[Evidence] = []
    for e in evidence:
        key = (e.span.section_id, e.span.quote)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def _judge_quote_evidence(quotes: list[str], sections: list[Section]) -> list[Evidence]:
    out: list[Evidence] = []
    for raw in quotes:
        q = raw.strip()
        sec = next((s for s in sections if q and q in s.text), None)
        if sec:
            # The model verifiably quoted the paper, but usually a clause fragment — expand to the
            # enclosing sentence(s) so "In the paper" reads coherently (still a verbatim substring).
            i = sec.text.find(q)
            quote = sentence_span(sec.text, i, i + len(q))
            out.append(
                Evidence(
                    detector_id="assess.judge",
                    detector_version="0",
                    kind=EvidenceKind.judge_quote,
                    span=EvidenceSpan(section_id=sec.id, page=None, quote=quote),
                )
            )
    return out


def _absence_search(searched: list[str], parsed) -> Evidence:
    top = next((s for s in parsed.sections if s.id in searched and s.text), None)
    sid = top.id if top else (parsed.sections[0].id if parsed.sections else "s00")
    # The first sentence of the searched section (was a blind [:80] slice — always a fragment).
    quote = (
        sentence_span(top.text, 0, 0, max_chars=200) if top and top.text else "(no text searched)"
    )
    return Evidence(
        detector_id="assess.where_looked",
        detector_version="0",
        kind=EvidenceKind.absence_search,
        value={"searched_sections": list(searched)},
        span=EvidenceSpan(section_id=sid, page=None, quote=quote),
    )


def _resolve_standards(
    step: RubricStep, selected_ids: list[str], rubric: RubricSpec
) -> list[StandardRef]:
    candidates: dict[str, StandardRef] = {}
    for sid in step.citations:
        if sid in rubric.citations:
            verified = any(t.source == sid and t.verified for t in step.thresholds.values())
            candidates[sid] = StandardRef(
                source_id=sid, citation=rubric.citations[sid], verified=verified, locator=None
            )
    return [candidates[sid] for sid in selected_ids if sid in candidates]  # unknown ids rejected
