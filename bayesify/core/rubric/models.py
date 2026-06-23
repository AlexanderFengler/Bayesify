"""Typed models for ``rubric/steps.yaml``.

These mirror the YAML's current ``0.1-draft`` shape (G5: pin the shape now so the loader is stable).
Fields that the rubric-v1.0 freeze will add — the machine-evaluable ``na_when``/``mandatory_when``
predicates (G5/G6), VI-specific S4 criteria (G7), and the scoring block (G5) — are modelled as
optional so today's draft loads and tomorrow's freeze is additive, not a schema break.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ThresholdEntry(_Base):
    """One attributed threshold (e.g. S4 ``rhat_modern``). ``verified`` records whether it was
    adversarially verified in the deep-research run — preserved, never collapsed (the project's own
    transparency rule). Flows into ``StandardRef.verified`` in the assessment."""

    value: str
    source: str
    verified: bool
    note: str | None = None


class GateRule(_Base):
    """Machine-evaluable applicability gate for a step (G5/G6), keyed on the evidence-derived
    ``gate_facts``. Resolved by ``rubric.applicability.step_applicability``; nothing here is
    hardcoded in the engine."""

    na_when_inference: list[str] = Field(default_factory=list)  # not_applicable if inference ∈ list
    na_when_single_model_no_bf: bool = False  # not_applicable if n_models <= 1 and no BF claim
    essential_when_models_gte: int | None = None  # escalate to "expected" if n_models >= this
    essential_when_bf_claimed: bool = False  # escalate to "expected" if a Bayes factor is claimed
    essential_when_prior_informative: bool = False  # escalate if (weakly-)informative priors used


class ScoringBlock(_Base):
    """The G5 scoring machine-half (f-score reads this; see ``rubric/steps.yaml``)."""

    sub_score: dict[str, float]  # status -> numeric sub-score; not_applicable is excluded
    low_confidence_threshold: float  # absences below this confidence count as "uncertain"
    weight_default: float = 1.0
    weights: dict[str, dict[str, float]] = Field(default_factory=dict)  # per-class step overrides
    mixing_rule: str = "max"  # mixed primary+secondary class weight resolution


class RubricStep(_Base):
    id: str
    name: str
    # Applicability gating (paper_class in {empirical, numerical_experiment, methodological}).
    essential_for: list[str] = Field(default_factory=list)
    recommended_for: list[str] = Field(default_factory=list)
    na_when: str | None = None  # human-readable reason; the machine predicate is `gate` (G5/G6)
    mandatory_when: str | None = None  # human-readable; the machine predicate is `gate` (G6)
    gate: GateRule | None = None  # machine-evaluable applicability gate (G5/G6)
    requires: list[str] = Field(default_factory=list)  # e.g. S6 -> [S8]
    inference_scope: list[str] = Field(default_factory=list)  # e.g. [mcmc, hmc_nuts, variational]
    why: str | None = None  # one line: why this step matters for the workflow (shown atop the card)
    adequate: str | None = None
    done_poorly: str | None = None
    note: str | None = None
    thresholds: dict[str, ThresholdEntry] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)


class RubricSpec(_Base):
    rubric_version: str
    status_values: list[str]
    steps: list[RubricStep]
    citations: dict[str, str] = Field(default_factory=dict)
    # Human-facing identity of this rubric (shown in the picker + as the report preamble).
    label: str = ""
    summary: str = ""  # the preamble: what this rubric is and its properties
    # Prose summary (documentation) alongside the structured machine scoring block (G5).
    scoring_rule: str | None = None
    scoring: ScoringBlock | None = None  # the G5 machine scoring block
    # Which rubric this spec is (set by the loader from the registry id): "synthesis" | "gelman" | …
    profile: str = "synthesis"

    @property
    def sources(self) -> list[str]:
        """Source ids this rubric draws on (its citations table). len == 1 ⇒ single-source, so steps
        carry no per-step citation and the source lives in the preamble instead."""
        return sorted(self.citations)

    def step(self, step_id: str) -> RubricStep:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def citation(self, source_id: str) -> str:
        return self.citations[source_id]


class RubricInfo(_Base):
    """A registry entry for the rubric pickers (one per available rubric)."""

    id: str
    label: str
    summary: str
    rubric_version: str
