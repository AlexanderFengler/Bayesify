"""API transport: synchronous endpoints via TestClient + the async job machinery directly."""

from __future__ import annotations

import asyncio
import json

import fitz  # PyMuPDF — a base dep so the API can parse in local-only mode
import pytest
from fastapi.testclient import TestClient

from veribayes.api.app import app, store
from veribayes.api.jobs import LOCAL_STAGES, STAGES, Job, event_stream, run_job

client = TestClient(app)


def _pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    return doc.tobytes()


_HDDM_PDF = _pdf(
    [
        "A hierarchical drift-diffusion model of decision making",
        "Abstract. We fit a hierarchical drift-diffusion model to response-time data using",
        "Bayesian inference in Stan, with weakly-informative priors on every drift rate.",
        "Methods. We drew from the posterior distribution with the NUTS sampler, running",
        "4 chains of 2000 iterations after 1000 warm-up draws with a fixed random seed.",
        "Convergence was checked with R-hat and bulk-ESS; all R-hat < 1.01 and there were",
        "no divergent transitions. Posterior predictive checks reproduced the RT data.",
        "Results. Model comparison used PSIS-LOO and WAIC; code is available on github.com.",
        "References. Carpenter et al. Stan: a probabilistic programming language.",
    ]
)

# A non-Bayesian decoy (no detector hits → no detector floor), so a screened 'no' actually stands.
_DECOY_PDF = _pdf(
    [
        "Returns to schooling: an instrumental-variables analysis",
        "Abstract. We estimate the causal effect of schooling on wages using ordinary",
        "least squares and two-stage least squares regression on survey data.",
        "Methods. Standard errors are clustered by region; we report p-values and 95 percent",
        "confidence intervals. Robustness is assessed with placebo regressions.",
        "Results. The estimated return is 8 percent per year of schooling.",
    ]
)


# --- synchronous endpoints ------------------------------------------------------------------------


def test_create_requires_some_input() -> None:
    r = client.post("/api/papers", data={"mode": "full"})
    assert r.status_code == 422


def test_create_with_id_returns_paper_id() -> None:
    r = client.post("/api/papers", data={"mode": "full", "arxiv_id": "2011.01808"})
    assert r.status_code == 200
    body = r.json()
    assert body["paper_id"]
    assert body["status"] in ("queued", "running", "done")


def test_unknown_paper_is_404() -> None:
    assert client.get("/api/papers/nope").status_code == 404


def test_single_process_serves_ui_without_shadowing_api() -> None:
    """When web/dist is built, the static mount serves the SPA at / but must not shadow /api.
    Skips when the bundle is absent (the Vite dev flow), since the mount is conditional."""
    if not any(getattr(r, "name", None) == "web" for r in app.routes):
        pytest.skip("web/dist not built — single-process serving inactive")
    root = client.get("/")
    assert root.status_code == 200 and "text/html" in root.headers["content-type"]
    assert client.get("/api/calibration").json()["status"] == "not_yet_validated"


def test_calibration_is_honest_about_not_being_validated() -> None:
    assert client.get("/api/calibration").json()["status"] == "not_yet_validated"


def test_override_is_recorded_but_not_yet_learned_from() -> None:
    r = client.post(
        "/api/assessments/abc/steps/S4/override",
        data={"corrected_status": "partial", "rationale": "supplement has it"},
    )
    body = r.json()
    assert body["recorded"] is True
    assert "not yet used" in body["note"]


# --- async job machinery --------------------------------------------------------------------------


def test_run_job_emits_every_stage_then_done_and_attaches_result() -> None:
    job = Job(id="t1", mode="full", source_label="paper.pdf")
    asyncio.run(run_job(job))
    stages_done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert stages_done == list(STAGES)
    assert job.events[-1]["type"] == "done"
    assert job.status == "done"
    assert job.result is not None and job.result.coverage is not None


def test_local_mode_produces_no_scores_and_fewer_stages() -> None:
    job = Job(id="t3", mode="local", source_label="paper.pdf")
    asyncio.run(run_job(job))
    stages_done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert stages_done == list(LOCAL_STAGES)  # detectors only — no screen/classify/assess/score
    assert job.result is None  # no scores in local mode
    assert job.local_notice is not None
    assert job.status == "done"


# --- real local-only pipeline (a+b+c on-device) ---------------------------------------------------


def test_local_upload_runs_real_detection(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    job = Job(id="loc1", mode="local", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))

    assert job.status == "done"
    assert job.result is None  # local mode never produces scores
    assert job.parser == "pymupdf"  # default env has no docling → fast fallback
    assert job.inventory is not None and job.inventory.n_hits > 0
    found = {h.detector_id for fam in job.inventory.families for h in fam.found}
    assert {"software.stan", "diag.rhat", "sampler.chains"} <= found
    # stages are detection-only, in order
    done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert done == list(LOCAL_STAGES)
    assert job.data is None  # bytes freed after ingest


