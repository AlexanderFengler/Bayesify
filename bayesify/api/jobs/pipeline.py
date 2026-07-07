"""Async job runner for local and full analyses."""

from __future__ import annotations

import asyncio

from bayesify.api import resources
from bayesify.api.db.mongo import mongo
from bayesify.api.runtime import api
from bayesify.core import schema as s
from bayesify.core.cache import sha256_bytes
from bayesify.core.detectors import evidence_inventory, run_detectors
from bayesify.core.engine import grade_parsed
from bayesify.core.errors import IngestError
from bayesify.core.extract import extract_metadata
from bayesify.core.fetcher import Fetcher
from bayesify.core.ingest import ingest_upload, parse_input
from bayesify.core.parse import parse
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.stub import build_stub_result, engine_version
from bayesify.core.validation.rating_store import bucket_key
from bayesify.llm import LLMClient, LLMError
from bayesify.llm import config as llm_config

from . import overrides, reports
from .model import STAGES, Job

LOCAL_NOTICE = (
    "Local detection: deterministic detectors ran on this machine - no LLM, no scores, and "
    "the paper text was not sent to any model. This is an evidence inventory (what was detected "
    "and where the engine looked), not a graded assessment."
)
NEEDS_UPLOAD = (
    "Nothing to analyze - drop a PDF here, or paste a paper identifier (arXiv / DOI / OpenAlex / "
    "URL) to fetch its open-access copy."
)
STAGE_DELAY_S = 0.45


def save_job_state(job: Job) -> None:
    from . import tasks

    tasks.spawn(asyncio.to_thread(mongo.save_event, reports.job_state_payload(job)))


async def run_job(job: Job) -> None:
    try:
        job.status = "running"
        job.emit({"type": "status", "status": "running"})
        save_job_state(job)
        source: s.SourceDoc | None = None
        if job.data is None and job.identifier:
            source = await fetch_into(job)
        if job.data is None:
            await run_needs_upload(job)
        elif job.mode == "local":
            await run_local(job, source=source)
        elif job.mode == "full" and llm_config.llm_backend() != "none":
            await run_full(job, source=source)
        else:
            await run_stub(job)
    except IngestError as exc:
        api.logger.warning(
            "job %s failed (ingest, stage=%s): %s", job.id, job.stage, exc.user_message
        )
        job.status = "failed"
        job.error = exc.user_message
        job.emit({"type": "failed", "reason": exc.user_message})
        save_job_state(job)
    except Exception as exc:
        api.logger.exception("job %s failed in stage %s", job.id, job.stage)
        job.status = "failed"
        job.error = str(exc)
        job.emit({"type": "failed", "reason": str(exc)})
        save_job_state(job)


async def fetch_into(job: Job) -> s.SourceDoc:
    assert job.identifier is not None
    job.stage = "fetch"
    job.emit({"type": "stage", "stage": "fetch", "state": "running"})
    parsed = parse_input(job.identifier)
    fetched = await asyncio.to_thread(resources.fetcher().fetch, parsed)
    job.data = resources.blob_store().get(fetched.source_doc.sha256)
    job.paper_title = fetched.title
    job.paper_authors = fetched.authors
    job.paper_year = fetched.year
    job.emit({"type": "stage", "stage": "fetch", "state": "done"})
    return fetched.source_doc


