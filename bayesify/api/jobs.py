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
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from bayesify.api.mongo import find_report, find_trusted_step_overrides, save_event, upsert_report
from bayesify.api.papers_store import (
    ArchivedPaper,
    discipline_tags,
    methods_from_inventory,
    paper_type_tags,
    report_fields,
)
from bayesify.core import config
from bayesify.core import schema as s
from bayesify.core.cache import BlobStore, sha256_bytes
from bayesify.core.detectors import EvidenceInventory, evidence_inventory, run_detectors
from bayesify.core.engine import grade_parsed
from bayesify.core.errors import IngestError
from bayesify.core.fetcher import Fetcher
from bayesify.core.ingest import ingest_upload, parse_input
from bayesify.core.override_review import AppliedCorrection, BankOverride, review_overrides
from bayesify.core.parse import parse
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.stub import ENGINE_VERSION, build_stub_result
from bayesify.core.validation.override_store import OverrideStore
from bayesify.core.validation.rating_store import RatingStore, bucket_key
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
    "Local detection: deterministic detectors ran on this machine — no LLM, no scores, and "
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
    """Where the durable ratings/overrides stores live. Defaults to ``~/.bayesify`` (never the
    repo); overridable via ``BAYESIFY_DATA_DIR`` so tests point at a temp dir."""
    return Path(os.environ.get("BAYESIFY_DATA_DIR", str(Path.home() / ".bayesify")))


_blob_dir: Path | None = None


def _blobs() -> BlobStore:
    """Transient store for the manuscript bytes while a job runs (parse needs them on-device). Kept
    in an ephemeral per-process temp dir — never under the data root — so the uploaded paper is not
    durably saved: only the report and its content hash are persisted (to Mongo). The dir is purged
    on process exit / restart, so nothing about the paper survives beyond the analysis."""
    global _blob_dir
    if _blob_dir is None:
        _blob_dir = Path(tempfile.mkdtemp(prefix="bayesify-blobs-"))
    return BlobStore(_blob_dir)


def _ratings_store() -> RatingStore:
    """Durable store for blind ratings (survives restart; the in-memory job dict does not)."""
    return RatingStore(_data_root() / "ratings")


def _overrides_store() -> OverrideStore:
    """Durable A5 override/rerun log (survives restart; the in-memory job dict does not)."""
    return OverrideStore(_data_root())


def _cache_enabled() -> bool:
    """Report dedup is on unless BAYESIFY_NO_CACHE is set. It is **success-only** and the hit is
    surfaced (``from_cache``), so it can never silently mask a broken live run — a failure is never
    stored, and a hit is always labelled."""
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
    paper_authors: list[str] = field(default_factory=list)  # best-effort (provider/PDF metadata)
    paper_year: int | None = None  # best-effort publication year (provider/PDF metadata)
    backend: str | None = None  # who produced the result: "agent-sdk" | "api" | "openai" | "stub"
    from_cache: bool = False  # this result was a cache replay, not a fresh run (surfaced in the UI)
    force_fresh: bool = False  # bypass the cache for this run (set by the rerun escape hatch)
    local_notice: str | None = None  # the labelled local-mode explanation
    error: str | None = None
    # override-review provenance: the trusted corrections applied to the displayed result + the
    # pre-overlay engine coverage/quality, so the report can show what changed and by how much.
    applied_corrections: list[AppliedCorrection] = field(default_factory=list)
    base_coverage: s.Coverage | None = None
    base_quality: float | None = None
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
        "paper_authors": job.paper_authors,
        "paper_year": job.paper_year,
        "parser": job.parser,
        "parser_version": job.parser_version,
        "backend": job.backend,
        "from_cache": job.from_cache,
        "result": job.result.model_dump(mode="json") if job.result else None,
        "inventory": job.inventory.model_dump(mode="json") if job.inventory else None,
        "local_notice": job.local_notice,
    }


def job_state_payload(job: Job) -> dict:
    """Mongo-ready coarse state so any API instance can answer polls for an in-flight job."""
    return {
        "event": "job_state",
        "paper_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "mode": job.mode,
        "source_label": job.source_label,
        "rubric_profile": job.profile,
        "paper_title": job.paper_title,
        "paper_authors": job.paper_authors,
        "paper_year": job.paper_year,
        "parser": job.parser,
        "parser_version": job.parser_version,
        "backend": job.backend,
        "from_cache": job.from_cache,
        "local_notice": job.local_notice,
        "error": job.error,
    }


