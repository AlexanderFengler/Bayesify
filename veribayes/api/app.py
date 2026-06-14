"""VeriBayes API + single-process web server.

Implements the real upload -> job -> SSE -> report flow (real on-device pipeline in local-only mode;
stub engine for full mode until those components land), plus the endpoint surface from plans
02-mvp/g §5. Endpoints that need later components (real calibration data, real purge) return honest
stubs and are labelled as such.

**One process serves both the API and the built UI** (`pixi run app`): the FastAPI app mounts
``web/dist`` at ``/`` so the SPA and its ``/api`` calls share one origin — one command to run, no
second server, no CORS. The Vite dev server (``pixi run web``, hot-reload, proxies ``/api``) is for
development only; the static mount is conditional, so it is simply absent when ``web/dist`` is
unbuilt.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from veribayes.api import jobs as jobsmod
from veribayes.api.jobs import JobStore, event_stream, run_job
from veribayes.core.report import fix_list

app = FastAPI(title="VeriBayes API", version="0.1.0")

# Local-first dev: the Vite dev server runs on 5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = JobStore()


def _source_label(file: UploadFile | None, arxiv_id, doi, openalex_id, url) -> str:
    if file is not None and file.filename:
        return file.filename
    for value in (arxiv_id, doi, openalex_id, url):
        if value:
            return value
    return "unknown source"


@app.post("/api/papers")
async def create_paper(
    mode: str = Form("full"),
    file: UploadFile | None = File(None),
    arxiv_id: str | None = Form(None),
    doi: str | None = Form(None),
    openalex_id: str | None = Form(None),
    url: str | None = Form(None),
) -> dict:
    """Accept a dropped PDF *or* a pasted ID/URL and enqueue an assessment job."""
    if file is None and not any((arxiv_id, doi, openalex_id, url)):
        raise HTTPException(
            status_code=422, detail="Provide a PDF file or one of arxiv_id/doi/openalex_id/url."
        )
    if mode not in ("full", "local"):
        raise HTTPException(status_code=422, detail="mode must be 'full' or 'local'.")
    # Local-only mode runs the real on-device pipeline (a+b+c) over the uploaded bytes; carry them
    # to the worker. (Full mode is still the stub, so the bytes are only needed for local mode.)
    data = await file.read() if file is not None else None
    job = store.create(
        mode=mode,
        source_label=_source_label(file, arxiv_id, doi, openalex_id, url),
        data=data,
        filename=file.filename if file is not None else None,
    )
    asyncio.create_task(run_job(job))
    return {"paper_id": job.id, "status": job.status}


def _job_payload(job: jobsmod.Job) -> dict:
    return {
        "paper_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "mode": job.mode,
        "source_label": job.source_label,
        "relevance_override": job.relevance_override,
        "result": job.result.model_dump(mode="json") if job.result else None,
        # D2 prioritised fix-list, derived server-side (the SPA renders it; not in the contract).
        "fix_list": (
            [f.model_dump(mode="json") for f in fix_list(job.result)] if job.result else None
        ),
        "inventory": job.inventory.model_dump(mode="json") if job.inventory else None,
        "parser": job.parser,
        "parser_version": job.parser_version,
        "backend": job.backend,
        "from_cache": job.from_cache,
        "local_notice": job.local_notice,
        "error": job.error,
    }


@app.get("/api/papers/{paper_id}")
async def get_paper(paper_id: str) -> dict:
    job = store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    return _job_payload(job)


@app.get("/api/papers/{paper_id}/events")
async def get_events(paper_id: str):
    job = store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    return EventSourceResponse(event_stream(job))


@app.get("/api/papers/{paper_id}/report.json")
async def report_json(paper_id: str):
    job = store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    if job.result is not None:
        return JSONResponse(job.result.model_dump(mode="json"))
    if job.inventory is not None:  # local-only detection report
        return JSONResponse(
            {
                "mode": "local",
                "parser": job.parser,
                "parser_version": job.parser_version,
                "inventory": job.inventory.model_dump(mode="json"),
            }
        )
    raise HTTPException(status_code=404, detail="no result yet")


@app.get("/api/papers/{paper_id}/report.md")
async def report_md(paper_id: str):
    job = store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    if job.result is not None:
        return PlainTextResponse(_render_markdown(job))
    if job.inventory is not None:
        return PlainTextResponse(_render_inventory_markdown(job))
    raise HTTPException(status_code=404, detail="no result yet")


@app.post("/api/papers/{paper_id}/rerun")
async def rerun(paper_id: str, relevance_override: str = Form("partial")) -> dict:
    """Gate-page escape hatch: re-run treating relevance as the override (A5-recorded)."""
    job = store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    job.relevance_override = relevance_override
    job.status = "queued"
    job.stage = None
    job.result = None
    job.from_cache = False
    job.force_fresh = True  # an explicit rerun always bypasses the cache (verify the live path)
    job.events.clear()
    store.overrides.append(
        {"assessment_id": paper_id, "kind": "relevance_rerun", "value": relevance_override}
    )
    asyncio.create_task(run_job(job))
    return {"paper_id": job.id, "status": job.status}


@app.post("/api/assessments/{assessment_id}/steps/{step_id}/override")
async def record_override(
    assessment_id: str,
    step_id: str,
    corrected_status: str = Form(...),
    rationale: str = Form(""),
    author: str = Form("anonymous"),
) -> dict:
    """A5 scaffolding: record an expert correction. Append-only; never mutates engine output, and
    (honestly) not yet used to change judgments."""
    record = {
        "assessment_id": assessment_id,
        "step_id": step_id,
        "corrected_status": corrected_status,
        "rationale": rationale,
        "author": author,
    }
    store.overrides.append(record)
    return {
        "recorded": True,
        "note": "recorded for the v1 learning loop — not yet used to change judgments",
    }


@app.get("/api/overrides/export")
async def export_overrides() -> PlainTextResponse:
    body = "\n".join(__import__("json").dumps(o) for o in store.overrides)
    return PlainTextResponse(body, media_type="application/x-ndjson")


@app.get("/api/calibration")
async def calibration() -> dict:
    """Pre-M7: no validation has run yet. The calibration page renders this honestly."""
    return {
        "status": "not_yet_validated",
        "note": "Validation (validation/protocol.md) runs at M7; no agreement metrics exist yet.",
    }


@app.delete("/api/papers/{paper_id}")
async def delete_paper(paper_id: str) -> dict:
    if not store.delete(paper_id):
        raise HTTPException(status_code=404, detail="unknown paper_id")
    return {"deleted": paper_id}


def _render_markdown(job: jobsmod.Job) -> str:
    r = job.result
    assert r is not None
    lines = [f"# VeriBayes report — {job.source_label}", ""]
    if r.coverage:
        lo, hi = (
            round(r.coverage.strict * r.coverage.applicable),
            round(r.coverage.lenient * r.coverage.applicable),
        )
        rng = f"{lo}" if lo == hi else f"{lo}–{hi}"
        lines.append(f"**Coverage:** {rng} / {r.coverage.applicable} applicable steps present")
    if r.quality_score is not None:
        lines.append(f"**Quality:** {r.quality_score}")
    lines += [
        f"**Relevance:** {r.relevance.label.value} · **Paper type:** "
        f"{r.paper_class.primary.value if r.paper_class else 'n/a'} · "
        f"**Profile:** {r.rubric_profile}",
        "",
    ]
    fixes = fix_list(r)
    if fixes:
        lines.append("## Priority fixes")
        for f in fixes:
            lines.append(
                f"- [{f.severity.value}] {f.step_id}: {f.text} "
                f"— _{f.how_to}_ ({f.ease.value} effort)"
            )
        lines.append("")
    for a in r.step_assessments:
        lines.append(f"## {a.step_id} — {a.status.value}")
        for d in a.did_well:
            lines.append(f"- ✓ {d}")
        for sug in a.suggestions:
            lines.append(f"- [{sug.severity.value}] {sug.text}")
        lines.append("")
    lines.append(
        f"_Engine {r.engine_version} · rubric {r.rubric_version} · "
        f"${r.cost_ledger.total_cost_usd} · {r.validation_ref}. Formative report, not a verdict._"
    )
    return "\n".join(lines)


def _render_inventory_markdown(job: jobsmod.Job) -> str:
    """The local-only detection report as Markdown — found / not-detected / where-looked. Labelled
    'detection only, not graded' (no scores, no LLM)."""
    inv = job.inventory
    assert inv is not None
    lines = [
        f"# VeriBayes — local detection report — {job.source_label}",
        "",
        f"_Detection only, not graded. Parser: {job.parser} ({job.parser_version}). "
        f"{inv.n_hits} signals detected. No LLM; nothing left this machine._",
        "",
    ]
    for fam in inv.families:
        lines.append(f"## {fam.family.replace('_', ' ')}")
        if fam.found:
            for h in fam.found:
                val = f" — `{h.value}`" if h.value else ""
                page = f", p.{h.page}" if h.page is not None else ""
                lines.append(f'- **{h.detector_id}**{val}: "{h.quote}" (§{h.section_id}{page})')
        if fam.not_detected:
            lines.append(f"- _not detected: {', '.join(fam.not_detected)}_")
        lines.append("")
    looked = ", ".join(f"{sc.kind.value} ({sc.title})" for sc in inv.where_looked) or "—"
    skipped = ", ".join(f"{sc.title}" for sc in inv.skipped) or "none"
    lines += [
        "## Where the engine looked",
        f"Scanned: {looked}.",
        f"Skipped (not scanned): {skipped}.",
    ]
    return "\n".join(lines)


# --- Static frontend (single-process mode) --------------------------------------------------------
# Mounted LAST so it never shadows the /api routes above. Present only when web/dist exists (built
# by `pixi run app`); absent in the Vite dev flow. Override the location via VERIBAYES_WEB_DIST.
_default_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
_web_dist = Path(os.environ.get("VERIBAYES_WEB_DIST", str(_default_dist)))
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
