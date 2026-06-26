"""In-process async job worker + SSE pub/sub.

In **local-only mode with an uploaded PDF** a job now runs the real engine front-half on-device —
ingest -> parse -> detect -> evidence inventory (components a + b + c) — with no LLM and nothing
sent to a model (F3). The full pipeline and identifier-fetch paths remain the M1 stub / placeholder
until their components land. A job broadcasts a stage event stream; late SSE subscribers replay
missed events via a monotonic ``seq`` so nothing is dropped between start and stream open.

This is M1/M2-scale on purpose (a dict registry, asyncio tasks, a content-addressed blob store under
the user's home). Runtime-hardening items (orphan sweep, arq/rq escalation) are later milestones.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from bayesify.api.mongo import save_event
from bayesify.core import config
from bayesify.core import schema as s
from bayesify.core.cache import BlobStore, FullResultKey, ResultCache, sha256_bytes
from bayesify.core.detectors import EvidenceInventory, evidence_inventory, run_detectors
from bayesify.core.engine import grade_parsed
from bayesify.core.errors import IngestError
from bayesify.core.fetcher import Fetcher
from bayesify.core.ingest import ingest_upload, parse_input
from bayesify.core.parse import parse
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.stub import ENGINE_VERSION, build_stub_result
from bayesify.core.validation.override_store import OverrideStore
from bayesify.core.validation.rating_store import RatingStore
from bayesify.llm import LLMClient, make_llm_client

_RUBRIC = load_rubric()  # static rubric spec, loaded once

# Pipeline stages surfaced to the UI (plans 02 §3.4).
STAGES: tuple[str, ...] = (
    "ingest",
    "parse",
    "detect",
    "screen",
    "classify",
    "assess",
    "score",
)
# Local-only mode (F3): parse + detectors only — no LLM, no scores. Fewer stages, honestly.
LOCAL_STAGES: tuple[str, ...] = ("ingest", "parse", "detect")
_LOCAL_NOTICE = (
    "Local-only detection: deterministic detectors ran on this machine — no LLM, no scores, and "
    "the paper text was not sent to any model. This is an evidence inventory (what was detected "
    "and where the engine looked), not a graded assessment."
)
_NEEDS_UPLOAD = (
    "Nothing to analyze — drop a PDF here, or paste a paper identifier (arXiv / DOI / OpenAlex / "
    "URL) to fetch its open-access copy."
)
_TERMINAL = {"done", "failed"}
_STAGE_DELAY_S = 0.45  # simulated per-stage work (stub paths) so progress is visible in the UI
_log = logging.getLogger("bayesify.jobs")

# Background tasks (the grade runs and the fire-and-forget Mongo writes) are held in a set with a
# strong reference until they finish, so the event loop can't GC one mid-run, and a done-callback
# logs any unexpected failure instead of letting it vanish as an unretrieved-exception warning.
_background_tasks: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    """Create a tracked background task: retained until done, with unexpected failures logged."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)
    return task


def _on_task_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        _log.error("background task failed", exc_info=task.exception())


def _data_root() -> Path:
    """Where uploaded blobs live. Defaults to ``~/.bayesify`` (never the repo); overridable via
    ``BAYESIFY_DATA_DIR`` so tests point at a temp dir."""
    return Path(os.environ.get("BAYESIFY_DATA_DIR", str(Path.home() / ".bayesify")))


def _blobs() -> BlobStore:
    return BlobStore(_data_root() / "blobs")


def _results() -> ResultCache:
    return ResultCache(_data_root() / "results")


def _ratings_store() -> RatingStore:
    """Durable store for blind ratings (survives restart; the in-memory job dict does not)."""
    return RatingStore(_data_root() / "ratings")


def _overrides_store() -> OverrideStore:
    """Durable A5 override/rerun log (survives restart; the in-memory job dict does not)."""
    return OverrideStore(_data_root())


def _cache_enabled() -> bool:
    """Result caching is on unless BAYESIFY_NO_CACHE is set. Caching is **success-only** and the
    cache hit is surfaced (``from_cache``), so it can never silently mask a broken live run — a
    failure is never cached, and a hit is always labelled."""
    return os.environ.get("BAYESIFY_NO_CACHE", "").strip().lower() not in ("1", "true", "yes")