def _archived_from_analysis(job: Job) -> ArchivedPaper:
    """Build the Archive/dedup entry for a completed AI analysis: metadata + auto tags (paper type +
    discipline from the PaperClass, methods/software from the detector inventory) + the full graded
    result and the engine identity, so a matching content+rubric resubmission can replay it."""
    r = job.result
    paper_class = r.paper_class if r else None
    cov = r.coverage if r else None
    return ArchivedPaper(
        key=bucket_key(job.content_sha256 or "", job.profile),
        paper_id=job.id,
        identifier=(job.identifier.strip() if job.identifier else None),
        source_sha256=job.content_sha256 or "",
        rubric_profile=job.profile,
        version_label=job.version_label or "",
        source_label=job.source_label,
        paper_title=job.paper_title,
        paper_authors=job.paper_authors,
        paper_year=job.paper_year,
        mode=job.mode,
        backend=job.backend,
        relevance_label=r.relevance.label.value if r else "",
        quality_score=r.quality_score if r else None,
        coverage_present=(cov.present if cov else None),
        coverage_applicable=(cov.applicable if cov else None),
        paper_type=paper_type_tags(paper_class),
        discipline=discipline_tags(paper_class),
        methods=methods_from_inventory(job.inventory),
        result=r.model_dump(mode="json") if r else None,
        inventory=job.inventory.model_dump(mode="json") if job.inventory else None,
        engine_version=ENGINE_VERSION,
        rubric_version=r.rubric_version if r else "",
        grading_strategy=config.grading_strategy(),
    )


async def _save_analysis_report_payload(job: Job) -> None:
    """Persist one analysis report event (the by-paper_id rehydration path, fire-and-forget) and
    upsert the Mongo ``reports`` entry (auto-tagged, with the full result) so the paper is
    browsable/searchable and a later matching resubmission dedups to it. The report upsert is
    **awaited** — like the old synchronous cache write — so the dedup entry exists before the job
    reports done (a no-op when Mongo is down)."""
    spawn(asyncio.to_thread(save_event, _analysis_report_payload(job)))
    archived = _archived_from_analysis(job)
    await asyncio.to_thread(upsert_report, archived.key, report_fields(archived))


def _replayable(doc: dict | None, rubric) -> bool:
    """Whether a stored report may be replayed for a fresh clean submit: it must carry a full
    result, be an AI (full-mode) run, and match the current engine/rubric/strategy identity —
    otherwise a code / model / rubric / strategy change would serve a stale report, so we re-run."""
    return bool(
        doc
        and doc.get("result")
        and doc.get("mode") == "full"
        and doc.get("engine_version") == ENGINE_VERSION
        and doc.get("rubric_version") == rubric.rubric_version
        and doc.get("grading_strategy") == config.grading_strategy()
    )


def _save_job_state(job: Job) -> None:
    """Persist coarse job state without blocking the worker."""
    spawn(asyncio.to_thread(save_event, job_state_payload(job)))


async def run_job(job: Job) -> None:
    """Drive a job to completion. An identifier with no uploaded file is fetched first (its OA PDF
    into the blob store). Then: local mode runs the on-device engine (ingest->parse->detect); full
    mode with a backend runs the full real engine (screen->classify->assess->score), or falls back
    to the labelled stub when no credentials are configured."""
    try:
        job.status = "running"
        job.emit({"type": "status", "status": "running"})
        _save_job_state(job)
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
        _save_job_state(job)
    except Exception as exc:
        # Log the full traceback to the app console so failures are debuggable (not swallowed), and
        # surface the message to the UI. str(exc) carries the chained cause (e.g. the SDK's error).
        _log.exception("job %s failed in stage %s", job.id, job.stage)
        job.status = "failed"
        job.error = str(exc)
        job.emit({"type": "failed", "reason": str(exc)})
        _save_job_state(job)


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
    # Provider metadata is preferred over the parsed-PDF metadata (cleaner, structured).
    job.paper_title = fetched.title
    job.paper_authors = fetched.authors
    job.paper_year = fetched.year
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
    # Prefer the provider metadata (set during fetch); for uploads, use the parsed-PDF metadata.
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


async def _run_local(job: Job, *, source: s.SourceDoc | None = None) -> None:
    """The real F3 local-only pipeline: ingest -> parse -> detect -> inventory, on-device."""
    await _front_half(job, source=source)
    job.local_notice = _LOCAL_NOTICE
    job.status = "done"
    job.emit({"type": "done"})


_BANK_PER_STEP = 8  # cap candidate overrides per step so the relevance prompt stays bounded


def _local_trusted_overrides(profile: str) -> list[dict]:
    """Trusted step-status overrides from the on-disk log — the fallback bank when Atlas is down.
    Append-only (oldest→newest), so we reverse to newest-first like the Atlas read."""
    out = [
        o.model_dump()
        for o in _overrides_store().all()
        if o.kind == "step_status" and o.trusted and o.step_id and o.rubric_profile == profile
    ]
    out.reverse()
    return out


