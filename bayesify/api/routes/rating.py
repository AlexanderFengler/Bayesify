"""Blind human-rating routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from bayesify.api import resources
from bayesify.api.db.mongo import mongo
from bayesify.api.papers_store import (
    ArchivedPaper,
    report_fields,
    software_from_inventory,
)
from bayesify.api.routes.rubrics import rubric_payload
from bayesify.api.runtime import api
from bayesify.core import schema as s
from bayesify.core.rubric import RubricProfileError, load_rubric
from bayesify.core.schema import EvidenceKind
from bayesify.core.validation import Rating
from bayesify.core.validation.rating_store import SubmittedRating, bucket_key

router = APIRouter()

RATE_BLIND_EXCLUDE = {EvidenceKind.absence_search, EvidenceKind.judge_quote}


class RateSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    profile: str = "synthesis"
    source_sha256: str = ""
    version_label: str = ""
    rating: Rating


def compact_event(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def rating_passed_gate(rating: Rating) -> bool:
    return rating.relevance_label in (s.RelevanceLabel.yes, s.RelevanceLabel.partial)


def require_complete_relevant_rating(rating: Rating, rubric) -> None:
    if not rating_passed_gate(rating):
        return
    expected = [step.id for step in rubric.steps]
    got = [step.step_id for step in rating.steps]
    missing = [step_id for step_id in expected if step_id not in got]
    extra = [step_id for step_id in got if step_id not in expected]
    if missing or extra:
        bits = []
        if missing:
            bits.append(f"missing: {', '.join(missing)}")
        if extra:
            bits.append(f"unknown: {', '.join(extra)}")
        raise HTTPException(
            status_code=422,
            detail=(
                "Relevant human reports must include one judgment for every rubric step "
                f"(not_applicable is allowed); {'; '.join(bits)}."
            ),
        )


async def stored_report_for_expired_job(paper_id: str) -> dict | None:
    return await asyncio.to_thread(mongo.find_report_by_paper_id, paper_id)


@router.get("/api/rate/context/{paper_id}")
async def rate_context(paper_id: str, profile: str = "synthesis") -> dict:
    job = api.store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    try:
        rubric = rubric_payload(profile)
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    evidence: list[dict] = []
    where_looked: list[dict] = []
    if job.inventory is not None:
        for family in job.inventory.families:
            for hit in family.found:
                if hit.kind in RATE_BLIND_EXCLUDE:
                    continue
                evidence.append(
                    {
                        "section_id": hit.section_id,
                        "section_title": hit.section_title,
                        "page": hit.page,
                        "quote": hit.quote,
                        "family": hit.family,
                        "detector_id": hit.detector_id,
                        "kind": hit.kind.value,
                    }
                )
        where_looked = [
            {
                "section_id": section.section_id,
                "title": section.title,
                "kind": section.kind.value,
                "page": section.page,
            }
            for section in job.inventory.where_looked
        ]
    return {
        "paper_id": job.id,
        "source_label": job.source_label,
        "source_sha256": job.content_sha256,
        "version_label": job.version_label,
        "rubric": rubric,
        "evidence": evidence,
        "where_looked": where_looked,
    }


@router.post("/api/rate/submit")
async def rate_submit(body: RateSubmit) -> dict:
    job = api.store.get(body.paper_id)
    try:
        rubric = load_rubric(profile=body.profile)
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    require_complete_relevant_rating(body.rating, rubric)

    report = None
    if job is None:
        report = await stored_report_for_expired_job(body.paper_id)
    source_sha256 = (
        (job.content_sha256 if job is not None else None)
        or (report or {}).get("source_sha256")
        or body.source_sha256
    )
    version_label = (
        (job.version_label if job is not None else None)
        or (report or {}).get("version_label")
        or body.version_label
    )
    sub = SubmittedRating(
        paper_id=body.paper_id,
        source_sha256=source_sha256,
        version_label=version_label,
        rubric_version=rubric.rubric_version,
        rubric_profile=body.profile,
        rating=body.rating,
    )
    rating_store = resources.ratings_store()
    rating_store.add(sub)
    n_ratings = rating_store.count_for(sub.source_sha256, sub.rubric_profile, sub.paper_id)
    rating_bucket = bucket_key(sub.source_sha256, sub.rubric_profile, sub.paper_id)
    report_id = (
        bucket_key(sub.source_sha256, sub.rubric_profile)
        if rating_passed_gate(body.rating) and sub.source_sha256
        else ""
    )
    if report_id:
        archived = ArchivedPaper(
            key=report_id,
            paper_id=sub.paper_id,
            source_sha256=sub.source_sha256,
            rubric_profile=sub.rubric_profile,
            version_label=sub.version_label,
            source_label=(
                (job.source_label if job is not None else None)
                or (report or {}).get("source_label")
                or sub.paper_id
            ),
            paper_title=(
                (job.paper_title if job is not None else None) or (report or {}).get("paper_title")
            ),
            paper_authors=(
                (job.paper_authors if job is not None else None)
                or (report or {}).get("paper_authors")
                or []
            ),
            paper_year=(
                (job.paper_year if job is not None else None) or (report or {}).get("paper_year")
            ),
            mode="rate",
            relevance_label=body.rating.relevance_label.value,
            paper_type=[label.value for label in body.rating.paper_class_labels],
            methods=(report or {}).get("methods") or [],
            software=(
                software_from_inventory(job.inventory if job is not None else None)
                or (report or {}).get("software")
                or []
            ),
            human_rating=sub.model_dump(mode="json"),
        )
        await asyncio.to_thread(mongo.upsert_report, archived.key, report_fields(archived))
    await asyncio.to_thread(
        mongo.save_event,
        compact_event(
            {
                "event": "blind_rating_submitted",
                "paper_id": sub.paper_id,
                "rating_id": f"{rating_bucket}:{body.rating.rater_id}",
                "report_id": report_id,
                "n_ratings": n_ratings,
            }
        ),
    )
    return {"recorded": True, "n_ratings": n_ratings}