@dataclass
class Job:
    id: str
    mode: str  # "full" | "local"
    source_label: str  # what the user gave us (filename or an ID/URL)
    data: bytes | None = None  # uploaded PDF bytes (local-only real pipeline); cleared after parse
    filename: str | None = None
    identifier: str | None = None  # a pasted arXiv/DOI/OpenAlex/URL to fetch (no uploaded file)
    profile: str = "synthesis"  # which rubric to grade against (registry id; default synthesis)
    content_sha256: str | None = None  # set at ingest; lets the rerun escape hatch re-read the blob
    version_label: str | None = None  # e.g. "arXiv v2" / "uploaded PDF"; pins the rated doc version
    relevance_override: str | None = None  # rerun escape hatch: force a relevance (not-Bayesian)
    force_grade: bool = False  # rerun escape hatch: grade a review/opinion piece anyway (advisory)
    status: str = "queued"  # queued | running | done | failed
    stage: str | None = None
    result: s.ScoredResult | None = None  # None in local mode (no scores)
    inventory: EvidenceInventory | None = None  # local-only detection result
    parser: str | None = None  # which parser ran (docling | pymupdf), surfaced in the local report
    parser_version: str | None = None
    paper_title: str | None = None  # best-effort title for display (provider/page-1; may be None)
    backend: str | None = None  # who produced the result: "agent-sdk" | "api" | "openai" | "stub"
    from_cache: bool = False  # this result was a cache replay, not a fresh run (surfaced in the UI)
    force_fresh: bool = False  # bypass the cache for this run (set by the rerun escape hatch)
    local_notice: str | None = None  # the labelled local-mode explanation
    error: str | None = None
    _seq: int = 0
    events: list[dict] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)

    def emit(self, event: dict) -> None:
        self._seq += 1
        event = {"seq": self._seq, **event}
        self.events.append(event)
        for q in list(self.subscribers):
            q.put_nowait(event)


def _max_jobs() -> int:
    """Cap on retained in-memory jobs (overridable via ``BAYESIFY_MAX_JOBS``). Generous for local
    single-user use; durable state (ratings/overrides/blobs/results) lives on disk, so eviction only
    drops a finished job's in-memory view, never user data."""
    try:
        return max(1, int(os.environ.get("BAYESIFY_MAX_JOBS", "256")))
    except ValueError:
        return 256


class JobStore:
    def __init__(self) -> None:
        # Bounded LRU so a long-running process can't grow without limit. Blind ratings and A5
        # overrides are persisted durably via `_ratings_store()` / `_overrides_store()`, not here —
        # this only holds the live/recent job views, which are safe to evict once finished.
        self._jobs: OrderedDict[str, Job] = OrderedDict()

    def create(
        self,
        *,
        mode: str,
        source_label: str,
        data: bytes | None = None,
        filename: str | None = None,
        identifier: str | None = None,
        profile: str = "synthesis",
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            mode=mode,
            source_label=source_label,
            data=data,
            filename=filename,
            identifier=identifier,
            profile=profile,
        )
        self._jobs[job.id] = job  # newest key is inserted last → most-recently-used
        while len(self._jobs) > _max_jobs():
            self._jobs.popitem(last=False)  # evict the least-recently-used
        return job

    def get(self, paper_id: str) -> Job | None:
        job = self._jobs.get(paper_id)
        if job is not None:
            self._jobs.move_to_end(paper_id)  # a touch keeps an active job warm (LRU)
        return job


def _fetcher() -> Fetcher:
    """The open-access fetcher for identifier submissions. A seam: tests monkeypatch this with a
    Fetcher over an httpx ``MockTransport`` so no live network is hit."""
    return Fetcher(
        httpx.Client(),
        _blobs(),
        openalex_api_key=config.openalex_api_key(),
        unpaywall_email=config.unpaywall_email(),
    )


def _llm_client() -> LLMClient:
    """The configured LLM client for full mode. Tests monkeypatch this seam."""
    return make_llm_client()


def _analysis_report_payload(job: Job) -> dict:
    """Mongo-ready shape for an analyze click once the report/inventory exists."""
    return {
        "event": "analysis_report_ready",
        "paper_id": job.id,
        "mode": job.mode,
        "source_label": job.source_label,
        "source_sha256": job.content_sha256,
        "version_label": job.version_label,
        "rubric_profile": job.profile,
        "paper_title": job.paper_title,
        "parser": job.parser,
        "parser_version": job.parser_version,
        "backend": job.backend,
        "from_cache": job.from_cache,
        "result": job.result.model_dump(mode="json") if job.result else None,
        "inventory": job.inventory.model_dump(mode="json") if job.inventory else None,
        "local_notice": job.local_notice,
    }


def _save_analysis_report_payload(job: Job) -> None:
    """Persist one analysis report event when a user-triggered analysis completes."""
    spawn(asyncio.to_thread(save_event, _analysis_report_payload(job)))


