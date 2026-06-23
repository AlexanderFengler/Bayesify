"""The gradable engine composition — screen → classify → assess → score over a parsed document.

Shared core so the **validation harness grades a paper with the same engine the app ships**:
``api/jobs._run_full`` composes these same stage functions (with UI stage-events + the rerun escape
hatch around them); keep the two aligned. Pure over the LLM-client seam (testable with a fake
client) — no caching, no UI events, no escape-hatch overrides (those are app concerns).
"""

from __future__ import annotations

from bayesify.core.assess import assess
from bayesify.core.cache import BlobStore
from bayesify.core.detectors import run_detectors
from bayesify.core.ingest import ingest_upload
from bayesify.core.parse import parse
from bayesify.core.pipeline import screen_and_classify
from bayesify.core.rubric.models import RubricSpec
from bayesify.core.schema import (
    Evidence,
    PaperClassLabel,
    ParsedDoc,
    RelevanceLabel,
    ScoredResult,
)
from bayesify.core.score import ScoreMeta, score
from bayesify.core.stub import cost_ledger
from bayesify.llm import LLMClient


def grade_parsed(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    rubric: RubricSpec,
    engine_version: str,
    rubric_version: str,
) -> ScoredResult:
    """Grade a parsed+detected document end-to-end: relevance gate → (short-circuit on ``no``) →
    classify → assess → score. The standard engine path (no escape-hatch override)."""
    relevance, paper_class, costs = screen_and_classify(parsed, evidence, client=client)
    if relevance.label is RelevanceLabel.no or paper_class is None:
        return ScoredResult.short_circuit(
            relevance=relevance,
            engine_version=engine_version,
            rubric_version=rubric_version,
            rubric_profile=rubric.profile,
            cost_ledger=cost_ledger(costs),
        )
    if paper_class.primary is PaperClassLabel.review:  # discusses the workflow, doesn't apply it
        return ScoredResult.short_circuit(
            relevance=relevance,
            reason="not_an_application",
            paper_class=paper_class,
            engine_version=engine_version,
            rubric_version=rubric_version,
            rubric_profile=rubric.profile,
            cost_ledger=cost_ledger(costs),
        )
    assessments, gate_facts, assess_costs = assess(
        parsed, evidence, relevance, paper_class, rubric, client=client
    )
    meta = ScoreMeta(engine_version=engine_version, cost_ledger=cost_ledger(costs + assess_costs))
    return score(relevance, paper_class, assessments, gate_facts, rubric, meta)


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
