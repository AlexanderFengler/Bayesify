"""The fake demo dataset (V5b) — fabricated (HumanReport, ScoredResult) pairs that drive the whole
validation pipeline end-to-end so the owner can critique the finished calibration product BEFORE any
real rater exists.

Everything here is ``origin=fake_llm`` by construction, so the honesty firewall (see ``harness``)
can never let it produce a real ``VALIDATION.md``. The papers are seeded to exercise the metrics:
agreement, an absence-FPR disagreement (engine cries 'missing', human saw it), a status
disagreement, and a relevance='no' decoy (Tier B). The numbers it yields are deliberately, visibly
fake — an LLM-shaped 'human' agrees with the engine too readily — and are labelled as such.
"""

from __future__ import annotations

from dataclasses import dataclass

from veribayes.core.rubric.applicability import step_applicability
from veribayes.core.rubric.loader import load_rubric
from veribayes.core.schema import (
    CostLedger,
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    GateFacts,
    InferenceMethod,
    PaperClass,
    PaperClassLabel,
    Relevance,
    RelevanceLabel,
    ScoredResult,
    StepAssessment,
    StepStatus,
)
from veribayes.core.score import ScoreMeta, score
from veribayes.core.stub import ENGINE_VERSION, RUBRIC_VERSION
from veribayes.core.validation.human_report import (
    GoldOrigin,
    GoldProvenance,
    GoldTier,
    HumanReport,
    RaterRelationship,
    Rating,
    StepRating,
)

_RUBRIC = load_rubric()
_PRESENT = (StepStatus.done_well, StepStatus.partial)
_DEFAULT_GATE = GateFacts()  # mcmc/unstated, 1 model, no BF, unstated priors
_ANALYTIC_GATE = GateFacts(inference_method=InferenceMethod.exact_analytic)  # → S4 N/A (G6)
_SPAN = EvidenceSpan(section_id="s01", quote="a demonstration span")


@dataclass(frozen=True)
class DemoPaper:
    work_id: str
    sha256: str
    human: HumanReport
    engine: ScoredResult


def _engine(
    primary: PaperClassLabel, gate: GateFacts, overrides: dict[str, StepStatus]
) -> ScoredResult:
    """A relevant engine ScoredResult, scored for real over assessments whose applicability matches
    the resolver (so score() is happy); ``overrides`` set the status of given applicable steps."""
    pc = PaperClass(primary=primary, confidence=0.9, rationale="demo", evidence_refs=[0])
    assessments: list[StepAssessment] = []
    for step in _RUBRIC.steps:
        appl = step_applicability(step, primary, gate)
        if not appl.applicable:
            assessments.append(
                StepAssessment(
                    step_id=step.id,
                    applicable=False,
                    applicability_reason=appl.reason,
                    status=StepStatus.not_applicable,
                    confidence=0.9,
                )
            )
            continue
        status = overrides.get(step.id, StepStatus.done_well)
        ev = (
            [
                Evidence(
                    detector_id="demo",
                    detector_version="0",
                    kind=EvidenceKind.judge_quote,
                    span=_SPAN,
                )
            ]
            if status in _PRESENT
            else []
        )
        assessments.append(
            StepAssessment(
                step_id=step.id,
                applicable=True,
                applicability_reason=appl.reason or "applicable",
                status=status,
                confidence=0.9,
                evidence=ev,
            )
        )
    relevance = Relevance(
        label=RelevanceLabel.yes, confidence=0.9, rationale="Bayesian", evidence_refs=[0]
    )
    meta = ScoreMeta(engine_version=ENGINE_VERSION, cost_ledger=CostLedger())
    return score(relevance, pc, assessments, gate, _RUBRIC, meta)


def _rating(
    primary: PaperClassLabel,
    gate: GateFacts,
    overrides: dict[str, StepStatus],
    rater_id: str,
    rel: RaterRelationship,
) -> Rating:
    steps: list[StepRating] = []
    for step in _RUBRIC.steps:
        appl = step_applicability(step, primary, gate)
        if not appl.applicable:
            steps.append(
                StepRating(
                    step_id=step.id,
                    applicable=False,
                    status=StepStatus.not_applicable,
                    confidence=0.85,
                )
            )
            continue
        status = overrides.get(step.id, StepStatus.done_well)
        steps.append(
            StepRating(
                step_id=step.id,
                applicable=True,
                status=status,
                confidence=0.85,
                evidence=[_SPAN] if status in _PRESENT else [],
                rationale="rater note",
            )
        )
    return Rating(
        rater_id=rater_id,
        relationship=rel,
        relevance_label=RelevanceLabel.yes,
        relevance_rationale="fits a Bayesian model",
        paper_class_label=primary,
        gate_facts=gate,
        steps=steps,
    )