async def run_job(job: Job) -> None:
    """Drive a job to completion. An identifier with no uploaded file is fetched first (its OA PDF
    into the blob store). Then: local mode runs the on-device engine (ingest->parse->detect); full
    mode with a backend runs the full real engine (screen->classify->assess->score), or falls back
    to the labelled stub when no credentials are configured."""
    try:
        job.status = "running"
        job.emit({"type": "status", "status": "running"})
        source: s.SourceDoc | None = None
        if job.data is None and job.identifier:
            source = await _fetch_into(job)  # OA fetch → bytes in the blob store; sets job.data
        if job.data is None:
            await _run_needs_upload(job)  # neither a file nor a fetchable identifier
        elif job.mode == "local":
            await _run_local(job, source=source)
        elif job.mode == "full" and config.llm_backend() != "none":
            await _run_full(job, source=source)
        else:
            await _run_stub(job)  # full mode, real bytes, but no credentials → the labelled stub
    except IngestError as exc:  # typed, user-facing (bad PDF, scanned, encrypted, …)
        _log.warning("job %s failed (ingest, stage=%s): %s", job.id, job.stage, exc.user_message)
        job.status = "failed"
        job.error = exc.user_message
        job.emit({"type": "failed", "reason": exc.user_message})
    except Exception as exc:
        # Log the full traceback to the app console so failures are debuggable (not swallowed), and
        # surface the message to the UI. str(exc) carries the chained cause (e.g. the SDK's error).
        _log.exception("job %s failed in stage %s", job.id, job.stage)
        job.status = "failed"
        job.error = str(exc)
        job.emit({"type": "failed", "reason": str(exc)})


async def _fetch_into(job: Job) -> s.SourceDoc:
    """Resolve an identifier to its open-access PDF (off the request path) and stage the bytes in
    the blob store. Returns the fetched ``SourceDoc`` and sets ``job.data`` so the normal grade
    dispatch runs. Fetch failures are ``IngestError`` subclasses → ``run_job`` surfaces them."""
    assert job.identifier is not None
    job.stage = "fetch"
    job.emit({"type": "stage", "stage": "fetch", "state": "running"})
    parsed = parse_input(job.identifier)
    fetched = await asyncio.to_thread(_fetcher().fetch, parsed)
    job.data = _blobs().get(fetched.source_doc.sha256)
    job.paper_title = fetched.title  # the provider/webpage title — preferred over the parsed one
    job.emit({"type": "stage", "stage": "fetch", "state": "done"})
    return fetched.source_doc


async def _front_half(
    job: Job, *, source: s.SourceDoc | None = None
) -> tuple[s.ParsedDoc, list[s.Evidence]]:
    """The on-device front half shared by local and full mode: ingest -> parse -> detect, with a
    stage event around each (parse is CPU-bound, so each step runs in a worker thread). ``source``
    is set for already-fetched papers (bytes already in the blob, ingest skipped). Sets the job's
    parser + evidence inventory. ``IngestError`` propagates to ``run_job``."""
    blobs = _blobs()
    if source is None:
        data, filename = job.data, job.filename
        assert data is not None
        job.stage = "ingest"
        job.emit({"type": "stage", "stage": "ingest", "state": "running"})
        source = await asyncio.to_thread(ingest_upload, blobs, data, filename=filename)
        job.emit({"type": "stage", "stage": "ingest", "state": "done"})
    job.content_sha256 = source.sha256  # the rerun escape hatch re-reads the blob by this
    job.version_label = source.version_label  # pins which doc version a rater rated (protocol §1)
    job.data = None  # bytes are now content-addressed in the blob store; free the in-memory copy

    job.stage = "parse"
    job.emit({"type": "stage", "stage": "parse", "state": "running"})
    parsed = await asyncio.to_thread(parse, source, blobs)
    job.parser, job.parser_version = parsed.parser, parsed.parser_version
    # Prefer the provider/webpage title (set during fetch); for uploads, use the page-1 title.
    job.paper_title = job.paper_title or parsed.title
    job.emit({"type": "stage", "stage": "parse", "state": "done"})

    job.stage = "detect"
    job.emit({"type": "stage", "stage": "detect", "state": "running"})
    evidence = await asyncio.to_thread(run_detectors, parsed)
    job.inventory = evidence_inventory(parsed, evidence)
    job.emit({"type": "stage", "stage": "detect", "state": "done"})
    return parsed, evidence


async def _run_local(job: Job, *, source: s.SourceDoc | None = None) -> None:
    """The real F3 local-only pipeline: ingest -> parse -> detect -> inventory, on-device."""
    await _front_half(job, source=source)
    job.local_notice = _LOCAL_NOTICE
    job.status = "done"
    _save_analysis_report_payload(job)
    job.emit({"type": "done"})


