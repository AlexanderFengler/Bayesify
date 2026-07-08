"""In-memory job state and bounded job registry."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from bayesify.core import schema
from bayesify.core.detectors import EvidenceInventory
from bayesify.core.override_review import AppliedCorrection

STAGES = (
    "ingest",
    "parse",
    "detect",
    "screen",
    "classify",
    "assess",
    "score",
)
TERMINAL_EVENTS = {"done", "failed"}


@dataclass
class Job:
    id: str
    mode: str
    source_label: str
    data: bytes | None = None
    filename: str | None = None
    identifier: str | None = None
    profile: str = "synthesis"
    # May be precomputed by the upload route for its archive lookup; direct/background jobs compute
    # it lazily in the pipeline. Reusing it avoids hashing a large upload twice.
    content_sha256: str | None = None
    version_label: str | None = None
    relevance_override: str | None = None
    force_grade: bool = False
    status: str = "queued"
    stage: str | None = None
    result: schema.ScoredResult | None = None
    inventory: EvidenceInventory | None = None
    parser: str | None = None
    parser_version: str | None = None
    paper_title: str | None = None
    paper_authors: list[str] = field(default_factory=list)
    paper_year: int | None = None
    # Transient mid-run classification (PaperClass.model_dump), set once classify passes so the
    # Analyzing screen can reveal the paper type / methods while assess+score run. Not persisted;
    # the final classification lives in `result`.
    paper_class: dict | None = None
    backend: str | None = None
    from_cache: bool = False
    force_fresh: bool = False
    local_notice: str | None = None
    error: str | None = None
    applied_corrections: list[AppliedCorrection] = field(default_factory=list)
    base_coverage: schema.Coverage | None = None
    base_quality: float | None = None
    seq: int = 0
    events: list[dict] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)

    def emit(self, event: dict) -> None:
        self.seq += 1
        event = {"seq": self.seq, **event}
        self.events.append(event)
        for queue in list(self.subscribers):
            queue.put_nowait(event)


def max_jobs() -> int:
    try:
        return max(1, int(os.environ.get("BAYESIFY_MAX_JOBS", "256")))
    except ValueError:
        return 256


class JobStore:
    def __init__(self) -> None:
        self._jobs = OrderedDict()

    def create(
        self,
        *,
        mode: str,
        source_label: str,
        data: bytes | None = None,
        filename: str | None = None,
        identifier: str | None = None,
        profile: str = "synthesis",
        content_sha256: str | None = None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            mode=mode,
            source_label=source_label,
            data=data,
            filename=filename,
            identifier=identifier,
            profile=profile,
            content_sha256=content_sha256,
        )
        self._jobs[job.id] = job

        while len(self._jobs) > max_jobs():
            self._jobs.popitem(last=False)
        return job

    def get(self, paper_id: str) -> Job | None:
        job = self._jobs.get(paper_id)
        if job is not None:
            self._jobs.move_to_end(paper_id)
        return job

    def find_cached_rejection(self, content_sha256: str, profile: str) -> Job | None:
        """Newest completed full-mode result for this exact document/rubric, when it stopped at
        the not-Bayesian gate. This is intentionally process-local: rejected uploads avoid repeated
        classification during the current session without becoming entries in the public archive."""
        for paper_id in reversed(self._jobs):
            job = self._jobs[paper_id]
            if (
                job.mode != "full"
                or job.profile != profile
                or job.content_sha256 != content_sha256
                or job.status != "done"
                or job.result is None
            ):
                continue

            # The newest completed result is authoritative. A later forced/overridden run must not
            # be shadowed by an older rejection of the same bytes.
            if (
                not job.relevance_override
                and not job.force_grade
                and job.result.not_applicable_reason == "not_bayesian"
            ):
                self._jobs.move_to_end(paper_id)
                return job
            return None
        return None
