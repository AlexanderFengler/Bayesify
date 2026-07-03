"""Job view-model helpers and cross-worker recovery."""

from __future__ import annotations

import asyncio

from bayesify.api.jobs.model import Job
from bayesify.api.mongo import find_latest_job_state, find_report_by_paper_id
from bayesify.api.runtime import api
from bayesify.core import schema as s
from bayesify.core.detectors import EvidenceInventory
from bayesify.core.report import fix_list


def job_payload(job: Job) -> dict:
    return {
        "paper_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "mode": job.mode,
        "source_label": job.source_label,
        "paper_title": job.paper_title,
        "paper_authors": job.paper_authors,
        "paper_year": job.paper_year,
        "relevance_override": job.relevance_override,
        "result": job.result.model_dump(mode="json") if job.result else None,
        "fix_list": (
            [f.model_dump(mode="json") for f in fix_list(job.result)] if job.result else None
        ),
        "inventory": job.inventory.model_dump(mode="json") if job.inventory else None,
        "parser": job.parser,
        "parser_version": job.parser_version,
        "backend": job.backend,
        "from_cache": job.from_cache,
        "applied_corrections": [c.model_dump(mode="json") for c in job.applied_corrections],
        "base_coverage": job.base_coverage.model_dump(mode="json") if job.base_coverage else None,
        "base_quality": job.base_quality,
        "local_notice": job.local_notice,
        "error": job.error,
    }


def job_from_report_doc(doc: dict) -> Job:
    result = s.ScoredResult.model_validate(doc["result"]) if doc.get("result") else None
    inventory = EvidenceInventory.model_validate(doc["inventory"]) if doc.get("inventory") else None
    return Job(
        id=doc.get("paper_id", ""),
        mode=doc.get("mode") or "full",
        source_label=doc.get("source_label") or "unknown source",
        profile=doc.get("rubric_profile") or "synthesis",
        content_sha256=doc.get("source_sha256"),
        version_label=doc.get("version_label"),
        status="done",
        stage="score" if result is not None else "detect",
        result=result,
        inventory=inventory,
        parser=doc.get("parser"),
        parser_version=doc.get("parser_version"),
        paper_title=doc.get("paper_title"),
        paper_authors=doc.get("paper_authors") or [],
        paper_year=doc.get("paper_year"),
        backend=doc.get("backend"),
        from_cache=bool(doc.get("from_cache", False)),
        local_notice=doc.get("local_notice"),
    )


def job_from_state_event(doc: dict) -> Job:
    return Job(
        id=doc.get("paper_id", ""),
        mode=doc.get("mode") or "full",
        source_label=doc.get("source_label") or "unknown source",
        profile=doc.get("rubric_profile") or "synthesis",
        status=doc.get("status") or "running",
        stage=doc.get("stage"),
        error=doc.get("error"),
    )


async def job_or_mongo_report(paper_id: str) -> Job | None:
    job = api.store.get(paper_id)
    if job is not None:
        return job
    report = await asyncio.to_thread(find_report_by_paper_id, paper_id)
    if report is not None:
        return job_from_report_doc(report)
    state = await asyncio.to_thread(find_latest_job_state, paper_id)
    return job_from_state_event(state) if state is not None else None
