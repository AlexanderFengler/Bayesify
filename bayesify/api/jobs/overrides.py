"""Trusted override bank and display-time review overlay."""

from __future__ import annotations

import asyncio

from bayesify.api import config as api_config
from bayesify.api.mongo import find_trusted_step_overrides
from bayesify.api.runtime import api
from bayesify.core.override_review import BankOverride, review_overrides
from bayesify.llm import config as llm_config

from . import resources
from .model import Job

BANK_PER_STEP = 8


def local_trusted_overrides(profile: str) -> list[dict]:
    overrides = [
        override.model_dump()
        for override in resources.overrides_store().all()
        if (
            override.kind == "step_status"
            and override.trusted
            and override.step_id
            and override.rubric_profile == profile
        )
    ]
    overrides.reverse()
    return overrides


def override_bank(profile: str) -> dict[str, list[BankOverride]]:
    docs = find_trusted_step_overrides(profile)
    if docs is None:
        docs = local_trusted_overrides(profile)
    bank: dict[str, list[BankOverride]] = {}
    for doc in docs:
        step_id = doc.get("step_id")
        if not step_id or not doc.get("corrected_status"):
            continue
        bucket = bank.setdefault(step_id, [])
        if len(bucket) >= BANK_PER_STEP:
            continue
        bucket.append(
            BankOverride(
                step_id=step_id,
                original_status=doc.get("original_status") or "",
                corrected_status=doc["corrected_status"],
                rationale=doc.get("rationale") or "",
                engine_rationale=doc.get("engine_rationale") or "",
                paper_title=doc.get("paper_title") or "",
                author=doc.get("author") or "",
                evidence_quotes=list(doc.get("evidence_quotes") or []),
            )
        )
    return bank


async def review_overlay(job: Job, rubric) -> None:
    if job.result is None or not job.result.step_assessments or llm_config.llm_backend() == "none":
        return
    bank = await asyncio.to_thread(override_bank, job.profile)
    if not bank:
        return
    corrected, applied, _cost = await asyncio.to_thread(
        review_overrides,
        job.result,
        bank,
        rubric,
        client=resources.llm_client(),
        model=llm_config.judge_model(),
    )
    if applied:
        job.base_coverage = job.result.coverage
        job.base_quality = job.result.quality_score
        job.result = corrected
        job.applied_corrections = applied


async def try_review_overlay(job: Job, rubric) -> None:
    timeout = api_config.override_review_timeout_s()
    try:
        if timeout == 0:
            return
        await asyncio.wait_for(review_overlay(job, rubric), timeout=timeout)
    except TimeoutError:
        api.logger.warning(
            "job %s override review timed out after %.1fs; serving raw result", job.id, timeout
        )
    except Exception:
        api.logger.exception("job %s override review failed; serving raw result", job.id)