async def front_half(
    job: Job, *, source: s.SourceDoc | None = None, client: LLMClient | None = None
) -> tuple[s.ParsedDoc, list[s.Evidence]]:
    blobs = resources.blob_store()
    if source is None:
        data, filename = job.data, job.filename
        assert data is not None
        job.stage = "ingest"
        job.emit({"type": "stage", "stage": "ingest", "state": "running"})
        source = await asyncio.to_thread(ingest_upload, blobs, data, filename=filename)
        job.emit({"type": "stage", "stage": "ingest", "state": "done"})
    job.content_sha256 = source.sha256
    job.version_label = source.version_label
    job.data = None

    job.stage = "parse"
    job.emit({"type": "stage", "stage": "parse", "state": "running"})
    parsed = await asyncio.to_thread(parse, source, blobs)
    job.parser, job.parser_version = parsed.parser, parsed.parser_version
    # Title precedence: a provider (arXiv/DOI) title wins; else an LLM extraction on full runs; else
    # the parse heuristic (weak for uploads). Runs in the parse stage so the parse-done refresh
    # surfaces it; a title miss is never fatal.
    if client is not None and not job.paper_title:
        try:
            job.paper_title = await asyncio.to_thread(extract_metadata, parsed, client=client)
        except LLMError as exc:
            api.logger.warning("title extraction failed for job %s: %s", job.id, exc)
    job.paper_title = job.paper_title or parsed.title
    job.paper_authors = job.paper_authors or parsed.authors
    job.paper_year = job.paper_year or parsed.year
    job.emit({"type": "stage", "stage": "parse", "state": "done"})

    job.stage = "detect"
    job.emit({"type": "stage", "stage": "detect", "state": "running"})
    evidence = await asyncio.to_thread(run_detectors, parsed)
    job.inventory = evidence_inventory(parsed, evidence)
    job.emit({"type": "stage", "stage": "detect", "state": "done"})
    return parsed, evidence


async def run_local(job: Job, *, source: s.SourceDoc | None = None) -> None:
    await front_half(job, source=source)
    job.local_notice = LOCAL_NOTICE
    job.status = "done"
    job.emit({"type": "done"})


async def run_full(job: Job, *, source: s.SourceDoc | None = None) -> None:
    rubric = load_rubric(profile=job.profile)
    content_sha = sha256_bytes(job.data)
    key = bucket_key(content_sha, job.profile)
    clean = not job.force_fresh and not job.relevance_override and not job.force_grade
    if resources.cache_enabled() and clean:
        doc = await asyncio.to_thread(mongo.find_report, key)
        if reports.replayable_report(doc, rubric):
            job.result = s.ScoredResult.model_validate(doc["result"])
            job.backend = doc.get("backend")
            job.content_sha256 = content_sha
            job.from_cache = True
            for stage in STAGES:
                job.emit({"type": "stage", "stage": stage, "state": "done"})
            job.status = "done"
            await overrides.try_review_overlay(job, rubric)
            job.emit({"type": "done"})
            return

    client = resources.llm_client()
    job.backend = llm_config.llm_backend()
    parsed, evidence = await front_half(job, source=source, client=client)
    loop = asyncio.get_running_loop()

    def on_stage(stage: str, state: str) -> None:
        def apply() -> None:
            if state == "running":
                job.stage = stage
            job.emit({"type": "stage", "stage": stage, "state": state})

        loop.call_soon_threadsafe(apply)

    def on_paper_class(pc: s.PaperClass) -> None:
        # Transient: lets the Analyzing screen reveal the classification while assess/score run. Set
        # before the classify-done SSE the frontend refreshes on, so getPaper sees it. A plain
        # attribute assignment is atomic under the GIL — no need to hop to the loop thread.
        job.paper_class = pc.model_dump(mode="json")

    job.result = await asyncio.to_thread(
        grade_parsed,
        parsed,
        evidence,
        client=client,
        rubric=rubric,
        engine_version=engine_version(),
        rubric_version=rubric.rubric_version,
        relevance_override=job.relevance_override,
        force_grade=job.force_grade,
        on_stage=on_stage,
        on_paper_class=on_paper_class,
    )

    job.status = "done"
    await reports.save_analysis_report(job)
    await overrides.try_review_overlay(job, rubric)
    job.emit({"type": "done"})


async def run_needs_upload(job: Job) -> None:
    job.local_notice = NEEDS_UPLOAD
    job.status = "done"
    job.emit({"type": "done"})


async def run_stub(job: Job) -> None:
    for stage in STAGES:
        job.stage = stage
        job.emit({"type": "stage", "stage": stage, "state": "running"})
        await asyncio.sleep(STAGE_DELAY_S)
        job.emit({"type": "stage", "stage": stage, "state": "done"})
    job.result = build_stub_result(job.mode)
    job.backend = "stub"
    job.status = "done"
    job.emit({"type": "done"})


__all__ = [
    "Fetcher",
    "front_half",
    "fetch_into",
    "grade_parsed",
    "run_full",
    "run_job",
    "run_local",
    "run_needs_upload",
    "run_stub",
    "save_job_state",
]
