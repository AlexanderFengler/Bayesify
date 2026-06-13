"""In-process async job worker + SSE pub/sub.

A job runs the pipeline stages (at M1: simulated, then the stub engine) and broadcasts a stage
event stream. The SSE endpoint subscribes per connection; late subscribers replay missed events via
a monotonic ``seq`` so no event is dropped between job start and stream open.

This is M1-scale on purpose (a dict registry, asyncio tasks). The plan's runtime-hardening items
(on-boot sweep for orphaned jobs, optional arq/rq escalation) are tracked for later milestones.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from veribayes.core import schema as s
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
_TERMINAL = {"done", "failed"}
_STAGE_DELAY_S = 0.45  # simulated per-stage work so progress is visible in the UI


@dataclass
class Job:
    id: str
    mode: str  # "full" | "local"
    source_label: str  # what the user gave us (filename or an ID/URL)
    relevance_override: str | None = None  # set by the rerun escape hatch
    status: str = "queued"  # queued | running | done | failed
    stage: str | None = None
    result: s.ScoredResult | None = None
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

    def create(self, *, mode: str, source_label: str) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], mode=mode, source_label=source_label)
        self._jobs[job.id] = job
        return job

    def get(self, paper_id: str) -> Job | None:
        return self._jobs.get(paper_id)

    def delete(self, paper_id: str) -> bool:
        return self._jobs.pop(paper_id, None) is not None


async def run_job(job: Job) -> None:
    """Drive a job through the stages and attach the stub result."""
    try:
        job.status = "running"
        job.emit({"type": "status", "status": "running"})
        for stage in STAGES:
            job.stage = stage
            job.emit({"type": "stage", "stage": stage, "state": "running"})
            await asyncio.sleep(_STAGE_DELAY_S)
            job.emit({"type": "stage", "stage": stage, "state": "done"})
        job.result = build_stub_result(job.mode)
        job.status = "done"
        job.emit({"type": "done"})
    except Exception as exc:  # pragma: no cover - defensive; stub never raises
        job.status = "failed"
        job.error = str(exc)
        job.emit({"type": "failed", "reason": str(exc)})


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