def _human(
    work_id: str,
    sha: str,
    primary: PaperClassLabel,
    gate: GateFacts,
    consensus_overrides: dict[str, StepStatus],
    tier: GoldTier = GoldTier.A,
) -> HumanReport:
    # two independent blind raters who agree with each other, plus the adjudicated consensus.
    r1 = _rating(primary, gate, consensus_overrides, "r1", RaterRelationship.independent)
    r2 = _rating(primary, gate, consensus_overrides, "r2", RaterRelationship.independent)
    cons = _rating(primary, gate, consensus_overrides, "consensus", RaterRelationship.consensus)
    return HumanReport(
        work_id=work_id,
        source_sha256=sha,
        version_label="arXiv v1 (demo)",
        rubric_version=RUBRIC_VERSION,
        tier=tier,
        provenance=GoldProvenance(origin=GoldOrigin.fake_llm, authored_by="demo-generator"),
        ratings=[r1, r2],
        consensus=cons,
    )


def _decoy(work_id: str, sha: str) -> DemoPaper:
    """A non-Bayesian decoy: engine short-circuits (relevance=no), human agrees → Tier-B spec."""
    rel = Relevance(
        label=RelevanceLabel.no,
        confidence=0.9,
        rationale="No Bayesian methodology; searched methods/results and found only OLS.",
    )
    engine = ScoredResult.short_circuit(
        relevance=rel, engine_version=ENGINE_VERSION, rubric_version=RUBRIC_VERSION
    )

    def no_rating(rid: str, r: RaterRelationship) -> Rating:
        return Rating(
            rater_id=rid,
            relationship=r,
            relevance_label=RelevanceLabel.no,
            relevance_rationale="frequentist paper; no Bayesian methods",
        )

    human = HumanReport(
        work_id=work_id,
        source_sha256=sha,
        version_label="arXiv v1 (demo)",
        rubric_version=RUBRIC_VERSION,
        tier=GoldTier.B,
        provenance=GoldProvenance(origin=GoldOrigin.fake_llm, authored_by="demo-generator"),
        ratings=[
            no_rating("r1", RaterRelationship.independent),
            no_rating("r2", RaterRelationship.independent),
        ],
        consensus=no_rating("consensus", RaterRelationship.consensus),
    )
    return DemoPaper(work_id, sha, human, engine)


def build_demo_dataset() -> list[DemoPaper]:
    """Five fabricated papers exercising the metric surfaces. Deterministic."""
    empirical = PaperClassLabel.empirical
    numerical = PaperClassLabel.numerical_experiment
    return [
        # 1) high agreement
        DemoPaper(
            "demo-agree",
            "sha-agree",
            _human("demo-agree", "sha-agree", empirical, _DEFAULT_GATE, {}),
            _engine(empirical, _DEFAULT_GATE, {}),
        ),
        # 2) absence-FPR: engine cries 'missing' on S5, human saw it (done_well)
        DemoPaper(
            "demo-fpr",
            "sha-fpr",
            _human("demo-fpr", "sha-fpr", empirical, _DEFAULT_GATE, {}),
            _engine(empirical, _DEFAULT_GATE, {"S5": StepStatus.missing}),
        ),
        # 3) status disagreement: engine done_well, human partial on S1 + S3
        DemoPaper(
            "demo-status",
            "sha-status",
            _human(
                "demo-status",
                "sha-status",
                numerical,
                _DEFAULT_GATE,
                {"S1": StepStatus.partial, "S3": StepStatus.partial},
            ),
            _engine(numerical, _DEFAULT_GATE, {}),
        ),
        # 4) a relevance='no' decoy (Tier B)
        _decoy("demo-decoy", "sha-decoy"),
        # 5) Tier-C special case: an analytic-posterior paper. S4 (convergence) has no sampler to
        #    diagnose → N/A by the G6 gate; reported as an individual case, never pooled.
        DemoPaper(
            "demo-analytic",
            "sha-analytic",
            _human(
                "demo-analytic", "sha-analytic", empirical, _ANALYTIC_GATE, {}, tier=GoldTier.C
            ),
            _engine(empirical, _ANALYTIC_GATE, {}),
        ),
    ]


def write_demo_dataset(goldset_dir: str, engine_dir: str) -> int:
    """Write the fake goldset (HumanReports) + paired engine ScoredResults to disk. Returns the
    paper count. Deterministic, so the committed demo is reproducible (``pixi run demo-data``)."""
    from pathlib import Path

    g, e = Path(goldset_dir), Path(engine_dir)
    g.mkdir(parents=True, exist_ok=True)
    e.mkdir(parents=True, exist_ok=True)
    papers = build_demo_dataset()
    for p in papers:
        (g / f"{p.work_id}.json").write_text(p.human.model_dump_json(indent=2))
        (e / f"{p.work_id}.json").write_text(p.engine.model_dump_json(indent=2))
    return len(papers)


if __name__ == "__main__":  # pragma: no cover - regeneration entrypoint
    n = write_demo_dataset("validation/_fake_goldset", "validation/_fake_goldset/_engine")
    print(f"wrote {n} fake demo papers to validation/_fake_goldset/")
