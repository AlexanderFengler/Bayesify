"""VeriBayes API + single-process web server.

Implements the real upload -> job -> SSE -> report flow: the on-device pipeline in local-only mode,
and the full real engine (screen/classify/assess/score) in full mode when a backend is configured,
falling back to a labelled stub only when no credentials are available. Plus the endpoint surface
from plans 02-mvp/g §5. Endpoints that need later components (real calibration data) return honest
stubs and are labelled as such.

**One process serves both the API and the built UI** (`pixi run app`): the FastAPI app mounts
``web/dist`` at ``/`` so the SPA and its ``/api`` calls share one origin — one command to run, no
second server, no CORS. The Vite dev server (``pixi run web``, hot-reload, proxies ``/api``) is for
development only; the static mount is conditional, so it is simply absent when ``web/dist`` is
unbuilt.
"""

from __future__ import annotations

import asyncio
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sse_starlette.sse import EventSourceResponse

from veribayes.api import jobs as jobsmod
from veribayes.api.jobs import JobStore, event_stream, run_job
from veribayes.core.report import fix_list
from veribayes.core.rubric import RubricProfileError, available_rubrics, load_rubric
from veribayes.core.schema import EvidenceKind
from veribayes.core.validation import Rating, harness, to_calibration_payload
from veribayes.core.validation.override_store import Override
from veribayes.core.validation.rating_store import SubmittedRating

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
    profile: str = Form("synthesis"),
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
    try:
        load_rubric(profile=profile)  # validate the chosen rubric exists (registry)
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # A dropped PDF carries its bytes; a pasted identifier (no file) is fetched in the worker (the
    # OA PDF is resolved off the request path). Both modes then grade the same way.
    data = await file.read() if file is not None else None
    identifier = None if file is not None else (arxiv_id or doi or openalex_id or url)
    job = store.create(
        mode=mode,
        source_label=_source_label(file, arxiv_id, doi, openalex_id, url),
        data=data,
        filename=file.filename if file is not None else None,
        identifier=identifier,
        profile=profile,
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


@lru_cache(maxsize=8)
def _rubric_payload(profile: str) -> dict:
    """The compiled rubric a profile resolves to — the single source of truth for step names and the
    per-step prose the report + (V3) the blind rating form render. Cached per profile (static)."""
    spec = load_rubric(profile=profile)
    return {
        "rubric_version": spec.rubric_version,
        "rubric_profile": spec.profile,
        "label": spec.label,
        "summary": spec.summary,  # the preamble shown on the report + rating form
        "status_values": spec.status_values,
        "steps": [
            {
                "id": s.id,
                "name": s.name,
                "why": s.why,
                "essential_for": s.essential_for,
                "recommended_for": s.recommended_for,
                "adequate": s.adequate,
                "done_poorly": s.done_poorly,
                "citations": s.citations,
            }
            for s in spec.steps
        ],
    }


@app.get("/api/rubric")
async def get_rubric(profile: str = "synthesis") -> dict:
    """Serve the compiled rubric so the UI never hardcodes step names/prose (they'd drift from the
    rubric files). ``profile`` defaults to the 'synthesis' rubric; an unknown id -> 422."""
    try:
        return _rubric_payload(profile)
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/rubrics")
async def get_rubrics() -> list[dict]:
    """List available rubrics (id, label, summary, version) for the analysis + rating pickers."""
    return [r.model_dump(mode="json") for r in available_rubrics()]


@app.post("/api/papers/{paper_id}/rerun")
async def rerun(paper_id: str, relevance_override: str = Form("partial")) -> dict:
    """Escape hatch: grade a short-circuited paper anyway. A not-Bayesian paper is graded under a
    forced relevance; a review/opinion piece is force-graded as advisory (the right mechanism is
    chosen from the prior short-circuit reason, not the caller). A5-recorded."""
    job = store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    is_review = bool(job.result and job.result.not_applicable_reason == "not_an_application")
    # Capture what the rerun overrides BEFORE job.result is cleared below: the short-circuit reason
    # (e.g. "not_bayesian" / "not_an_application") is the verdict the user is overriding.
    overridden = job.result.not_applicable_reason if job.result else None
    # Restore the upload bytes (the worker freed them after the first ingest) so the rerun can
    # actually re-run the pipeline rather than fall back to the stub.
    if job.data is None and job.content_sha256:
        blobs = jobsmod._blobs()
        if blobs.exists(job.content_sha256):
            job.data = blobs.get(job.content_sha256)
    if is_review:
        job.force_grade = True  # relevance is already 'yes'; just grade the rubric as advisory
    else:
        job.relevance_override = relevance_override  # not-Bayesian: force a gradeable relevance
    job.status = "queued"
    job.stage = None
    job.result = None
    job.inventory = None
    job.from_cache = False
    job.force_fresh = True  # an explicit rerun always bypasses the cache (verify the live path)
    job.events.clear()
    jobsmod._overrides_store().add(
        Override(
            paper_id=paper_id,
            kind="relevance_rerun",
            original_status=overridden,  # the short-circuit the user is overriding
            rubric_profile=job.profile,
            source_sha256=job.content_sha256 or "",
            version_label=job.version_label or "",
            value="force_grade" if is_review else relevance_override,
        )
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
    original_status: str = Form(""),  # client fallback for what was overridden (if job expired)
    rubric_profile: str = Form("synthesis"),  # client fallback for the rubric (if job expired)
) -> dict:
    """A5 scaffolding: record an expert correction. Append-only; never mutates engine output, and
    (honestly) not yet used to change judgments.

    We record the correction *and what it overrode*: the live job is the authoritative source for
    the engine's original status, the rubric, and the durable paper sha. When the job has expired
    we still record the correction (never dropped), using the client-sent fallbacks for the
    status/rubric so a disagreement is never lost."""
    job = store.get(assessment_id)
    overridden = original_status or None
    profile = rubric_profile
    source_sha256 = ""
    version_label = ""
    if job is not None:
        profile = job.profile
        source_sha256 = job.content_sha256 or ""
        version_label = job.version_label or ""
        if job.result is not None:  # authoritative: the engine verdict for this very step
            engine_status = next(
                (a.status.value for a in job.result.step_assessments if a.step_id == step_id), None
            )
            if engine_status is not None:
                overridden = engine_status
    jobsmod._overrides_store().add(
        Override(
            paper_id=assessment_id,
            kind="step_status",
            step_id=step_id,
            corrected_status=corrected_status,
            original_status=overridden,
            rubric_profile=profile,
            source_sha256=source_sha256,
            version_label=version_label,
            rationale=rationale,
            author=author,
        )
    )
    return {
        "recorded": True,
        "note": "recorded for the v1 learning loop — not yet used to change judgments",
    }


@app.get("/api/overrides/export")
async def export_overrides() -> PlainTextResponse:
    """The durable A5 override/rerun log as NDJSON (one correction per line)."""
    body = "\n".join(o.model_dump_json() for o in jobsmod._overrides_store().all())
    return PlainTextResponse(body, media_type="application/x-ndjson")


# --- Blind expert rating (V3) ---------------------------------------------------------------------
# The rating surface is the human side of validation. Blindness is enforced HERE, server-side: the
# context handler has no access path to job.result, and assess-minted evidence kinds are excluded.
_RATE_BLIND_EXCLUDE = {EvidenceKind.absence_search, EvidenceKind.judge_quote}


@app.get("/api/rate/context/{paper_id}")
async def rate_context(paper_id: str, profile: str = "synthesis") -> dict:
    """Blind rating context: the rubric to walk + the deterministic detector evidence to cite from,
    and NOTHING from the engine's ScoredResult. A rater handed the engine's framing would measure an
    echo, so this never reads job.result; absence_search/judge_quote spans (which would leak the
    engine's missing-calls) are excluded. Asserted by test_rate_context_is_blind."""
    job = store.get(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    try:
        rubric = _rubric_payload(profile)
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    evidence: list[dict] = []
    where_looked: list[dict] = []
    if job.inventory is not None:
        for fam in job.inventory.families:
            for hit in fam.found:
                if hit.kind in _RATE_BLIND_EXCLUDE:  # defensive: detectors never mint these
                    continue
                evidence.append(
                    {
                        "section_id": hit.section_id,
                        "section_title": hit.section_title,
                        "page": hit.page,
                        "quote": hit.quote,
                        "family": hit.family,
                        "detector_id": hit.detector_id,
                        "kind": hit.kind.value,
                    }
                )
        where_looked = [
            {"section_id": s.section_id, "title": s.title, "kind": s.kind.value, "page": s.page}
            for s in job.inventory.where_looked
        ]
    return {
        "paper_id": job.id,
        "source_label": job.source_label,
        "source_sha256": job.content_sha256,
        "rubric": rubric,
        "evidence": evidence,
        "where_looked": where_looked,
    }


class RateSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paper_id: str
    profile: str = "synthesis"  # which rubric the rater rated against (registry id)
    rating: Rating  # validated by its own contract (relevance/class/gate + per-step grounding)


@app.post("/api/rate/submit")
async def rate_submit(body: RateSubmit) -> dict:
    """Record one rater's blind ``Rating`` to **durable** storage (append-only; A5 — never mutates
    engine output), capturing the paper's sha256/version so `assemble-goldset` can pin the gold
    record. Grouping ratings into a HumanReport with auto-consensus is `assemble-goldset`."""
    job = store.get(body.paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown paper_id")
    try:
        rubric = load_rubric(profile=body.profile)  # the rubric the rater rated against
    except RubricProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    sub = SubmittedRating(
        paper_id=body.paper_id,
        source_sha256=job.content_sha256 or "",
        version_label=job.version_label or "",
        rubric_version=rubric.rubric_version,
        rubric_profile=body.profile,
        rating=body.rating,
    )
    rstore = jobsmod._ratings_store()
    rstore.add(sub)
    n = rstore.count_for(sub.source_sha256, sub.rubric_profile, sub.paper_id)
    return {"recorded": True, "n_ratings": n}


@app.get("/api/calibration")
async def calibration() -> dict:
    """Serve the validation report the calibration page renders. Precedence: a real report (post-M7,
    validation/reports/) → the committed FAKE demo report (finished page, critique-able now, behind
    a loud DEMO banner) → ``not_yet_validated`` when neither exists. The report's own status /
    is_demo / caveats make the demo unmistakable; the firewall guarantees it can't be a real one."""
    real_dir = Path(harness.REAL_REPORTS_DIR)
    real = sorted(real_dir.glob("*.json")) if real_dir.is_dir() else []
    if real:
        return JSONResponse(json.loads(real[-1].read_text(encoding="utf-8")))  # latest real report
    fake = Path(harness.FAKE_GOLDSET_DIR)
    if fake.is_dir() and any(fake.glob("*.json")):
        report = harness.build(
            goldset_dir=harness.FAKE_GOLDSET_DIR,
            engine_dir=harness.FAKE_ENGINE_DIR,
            treat_as_real=False,
            n_resamples=300,  # snappy for the API; the demo numbers are fake anyway
        )
        return to_calibration_payload(report)
    return {
        "status": "not_yet_validated",
        "note": "Validation (validation/protocol.md) runs at M7; no agreement metrics exist yet.",
    }


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
