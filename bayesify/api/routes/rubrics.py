"""Rubric metadata routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from bayesify.core.rubric import RubricProfileError, available_rubrics, load_rubric

router = APIRouter()


@lru_cache(maxsize=8)
def rubric_payload(profile: str) -> dict:
    spec = load_rubric(profile=profile)
    return {
        "rubric_version": spec.rubric_version,
        "rubric_profile": spec.profile,
        "label": spec.label,
        "summary": spec.summary,
        "status_values": spec.status_values,
        "steps": [
            {
                "id": step.id,
                "name": step.name,
                "why": step.why,
                "essential_for": step.essential_for,
                "recommended_for": step.recommended_for,
                "adequate": step.adequate,
                "missing": step.missing,
                "citations": step.citations,
            }
            for step in spec.steps
        ],
    }


@router.get("/api/rubric")
async def get_rubric(profile: str = "synthesis") -> dict:
    try:
        return rubric_payload(profile)
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/rubrics")
async def get_rubrics() -> list[dict]:
    return [rubric.model_dump(mode="json") for rubric in available_rubrics()]
