"""Read-only archive routes backed by Mongo reports."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from bayesify.api.db.mongo import mongo

router = APIRouter()


def facets(papers: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "paper_type": [],
        "discipline": [],
        "methods": [],
        "software": [],
    }
    for paper in papers:
        for bucket in out:
            for value in paper.get(bucket) or []:
                if value not in out[bucket]:
                    out[bucket].append(value)
    for bucket in out:
        out[bucket].sort(key=str.lower)
    return out


@router.get("/api/papers")
async def list_papers(
    q: str = "",
    paper_type: list[str] = Query(default=[]),
    discipline: list[str] = Query(default=[]),
    method: list[str] = Query(default=[]),
    software: list[str] = Query(default=[]),
    mode: str = "",
    rubric: str = "",
) -> dict:
    docs = await asyncio.to_thread(mongo.list_reports) or []
    for doc in docs:
        doc.pop("_id", None)
        for array_field in ("paper_authors", "paper_type", "discipline", "methods", "software"):
            doc.setdefault(array_field, [])
    needle = q.strip().lower()

    def matches(paper: dict) -> bool:
        if needle:
            parts = [
                paper.get("paper_title") or paper.get("source_label") or "",
                *(paper.get("paper_authors") or []),
                *(paper.get("paper_type") or []),
                *(paper.get("discipline") or []),
                *(paper.get("methods") or []),
                *(paper.get("software") or []),
            ]
            hay = " ".join(parts).lower().replace("_", " ").replace("-", " ")
            if needle.replace("_", " ").replace("-", " ") not in hay:
                return False
        # Within a facet the selected values combine with OR (a paper matches if it carries ANY of
        # them); across facets it's AND (each block is an independent early-return). The empty guard
        # keeps an unselected facet a no-op.
        if paper_type and not any(tag in (paper.get("paper_type") or []) for tag in paper_type):
            return False
        if discipline and not any(tag in (paper.get("discipline") or []) for tag in discipline):
            return False
        if method and not any(tag in (paper.get("methods") or []) for tag in method):
            return False
        if software and not any(tag in (paper.get("software") or []) for tag in software):
            return False
        if mode and paper.get("mode") != mode:
            return False
        if rubric and paper.get("rubric_profile") != rubric:
            return False
        return True

    items = [paper for paper in docs if matches(paper)]
    return {"papers": items, "facets": facets(docs), "total": len(docs)}
