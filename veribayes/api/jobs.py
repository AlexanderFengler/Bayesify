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
from dataclasses import dataclass, field
from pathlib import Path

from veribayes.core import config
from veribayes.core import schema as s
from veribayes.core.assess import assess
from veribayes.core.cache import BlobStore, FullResultKey, ResultCache, sha256_bytes
from veribayes.core.classify import classify
from veribayes.core.detectors import EvidenceInventory, evidence_inventory, run_detectors
from veribayes.core.errors import IngestError
from veribayes.core.ingest import ingest_upload
from veribayes.core.llm import AgentSDKClient, AnthropicClient, LLMClient
from veribayes.core.parse import parse
from veribayes.core.pipeline import screen_and_classify
from veribayes.core.rubric.loader import load_rubric
from veribayes.core.score import ScoreMeta, score
from veribayes.core.stub import ENGINE_VERSION, RUBRIC_VERSION, build_stub_result, cost_ledger

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
_LOCAL_NEEDS_UPLOAD = (
    "Local-only mode currently runs on an uploaded PDF (so nothing leaves your machine). Fetching "
    "a paper by identifier in local mode is coming next — drop the PDF here, or use Full mode."
)
_TERMINAL = {"done", "failed"}
_STAGE_DELAY_S = 0.45  # simulated per-stage work (stub paths) so progress is visible in the UI
_log = logging.getLogger("veribayes.jobs")


def _data_root() -> Path:
    """Where uploaded blobs live. Defaults to ``~/.veribayes`` (never the repo); overridable via
    ``VERIBAYES_DATA_DIR`` so tests point at a temp dir."""
    return Path(os.environ.get("VERIBAYES_DATA_DIR", str(Path.home() / ".veribayes")))


def _blobs() -> BlobStore:
    return BlobStore(_data_root() / "blobs")


def _results() -> ResultCache:
    return ResultCache(_data_root() / "results")


def _cache_enabled() -> bool:
    """Result caching is on unless VERIBAYES_NO_CACHE is set. Caching is **success-only** and the
    cache hit is surfaced (``from_cache``), so it can never silently mask a broken live run — a
    failure is never cached, and a hit is always labelled."""
    return os.environ.get("VERIBAYES_NO_CACHE", "").strip().lower() not in ("1", "true", "yes")


@dataclass
class Job:
    id: str
    mode: str  # "full" | "local"
    source_label: str  # what the user gave us (filename or an ID/URL)
    data: bytes | None = None  # uploaded PDF bytes (local-only real pipeline); cleared after parse
    filename: str | None = None
    content_sha256: str | None = None  # set at ingest; lets the rerun escape hatch re-read the blob
    relevance_override: str | None = None  # set by the rerun escape hatch
    status: str = "queued"  # queued | running | done | failed
    stage: str | None = None
    result: s.ScoredResult | None = None  # None in local mode (no scores)
    inventory: EvidenceInventory | None = None  # local-only detection result
    parser: str | None = None  # which parser ran (docling | pymupdf), surfaced in the local report
    parser_version: str | None = None
    backend: str | None = None  # who produced the result: "agent-sdk" | "api" | "stub"
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


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        # A5 scaffolding: append-only override log, keyed by assessment id (= paper id at M1).
        self.overrides: list[dict] = []

    def create(
        self,
        *,
        mode: str,
        source_label: str,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            mode=mode,
            source_label=source_label,
            data=data,
            filename=filename,
        )
        self._jobs[job.id] = job
        return job

    def get(self, paper_id: str) -> Job | None:
        return self._jobs.get(paper_id)

    def delete(self, paper_id: str) -> bool:
        return self._jobs.pop(paper_id, None) is not None


def _llm_client() -> LLMClient:
    """The LLM client for full mode, chosen by ``config.llm_backend()``: the Claude subscription via
    the Agent SDK, or the API key. A seam: tests monkeypatch this to inject a FakeLLMClient."""
    if config.llm_backend() == "agent-sdk":
        return AgentSDKClient()
    return AnthropicClient(api_key=config.anthropic_api_key())


async def run_job(job: Job) -> None:
    """Drive a job to completion. Uploads run the real front-half engine (ingest->parse->detect);
    full mode with an API key adds screen+classify; every other path keeps the M1 stub / placeholder
    until its component lands."""
    try:
        job.status = "running"
        job.emit({"type": "status", "status": "running"})
        if job.mode == "local" and job.data is not None:
            await _run_local(job)
        elif job.mode == "full" and job.data is not None and config.llm_backend() != "none":
            await _run_full(job)
        else:
            await _run_stub(job)
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


async def _front_half(job: Job) -> tuple[s.ParsedDoc, list[s.Evidence]]:
    """The on-device front half shared by local and full mode: ingest -> parse -> detect, with a
    stage event around each (parse is CPU-bound, so each step runs in a worker thread). Sets the
    job's parser + evidence inventory. ``IngestError`` propagates to ``run_job``."""
    blobs = _blobs()
    data, filename = job.data, job.filename
    assert data is not None

    job.stage = "ingest"
    job.emit({"type": "stage", "stage": "ingest", "state": "running"})
    source = await asyncio.to_thread(ingest_upload, blobs, data, filename=filename)
    job.content_sha256 = source.sha256  # the rerun escape hatch re-reads the blob by this
    job.data = None  # bytes are now content-addressed in the blob store; free the in-memory copy
    job.emit({"type": "stage", "stage": "ingest", "state": "done"})

    job.stage = "parse"
    job.emit({"type": "stage", "stage": "parse", "state": "running"})
    parsed = await asyncio.to_thread(parse, source, blobs)
    job.parser, job.parser_version = parsed.parser, parsed.parser_version
    job.emit({"type": "stage", "stage": "parse", "state": "done"})

    job.stage = "detect"
    job.emit({"type": "stage", "stage": "detect", "state": "running"})
    evidence = await asyncio.to_thread(run_detectors, parsed)
    job.inventory = evidence_inventory(parsed, evidence)
    job.emit({"type": "stage", "stage": "detect", "state": "done"})
    return parsed, evidence


