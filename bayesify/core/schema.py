"""The stage contracts — the single spec that keeps the pipeline components independent.

Every component (a-h) codes against these pydantic models and tests against recorded fixtures of
them; Phase 3 stores them as-is. This file is the authoritative definition referenced by
``plans/02-mvp-tool-plan.md`` §4.3. Field names here are law for every subplan.

Conventions:
- All models forbid extra fields (``extra="forbid"``) to catch typos at the contract boundary.
- ``confidence`` fields are in [0, 1].
- The post-2026-06-12 scoring model is **no categorical badge**: the outputs are the per-step
  ``profile`` plus ``coverage`` (uncertainty-honest range) and ``quality_score``.
- On a relevance-``no`` short-circuit, ``paper_class``/``gate_facts``/``profile``/``coverage``/
  ``quality_score`` are ``None`` and ``step_assessments`` is empty (the g job loop persists d's
  output directly; f is never invoked). See ``short_circuit`` constructor below.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_log = logging.getLogger("bayesify.core.schema")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SectionKind(StrEnum):
    body = "body"
    abstract = "abstract"
    caption = "caption"
    supplement = "supplement"
    references = "references"


class EvidenceKind(StrEnum):
    # Emitted by the deterministic detectors (component c):
    software_mention = "software_mention"
    method_mention = "method_mention"
    diagnostic_value = "diagnostic_value"
    diagnostic_mention = "diagnostic_mention"
    workflow_signal = "workflow_signal"
    sampler_config = "sampler_config"
    open_science = "open_science"
    # Minted by the assess stage (component e), never by detectors:
    absence_search = "absence_search"  # e's where-looked enumeration on a missing finding
    judge_quote = "judge_quote"  # a verbatim span the judge/refuter cited (quote-verified)


class RelevanceLabel(StrEnum):
    yes = "yes"
    partial = "partial"
    no = "no"


class PaperClassLabel(StrEnum):
    model_development = "model_development"
    method_development = "method_development"
    software_development = "software_development"
    data_analysis = "data_analysis"
    numerical_analysis = "numerical_analysis"
    theoretical_analysis = "theoretical_analysis"
    review = "review"


class StepStatus(StrEnum):
    adequate = "adequate"
    partial = "partial"
    missing = "missing"
    not_applicable = "not_applicable"


class InferenceMethod(StrEnum):
    mcmc = "mcmc"
    hmc_nuts = "hmc_nuts"
    variational = "variational"
    sbi = "sbi"
    smc = "smc"
    abc = "abc"
    laplace_inla = "laplace_inla"
    em = "em"
    exact_analytic = "exact_analytic"
    unstated = "unstated"


class FactAnswer(StrEnum):
    yes = "yes"
    no = "no"


class FactConfidence(StrEnum):
    high = "high"
    low = "low"


class PriorInformativeness(StrEnum):
    informative = "informative"
    weakly_informative = "weakly_informative"
    default = "default"
    none = "none"
    unstated = "unstated"


class Severity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class Ease(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ExpectationTier(StrEnum):
    """The post-badge meaning of the rubric's ``essential`` flag (f-score): drives suggestion
    severity, not a verdict."""

    expected = "expected"  # tier-1: missing => error severity
    recommended = "recommended"  # tier-2: missing => warning/info
    none = "none"  # not expected for this paper class


class PaperIds(_Base):
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None


class SourceDoc(_Base):
    sha256: str
    ids: PaperIds = Field(default_factory=PaperIds)
    version_label: str  # e.g. "arXiv v2", "publisher VoR (Unpaywall)", "uploaded PDF"
    source: str  # upload | arxiv | openalex | unpaywall | crossref | url (+ resolved URL)
    fetched_at: datetime


class PageSpan(_Base):
    doc_sha256: str  # which document the span lives in (primary or a supplement)
    page_start: int
    page_end: int


class Section(_Base):
    id: str  # deterministic: s01, s02, ... in reading order, supplements last
    kind: SectionKind
    title: str
    text: str
    page_spans: list[PageSpan] = Field(default_factory=list)


class ParsedDoc(_Base):
    source: SourceDoc  # the *primary* source; supplement provenance lives in page_spans
    sections: list[Section] = Field(default_factory=list)
    parser: str  # "grobid" | "pymupdf"
    parser_version: str
    title: str | None = None  # best-effort paper title from the first page (None if undetected)
    authors: list[str] = Field(default_factory=list)  # best-effort, from PDF/provider metadata
    year: int | None = None  # best-effort publication year (PDF/provider metadata; may be missing)


class EvidenceSpan(_Base):
    section_id: str
    page: int | None = None
    quote: str  # a verbatim substring of the section's text (hard guarantee)


class Evidence(_Base):
    detector_id: str
    detector_version: str
    kind: EvidenceKind
    # structured payload (e.g. {metric, op?, number}); None for pure mentions
    value: dict[str, object] | None = None
    span: EvidenceSpan


class Relevance(_Base):
    label: RelevanceLabel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_refs: list[int] = Field(default_factory=list)  # indices into the consumed Evidence[]
    # Provenance: True when a human overrode the gate (the rerun escape hatch), not the model. The
    # grounding discipline below disciplines the *model's* claims; a human override is exempt. The
    # screen stage never sets this — only the API rerun path does (disclosed in the rationale).
    overridden: bool = False

    @model_validator(mode="after")
    def _refs_discipline(self) -> Relevance:
        # d-screen-classify.md: 'yes'/'partial' must cite >=1 detector hit; 'no' may have empty refs
        # but its rationale must enumerate what was searched and not found (so always non-empty).
        if not self.rationale.strip():
            raise ValueError("Relevance.rationale must be non-empty")
        if (
            not self.overridden
            and self.label in (RelevanceLabel.yes, RelevanceLabel.partial)
            and not self.evidence_refs
        ):
            raise ValueError(f"relevance '{self.label.value}' requires >=1 evidence_ref")
        return self


class PaperClass(_Base):
    labels: list[PaperClassLabel] = Field(default_factory=list)
    # The scientific field(s) the paper belongs to (multi-label). A *soft* vocabulary: the classify
    # prompt seeds preferred terms but the model may add one that fits better, so these are free
    # strings (normalised to lower-case, hyphenated) rather than an enum. Drives the Archive's
    # discipline facet; never gates scoring. Empty is allowed (a rater-supplied class carries none).
    disciplines: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_refs: list[int] = Field(default_factory=list)
    # Bayesian computation methods the paper's own analysis USES (not merely mentions). Typed to
    # InferenceMethod for a controlled facet vocabulary; the mode="before" validator drops any
    # out-of-vocab token the classifier emits so one stray word can't fail the whole call, and the
    # after-validator drops "unstated" (a list uses empty, never [unstated]) and de-duplicates.
    methods_used: list[InferenceMethod] = Field(default_factory=list)
    # Software the classifier judged to be actually USED in an analysis, experiment, numerical
    # study, or reported baseline. Detector inventory can still provide a fallback, but this is the
    # context-aware source that distinguishes use from a mere mention.
    software_used: list[str] = Field(default_factory=list)

    @field_validator("methods_used", mode="before")
    @classmethod
    def _drop_unknown_methods(cls, v: object) -> object:
        """Drop tokens that aren't a real InferenceMethod (so one stray/hallucinated method can't
        fail the whole classify call) and log them, so a method we don't yet track surfaces instead
        of vanishing silently."""
        if not isinstance(v, list):
            return v
        known = {m.value for m in InferenceMethod}
        kept, dropped = [], []
        for x in v:
            token = x.value if isinstance(x, InferenceMethod) else x
            (kept if token in known else dropped).append(token)
        if dropped:
            _log.warning("classifier named methods outside InferenceMethod (dropped): %s", dropped)
        return kept

    @model_validator(mode="after")
    def _refs_discipline(self) -> PaperClass:
        if not self.labels:
            raise ValueError("PaperClass requires >=1 label")
        if len(self.labels) != len(set(self.labels)):
            raise ValueError("PaperClass.labels must not contain duplicates")
        if not self.rationale.strip():
            raise ValueError("PaperClass.rationale must be non-empty")
        # The classifier now returns quote-grounded binary facts. Detector evidence_refs are
        # retained only when a fact quote overlaps a detector span; they are not required.
        # Normalise disciplines to a clean, de-duplicated soft vocabulary (order-preserving).
        seen: set[str] = set()
        normalised: list[str] = []
        for d in self.disciplines:
            tag = d.strip().lower().replace(" ", "-")
            if tag and tag not in seen:
                seen.add(tag)
                normalised.append(tag)
        self.disciplines = normalised
        # methods_used: drop "unstated" and de-duplicate, order-preserving (unknowns already gone).
        seen_m: set[InferenceMethod] = set()
        methods: list[InferenceMethod] = []
        for m in self.methods_used:
            if m is InferenceMethod.unstated or m in seen_m:
                continue
            seen_m.add(m)
            methods.append(m)
        self.methods_used = methods
        seen_s: set[str] = set()
        software: list[str] = []
        for s in self.software_used:
            tag = s.strip()
            key = tag.lower()
            if tag and key not in seen_s:
                seen_s.add(key)
                software.append(tag)
        self.software_used = software
        return self


class ClassifierFact(_Base):
    answer: FactAnswer
    confidence: FactConfidence
    evidence: str = ""

    @model_validator(mode="after")
    def _yes_needs_evidence(self) -> ClassifierFact:
        self.evidence = self.evidence.strip()
        if self.answer is FactAnswer.yes and not self.evidence:
            raise ValueError("yes classifier facts require evidence")
        return self


class ClassifierPaperTypeFacts(_Base):
    develops_new_bayesian_model: ClassifierFact
    develops_new_bayesian_method: ClassifierFact
    develops_new_bayesian_software: ClassifierFact
    uses_bayesian_model_on_real_data: ClassifierFact
    runs_numerical_or_simulation_study: ClassifierFact
    investigates_theoretical_behavior: ClassifierFact
    is_review_tutorial_or_commentary: ClassifierFact


class ClassifierMethodFacts(_Base):
    uses_mcmc: ClassifierFact
    uses_variational_inference: ClassifierFact
    uses_sbi: ClassifierFact
    uses_abc: ClassifierFact
    uses_smc_or_particle_filter: ClassifierFact
    uses_laplace_or_inla: ClassifierFact
    uses_em: ClassifierFact
    uses_exact_or_analytic_posterior: ClassifierFact


class ClassifierFacts(_Base):
    paper_type: ClassifierPaperTypeFacts
    methods: ClassifierMethodFacts
    software: list[str] = Field(default_factory=list)
    disciplines: list[str] = Field(default_factory=list)


class GateFacts(_Base):
    """Gate G6 (three-lens review): the compact, evidence-derived facts that drive the rubric's
    *evidence-conditioned* gates — S4 N/A for analytic posteriors, S6 only when >=2 models or a BF,
    S8 mandatory under informative priors / any BF. Emitted by component e from PaperClass + the
    detector Evidence; consumed by component f's ``score()`` so it can re-derive applicability and
    essentialness deterministically without the raw ``Evidence[]``."""

    inference_method: InferenceMethod = InferenceMethod.unstated
    n_models: int = 1
    bf_claimed: bool = False
    prior_informativeness: PriorInformativeness = PriorInformativeness.unstated


class StandardRef(_Base):
    """The second grounding (A3): the methodological standard behind a judgment — "says who?".
    Compiled from ``rubric/steps.yaml`` provenance, carrying its verified/unverified status."""

    source_id: str  # e.g. "barg2021" — key into the rubric's citations table
    citation: str
    verified: bool  # whether the threshold/claim was adversarially verified in the research run
    locator: str | None = None  # e.g. "Step 2.B-C"


class Suggestion(_Base):
    severity: Severity
    text: str
    how_to: str
    ease: Ease


class AdversarialVerdict(_Base):
    """A4: the refutation pass over a negative finding."""

    challenged: bool
    refuted: bool
    notes: str = ""


class StepAssessment(_Base):
    step_id: str  # references a rubric step (S1..S10)
    applicable: bool
    applicability_reason: str
    status: StepStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)  # grounding 1: in the paper
    standards: list[StandardRef] = Field(default_factory=list)  # grounding 2: in the literature
    did_well: list[str] = Field(default_factory=list)  # D3: specific, evidence-cited praise
    suggestions: list[Suggestion] = Field(default_factory=list)  # D2
    adversarial_verdict: AdversarialVerdict | None = None


class StepProfile(_Base):
    step_id: str
    applicable: bool
    status: StepStatus
    sub_score: float | None = None  # None for N/A steps (excluded from the denominator)
    weight: float
    tier: ExpectationTier


class Profile(_Base):
    steps: list[StepProfile] = Field(default_factory=list)
    n_applicable: int
    n_na: int
    n_uncertain: int  # applicable steps whose status is a low-confidence absence


class Coverage(_Base):
    """Share of applicable steps present (adequate | partial). ``strict``/``lenient`` bracket the
    uncertainty from low-confidence absences (e.g. "6-7 / 9")."""

    present: int  # high-confidence present count
    applicable: int
    strict: float  # uncertain absences counted as absent
    lenient: float  # uncertain absences counted as present


class ScoreImpact(_Base):
    """A re-scoring-verified delta: upgrading one step's status by this much (replaces the badge-era
    what-if explainer; feeds D2's suggestion ranking)."""

    step_id: str
    from_status: StepStatus
    to_status: StepStatus
    coverage_delta: float
    quality_delta: float


