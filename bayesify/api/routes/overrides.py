"""Rerun and expert-override routes."""

from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import PlainTextResponse

from bayesify.api import config, resources
from bayesify.api.db.mongo import mongo
from bayesify.api.jobs import pipeline, tasks
from bayesify.api.runtime import api
from bayesify.core.validation.override_store import Override

router = APIRouter()


def trusted_author(token: str) -> str | None:
    if not token:
        return None
    for configured_token, name in config.trusted_tokens().items():
        if secrets.compare_digest(configured_token, token):
            return name
    return None


def engine_step_rationale(assessment) -> str:
    parts = list(assessment.did_well) + [suggestion.text for suggestion in assessment.suggestions]
    return " ".join(part.strip() for part in parts if part.strip())[:1200]


def override_event_payload(override: Override) -> dict:
    return {
        "event": "override_recorded",
        "kind": override.kind,
        "paper_id": override.paper_id,
        "step_id": override.step_id,
        "corrected_status": override.corrected_status,
        "original_status": override.original_status,
        "source_sha256": override.source_sha256,
        "version_label": override.version_label,
        "rubric_profile": override.rubric_profile,
        "author": override.author,
        "trusted": override.trusted,
        "rationale": override.rationale,
        "paper_title": override.paper_title,
        "paper_class_labels": override.paper_class_labels,
        "engine_rationale": override.engine_rationale,
        "evidence_quotes": override.evidence_quotes,
        "value": override.value,
    }


@router.post("/api/papers/{paper_id}/rerun")
async def rerun(
    paper_id: str, relevance_override: str = Form("partial"), token: str = Form("")
) -> dict:
    job = api.store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    is_review = bool(job.result and job.result.not_applicable_reason == "not_an_application")
    overridden = job.result.not_applicable_reason if job.result else None
    if job.data is None and job.content_sha256:
        blobs = resources.blob_store()
        if blobs.exists(job.content_sha256):
            job.data = blobs.get(job.content_sha256)
    if is_review:
        job.force_grade = True
    else:
        job.relevance_override = relevance_override
    job.status = "queued"
    job.stage = None
    job.result = None
    job.inventory = None
    job.from_cache = False
    job.force_fresh = True
    job.events.clear()
    author = trusted_author(token)
    override = Override(
        paper_id=paper_id,
        kind="relevance_rerun",
        original_status=overridden,
        rubric_profile=job.profile,
        source_sha256=job.content_sha256 or "",
        version_label=job.version_label or "",
        author=author or "",
        trusted=author is not None,
        value="force_grade" if is_review else relevance_override,
    )
    resources.overrides_store().add(override)
    await asyncio.to_thread(mongo.save_event, override_event_payload(override))
    tasks.spawn(pipeline.run_job(job))
    return {"paper_id": job.id, "status": job.status}


@router.post("/api/assessments/{assessment_id}/steps/{step_id}/override")
async def record_override(
    assessment_id: str,
    step_id: str,
    corrected_status: str = Form(...),
    rationale: str = Form(""),
    author: str = Form("anonymous"),
    original_status: str = Form(""),
    rubric_profile: str = Form("synthesis"),
    token: str = Form(""),
) -> dict:
    job = api.store.get(assessment_id)
    overridden = original_status or None
    profile = rubric_profile
    source_sha256 = ""
    version_label = ""
    paper_title = ""
    rationale_snapshot = ""
    evidence_quotes: list[str] = []
    paper_class_labels: list[str] = []
    if job is not None:
        profile = job.profile
        source_sha256 = job.content_sha256 or ""
        version_label = job.version_label or ""
        paper_title = job.paper_title or ""
        if job.result is not None:
            assessment = next(
                (a for a in job.result.step_assessments if a.step_id == step_id), None
            )
            if assessment is not None:
                overridden = assessment.status.value
                rationale_snapshot = engine_step_rationale(assessment)
                evidence_quotes = [
                    e.span.quote for e in assessment.evidence if e.span and e.span.quote
                ][:5]
            if job.result.paper_class is not None:
                paper_class_labels = [label.value for label in job.result.paper_class.labels]
    configured_author = trusted_author(token)
    if configured_author is not None:
        author = configured_author
    override = Override(
        paper_id=assessment_id,
        kind="step_status",
        step_id=step_id,
        corrected_status=corrected_status,
        original_status=overridden,
        rubric_profile=profile,
        source_sha256=source_sha256,
        version_label=version_label,
        rationale=rationale,
        author=author,
        trusted=configured_author is not None,
        paper_title=paper_title,
        paper_class_labels=paper_class_labels,
        engine_rationale=rationale_snapshot,
        evidence_quotes=evidence_quotes,
    )
    resources.overrides_store().add(override)
    await asyncio.to_thread(mongo.save_event, override_event_payload(override))
    return {
        "recorded": True,
        "trusted": override.trusted,
        "note": (
            "recorded as a trusted correction"
            if override.trusted
            else "recorded as an advisory note (not applied to grading)"
        ),
    }


@router.get("/api/overrides/export")
async def export_overrides() -> PlainTextResponse:
    overrides = resources.overrides_store().all()
    body = "\n".join(override.model_dump_json() for override in overrides)
    return PlainTextResponse(body, media_type="application/x-ndjson")
