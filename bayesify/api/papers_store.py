"""The report record for the Archive page and the cross-user dedup cache.

The archive is backed by the MongoDB ``reports`` collection (see ``bayesify.api.db``): one doc
per paper-content + rubric, keyed by the **durable** identity ``<sha>__<profile>`` (the same
``bucket_key`` the rating store uses), so a paper processed twice (rerun, or AI then a human rating)
updates one entry rather than duplicating. Nothing is written to local disk — only the report and
its content hash are stored, never the manuscript bytes.

This module holds the record schema (``ArchivedPaper``) and the pure helpers that derive its auto
tags; ``report_fields`` turns a record into the Mongo ``$set`` payload. Each entry carries the
paper's metadata plus auto tags — ``paper_type`` / ``discipline`` / ``methods``, derived from the
engine's PaperClass and the detector inventory — and, for an AI run, the full ``result`` for replay.
The archive is populated by real analysis runs and human ratings — never by the labelled stub (a
fake result is not archived), matching the analysis-event persistence policy.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bayesify.core.detectors import EvidenceInventory
from bayesify.core.schema import InferenceMethod, PaperClass

# Software-detector-id -> friendly tag for the Archive facet. Software mentions are high-precision
# proper nouns; the context-free method detectors (MCMC/VI/SBI) fire on any mention (incl.
# alternatives / related work), so they are too noisy as facet tags and are NOT surfaced here —
# inference-method tags come from the classifier. Unknown ids are skipped rather than prettified.
_METHOD_LABELS: dict[str, str] = {
    "software.stan": "Stan",
    "software.brms": "brms",
    "software.rstanarm": "rstanarm",
    "software.pymc": "PyMC",
    "software.numpyro": "NumPyro",
    "software.tfp": "TensorFlow Probability",
    "software.jags": "JAGS",
    "software.bugs": "BUGS",
    "software.hddm": "HDDM",
    "software.hssm": "HSSM",
    "software.turing": "Turing.jl",
    "software.bayesflow": "BayesFlow",
}
_METHOD_FAMILIES = {"software"}

def methods_from_inventory(inventory: EvidenceInventory | None) -> list[str]:
    """Friendly method/software tags from the detector inventory's found hits (order-preserving,
    de-duplicated). Empty when there is no inventory (e.g. the placeholder stub path)."""
    if inventory is None:
        return []
    seen = set()
    out = []
    for fam in inventory.families:

        if fam.family not in _METHOD_FAMILIES:
            continue

        for hit in fam.found:
            label = _METHOD_LABELS.get(hit.detector_id)
            if label is None:
                continue
            if label not in seen:
                seen.add(label)
                out.append(label)
    return out


class ArchivedPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = ""  # bucket_key: the durable archive id (<sha>__<profile>)
    paper_id: str = ""  # the most recent (ephemeral) job id, for a "reopen report" link
    identifier: str | None = None  # the submitted arXiv/DOI/URL (identifier-first dedup lookup)
    source_sha256: str = ""
    rubric_profile: str = "synthesis"
    version_label: str = ""
    source_label: str = ""
    paper_title: str | None = None
    paper_authors: list[str] = Field(default_factory=list)
    paper_year: int | None = None
    mode: str = "full"  # "full" (AI) | "local"/"rate" (Human)
    backend: str | None = None
    relevance_label: str = ""
    quality_score: float | None = None
    coverage_present: int | None = None
    coverage_applicable: int | None = None
    # auto tags (refreshed on every upsert)
    paper_type: list[str] = Field(default_factory=list)
    discipline: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    # the full graded report + the detection inventory — kept only for an AI run, so a matching
    # content+rubric resubmission replays this instead of re-analyzing (cross-user dedup cache).
    result: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    # Latest complete, relevance-passing human rubric pass. The append-only local rating store
    # remains the adjudication source; Mongo keeps this with reports so events stay pointer-only.
    human_rating: dict[str, Any] | None = None
    # cache-bust dimensions: a code/model/rubric/strategy change makes a stored report stale, so a
    # replay is served only when these still match the current engine.
    engine_version: str = ""
    rubric_version: str = ""
    grading_strategy: str = ""


def report_fields(paper: ArchivedPaper) -> dict[str, Any]:
    """The Mongo ``$set`` payload for an archive upsert. Empty/None values are dropped so a later
    Human rating (no ``result``, maybe no inventory-derived methods) refreshes metadata without
    wiping the AI report's ``result`` or auto tags — the merge-preserve behaviour the old on-disk
    store did by hand. ``created_at`` / ``updated_at`` are owned by the Mongo upsert."""
    raw = paper.model_dump(mode="json")
    return {k: v for k, v in raw.items() if v not in (None, "", [], {})}


def paper_type_tags(paper_class: PaperClass | None) -> list[str]:
    """Auto paper-type tags from a PaperClass (raw enum values; the UI prettifies)."""
    return [label.value for label in paper_class.labels] if paper_class else []


def discipline_tags(paper_class: PaperClass | None) -> list[str]:
    """Auto discipline tags from a PaperClass (already normalised soft-vocabulary strings)."""
    return list(paper_class.disciplines) if paper_class else []


# InferenceMethod -> friendly label for the report chips + Archive facet. Total over the enum (minus
# "unstated") so a classifier-emitted method never silently vanishes. Mirrors the friendly-label
# shape of methods_from_inventory (NOT paper_type_tags, which returns raw enum values).
_INFERENCE_LABELS: dict[InferenceMethod, str] = {
    InferenceMethod.mcmc: "MCMC",
    InferenceMethod.hmc_nuts: "MCMC (HMC/NUTS)",
    InferenceMethod.variational: "Variational inference",
    InferenceMethod.sbi: "SBI",
    InferenceMethod.smc: "SMC",
    InferenceMethod.abc: "ABC",
    InferenceMethod.laplace_inla: "Laplace/INLA",
    InferenceMethod.exact_analytic: "Analytic",
}


def inference_method_tags(paper_class: PaperClass | None) -> list[str]:
    """Friendly inference-method tags from a PaperClass's classifier-extracted ``methods_used``
    (order-preserving; ``unstated`` is already dropped by the PaperClass validator). This is the
    single source of truth for inference-method labels — the report chips read the same list."""
    if paper_class is None:
        return []
    return [_INFERENCE_LABELS[m] for m in paper_class.methods_used if m in _INFERENCE_LABELS]