class CostLedgerEntry(_Base):
    stage: str  # screen | classify | assess | ...
    step_id: str | None = None
    pass_label: str | None = None  # e.g. "primary" | "adversarial"
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostLedger(_Base):
    entries: list[CostLedgerEntry] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class ScoredResult(_Base):
    """The final result object — what the report renders and what Phase 3 stores, verbatim."""

    relevance: Relevance
    paper_class: PaperClass | None = None  # None on short-circuit
    gate_facts: GateFacts | None = None  # None on short-circuit
    step_assessments: list[StepAssessment] = Field(default_factory=list)
    profile: Profile | None = None
    coverage: Coverage | None = None
    quality_score: float | None = None
    score_impacts: list[ScoreImpact] = Field(default_factory=list)
    # Why the per-step rubric was not run (None when graded): "not_bayesian" (relevance gate said
    # no) or "not_an_application" (a review/opinion piece — Bayesian-relevant, but the rubric grades
    # papers that *apply* a workflow to data).
    not_applicable_reason: str | None = None
    engine_version: str
    rubric_version: str
    rubric_profile: str = "synthesis"  # synthesis | schad2021 | ...
    cost_ledger: CostLedger = Field(default_factory=CostLedger)
    validation_ref: str = "unvalidated"

    @classmethod
    def short_circuit(
        cls,
        *,
        relevance: Relevance,
        engine_version: str,
        rubric_version: str,
        reason: str = "not_bayesian",
        paper_class: PaperClass | None = None,
        rubric_profile: str = "synthesis",  # the chosen rubric (registry id)
        cost_ledger: CostLedger | None = None,
        validation_ref: str = "unvalidated",
    ) -> ScoredResult:
        """Construct a no-grade result: scores null, no assessments. ``reason`` distinguishes a
        relevance-``no`` paper ("not_bayesian") from a review/opinion piece the rubric doesn't apply
        to ("not_an_application", which keeps relevance=yes + the review paper_class)."""
        return cls(
            relevance=relevance,
            paper_class=paper_class,
            not_applicable_reason=reason,
            engine_version=engine_version,
            rubric_version=rubric_version,
            rubric_profile=rubric_profile,
            cost_ledger=cost_ledger or CostLedger(),
            validation_ref=validation_ref,
        )
