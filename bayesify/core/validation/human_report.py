"""The human-report contract — the golden record a blind expert authors (component h, validation).

Bayesify validates by **report-to-report comparison**: a human rater walks the same rubric the
engine walks (blind) and produces a ``HumanReport``; the harness diffs it against the engine's
``ScoredResult``. This module is the human side of that comparison, and it is deliberately
**decoupled** from the engine output shape. It shares only the comparison *vocabulary* — the
status/label enums, ``EvidenceSpan``, the per-step ``{step_id, applicable, status, confidence}``
skeleton, and ``GateFacts`` by value — and it **omits every engine-narrative field**
(``did_well``/``suggestions``/``standards``/``adversarial_verdict``). The asymmetry is the validity
firewall: a human handed the engine's framing would be measuring an echo, not judging independently.
Coverage and quality are **never authored here** — the harness derives them from the consensus
statuses via the engine's own arithmetic, so disagreement lives purely in the statuses.

Engine-free by contract: this module never imports the engine output shape (no reference to
``ScoredResult``/``StepAssessment``, asserted by ``tests/test_human_report.py``) and never imports
engine *behaviour* (enforced by import-linter). Only the shared ``core.schema`` vocabulary is used.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bayesify.core.schema import (
    EvidenceSpan,
    GateFacts,
    PaperClassLabel,
    PaperIds,
    RelevanceLabel,
    StepStatus,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- enums (the human-only vocabulary the engine does not carry) ----------------------------------


class GoldOrigin(StrEnum):
    """Who authored this gold record — the load-bearing honesty field, REQUIRED with no default.

    A ``HumanReport`` cannot be constructed or deserialized without declaring its origin, so
    fabricated demo data can never silently masquerade as real validation (the real harness path
    asserts ``blind_human``; the public report emitter refuses anything else)."""

    blind_human = "blind_human"  # a recorded blind expert rating session
    fake_llm = "fake_llm"  # an LLM-authored fake, for the plumbing demo only
    dry_run_fixture = "dry_run_fixture"  # a hand-authored fixture for the CI dry run


class GoldTier(StrEnum):
    """Routes which metrics apply (protocol §1): A = full per-step grade, B = relevance-only probe,
    C = case-reported (analytic-N/A gating, figure-only diagnostics)."""

    A = "A"
    B = "B"
    C = "C"


class RaterRelationship(StrEnum):
    """Disclosed in the validation report (protocol §2.1). ``independent`` = no role in
    engine/prompt development; ``consensus`` = the synthetic rater of an adjudicated rating."""

    independent = "independent"
    engine_dev = "engine_dev"
    prompt_author = "prompt_author"
    consensus = "consensus"


class MissingSubtag(StrEnum):
    """A human-only distinction the engine does not make — collapsed in v0 metrics, stored for the
    v1 rigor-vs-reporting split."""

    not_done = "not-done"
    not_reported_suspected = "not-reported-suspected"


class StepDefectKind(StrEnum):
    """Construct-validity escape: the rater flags the step/gating itself as mis-specified, not the
    paper. Feeds a construct-validity log, NEVER the agreement metrics."""

    step_wrong = "step_wrong"
    gating_wrong = "gating_wrong"
    threshold_wrong = "threshold_wrong"


# --- per-step / per-rater / envelope --------------------------------------------------------------


class StepDefect(_Base):
    kind: StepDefectKind
    note: str


class StepRating(_Base):
    """One rater's blind judgment of one rubric step — the human-comparable SUBSET of the engine's
    ``StepAssessment`` plus the fields the engine lacks. It deliberately OMITS ``did_well``,
    ``suggestions``, ``standards``, ``adversarial_verdict`` — the engine's narrative, which would
    anchor a rater. Their absence is load-bearing (asserted by test)."""

    step_id: str  # references a rubric step (S1..S10); from the rubric payload, never free-typed
    applicable: bool  # stage-1 join axis; invariant: applicable iff status != not_applicable
    status: StepStatus  # stage-2 join axis
    confidence: float = Field(ge=0.0, le=1.0)  # the RATER's own confidence
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # spans the rater cited (verbatim)
    applicability_reason: str = ""  # why the rater judged the step N/A (optional; for adjudication)
    rationale: str = ""  # required on any non-N/A status (engine spreads this across did_well/…)
    missing_subtag: MissingSubtag | None = None  # only when status == missing
    step_defect: StepDefect | None = None  # construct-validity flag; never feeds agreement metrics

    @model_validator(mode="after")
    def _discipline(self) -> StepRating:
        na = self.status is StepStatus.not_applicable
        sid = self.step_id
        if na and self.applicable:
            raise ValueError(f"StepRating[{sid}]: applicable=True but status=not_applicable")
        if not na and not self.applicable:
            raise ValueError(f"StepRating[{sid}]: applicable=False requires status N/A")
        if self.missing_subtag is not None and self.status is not StepStatus.missing:
            raise ValueError(f"StepRating[{sid}]: missing_subtag only valid when status==missing")
        if na:
            return self
        if not self.rationale.strip():
            raise ValueError(f"StepRating[{sid}]: rationale required for {self.status.value}")
        # a 'present' judgment cites where it was seen; an absence (missing) can't quote what's gone
        if self.status in (StepStatus.adequate, StepStatus.partial) and not self.evidence:
            raise ValueError(f"StepRating[{sid}]: {self.status.value} needs an evidence span")
        return self


class Rating(_Base):
    """One rater's full blind pass over one paper. ``steps`` is empty on a relevance-``no``
    short-circuit (the same semantics as ``ScoredResult.short_circuit`` — by convention, not shared
    code). ``gate_facts`` are the rater's own answers to the four gate questions, which drive their
    per-step applicability; compared field-by-field to the engine's as a v0 diagnostic."""

    rater_id: str
    relationship: RaterRelationship
    relevance_label: RelevanceLabel
    relevance_rationale: str
    paper_class_labels: list[PaperClassLabel] = Field(default_factory=list)
    paper_class_rationale: str = ""
    gate_facts: GateFacts | None = None  # the rater's answers (shared schema type, by value)
    steps: list[StepRating] = Field(default_factory=list)
    # Freeform tags the rater attaches to the paper — the Archive's manual tags. Independent of the
    # blind judgment (allowed even on a relevance-``no`` short-circuit); purely a curation aid.
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _discipline(self) -> Rating:
        if not self.relevance_rationale.strip():
            raise ValueError("Rating.relevance_rationale must be non-empty")
        rel = self.relevance_label
        if len(self.paper_class_labels) != len(set(self.paper_class_labels)):
            raise ValueError("Rating: duplicate paper_class_labels")
        if rel is RelevanceLabel.no:
            if self.steps:
                raise ValueError("Rating: relevance 'no' must have no step ratings")
            if self.paper_class_labels:
                raise ValueError("Rating: relevance 'no' must have no paper_class_labels")
            if self.gate_facts is not None:
                raise ValueError("Rating: relevance 'no' must have gate_facts=None")
            return self
        if not self.paper_class_labels:
            raise ValueError(f"Rating: relevance '{rel.value}' needs >=1 paper_class_labels")
        if self.gate_facts is None:
            raise ValueError(f"Rating: relevance '{rel.value}' needs gate_facts")
        ids = [s.step_id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Rating: duplicate step_id in steps")
        return self


class GoldProvenance(_Base):
    """The honesty envelope. ``origin`` is required with no default (see ``GoldOrigin``)."""

    origin: GoldOrigin
    authored_by: str = ""  # rater ids, or the LLM model id for a fake
    selection_seed: int | None = None  # protocol §1 seeded-draw provenance (required to publish)
    rating_guide_version: str = ""  # instrument content-hash; a 'draft:' guide is inadmissible
    created_at: datetime | None = None


class HumanReport(_Base):
    """The persisted gold record for one paper — the human side of the report-to-report diff. Holds
    the 2..3 original blind ``ratings`` (immutable) and, once adjudicated, a ``consensus`` rating.
    Coverage/quality are intentionally absent: the harness derives them from the consensus."""

    work_id: str
    ids: PaperIds = Field(default_factory=PaperIds)
    source_sha256: str  # the byte-pin the harness joins on and hard-fails on drift (protocol §1)
    version_label: str
    rubric_version: str  # shared-by-value with ScoredResult.rubric_version (the relabel trigger)
    rubric_profile: str = "synthesis"  # v0 validates the synthesis profile only
    tier: GoldTier
    provenance: GoldProvenance
    ratings: list[Rating] = Field(default_factory=list)  # original blind passes, never overwritten
    consensus: Rating | None = None  # adjudicated; None until adjudication
    discussion_note: str = ""  # the protocol §2.3 recorded adjudication

    @model_validator(mode="after")
    def _discipline(self) -> HumanReport:
        if not self.ratings:
            raise ValueError("HumanReport requires >=1 rating")
        for r in self.ratings:
            if r.relationship is RaterRelationship.consensus:
                raise ValueError("HumanReport.ratings must not contain a consensus rating")
        cons = self.consensus
        if cons is not None and cons.relationship is not RaterRelationship.consensus:
            raise ValueError("HumanReport.consensus must have relationship 'consensus'")
        return self

    def validate_admissible(self, *, for_publication: bool = False) -> list[str]:
        """Structural admissibility for the harness (protocol §2). Returns a list of violation
        strings (empty == admissible) so the harness can refuse-and-log rather than silently drop a
        paper. ``for_publication`` adds the real-run gates (blind-human origin, a recorded selection
        seed, a frozen — non-'draft:' — rating guide); the fake/dry-run demo path leaves it False.
        The 'prompt author did not adjudicate their own disagreement' rule (G4) lands with the
        adjudication slice, where the disagreement set is available."""
        v: list[str] = []
        if not 2 <= len(self.ratings) <= 3:
            v.append(f"need 2-3 raters, got {len(self.ratings)}")
        if not any(r.relationship is RaterRelationship.independent for r in self.ratings):
            v.append("no independent rater (>=1 required, protocol §2.1)")
        dev = (RaterRelationship.prompt_author, RaterRelationship.engine_dev)
        if self.ratings and all(r.relationship in dev for r in self.ratings):
            v.append("all raters are engine/prompt developers (gate G4)")
        if self.consensus is None:
            v.append("no consensus rating (adjudication incomplete)")
        if not self.source_sha256:
            v.append("source_sha256 not set (protocol §1 byte-pin)")
        if for_publication:
            origin = self.provenance.origin
            if origin is not GoldOrigin.blind_human:
                v.append(f"publication requires origin=blind_human, got {origin.value}")
            if self.provenance.selection_seed is None:
                v.append("publication requires a recorded selection_seed (protocol §1)")
            if self.provenance.rating_guide_version.startswith("draft:"):
                v.append("publication requires a frozen rating guide (got 'draft:'; gate G8)")
        return v