async def _run_local(job: Job) -> None:
    """The real F3 local-only pipeline: ingest -> parse -> detect -> inventory, on-device."""
    await _front_half(job)
    job.local_notice = _LOCAL_NOTICE
    job.status = "done"
    job.emit({"type": "done"})


async def _run_full(job: Job) -> None:
    """Full mode (upload + credentials): the whole real engine — ingest -> parse -> detect ->
    screen -> classify -> assess -> score.

    A ``no`` short-circuits with null scores; a relevant paper is graded end-to-end (per-step
    assessments + profile/coverage/quality — no stub). Results are cached so identical re-uploads
    return instantly — but **safely**, so a hit can never mask a broken run: only successful runs
    are cached (a failure is never stored), the key includes ``engine_version`` (a code/model/prompt
    change busts it), the hit is labelled ``from_cache`` in the UI, and ``force_fresh`` /
    ``VERIBAYES_NO_CACHE`` bypass it entirely to force a real run.
    """
    key = FullResultKey(
        content_sha256=sha256_bytes(job.data),  # computed before _front_half clears job.data
        engine_version=ENGINE_VERSION,
        rubric_version=RUBRIC_VERSION,
        mode="full",
        relevance_override=job.relevance_override,
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
            job.emit({"type": "done"})
            return

    parsed, evidence = await _front_half(job)
    client = _llm_client()
    job.backend = config.llm_backend()  # "agent-sdk" (subscription) | "api" — shown in the report

    job.stage = "screen"
    job.emit({"type": "stage", "stage": "screen", "state": "running"})
    relevance, paper_class, costs = await asyncio.to_thread(
        screen_and_classify, parsed, evidence, client=client
    )
    job.emit({"type": "stage", "stage": "screen", "state": "done"})

    # Escape hatch (rerun): the user forces a relevance so a short-circuited paper is graded anyway.
    # Cite whatever the detectors found (better grounding for a false-negative screen); the override
    # is a human provenance, so it's exempt from the "relevant ⇒ ≥1 ref" rule even with no hits.
    if job.relevance_override:
        relevance = relevance.model_copy(
            update={
                "label": s.RelevanceLabel(job.relevance_override),
                "overridden": True,
                "evidence_refs": relevance.evidence_refs or list(range(len(evidence)))[:3],
                "rationale": relevance.rationale + " [User override: graded as "
                f"{job.relevance_override} on request.]",
            }
        )

    if relevance.label is s.RelevanceLabel.no:
        job.result = s.ScoredResult.short_circuit(
            relevance=relevance,
            engine_version=ENGINE_VERSION,
            rubric_version=RUBRIC_VERSION,
            cost_ledger=cost_ledger(costs),
        )
    else:
        if paper_class is None:  # the gate had said 'no' but the user forced grading → classify now
            paper_class, classify_cost = await asyncio.to_thread(
                classify, parsed, evidence, client=client
            )
            costs = costs + [classify_cost]
        job.emit({"type": "stage", "stage": "classify", "state": "done"})
        job.stage = "assess"
        job.emit({"type": "stage", "stage": "assess", "state": "running"})
        assessments, gate_facts, assess_costs = await asyncio.to_thread(
            assess, parsed, evidence, relevance, paper_class, _RUBRIC, client=client
        )
        job.emit({"type": "stage", "stage": "assess", "state": "done"})
        job.stage = "score"
        job.emit({"type": "stage", "stage": "score", "state": "running"})
        ledger = cost_ledger(costs + assess_costs)
        meta = ScoreMeta(engine_version=ENGINE_VERSION, cost_ledger=ledger)
        job.result = score(relevance, paper_class, assessments, gate_facts, _RUBRIC, meta)
        job.emit({"type": "stage", "stage": "score", "state": "done"})

    # Cache only on success (we reached here without raising) — never mask a broken run.
    if _cache_enabled():
        _results().put(key, {"backend": job.backend, "result": job.result.model_dump(mode="json")})
    job.status = "done"
    job.emit({"type": "done"})


async def _run_stub(job: Job) -> None:
    """The pre-component placeholder: simulate the stages, then attach the stub result (full mode)
    or the 'upload needed' notice (local mode without a PDF)."""
    stages = LOCAL_STAGES if job.mode == "local" else STAGES
    for stage in stages:
        job.stage = stage
        job.emit({"type": "stage", "stage": stage, "state": "running"})
        await asyncio.sleep(_STAGE_DELAY_S)
        job.emit({"type": "stage", "stage": stage, "state": "done"})
    if job.mode == "local":
        job.local_notice = _LOCAL_NEEDS_UPLOAD  # detection needs the bytes; nothing to show
    else:
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
