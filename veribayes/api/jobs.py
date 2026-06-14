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
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from veribayes.core import schema as s
from veribayes.core.cache import BlobStore
from veribayes.core.detectors import EvidenceInventory, evidence_inventory, run_detectors
from veribayes.core.errors import IngestError
from veribayes.core.ingest import ingest_upload
from veribayes.core.parse import parse
from veribayes.core.stub import build_stub_result

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


def _data_root() -> Path:
    """Where uploaded blobs live. Defaults to ``~/.veribayes`` (never the repo); overridable via
    ``VERIBAYES_DATA_DIR`` so tests point at a temp dir."""
    return Path(os.environ.get("VERIBAYES_DATA_DIR", str(Path.home() / ".veribayes")))


def _blobs() -> BlobStore:
    return BlobStore(_data_root() / "blobs")


@dataclass
class Job:
    id: str
    mode: str  # "full" | "local"
    source_label: str  # what the user gave us (filename or an ID/URL)
    data: bytes | None = None  # uploaded PDF bytes (local-only real pipeline); cleared after parse
    filename: str | None = None
    relevance_override: str | None = None  # set by the rerun escape hatch
    status: str = "queued"  # queued | running | done | failed
    stage: str | None = None
    result: s.ScoredResult | None = None  # None in local mode (no scores)
    inventory: EvidenceInventory | None = None  # local-only detection result
    parser: str | None = None  # which parser ran (docling | pymupdf), surfaced in the local report
    parser_version: str | None = None
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


async def run_job(job: Job) -> None:
    """Drive a job to completion. Local-only + upload runs the real front-half engine; every other
    path keeps the M1 stub / placeholder until its component lands."""
    try:
        job.status = "running"
        job.emit({"type": "status", "status": "running"})
        if job.mode == "local" and job.data is not None:
            await _run_local(job)
        else:
            await _run_stub(job)
    except IngestError as exc:  # typed, user-facing (bad PDF, scanned, encrypted, …)
        job.status = "failed"
        job.error = exc.user_message
        job.emit({"type": "failed", "reason": exc.user_message})
    except Exception as exc:  # pragma: no cover - defensive
        job.status = "failed"
        job.error = str(exc)
        job.emit({"type": "failed", "reason": str(exc)})


async def _run_local(job: Job) -> None:
    """The real F3 local-only pipeline: ingest -> parse -> detect -> inventory, on-device.

    Each stage runs in a worker thread (parse is CPU-bound) so the event loop keeps streaming
    progress. ``IngestError`` from ingest/parse propagates to ``run_job`` as a user-facing failure.
    """
    blobs = _blobs()
    data, filename = job.data, job.filename
    assert data is not None

    job.stage = "ingest"
    job.emit({"type": "stage", "stage": "ingest", "state": "running"})
    source = await asyncio.to_thread(ingest_upload, blobs, data, filename=filename)
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

    job.local_notice = _LOCAL_NOTICE
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