def _override_bank(profile: str) -> dict[str, list[BankOverride]]:
    """The global correction bank for one rubric, grouped by step (newest-first, capped). Atlas is
    the source of truth (every machine's corrections); the local log is the fallback when down."""
    docs = find_trusted_step_overrides(profile)
    if docs is None:
        docs = _local_trusted_overrides(profile)
    bank: dict[str, list[BankOverride]] = {}
    for d in docs:
        step_id = d.get("step_id")
        if not step_id or not d.get("corrected_status"):
            continue
        bucket = bank.setdefault(step_id, [])
        if len(bucket) >= _BANK_PER_STEP:
            continue
        bucket.append(
            BankOverride(
                step_id=step_id,
                original_status=d.get("original_status") or "",
                corrected_status=d["corrected_status"],
                rationale=d.get("rationale") or "",
                engine_rationale=d.get("engine_rationale") or "",
                paper_title=d.get("paper_title") or "",
                author=d.get("author") or "",
                evidence_quotes=list(d.get("evidence_quotes") or []),
            )
        )
    return bank


async def _review_overlay(job: Job, rubric) -> None:
    """Run the override-review pass over the graded result and overlay any trusted corrections (for
    display only — the raw result was already cached + saved to Atlas). Requires a live LLM backend;
    a no-op on stub/none, or when the bank has no candidates (zero LLM calls)."""
    if job.result is None or not job.result.step_assessments or config.llm_backend() == "none":
        return
    bank = await asyncio.to_thread(_override_bank, job.profile)
    if not bank:
        return
    corrected, applied, _cost = await asyncio.to_thread(
        review_overrides, job.result, bank, rubric, client=_llm_client(), model=config.judge_model()
    )
    if applied:
        job.base_coverage = job.result.coverage
        job.base_quality = job.result.quality_score
        job.result = corrected
        job.applied_corrections = applied


async def _try_review_overlay(job: Job, rubric) -> None:
    """Best-effort display correction layer; never withhold a completed raw grade."""
    timeout = config.override_review_timeout_s()
    try:
        if timeout == 0:
            return
        await asyncio.wait_for(_review_overlay(job, rubric), timeout=timeout)
    except TimeoutError:
        _log.warning("job %s override review timed out after %.1fs; serving raw result", job.id,
                     timeout)
    except Exception:
        _log.exception("job %s override review failed; serving raw result", job.id)


async def _run_full(job: Job, *, source: s.SourceDoc | None = None) -> None:
    """Full mode (upload + credentials): the whole real engine — ingest -> parse -> detect ->
    screen -> classify -> assess -> score.

    A ``no`` short-circuits with null scores; a relevant paper is graded end-to-end (per-step
    assessments + profile/coverage/quality — no stub). Successful reports are stored in the shared
    Mongo ``reports`` collection keyed by content+rubric, so an identical re-upload — from anyone —
    replays instantly, but **safely**: only successful clean runs are stored (a failure or a forced
    rerun never is), the stored engine/rubric/strategy identity must match the current engine (a
    code/model/prompt change re-analyzes), the hit is labelled ``from_cache`` in the UI, and
    ``force_fresh`` / ``BAYESIFY_NO_CACHE`` bypass it entirely to force a real run.
    """
    rubric = load_rubric(profile=job.profile)  # the chosen rubric (default synthesis)
    content_sha = sha256_bytes(job.data)  # computed before _front_half clears job.data
    key = bucket_key(content_sha, job.profile)  # the shared dedup id: <sha>__<profile>
    # A clean submit (no forced relevance / advisory grade) may replay a stored clean report.
    clean = not job.force_fresh and not job.relevance_override and not job.force_grade
    if _cache_enabled() and clean:
        doc = await asyncio.to_thread(find_report, key)
        if _replayable(doc, rubric):
            job.result = s.ScoredResult.model_validate(doc["result"])
            job.backend = doc.get("backend")
            job.content_sha256 = content_sha
            job.from_cache = True
            for stage in STAGES:  # complete the UI stepper instantly
                job.emit({"type": "stage", "stage": stage, "state": "done"})
            job.status = "done"
            await _try_review_overlay(job, rubric)
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

    # We reached here without raising, so the run succeeded. The store happens in
    # _save_analysis_report_payload below (success-only — a failure never gets persisted).
    job.status = "done"
    await _save_analysis_report_payload(job)  # the RAW engine result is what's persisted to Mongo
    await _try_review_overlay(job, rubric)  # trusted corrections overlay only for display
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
