"""Paper submission, status, SSE, and report export routes."""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from sse_starlette.sse import EventSourceResponse

from bayesify.api import resources
from bayesify.api.db.mongo import mongo
from bayesify.api.jobs import pipeline, reports, stream, tasks
from bayesify.api.jobs.views import job_or_mongo_report, job_payload
from bayesify.api.render import render_inventory_markdown, render_markdown
from bayesify.api.runtime import api
from bayesify.core.cache import sha256_bytes
from bayesify.core.rubric import RubricProfileError, load_rubric
from bayesify.core.validation.rating_store import bucket_key

router = APIRouter()


def max_upload_bytes() -> int:
    try:
        return max(1, int(os.environ.get("BAYESIFY_MAX_UPLOAD_MB", "50"))) * 1_000_000
    except ValueError:
        return 50_000_000


def source_label(file: UploadFile | None, arxiv_id, doi, openalex_id, url) -> str:
    if file is not None and file.filename:
        return file.filename
    for value in (arxiv_id, doi, openalex_id, url):
        if value:
            return value
    return "unknown source"


@router.post("/api/papers")
async def create_paper(
    mode: str = Form("full"),
    profile: str = Form("synthesis"),
    file: UploadFile | None = File(None),
    arxiv_id: str | None = Form(None),
    doi: str | None = Form(None),
    openalex_id: str | None = Form(None),
    url: str | None = Form(None),
) -> dict:
    if file is None and not any((arxiv_id, doi, openalex_id, url)):
        raise HTTPException(
            status_code=422, detail="Provide a PDF file or one of arxiv_id/doi/openalex_id/url."
        )
    if mode not in ("full", "local"):
        raise HTTPException(status_code=422, detail="mode must be 'full' or 'local'.")
    limit = max_upload_bytes()
    if file is not None and file.size is not None and file.size > limit:
        raise HTTPException(status_code=413, detail=f"PDF too large (max {limit // 1_000_000} MB).")
    try:
        rubric = load_rubric(profile=profile)
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = await file.read() if file is not None else None
    identifier = None if file is not None else (arxiv_id or doi or openalex_id or url)
    content_sha256 = sha256_bytes(data) if data is not None and mode == "full" else None

    # Do the cheapest exact archive lookup before creating a job. For uploads, Mongo's `_id` is the
    # SHA-256 of the submitted bytes plus the rubric profile, so this is an indexed primary-key read
    # with no fuzzy-match false positives. Identifier submissions retain their pre-fetch shortcut.
    if mode == "full" and resources.cache_enabled():
        if content_sha256 is not None:
            existing = await asyncio.to_thread(
                mongo.find_report, bucket_key(content_sha256, profile)
            )
        elif identifier:
            existing = await asyncio.to_thread(
                mongo.find_report_by_identifier, identifier.strip(), profile
            )
        else:  # guarded by input validation above; keeps the variable total for type checkers
            existing = None
        if reports.replayable_report(existing, rubric) and existing.get("paper_id"):
            return {
                "paper_id": existing["paper_id"],
                "status": "done",
                "archive_hit": True,
                "session_hit": False,
            }
        if content_sha256 is not None:
            rejected = api.store.find_cached_rejection(content_sha256, profile)
            if rejected is not None:
                return {
                    "paper_id": rejected.id,
                    "status": "done",
                    "archive_hit": False,
                    "session_hit": True,
                }

    job = api.store.create(
        mode=mode,
        source_label=source_label(file, arxiv_id, doi, openalex_id, url),
        data=data,
        filename=file.filename if file is not None else None,
        identifier=identifier,
        profile=profile,
        content_sha256=content_sha256,
    )
    tasks.spawn(asyncio.to_thread(mongo.save_event, reports.job_state_payload(job)))
    tasks.spawn(pipeline.run_job(job))
    return {
        "paper_id": job.id,
        "status": job.status,
        "archive_hit": False,
        "session_hit": False,
    }


@router.get("/api/papers/{paper_id}")
async def get_paper(paper_id: str) -> dict:
    job = await job_or_mongo_report(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    return job_payload(job)


@router.get("/api/papers/{paper_id}/events")
async def get_events(paper_id: str):
    job = api.store.get(paper_id)
    if job is not None:
        return EventSourceResponse(stream.event_stream(job))
    report = await asyncio.to_thread(mongo.find_report_by_paper_id, paper_id)
    state = None
    if report is None:
        state = await asyncio.to_thread(mongo.find_latest_job_state, paper_id)
    if report is None and state is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")

    async def completed_stream():
        if report is not None:
            yield {"data": json.dumps({"seq": 1, "type": "done"})}
        elif state.get("status") == "failed":
            yield {"data": json.dumps({"seq": 1, "type": "failed", "reason": state.get("error")})}
        else:
            yield {"data": json.dumps({"seq": 1, "type": "status", "status": state["status"]})}

    return EventSourceResponse(completed_stream())


@router.get("/api/papers/{paper_id}/report.json")
async def report_json(paper_id: str):
    job = await job_or_mongo_report(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    if job.result is not None:
        return JSONResponse(job.result.model_dump(mode="json"))
    if job.inventory is not None:
        return JSONResponse(
            {
                "mode": "local",
                "parser": job.parser,
                "parser_version": job.parser_version,
                "inventory": job.inventory.model_dump(mode="json"),
            }
        )
    raise HTTPException(status_code=404, detail="no result yet")


@router.get("/api/papers/{paper_id}/report.md")
async def report_md(paper_id: str):
    job = await job_or_mongo_report(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    if job.result is not None:
        return PlainTextResponse(render_markdown(job))
    if job.inventory is not None:
        return PlainTextResponse(render_inventory_markdown(job))
    raise HTTPException(status_code=404, detail="no result yet")
