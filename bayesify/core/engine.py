"""The gradable engine composition: screen -> classify -> assess -> score over a parsed document.

The single grading path is shared by the validation harness and the API job loop, so both grade a
paper identically. ``api/jobs/pipeline.run_full`` calls ``grade_parsed`` and keeps only its own
concerns - async/SSE plumbing and the result cache - around it. UI progress is delivered through the
injected ``on_stage`` callback, and the rerun escape-hatch overrides are parameters here. Pure over
the LLM-client seam (testable with a fake client); no caching, no web imports (the ``core is
web-free`` contract holds; ``on_stage`` is a plain stdlib ``Callable``).
"""

from __future__ import annotations

from collections.abc import Callable

from bayesify.core import config
from bayesify.core.assess import assess
from bayesify.core.assess_batch import assess_batch
from bayesify.core.cache import BlobStore
from bayesify.core.classify import classify
from bayesify.core.detectors import run_detectors
from bayesify.core.ingest import ingest_upload
from bayesify.core.parse import parse
from bayesify.core.pipeline import screen_and_classify
from bayesify.core.rubric.models import RubricSpec
from bayesify.core.schema import (
    Evidence,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    RelevanceLabel,
    ScoredResult,
)
from bayesify.core.score import ScoreMeta, score
from bayesify.core.stub import cost_ledger
from bayesify.llm import LLMClient

# (stage, state) progress sink, e.g. ("assess", "running"). The API injects one to drive its UI
# stepper; the harness omits it. A plain stdlib Callable, so the engine emits progress without
# importing anything web (the `core is web-free` contract holds).
StageCallback = Callable[[str, str], None]


def grade_parsed(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    rubric: RubricSpec,
    engine_version: str,
    rubric_version: str,
    relevance_override: str | None = None,
    force_grade: bool = False,
    on_stage: StageCallback | None = None,
    on_paper_class: Callable[[PaperClass], None] | None = None,
) -> ScoredResult:
    """Grade a parsed+detected document end-to-end: relevance gate → (short-circuit on ``no``) →
    classify → assess → score. The **single grading composition** shared by the validation harness
    and the API job loop, so both grade a paper identically.

    Escape hatch (the API rerun path; the harness uses the defaults): ``relevance_override`` forces
    a relevance so a screened-out paper is graded anyway, and ``force_grade`` grades a review piece
    as advisory instead of short-circuiting it. ``on_stage`` is an optional progress sink the API
    uses to drive its UI stepper; ``on_paper_class`` (fired once, just before ``classify`` is marked
    done — so only for papers that pass the gates and will be fully graded) lets the API reveal the
    classification mid-run. Neither ever affects the graded result.
    """
    emit = on_stage or (lambda stage, state: None)
    emit("screen", "running")
    relevance, paper_class, costs = screen_and_classify(parsed, evidence, client=client)
    emit("screen", "done")

    # Escape hatch (rerun): the user forces a relevance so a short-circuited paper is graded anyway.
    # Cite whatever the detectors found (better grounding for a false-negative screen); the override
    # is a human provenance, so it's exempt from the "relevant ⇒ ≥1 ref" rule even with no hits.
    if relevance_override:
        relevance = relevance.model_copy(
            update={
                "label": RelevanceLabel(relevance_override),
                "overridden": True,
                "evidence_refs": relevance.evidence_refs or list(range(len(evidence)))[:3],
                "rationale": relevance.rationale
                + f" [User override: graded as {relevance_override} on request.]",
            }
        )

    review_only = paper_class is not None and paper_class.labels == [PaperClassLabel.review]
    if relevance.label is RelevanceLabel.no:
        return ScoredResult.short_circuit(
            relevance=relevance,
            engine_version=engine_version,
            rubric_version=rubric_version,
            rubric_profile=rubric.profile,
            cost_ledger=cost_ledger(costs),
        )
    if review_only and not force_grade:  # discusses the workflow, doesn't apply it
        return ScoredResult.short_circuit(
            relevance=relevance,
            reason="not_an_application",
            paper_class=paper_class,
            engine_version=engine_version,
            rubric_version=rubric_version,
            rubric_profile=rubric.profile,
            cost_ledger=cost_ledger(costs),
        )
    if paper_class is None:  # the gate had said 'no' but the user forced grading → classify now
        paper_class, classify_cost = classify(parsed, evidence, client=client)
        costs = costs + [classify_cost]
    if on_paper_class is not None:  # paper_class is set past the short-circuits above
        on_paper_class(paper_class)
    emit("classify", "done")

    emit("assess", "running")
    assess_fn = assess_batch if config.grading_strategy() == "batch" else assess
    assessments, gate_facts, assess_costs = assess_fn(
        parsed, evidence, relevance, paper_class, rubric, client=client
    )
    emit("assess", "done")

    emit("score", "running")
    meta = ScoreMeta(engine_version=engine_version, cost_ledger=cost_ledger(costs + assess_costs))
    result = score(relevance, paper_class, assessments, gate_facts, rubric, meta)
    emit("score", "done")
    return result


def grade_document(
    data: bytes,
    *,
    blobs: BlobStore,
    client: LLMClient,
    rubric: RubricSpec,
    engine_version: str,
    rubric_version: str,
    filename: str | None = None,
) -> ScoredResult:
    """Grade raw document bytes: ingest → parse → detect → ``grade_parsed``. Used by the validation
    harness's live engine source to grade a gold-set paper from its content-addressed bytes."""
    source = ingest_upload(blobs, data, filename=filename)
    parsed = parse(source, blobs)
    evidence = run_detectors(parsed)
    return grade_parsed(
        parsed,
        evidence,
        client=client,
        rubric=rubric,
        engine_version=engine_version,
        rubric_version=rubric_version,
    )