async def _run_full(job: Job, *, source: s.SourceDoc | None = None) -> None:
    """Full mode (upload + credentials): the whole real engine — ingest -> parse -> detect ->
    screen -> classify -> assess -> score.

    A ``no`` short-circuits with null scores; a relevant paper is graded end-to-end (per-step
    assessments + profile/coverage/quality — no stub). Results are cached so identical re-uploads
    return instantly — but **safely**, so a hit can never mask a broken run: only successful runs
    are cached (a failure is never stored), the key includes ``engine_version`` (a code/model/prompt
    change busts it), the hit is labelled ``from_cache`` in the UI, and ``force_fresh`` /
    ``BAYESIFY_NO_CACHE`` bypass it entirely to force a real run.
    """
    rubric = load_rubric(profile=job.profile)  # the chosen rubric (default synthesis)
    key = FullResultKey(
        content_sha256=sha256_bytes(job.data),  # computed before _front_half clears job.data
        engine_version=ENGINE_VERSION,
        rubric_version=rubric.rubric_version,
        mode="full",
        relevance_override=job.relevance_override,
        force_grade=job.force_grade,
        rubric_profile=job.profile,
    )
    if _cache_enabled() and not job.force_fresh:
        cached = _results().get(key)
        if cached is not None:
            job.result = s.ScoredResult.model_validate(cached["result"])
            job.backend = cached.get("backend")
            job.from_cache = True
            for stage in STAGES:  # complete the UI stepper instantly
                job.emit({"type": "stage", "stage": stage, "state": "done"})
            job.status = "done"
            _save_analysis_report_payload(job)
            job.emit({"type": "done"})
            return

    parsed, evidence = await _front_half(job, source=source)
    client = _llm_client()
    job.backend = config.llm_backend()  # "agent-sdk" | "api" | "openai" — shown in the report

    # Grade through the ONE shared composition (engine.grade_parsed) — the same path the validation
    # harness runs — so the app and the harness can never grade a paper differently. grade_parsed is
    # CPU/IO-bound and runs in a worker thread; its stage events are bounced back onto the loop so
    # job.emit (which touches asyncio queues) only ever runs on the event-loop thread.
    loop = asyncio.get_running_loop()

    def on_stage(stage: str, state: str) -> None:
        def apply() -> None:
            if state == "running":
                job.stage = stage
            job.emit({"type": "stage", "stage": stage, "state": state})

        loop.call_soon_threadsafe(apply)

    job.result = await asyncio.to_thread(
        grade_parsed,
        parsed,
        evidence,
        client=client,
        rubric=rubric,
        engine_version=ENGINE_VERSION,
        rubric_version=rubric.rubric_version,
        relevance_override=job.relevance_override,
        force_grade=job.force_grade,
        on_stage=on_stage,
    )

    # Cache only on success (we reached here without raising) — never mask a broken run.
    if _cache_enabled():
        _results().put(key, {"backend": job.backend, "result": job.result.model_dump(mode="json")})
    job.status = "done"
    _save_analysis_report_payload(job)
    job.emit({"type": "done"})


async def _run_needs_upload(job: Job) -> None:
    """No bytes to work on — an identifier was submitted but fetch-by-identifier isn't wired into
    the pipeline yet (and local mode needs the bytes on-device). Show an honest notice rather than
    simulate stages or fabricate a stub report for a paper we never fetched."""
    job.local_notice = _NEEDS_UPLOAD
    job.status = "done"
    job.emit({"type": "done"})


async def _run_stub(job: Job) -> None:
    """Full mode with real bytes but no credentials configured: simulate the stages, then attach the
    labelled placeholder result so the UI is exercisable without an LLM (shown as 'Stub engine')."""
    for stage in STAGES:
        job.stage = stage
        job.emit({"type": "stage", "stage": stage, "state": "running"})
        await asyncio.sleep(_STAGE_DELAY_S)
        job.emit({"type": "stage", "stage": stage, "state": "done"})
    job.result = build_stub_result(job.mode)
    job.backend = "stub"  # no credentials → the labelled placeholder engine
    job.status = "done"
    _save_analysis_report_payload(job)
    job.emit({"type": "done"})


async def event_stream(job: Job):
    """Async generator of SSE payloads for one connection. Replays prior events (by seq) then
    streams live ones until a terminal event."""
    q: asyncio.Queue = asyncio.Queue()
    job.subscribers.add(q)
    try:
        replayed_through = 0
        for ev in list(job.events):
            replayed_through = ev["seq"]
            yield {"data": _dump(ev)}
            if ev["type"] in _TERMINAL:
                return
        while True:
            ev = await q.get()
            if ev["seq"] <= replayed_through:
                continue  # already replayed (emitted during registration)
            yield {"data": _dump(ev)}
            if ev["type"] in _TERMINAL:
                return
    finally:
        job.subscribers.discard(q)


def _dump(event: dict) -> str:
    import json

    return json.dumps(event)