def test_local_upload_skips_references_section(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    job = Job(id="loc2", mode="local", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))
    # the References line names Stan; it must not be scanned
    ref_sections = {sc.section_id for sc in job.inventory.skipped}
    hits_in_refs = [
        h for fam in job.inventory.families for h in fam.found if h.section_id in ref_sections
    ]
    assert not hits_in_refs


def test_local_upload_rejects_non_pdf(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    job = Job(id="loc3", mode="local", source_label="x.txt", data=b"not a pdf", filename="x.txt")
    asyncio.run(run_job(job))
    assert job.status == "failed"
    assert "PDF" in (job.error or "")  # the typed NotAPdfError user_message


def test_full_upload_with_fake_client_attaches_real_relevance_and_class(
    tmp_path, monkeypatch
) -> None:
    from veribayes.api import jobs as jobsmod
    from veribayes.core import config
    from veribayes.core.llm import FakeLLMClient
    from veribayes.core.schema import PaperClass, PaperClassLabel, Relevance, RelevanceLabel

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")  # makes run_job route to the full pipeline
    monkeypatch.setattr(config, "claude_code_available", lambda: False)  # deterministic backend
    fake = FakeLLMClient(
        Relevance(
            label=RelevanceLabel.yes, confidence=0.92, rationale="Bayesian", evidence_refs=[0]
        ),
        PaperClass(
            primary=PaperClassLabel.empirical,
            confidence=0.8,
            rationale="real data",
            evidence_refs=[0],
        ),
    )
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    job = Job(id="full1", mode="full", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))

    assert job.status == "done" and job.result is not None
    assert job.result.relevance.label is RelevanceLabel.yes  # real screen output
    assert job.result.paper_class.primary is PaperClassLabel.empirical  # real classify output
    assert job.backend == "api"  # the result is stamped with the live backend (not "stub")
    # both cheap-model calls are metered into the ledger
    assert {e.stage for e in job.result.cost_ledger.entries} == {"screen", "classify"}
    done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert done == ["ingest", "parse", "detect", "screen", "classify"]


def test_full_upload_short_circuits_on_no(tmp_path, monkeypatch) -> None:
    from veribayes.api import jobs as jobsmod
    from veribayes.core.llm import FakeLLMClient
    from veribayes.core.schema import Relevance, RelevanceLabel

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    fake = FakeLLMClient(
        Relevance(label=RelevanceLabel.no, confidence=0.9, rationale="not Bayesian")
    )
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    # a non-Bayesian PDF, so the detector floor doesn't (correctly) override the 'no'
    job = Job(id="full2", mode="full", source_label="x.pdf", data=_DECOY_PDF, filename="x.pdf")
    asyncio.run(run_job(job))

    assert job.status == "done" and job.result is not None
    assert job.result.relevance.label is RelevanceLabel.no
    assert job.result.paper_class is None  # short-circuit: classify skipped, scores null
    assert job.result.quality_score is None
    assert len(fake.calls) == 1  # classify never called


def test_full_upload_without_credentials_falls_back_to_stub(tmp_path, monkeypatch) -> None:
    from veribayes.core import config

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VERIBAYES_LLM_BACKEND", raising=False)
    monkeypatch.setattr(config, "claude_code_available", lambda: False)  # no key, no CLI → none
    job = Job(id="full3", mode="full", source_label="x.pdf", data=_HDDM_PDF, filename="x.pdf")
    asyncio.run(run_job(job))
    assert job.status == "done" and job.result is not None
    assert job.result.coverage is not None  # the labelled stub engine, unchanged sans credentials
    assert job.backend == "stub"  # the badge tells the UI this is NOT a live model run


def test_local_report_json_and_md(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    job = store.create(mode="local", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))

    rj = client.get(f"/api/papers/{job.id}/report.json").json()
    assert rj["mode"] == "local" and rj["inventory"]["n_hits"] > 0
    rm = client.get(f"/api/papers/{job.id}/report.md").text
    assert "local detection report" in rm
    assert "Where the engine looked" in rm
    # the status payload carries the inventory for the UI
    payload = client.get(f"/api/papers/{job.id}").json()
    assert payload["inventory"]["n_hits"] > 0 and payload["parser"] == "pymupdf"


def test_event_stream_replays_for_a_late_subscriber() -> None:
    async def go() -> list[dict]:
        job = Job(id="t2", mode="full", source_label="paper.pdf")
        await run_job(job)  # job is already terminal before the stream opens
        return [json.loads(payload["data"]) async for payload in event_stream(job)]

    events = asyncio.run(go())
    assert events[-1]["type"] == "done"
    assert {e["seq"] for e in events} == {e["seq"] for e in events}  # seqs unique/monotonic
