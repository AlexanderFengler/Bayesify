"""The validation report builder (component h) — turn paired (human, engine) reports into the one
computed ``ValidationReport`` that every artifact derives from.

Pure and deterministic: ``build_report`` takes in-memory (``HumanReport``, ``ScoredResult``) pairs
and the rubric, extracts aligned label pairs, runs the ``metrics`` engine, and returns a single
object. Rate CIs are analytic Wilson intervals; the κ cluster-bootstrap is OFF in v0 (see the
``_kappa_ci`` seam — κ ships as point + n). The CLI (V5b) is the impure shell that loads the
pairs from disk and writes the three artifacts — all rendered from this one object, so the
demo/real watermark (``is_demo`` / ``status``) is set ONCE and no surface can disagree (the
single-computation honesty guard).

Decoupling payoff (coverage/quality): the human side is NOT a typed-in number — it is derived from
the consensus statuses via the engine's OWN arithmetic (the ``score`` coverage seam + weights), so a
human-vs-engine coverage disagreement is purely a disagreement in statuses, not in whose formula.
(Caveat, surfaced on the page: a *systematic* scoring error is then invisible in that diff — both
sides share it.)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from veribayes.core.rubric.models import RubricSpec
from veribayes.core.schema import PaperClassLabel, RelevanceLabel, ScoredResult, StepStatus
from veribayes.core.score import StepCalc, coverage_quality_from_weighted_steps, step_weight
from veribayes.core.validation.human_report import GoldTier, HumanReport
from veribayes.core.validation.metrics import (
    STATUS_ORDER,
    Interval,
    Rate,
    absence_fpr,
    absence_miss_rate,
    accuracy,
    binary_sens_spec,
    cohen_kappa,
    confusion,
    gwet_ac,
    icc_a1,
    is_sufficient,
    percent_agreement,
    weighted_kappa,
    wilson_ci,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


DEFAULT_DOMAIN_NOTE = (
    "Validated on computational-neuroscience / computational-cognitive-science samples; "
    "accuracy outside this domain is unmeasured."
)
# Validity caveats rendered on the calibration page itself (the critic's standing requirements).
BASE_CAVEATS = (
    "Stage-1 'applicability agreement' is gate-rule agreement: the engine's applicability is "
    "resolver-locked, so this measures gate-fact detection, not an independent engine N/A call.",
    "Inter-expert agreement is pairwise and blind — NOT a ceiling. The engine can legitimately "
    "exceed it, because the consensus it is scored against is built by those same raters.",
    "Coverage/quality agreement uses the engine's own arithmetic on both sides, so a *systematic* "
    "scoring error would be invisible here (both sides would share it).",
)
DEMO_CAVEAT = (
    "FAKE DATA: these numbers are computed from fabricated reports for a plumbing demo. An LLM "
    "authored the 'human' side, so agreement is systematically optimistic vs real experts — this "
    "is NOT a measurement of the engine's accuracy."
)


# --- the report model --------------------------------------------------------------------------


class Stat(_Base):
    """A point estimate with its n, CI, and a preliminary (below-floor) flag."""

    label: str
    value: float | None
    n: int
    ci_lo: float | None = None
    ci_hi: float | None = None
    preliminary: bool = False


class RateStat(_Base):
    label: str
    x: int
    n: int
    value: float | None
    ci_lo: float | None = None
    ci_hi: float | None = None
    preliminary: bool = False


class TierCStep(_Base):
    step_id: str
    consensus: str
    engine: str
    agree: bool


class TierCCase(_Base):
    """A Tier-C paper reported as an individual case, not pooled into a rate (n is too small for a
    rate to mean anything). E.g. an analytic paper: did the engine correctly mark S4 N/A?"""

    work_id: str
    relevance_consensus: str
    relevance_engine: str
    steps: list[TierCStep]


class ValidationReport(_Base):
    engine_version: str
    rubric_version: str
    rubric_profile: str = "synthesis"
    status: str  # not_yet_validated | demo_fake_data | development_set | holdout
    is_demo: bool
    generated_label: str = ""  # the caller stamps a date if it wants one (pure: no clock here)
    n_papers: int
    n_excluded: int
    tier_counts: dict[str, int]
    rater_relationships: dict[str, int]
    domain_note: str
    validity_caveats: list[str]
    # engine vs consensus
    applicability_kappa: Stat
    status_kappa: Stat
    status_percent_agreement: Stat
    status_ac1: Stat
    absence_fpr_strict: RateStat
    absence_fpr_broad: RateStat
    absence_miss_rate: RateStat
    coverage_icc: Stat
    quality_icc: Stat
    relevance_sensitivity: RateStat
    relevance_specificity: RateStat
    paper_class_accuracy: RateStat
    confusion: dict[str, dict[str, int]]
    # human vs human (pairwise, blind) — explicitly NOT a ceiling
    inter_expert_status_kappa: Stat
    # engine vs ITSELF (two runs on the same paper) — the noise floor below which engine-vs-human
    # agreement is uninterpretable. value None when not measured (e.g. the demo: fixtures are
    # deterministic, so it is only computed on the real run with engine_runs >= 2).
    test_retest_kappa: Stat
    # Tier-C special cases — reported individually (analytic-N/A gating, figure-only diagnostics);
    # too few to pool into a rate, so they never enter the metrics above.
    tier_c_cases: list[TierCCase]


# --- builder -----------------------------------------------------------------------------------


def _flatten[T](groups: Sequence[Sequence[T]]) -> list[T]:
    return [x for g in groups for x in g]


def _human_coverage_quality(
    hr: HumanReport, rubric: RubricSpec
) -> tuple[float | None, float | None]:
    """Human-implied coverage(strict)/quality from the consensus statuses via the engine's own
    arithmetic + weights — so the diff vs the engine is purely about statuses."""
    cons = hr.consensus
    assert cons is not None and cons.paper_class_labels and rubric.scoring is not None
    calcs = [
        StepCalc(
            st.applicable,
            st.status,
            _multi_class_step_weight(rubric, st.step_id, cons.paper_class_labels),
            st.confidence,
        )
        for st in cons.steps
    ]
    cov, qual = coverage_quality_from_weighted_steps(
        calcs, rubric.scoring.sub_score, rubric.scoring.low_confidence_threshold
    )
    return (cov.strict if cov else None), qual


def _multi_class_step_weight(
    rubric: RubricSpec, step_id: str, labels: Sequence[PaperClassLabel]
) -> float:
    """Human ratings are genuinely multi-label; use the strongest rubric weight across labels."""
    return max(step_weight(rubric, step_id, label) for label in labels)


@dataclass
class _StepCells:
    """The pooled step-level cells the metrics need, binned per Tier-A paper. ``applic`` /
    ``status_both`` / ``inter_expert`` are per-paper lists (the cluster unit for κ); ``all_status``
    is flat (absence rates + confusion); ``coverage`` / ``quality`` are derived agreement pairs."""

    applic: list[list[tuple[bool, bool]]] = field(default_factory=list)
    status_both: list[list[tuple[StepStatus, StepStatus]]] = field(default_factory=list)
    all_status: list[tuple[StepStatus, StepStatus]] = field(default_factory=list)
    inter_expert: list[list[tuple[StepStatus, StepStatus]]] = field(default_factory=list)
    coverage: list[tuple[float, float]] = field(default_factory=list)
    quality: list[tuple[float, float]] = field(default_factory=list)


def _collect_step_cells(
    step_pairs: Sequence[tuple[HumanReport, ScoredResult]], rubric: RubricSpec
) -> _StepCells:
    """Align each Tier-A paper's consensus to the engine's step assessments and bin the cells the
    pooled step metrics consume. Human coverage/quality are DERIVED here (the engine's own
    arithmetic), never typed in — see the module docstring."""
    c = _StepCells()
    for h, s in step_pairs:
        eng = {a.step_id: a for a in s.step_assessments}
        ap: list[tuple[bool, bool]] = []
        both: list[tuple[StepStatus, StepStatus]] = []
        for st in h.consensus.steps:
            e = eng.get(st.step_id)
            if e is None:
                continue
            ap.append((st.applicable, e.applicable))
            c.all_status.append((st.status, e.status))
            if st.applicable and e.applicable:
                both.append((st.status, e.status))
        c.applic.append(ap)
        c.status_both.append(both)
        c.inter_expert.append(_inter_expert_cells(h))
        hc, hq = _human_coverage_quality(h, rubric)
        if hc is not None and s.coverage is not None:
            c.coverage.append((hc, s.coverage.strict))
        if hq is not None and s.quality_score is not None:
            c.quality.append((hq, s.quality_score))
    return c


def _relevance_class_rates(
    rate_pairs: Sequence[tuple[HumanReport, ScoredResult]],
) -> tuple[Rate, Rate, Rate]:
    """Relevance sensitivity/specificity (Tier A+B) and paper-class accuracy (rate-tier papers both
    judged relevant)."""
    rel_pairs = [
        (
            h.consensus.relevance_label is not RelevanceLabel.no,
            s.relevance.label is not RelevanceLabel.no,
        )
        for h, s in rate_pairs
    ]
    sens, spec = binary_sens_spec(rel_pairs)
    class_pairs = []
    for h, s in rate_pairs:
        if h.consensus.paper_class_labels and s.paper_class is not None:
            human = "|".join(sorted(label.value for label in h.consensus.paper_class_labels))
            engine = (
                human
                if s.paper_class.primary in h.consensus.paper_class_labels
                else s.paper_class.primary.value
            )
            class_pairs.append((human, engine))
    return sens, spec, accuracy(class_pairs)


def build_report(
    pairs: Sequence[tuple[HumanReport, ScoredResult]],
    rubric: RubricSpec,
    *,
    engine_version: str,
    is_demo: bool,
    status: str,
    seed: int = 0,
    n_floor: int = 15,
    n_resamples: int = 1000,
    domain_note: str = DEFAULT_DOMAIN_NOTE,
    retest_pairs: Sequence[tuple[ScoredResult, ScoredResult]] = (),
) -> ValidationReport:
    """Compute the single ``ValidationReport`` from in-memory pairs. Inadmissible human reports
    (missing consensus, too few raters, …) are excluded and counted, never silently dropped.
    ``retest_pairs`` are (engine run 1, engine run 2) for the same paper → the test-retest κ noise
    floor; empty when not measured (e.g. the demo, where fixtures are deterministic)."""
    admissible = [(h, s) for h, s in pairs if not h.validate_admissible() and h.consensus]
    n_excluded = len(pairs) - len(admissible)
    n_papers = len(admissible)
    prelim = not is_sufficient(n_papers, n_floor)

    def stat(label: str, value: float | None, n: int, ci: Interval | None) -> Stat:
        lo, hi = (ci.lo, ci.hi) if ci else (None, None)
        return Stat(label=label, value=value, n=n, ci_lo=lo, ci_hi=hi, preliminary=prelim)

    def rate_stat(label: str, r: Rate) -> RateStat:
        ci = wilson_ci(r.x, r.n) if r.n else None
        lo, hi = (ci.lo, ci.hi) if ci else (None, None)
        return RateStat(
            label=label, x=r.x, n=r.n, value=r.value, ci_lo=lo, ci_hi=hi, preliminary=prelim
        )

    # Tier routing. Tier A (full grade) feeds the pooled STEP metrics; Tier A+B (the rate tiers)
    # feed relevance/paper-class; Tier C is reported per-case (below), never pooled into a rate.
    rate_pairs = [(h, s) for h, s in admissible if h.tier in (GoldTier.A, GoldTier.B)]
    # papers the engine actually graded step-by-step (Tier A, both sides have steps)
    step_pairs = [
        (h, s)
        for h, s in admissible
        if h.tier is GoldTier.A and h.consensus.steps and s.step_assessments
    ]

    c = _collect_step_cells(step_pairs, rubric)
    applic_papers = c.applic
    status_both_papers = c.status_both
    all_status = c.all_status
    inter_expert_papers = c.inter_expert
    cov_pairs = c.coverage
    qual_pairs = c.quality

    # === v0 DECISION (owner, 2026-06-16): κ confidence intervals are OFF. ===
    # This is the SINGLE seam through which every κ CI flows. At v0 n (~15-30 papers) a paper-level
    # cluster bootstrap CI is noisy and contestable, and the uncertainties that matter most — rater
    # coherence and engine noise — are reported SEPARATELY as the inter-expert and test-retest κ.
    # So κ is reported as a point estimate + n + the 'preliminary (n below floor)' tag, no interval.
    # The cluster bootstrap (`metrics.bootstrap_ci`, still unit-tested) is retained for a possible
    # v1 re-enable once the real run has enough papers — flip this back at the G9 amendment by
    # restoring `return bootstrap_ci(papers, lambda ps: fn(_flatten(ps)), seed=seed,
    # n_resamples=n_resamples)` and re-importing it. seed/n_resamples are threaded for that.
    def _kappa_ci(papers, fn) -> Interval | None:
        return None

    applic_k = cohen_kappa(_flatten(applic_papers))
    status_k = weighted_kappa(_flatten(status_both_papers), STATUS_ORDER)
    ie_k = weighted_kappa(_flatten(inter_expert_papers), STATUS_ORDER)

    # test-retest: two engine runs of the same paper, both-applicable status cells (per-paper)
    retest_papers = [_engine_pair_cells(e1, e2) for e1, e2 in retest_pairs]
    retest_k = weighted_kappa(_flatten(retest_papers), STATUS_ORDER) if retest_papers else None

    sens, spec, cls_acc = _relevance_class_rates(rate_pairs)
    # Tier C — each paper reported as an individual case (too few to pool into a rate)
    tier_c_cases = [_tier_c_case(h, s) for h, s in admissible if h.tier is GoldTier.C]

    return ValidationReport(
        engine_version=engine_version,
        rubric_version=rubric.rubric_version,
        rubric_profile=rubric.profile,
        status=status,
        is_demo=is_demo,
        n_papers=n_papers,
        n_excluded=n_excluded,
        tier_counts=_tier_counts(admissible),
        rater_relationships=_rater_relationships(admissible),
        domain_note=domain_note,
        validity_caveats=[*BASE_CAVEATS, *([DEMO_CAVEAT] if is_demo else [])],
        applicability_kappa=stat(
            "applicability (gate-rule) κ, engine vs consensus",
            applic_k,
            len(_flatten(applic_papers)),
            _kappa_ci(applic_papers, cohen_kappa),
        ),
        status_kappa=stat(
            "status weighted κ, engine vs consensus",
            status_k,
            len(_flatten(status_both_papers)),
            _kappa_ci(status_both_papers, lambda ps: weighted_kappa(ps, STATUS_ORDER)),
        ),
        status_percent_agreement=stat(
            "status % agreement",
            percent_agreement(_flatten(status_both_papers)),
            len(_flatten(status_both_papers)),
            None,
        ),
        status_ac1=stat(
            "status Gwet AC1 (prevalence-robust)",
            gwet_ac(_flatten(status_both_papers), STATUS_ORDER),
            len(_flatten(status_both_papers)),
            None,
        ),
        absence_fpr_strict=rate_stat(
            "absence-FPR (strict: engine 'missing' but consensus adequate)",
            absence_fpr(all_status, mode="strict"),
        ),
        absence_fpr_broad=rate_stat(
            "absence-FPR (broad: engine 'missing' but consensus present)",
            absence_fpr(all_status, mode="broad"),
        ),
        absence_miss_rate=rate_stat(
            "absence-miss-rate (consensus 'missing' the engine failed to flag)",
            absence_miss_rate(all_status),
        ),
        coverage_icc=stat("coverage agreement ICC(A,1)", icc_a1(cov_pairs), len(cov_pairs), None),
        quality_icc=stat("quality agreement ICC(A,1)", icc_a1(qual_pairs), len(qual_pairs), None),
        relevance_sensitivity=rate_stat("relevance sensitivity (real papers caught)", sens),
        relevance_specificity=rate_stat("relevance specificity (decoys rejected)", spec),
        paper_class_accuracy=rate_stat("paper-class accuracy", cls_acc),
        confusion=confusion(all_status),
        inter_expert_status_kappa=stat(
            "inter-expert status κ (pairwise, blind — NOT a ceiling)",
            ie_k,
            len(_flatten(inter_expert_papers)),
            _kappa_ci(inter_expert_papers, lambda ps: weighted_kappa(ps, STATUS_ORDER)),
        ),
        test_retest_kappa=stat(
            "test-retest status κ (engine vs itself — the noise floor)",
            retest_k,
            len(_flatten(retest_papers)),
            _kappa_ci(retest_papers, lambda ps: weighted_kappa(ps, STATUS_ORDER))
            if retest_papers
            else None,
        ),
        tier_c_cases=tier_c_cases,
    )


def _tier_c_case(hr: HumanReport, s: ScoredResult) -> TierCCase:
    """A single Tier-C paper, consensus vs engine, step by step — the honest unit when n is too
    small for a rate (e.g. 'did the engine correctly mark S4 N/A on this analytic paper?')."""
    eng = {a.step_id: a for a in s.step_assessments}
    steps: list[TierCStep] = []
    for st in hr.consensus.steps if hr.consensus else []:
        e = eng.get(st.step_id)
        e_status = e.status.value if e is not None else "—"
        steps.append(
            TierCStep(
                step_id=st.step_id,
                consensus=st.status.value,
                engine=e_status,
                agree=e is not None and st.status is e.status,
            )
        )
    rel_c = hr.consensus.relevance_label.value if hr.consensus else "—"
    return TierCCase(
        work_id=hr.work_id,
        relevance_consensus=rel_c,
        relevance_engine=s.relevance.label.value,
        steps=steps,
    )


def _engine_pair_cells(e1: ScoredResult, e2: ScoredResult) -> list[tuple[StepStatus, StepStatus]]:
    """Both-applicable status cells across two engine runs of the same paper (test-retest)."""
    b = {a.step_id: a for a in e2.step_assessments}
    cells: list[tuple[StepStatus, StepStatus]] = []
    for sa in e1.step_assessments:
        sb = b.get(sa.step_id)
        if sb is not None and sa.applicable and sb.applicable:
            cells.append((sa.status, sb.status))
    return cells


def _inter_expert_cells(hr: HumanReport) -> list[tuple[StepStatus, StepStatus]]:
    """Pairwise (rater_i, rater_j) status cells where both raters deemed the step applicable."""
    raters = hr.ratings
    cells: list[tuple[StepStatus, StepStatus]] = []
    for i in range(len(raters)):
        a = {st.step_id: st for st in raters[i].steps}
        for j in range(i + 1, len(raters)):
            b = {st.step_id: st for st in raters[j].steps}
            for sid, sa in a.items():
                sb = b.get(sid)
                if sb is not None and sa.applicable and sb.applicable:
                    cells.append((sa.status, sb.status))
    return cells


def _tier_counts(pairs: Sequence[tuple[HumanReport, ScoredResult]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for h, _ in pairs:
        counts[h.tier.value] = counts.get(h.tier.value, 0) + 1
    return counts


def _rater_relationships(pairs: Sequence[tuple[HumanReport, ScoredResult]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for h, _ in pairs:
        for r in h.ratings:
            counts[r.relationship.value] = counts.get(r.relationship.value, 0) + 1
    return counts


# --- renderers (both read the SAME report object — single-computation watermark) ----------------


def to_calibration_payload(report: ValidationReport) -> dict:
    """The /api/calibration body — the report verbatim. ``status`` carries the demo/real state."""
    return report.model_dump(mode="json")


def _fmt(s: Stat | RateStat) -> str:
    if s.value is None:
        return "—"
    body = f"{s.value:.2f}"
    if isinstance(s, RateStat):
        body += f" ({s.x}/{s.n})"
    if s.ci_lo is not None and s.ci_hi is not None:
        body += f" [{s.ci_lo:.2f}, {s.ci_hi:.2f}]"
    if s.preliminary:
        body += " — preliminary (n below floor)"
    return body


def to_markdown(report: ValidationReport) -> str:
    """Render VALIDATION(.demo).md; a loud FAKE-DATA header when ``is_demo``."""
    lines: list[str] = []
    if report.is_demo:
        lines += ["# ⚠️ FAKE DATA — plumbing demonstration, NOT a measurement", ""]
    lines += [
        f"# VeriBayes validation — {report.rubric_profile} profile",
        "",
        f"_Engine {report.engine_version} · rubric {report.rubric_version} · status "
        f"`{report.status}` · {report.n_papers} papers ({report.n_excluded} excluded)._",
        "",
        f"**Domain:** {report.domain_note}",
        "",
        "## Agreement (development-set; all labels 'development-set agreement', never 'accuracy')",
        "",
    ]
    metrics: list[Stat | RateStat] = [
        report.applicability_kappa,
        report.status_kappa,
        report.status_percent_agreement,
        report.status_ac1,
        report.inter_expert_status_kappa,
        report.test_retest_kappa,
        report.absence_fpr_strict,
        report.absence_fpr_broad,
        report.absence_miss_rate,
        report.coverage_icc,
        report.quality_icc,
        report.relevance_sensitivity,
        report.relevance_specificity,
        report.paper_class_accuracy,
    ]
    lines += [f"- **{m.label}:** {_fmt(m)}" for m in metrics]
    if report.tier_c_cases:
        lines += [
            "",
            "## Tier-C special cases (reported individually — too few to pool)",
            "",
        ]
        for c in report.tier_c_cases:
            lines += [
                f"### {c.work_id} — relevance: consensus `{c.relevance_consensus}` / "
                f"engine `{c.relevance_engine}`",
            ]
            lines += [
                f"- {st.step_id}: consensus `{st.consensus}` / engine `{st.engine}` "
                f"{'✓' if st.agree else '✗'}"
                for st in c.steps
            ]
    lines += ["", "## Read this carefully"]
    lines += [f"- {c}" for c in report.validity_caveats]
    return "\n".join(lines)
