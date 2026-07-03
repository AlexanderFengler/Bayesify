"""Report persistence and replay eligibility for completed jobs."""

from __future__ import annotations

import asyncio

from bayesify.api.mongo import save_event, upsert_report
from bayesify.api.papers_store import (
    ArchivedPaper,
    discipline_tags,
    methods_from_inventory,
    paper_type_tags,
    report_fields,
)
from bayesify.core import config
from bayesify.core import schema as s
from bayesify.core.stub import ENGINE_VERSION
from bayesify.core.validation.rating_store import bucket_key

from . import tasks
from .model import Job


def compact_event(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def analysis_report_event(job: Job, report_id: str) -> dict:
    return {
        "event": "analysis_report_ready",
        "paper_id": job.id,
        "report_id": report_id,
    }


def job_state_payload(job: Job) -> dict:
    return compact_event(
        {
            "event": "job_state",
            "paper_id": job.id,
            "status": job.status,
            "stage": job.stage,
            "mode": job.mode,
            "source_label": job.source_label,
            "rubric_profile": job.profile,
            "error": job.error,
        }
    )


def is_persistable_report(job: Job) -> bool:
    result = job.result
    return bool(
        result
        and not job.relevance_override
        and not job.force_grade
        and result.relevance.label in (s.RelevanceLabel.yes, s.RelevanceLabel.partial)
        and result.step_assessments
        and result.coverage is not None
        and result.quality_score is not None
    )


def archived_from_analysis(job: Job) -> ArchivedPaper:
    result = job.result
    paper_class = result.paper_class if result else None
    coverage = result.coverage if result else None
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
        relevance_label=result.relevance.label.value if result else "",
        quality_score=result.quality_score if result else None,
        coverage_present=(coverage.present if coverage else None),
        coverage_applicable=(coverage.applicable if coverage else None),
        paper_type=paper_type_tags(paper_class),
        discipline=discipline_tags(paper_class),
        methods=methods_from_inventory(job.inventory),
        result=result.model_dump(mode="json") if result else None,
        inventory=job.inventory.model_dump(mode="json") if job.inventory else None,
        engine_version=ENGINE_VERSION,
        rubric_version=result.rubric_version if result else "",
        grading_strategy=config.grading_strategy(),
    )


async def save_analysis_report(job: Job) -> None:
    if not is_persistable_report(job):
        return
    archived = archived_from_analysis(job)
    await asyncio.to_thread(upsert_report, archived.key, report_fields(archived))
    tasks.spawn(asyncio.to_thread(save_event, analysis_report_event(job, archived.key)))


def replayable_report(doc: dict | None, rubric) -> bool:
    return bool(
        doc
        and doc.get("result")
        and doc.get("mode") == "full"
        and doc.get("engine_version") == ENGINE_VERSION
        and doc.get("rubric_version") == rubric.rubric_version
        and doc.get("grading_strategy") == config.grading_strategy()
    )
