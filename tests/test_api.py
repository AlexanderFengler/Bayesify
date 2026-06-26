"""API transport: synchronous endpoints via TestClient + the async job machinery directly."""

from __future__ import annotations

import asyncio
import json

import fitz  # PyMuPDF — a base dep so the API can parse in local-only mode
import httpx
import pytest
from fastapi.testclient import TestClient

from bayesify.api.app import RateSubmit, app, rate_submit, store
from bayesify.api.jobs import LOCAL_STAGES, STAGES, Job, JobStore, event_stream, run_job

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


def test_upload_rejects_oversize_pdf(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MAX_UPLOAD_MB", "1")
    big = b"%PDF-" + b"0" * 1_200_000  # ~1.2 MB > the 1 MB cap → rejected before buffering
    r = client.post(
        "/api/papers", files={"file": ("big.pdf", big, "application/pdf")}, data={"mode": "local"}
    )
    assert r.status_code == 413


def test_jobstore_evicts_least_recently_used_beyond_cap(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MAX_JOBS", "3")
    s = JobStore()
    ids = [s.create(mode="local", source_label=f"p{i}").id for i in range(5)]
    assert s.get(ids[0]) is None and s.get(ids[1]) is None  # the two oldest were evicted
    assert all(s.get(i) is not None for i in ids[2:])  # the three newest are retained


def test_jobstore_get_keeps_a_job_warm(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MAX_JOBS", "2")
    s = JobStore()
    a = s.create(mode="local", source_label="a").id
    s.create(mode="local", source_label="b")
    assert s.get(a) is not None  # touch a → most-recently-used
    c = s.create(mode="local", source_label="c").id  # evicts b (the LRU), not the warmed a
    assert s.get(a) is not None and s.get(c) is not None


def test_spawn_retains_then_discards_and_logs_failure(caplog) -> None:
    import logging

    from bayesify.api import jobs as jobsmod

    async def main() -> None:
        async def boom() -> None:
            raise RuntimeError("kaboom")

        await asyncio.gather(jobsmod.spawn(boom()), return_exceptions=True)
        await asyncio.sleep(0)  # let the done-callback run

    with caplog.at_level(logging.ERROR, logger="bayesify.jobs"):
        asyncio.run(main())
    assert jobsmod._background_tasks == set()  # the finished task was discarded from the set
    assert any("background task failed" in r.getMessage() for r in caplog.records)


def test_unknown_paper_is_404() -> None:
    assert client.get("/api/papers/nope").status_code == 404


def test_single_process_serves_ui_without_shadowing_api() -> None:
    """When web/dist is built, the static mount serves the SPA at / but must not shadow /api.
    Skips when the bundle is absent (the Vite dev flow), since the mount is conditional."""
    if not any(getattr(r, "name", None) == "web" for r in app.routes):
        pytest.skip("web/dist not built — single-process serving inactive")
    root = client.get("/")
    assert root.status_code == 200 and "text/html" in root.headers["content-type"]
    cal = client.get("/api/calibration")
    assert "application/json" in cal.headers["content-type"]  # /api reachable, not shadowed by SPA
    assert "status" in cal.json()


def test_calibration_serves_the_demo_report_behind_the_firewall() -> None:
    # With the committed fake goldset present, the page renders the finished surface — but the
    # report is unmistakably a demo (status + is_demo + a FAKE-DATA caveat), not a real measurement.
    body = client.get("/api/calibration").json()
    assert body["status"] == "demo_fake_data" and body["is_demo"] is True
    assert body["status_kappa"]["value"] is not None
    assert any("FAKE DATA" in c for c in body["validity_caveats"])


def test_calibration_is_not_yet_validated_without_a_goldset(tmp_path, monkeypatch) -> None:
    from bayesify.core.validation import harness as harnessmod

    monkeypatch.setattr(harnessmod, "FAKE_GOLDSET_DIR", str(tmp_path / "none"))
    monkeypatch.setattr(harnessmod, "REAL_REPORTS_DIR", str(tmp_path / "none-real"))
    assert client.get("/api/calibration").json()["status"] == "not_yet_validated"


def test_rubric_endpoint_serves_compiled_steps() -> None:
    # Single source of truth: the UI reads step names/prose from here, never a hardcoded map.
    body = client.get("/api/rubric").json()
    assert body["rubric_profile"] == "synthesis"
    assert body["rubric_version"]
    assert [s["id"] for s in body["steps"]] == [f"S{i}" for i in range(1, 11)]
    assert all(s["name"] for s in body["steps"])  # every step carries a display name
    assert "adequate" in body["steps"][0]  # the per-step prose a rater is guided by (V3)


def test_rubric_unknown_profile_is_422() -> None:
    assert client.get("/api/rubric", params={"profile": "does_not_exist"}).status_code == 422


def _all_keys(obj) -> set[str]:
    """Every dict key anywhere in a nested JSON structure."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for it in obj:
            keys |= _all_keys(it)
    return keys


def test_rate_context_is_blind(tmp_path, monkeypatch) -> None:
    from bayesify.core.stub import build_stub_result

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    job = store.create(mode="local", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))  # local front-half → detector inventory (no LLM, no grade)
    assert job.inventory is not None
    job.result = build_stub_result("full")  # pretend the engine ALSO graded it — must NOT leak

    body = client.get(f"/api/rate/context/{job.id}").json()
    assert body["rubric"]["steps"]  # the rater gets the rubric to walk...
    assert body["evidence"]  # ...and the HDDM paper's detector hits (Stan, NUTS, R-hat, …)
    # ...but NOTHING of the engine's judgment.
    leaked = _all_keys(body) & {
        "status",
        "coverage",
        "quality_score",
        "did_well",
        "suggestions",
        "adversarial_verdict",
        "score_impacts",
        "step_assessments",
        "relevance",
        "paper_class",
    }
    assert leaked == set(), f"engine judgment leaked into the blind context: {leaked}"
    assert all(e["kind"] not in ("absence_search", "judge_quote") for e in body["evidence"])


def test_rate_submit_records_a_blind_rating(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    saved_events: list[dict] = []
    monkeypatch.setattr("bayesify.api.app.save_event", lambda payload: saved_events.append(payload))

    async def inline_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("bayesify.api.app.asyncio.to_thread", inline_to_thread)
    job = store.create(mode="local", source_label="ddm.pdf")
    job.content_sha256 = "ab" * 32
    job.version_label = "uploaded PDF (ddm.pdf)"
    rating = {
        "rater_id": "r1",
        "relationship": "independent",
        "relevance_label": "yes",
        "relevance_rationale": "fits a hierarchical Bayesian model",
        "paper_class_labels": ["data_analysis"],
        "paper_class_rationale": "fit to behavioural data",
        "gate_facts": {
            "inference_method": "mcmc",
            "n_models": 1,
            "bf_claimed": False,
            "prior_informativeness": "weakly_informative",
        },
        "steps": [
            {
                "step_id": "S1",
                "applicable": True,
                "status": "adequate",
                "confidence": 0.9,
                "evidence": [{"section_id": "s01", "quote": "hierarchical drift-diffusion model"}],
                "rationale": "the model is specified and justified",
            }
        ],
    }
    ok = asyncio.run(rate_submit(RateSubmit(paper_id=job.id, rating=rating)))
    assert ok["recorded"] is True
    assert len(saved_events) == 1
    event = saved_events[0]
    assert event["event"] == "blind_rating_submitted"
    assert event["rater_id"] == "r1"
    assert event["relationship"] == "independent"
    assert event["relevance_label"] == "yes"
    assert event["relevance_rationale"] == "fits a hierarchical Bayesian model"
    assert event["paper_class_labels"] == ["data_analysis"]
    assert event["gate_facts"]["inference_method"] == "mcmc"
    assert event["steps"][0]["step_id"] == "S1"
    assert event["submission"]["rating"]["relevance_label"] == "yes"
    # the Rating contract is enforced at the boundary: 'partial' relevance needs a paper_class
    bad = {**rating, "relevance_label": "partial", "paper_class_labels": []}
    with pytest.raises(ValueError):
        RateSubmit(paper_id=job.id, rating=bad)


def test_rate_submit_records_no_relevance_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    saved_events: list[dict] = []
    monkeypatch.setattr("bayesify.api.app.save_event", lambda payload: saved_events.append(payload))

    async def inline_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("bayesify.api.app.asyncio.to_thread", inline_to_thread)
    rating = {
        "rater_id": "r-no",
        "relationship": "independent",
        "relevance_label": "no",
        "relevance_rationale": "not a Bayesian statistical-methodology paper",
        "paper_class_labels": [],
        "paper_class_rationale": "",
        "gate_facts": None,
        "steps": [],
    }

    ok = asyncio.run(
        rate_submit(
            RateSubmit(
                paper_id="paper-no",
                rating=rating,
                source_sha256="ef" * 32,
                version_label="uploaded PDF",
            )
        )
    )

    assert ok["recorded"] is True
    assert len(saved_events) == 1
    event = saved_events[0]
    assert event["rater_id"] == "r-no"
    assert event["relevance_label"] == "no"
    assert event["relevance_rationale"] == "not a Bayesian statistical-methodology paper"
    assert event["paper_class_labels"] == []
    assert event["gate_facts"] is None
    assert event["steps"] == []
    assert event["submission"]["rating"]["relevance_label"] == "no"


def test_rate_submit_survives_an_expired_job(tmp_path, monkeypatch) -> None:
    # A blind rating is ~an hour of work: if the in-memory job has expired (e.g. an API restart)
    # between rating and submit, it must NOT be dropped. The SPA echoes the paper provenance it got
    # from rate/context, and the server persists it instead of 404ing (mirrors record_override).
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    rating = {
        "rater_id": "r1",
        "relationship": "independent",
        "relevance_label": "yes",
        "relevance_rationale": "fits a hierarchical Bayesian model",
        "paper_class_labels": ["data_analysis"],
        "paper_class_rationale": "fit to behavioural data",
        "gate_facts": {
            "inference_method": "mcmc",
            "n_models": 1,
            "bf_claimed": False,
            "prior_informativeness": "weakly_informative",
        },
        "steps": [
            {
                "step_id": "S1",
                "applicable": True,
                "status": "adequate",
                "confidence": 0.9,
                "evidence": [{"section_id": "s01", "quote": "hierarchical drift-diffusion model"}],
                "rationale": "the model is specified and justified",
            }
        ],
    }
    # No job with this id exists in the store (it expired); submit with client-sent provenance.
    ok = client.post(
        "/api/rate/submit",
        json={
            "paper_id": "expired-job-id",
            "rating": rating,
            "source_sha256": "cd" * 32,
            "version_label": "uploaded PDF",
        },
    )
    assert ok.status_code == 200 and ok.json()["recorded"] is True
    # Durable: persisted under the bucket keyed by the client-sent sha, with the version pinned.
    from bayesify.api import jobs as jobsmod

    bucket = f"{'cd' * 32}__synthesis"
    assert jobsmod._ratings_store().count_for("cd" * 32, "synthesis") == 1
    subs = jobsmod._ratings_store().by_paper()[bucket]
    assert [s.version_label for s in subs] == ["uploaded PDF"]


def test_override_is_recorded_durably_but_not_yet_learned_from(tmp_path, monkeypatch) -> None:
    # Degraded path: no live job for "abc" (e.g. it expired) — the correction is still recorded,
    # never dropped, with the client-sent/defaulted provenance.
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    r = client.post(
        "/api/assessments/abc/steps/S4/override",
        data={"corrected_status": "partial", "rationale": "supplement has it"},
    )
    body = r.json()
    assert body["recorded"] is True
    assert "not yet used" in body["note"]
    # durable: a fresh store (a "restart") still sees the correction
    from bayesify.core.validation.override_store import OverrideStore

    saved = OverrideStore(tmp_path).all()
    assert [o.paper_id for o in saved] == ["abc"]
    assert saved[0].step_id == "S4" and saved[0].corrected_status == "partial"
    assert saved[0].rubric_profile == "synthesis"  # default when no live job / no client fallback


def test_override_captures_what_it_overrode_and_provenance(tmp_path, monkeypatch) -> None:
    # Enriched path: a live job is the authoritative source for what was overridden (the engine's
    # status for that step), the rubric, and the durable paper sha — all recorded with the fix.
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BAYESIFY_LLM_BACKEND", "none")  # billing-safe: the labelled stub
    job = Job(id="ovr1", mode="full", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    store._jobs[job.id] = job
    asyncio.run(run_job(job))  # labelled stub → a full ScoredResult with step_assessments
    job.content_sha256 = "ab" * 32  # real full mode sets this in _front_half; the stub skips ingest
    assert job.result is not None and job.result.step_assessments
    step = job.result.step_assessments[3]  # a graded step (S4)

    r = client.post(
        f"/api/assessments/{job.id}/steps/{step.step_id}/override",
        data={"corrected_status": "adequate", "rationale": "supplement has it"},
    )
    assert r.json()["recorded"] is True

    from bayesify.core.validation.override_store import OverrideStore

    saved = OverrideStore(tmp_path).all()
    assert len(saved) == 1
    o = saved[0]
    assert o.paper_id == job.id and o.step_id == step.step_id
    assert o.corrected_status == "adequate"
    assert o.original_status == step.status.value  # WHAT WAS OVERRIDDEN (engine verdict)
    assert o.rubric_profile == job.profile == "synthesis"  # which rubric the correction is against
    assert o.source_sha256 == job.content_sha256  # durable paper identity, not the ephemeral job id


# --- async job machinery --------------------------------------------------------------------------


def test_run_job_emits_every_stage_then_done_and_attaches_result(monkeypatch) -> None:
    # Full mode with bytes but NO credentials → the labelled stub: all stages, then a stub result.
    # (monkeypatch is scoped, so forcing the backend off here does not affect other tests.)
    monkeypatch.setenv("BAYESIFY_LLM_BACKEND", "none")
    saved_reports: list[str] = []
    monkeypatch.setattr(
        "bayesify.api.jobs._save_analysis_report_payload",
        lambda job: saved_reports.append(job.id),
    )
    job = Job(id="t1", mode="full", source_label="paper.pdf", data=b"%PDF-stub-bytes")
    asyncio.run(run_job(job))
    stages_done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert stages_done == list(STAGES)
    assert job.events[-1]["type"] == "done"
    assert job.status == "done"
    assert job.result is not None and job.result.coverage is not None
    assert job.backend == "stub"
    assert saved_reports == []  # no analysis event for the placeholder path; no LLM ran


def test_local_completion_does_not_save_analysis_event(monkeypatch) -> None:
    from bayesify.api import jobs as jobsmod

    saved_reports: list[str] = []
    monkeypatch.setattr(
        jobsmod,
        "_save_analysis_report_payload",
        lambda job: saved_reports.append(job.id),
    )

    async def fake_front_half(job, *, source=None):
        job.content_sha256 = "ab" * 32
        job.version_label = "uploaded PDF"
        return None, []

    monkeypatch.setattr(jobsmod, "_front_half", fake_front_half)
    job = Job(id="loc-nosave", mode="local", source_label="paper.pdf")

    asyncio.run(jobsmod._run_local(job))

    assert job.status == "done"
    assert saved_reports == []


def test_fresh_full_llm_completion_saves_analysis_event(monkeypatch) -> None:
    from bayesify.api import jobs as jobsmod
    from bayesify.core.stub import build_stub_result

    saved_reports: list[str] = []
    monkeypatch.setattr(
        jobsmod,
        "_save_analysis_report_payload",
        lambda job: saved_reports.append(job.id),
    )
    monkeypatch.setattr(jobsmod, "_cache_enabled", lambda: False)
    monkeypatch.setattr(jobsmod.config, "llm_backend", lambda: "api")
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: object())

    async def fake_front_half(job, *, source=None):
        job.content_sha256 = "ab" * 32
        job.version_label = "uploaded PDF"
        return object(), []

    async def fake_to_thread(func, *args, **kwargs):
        if func is jobsmod.grade_parsed:
            return build_stub_result("full")
        return func(*args, **kwargs)

    monkeypatch.setattr(jobsmod, "_front_half", fake_front_half)
    monkeypatch.setattr(jobsmod.asyncio, "to_thread", fake_to_thread)
    job = Job(id="full-save", mode="full", source_label="paper.pdf", data=b"%PDF-fake")

    asyncio.run(jobsmod._run_full(job))

    assert job.status == "done"
    assert saved_reports == ["full-save"]


def test_no_input_shows_honest_needs_upload_notice() -> None:
    # No file AND no identifier → nothing to analyze. BOTH modes must show an honest notice — never
    # a fabricated stub report, and never simulated pipeline stages.
    for mode in ("local", "full"):
        job = Job(id=f"t3-{mode}", mode=mode, source_label="(none)")
        asyncio.run(run_job(job))
        assert job.status == "done"
        assert job.result is None  # no fabricated report for a paper we never had
        assert job.local_notice is not None and "drop a pdf" in job.local_notice.lower()
        assert [e for e in job.events if e["type"] == "stage"] == []  # no simulated stages


# --- real local-only pipeline (a+b+c on-device) ---------------------------------------------------


def test_local_upload_runs_real_detection(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
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
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    job = Job(id="loc2", mode="local", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))
    # the References line names Stan; it must not be scanned
    ref_sections = {sc.section_id for sc in job.inventory.skipped}
    hits_in_refs = [
        h for fam in job.inventory.families for h in fam.found if h.section_id in ref_sections
    ]
    assert not hits_in_refs


# --- identifier fetch (wired; offline via httpx MockTransport, no live network) ----------------


_ARXIV_FEED = (
    '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" '
    'xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>'
    "<id>http://arxiv.org/abs/2011.01808v3</id><title>Bayesian Workflow</title>"
    "<arxiv:license>http://creativecommons.org/licenses/by/4.0/</arxiv:license></entry></feed>"
)
_ARXIV_ERR = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Error</title></entry></feed>'


def _arxiv_transport(pdf: bytes) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/api/query" in url:
            return httpx.Response(200, text=_ARXIV_ERR if "9999.99999" in url else _ARXIV_FEED)
        if "arxiv.org/pdf/" in url:
            return httpx.Response(200, content=pdf)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _patch_fetcher(monkeypatch, pdf: bytes) -> None:
    from bayesify.api import jobs as jobsmod
    from bayesify.core.fetcher import Fetcher

    httpx_client = httpx.Client(transport=_arxiv_transport(pdf))

    def make_fetcher() -> Fetcher:
        return Fetcher(httpx_client, jobsmod._blobs(), openalex_api_key=None, unpaywall_email=None)

    monkeypatch.setattr(jobsmod, "_fetcher", make_fetcher)


def test_identifier_is_fetched_then_graded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    _patch_fetcher(monkeypatch, _HDDM_PDF)
    job = Job(id="fetch1", mode="local", source_label="2011.01808", identifier="2011.01808")
    asyncio.run(run_job(job))

    assert job.status == "done"
    assert job.content_sha256 and job.version_label == "arXiv v3"  # fetched, not a generic upload
    assert job.inventory is not None and job.inventory.n_hits > 0  # parsed + detected fetched PDF
    done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert "fetch" in done and "ingest" not in done  # fetch replaces the upload-ingest step


def test_identifier_fetch_failure_is_surfaced(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    _patch_fetcher(monkeypatch, _HDDM_PDF)
    job = Job(id="fetch2", mode="local", source_label="9999.99999", identifier="9999.99999")
    asyncio.run(run_job(job))
    assert job.status == "failed" and "9999.99999" in (job.error or "")  # IngestError surfaced


def test_local_upload_rejects_non_pdf(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    job = Job(id="loc3", mode="local", source_label="x.txt", data=b"not a pdf", filename="x.txt")
    asyncio.run(run_job(job))
    assert job.status == "failed"
    assert "PDF" in (job.error or "")  # the typed NotAPdfError user_message


def _full_fake(
    relevance: str = "yes", judge_status: str = "adequate", paper_class: str = "data_analysis"
):
    """A schema-aware fake for the whole full pipeline: Relevance for screen, PaperClass for
    classify, StepJudgment for each assess judge call, RefuterVerdict for refuters. Records the
    schema name of every call so tests can assert what ran."""
    from bayesify.core.assess import RefuterVerdict, StepJudgment
    from bayesify.core.llm import LLMResponse
    from bayesify.core.schema import PaperClass, PaperClassLabel, Relevance, RelevanceLabel

    class _F:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def complete(self, *, model, system, user, schema, max_tokens=1024):
            self.calls.append(schema.__name__)
            if schema.__name__ == "Relevance":
                refs = [] if relevance == "no" else [0]
                p = Relevance(
                    label=RelevanceLabel(relevance),
                    confidence=0.9,
                    rationale="b",
                    evidence_refs=refs,
                )
            elif schema.__name__ == "PaperClass":
                p = PaperClass(
                    labels=[PaperClassLabel(paper_class)],
                    confidence=0.8,
                    rationale="r",
                    evidence_refs=[0],
                )
            elif schema.__name__ == "StepJudgment":
                p = StepJudgment(status=judge_status, confidence=0.9)
            else:
                p = RefuterVerdict(refuted=False, notes="absent")
            return LLMResponse(parsed=p, model=model, input_tokens=10, output_tokens=5)

    return _F()


def test_full_upload_grades_end_to_end(tmp_path, monkeypatch) -> None:
    from bayesify.api import jobs as jobsmod
    from bayesify.core import config
    from bayesify.core.schema import PaperClassLabel, RelevanceLabel

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")  # makes run_job route to the full pipeline
    monkeypatch.setattr(config, "claude_code_available", lambda: False)  # deterministic backend
    fake = _full_fake()
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    job = Job(id="full1", mode="full", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))

    r = job.result
    assert job.status == "done" and r is not None
    assert r.relevance.label is RelevanceLabel.yes  # real screen
    assert r.paper_class.labels == [PaperClassLabel.data_analysis]  # real classify
    assert len(r.step_assessments) == 10 and r.profile is not None  # real assess + score (no stub)
    assert r.coverage is not None and r.quality_score is not None
    assert job.backend == "api"
    assert {"screen", "classify", "assess"} <= {e.stage for e in r.cost_ledger.entries}
    done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert done == ["ingest", "parse", "detect", "screen", "classify", "assess", "score"]


def test_full_upload_short_circuits_on_no(tmp_path, monkeypatch) -> None:
    from bayesify.api import jobs as jobsmod
    from bayesify.core.schema import RelevanceLabel

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    fake = _full_fake(relevance="no")
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    # a non-Bayesian PDF, so the detector floor doesn't (correctly) override the 'no'
    job = Job(id="full2", mode="full", source_label="x.pdf", data=_DECOY_PDF, filename="x.pdf")
    asyncio.run(run_job(job))

    assert job.status == "done" and job.result is not None
    assert job.result.relevance.label is RelevanceLabel.no
    assert job.result.paper_class is None  # short-circuit: classify + assess skipped, scores null
    assert job.result.quality_score is None
    assert fake.calls == ["Relevance"]  # only the screen call; no classify/assess


def test_rerun_escape_hatch_grades_a_short_circuited_paper(tmp_path, monkeypatch) -> None:
    """The gate says 'no', but the user overrides it: the rerun forces relevance to 'partial' and
    grades end-to-end — classify runs even though screen had skipped it, and the override is
    disclosed in the rationale (A5)."""
    from bayesify.api import jobs as jobsmod
    from bayesify.core.schema import RelevanceLabel

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    fake = _full_fake(relevance="no")  # the gate would short-circuit this paper...
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    # ...but the user forced a full grade via the escape hatch (relevance_override set on the job).
    job = Job(
        id="rerun-eh",
        mode="full",
        source_label="x.pdf",
        data=_DECOY_PDF,
        filename="x.pdf",
        relevance_override="partial",
    )
    asyncio.run(run_job(job))

    r = job.result
    assert job.status == "done" and r is not None
    assert r.relevance.label is RelevanceLabel.partial  # forced by the override, not 'no'
    assert "[User override:" in r.relevance.rationale  # the override is disclosed in-band
    assert r.paper_class is not None  # classify ran even though the gate had said 'no'
    assert len(r.step_assessments) == 10  # fully graded, not short-circuited
    assert r.coverage is not None and r.quality_score is not None
    assert fake.calls[0] == "Relevance" and "PaperClass" in fake.calls  # screen + forced classify


def test_grading_under_gelman_uses_the_gelman_rubric(tmp_path, monkeypatch) -> None:
    """Choosing the Gelman rubric grades against ITS ten steps (S1..S10, but the Gelman version +
    names, not synthesis), and stamps the result + cache key with that profile (separate entry)."""
    from bayesify.api import jobs as jobsmod

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: _full_fake())

    job = Job(
        id="gel1", mode="full", source_label="x.pdf", data=_HDDM_PDF, filename="x.pdf",
        profile="gelman",
    )
    asyncio.run(run_job(job))

    r = job.result
    assert job.status == "done" and r is not None
    assert r.rubric_profile == "gelman" and r.rubric_version == "0.1-gelman"
    assert [a.step_id for a in r.step_assessments] == [f"S{i}" for i in range(1, 11)]


def test_grading_under_schad_uses_the_schad_rubric(tmp_path, monkeypatch) -> None:
    """A third rubric needed no new code — choosing 'schad' grades against its seven steps (S1..S7,
    Schad version + names) and stamps the result with that profile (the registry carries it)."""
    from bayesify.api import jobs as jobsmod

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: _full_fake())

    job = Job(
        id="sc1", mode="full", source_label="x.pdf", data=_HDDM_PDF, filename="x.pdf",
        profile="schad",
    )
    asyncio.run(run_job(job))

    r = job.result
    assert job.status == "done" and r is not None
    assert r.rubric_profile == "schad" and r.rubric_version == "0.1-schad"
    assert [a.step_id for a in r.step_assessments] == [f"S{i}" for i in range(1, 8)]


def test_review_paper_short_circuits(tmp_path, monkeypatch) -> None:
    """A review/opinion piece is Bayesian-relevant but the per-step rubric doesn't apply: classify
    returns 'review' → short-circuit before assess (reason='not_an_application'), nothing graded."""
    from bayesify.api import jobs as jobsmod
    from bayesify.core.schema import PaperClassLabel, RelevanceLabel

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    fake = _full_fake(paper_class="review")
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    job = Job(id="rev1", mode="full", source_label="op.pdf", data=_HDDM_PDF, filename="op.pdf")
    asyncio.run(run_job(job))

    r = job.result
    assert job.status == "done" and r is not None
    assert r.not_applicable_reason == "not_an_application"
    assert r.relevance.label is RelevanceLabel.yes  # Bayesian-relevant...
    assert r.paper_class.labels == [PaperClassLabel.review] and not r.step_assessments  # not graded
    assert "StepJudgment" not in fake.calls  # assess never ran


def test_force_grade_reruns_a_review_paper(tmp_path, monkeypatch) -> None:
    """The escape hatch sets force_grade → the review piece is graded anyway (advisory)."""
    from bayesify.api import jobs as jobsmod

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    fake = _full_fake(paper_class="review")
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    job = Job(
        id="rev2", mode="full", source_label="op.pdf", data=_HDDM_PDF, filename="op.pdf",
        force_grade=True,
    )
    asyncio.run(run_job(job))

    r = job.result
    assert job.status == "done" and r is not None and r.not_applicable_reason is None
    assert len(r.step_assessments) == 10 and "StepJudgment" in fake.calls  # graded despite review


def test_rerun_endpoint_force_grades_a_review_result(tmp_path, monkeypatch) -> None:
    """The rerun endpoint picks the mechanism from the prior short-circuit reason: a review result
    sets force_grade (relevance is already 'yes'), not relevance_override."""
    from bayesify.core import schema as sm

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    job = store.create(mode="full", source_label="op.pdf")
    job.result = sm.ScoredResult.short_circuit(
        relevance=sm.Relevance(
            label=sm.RelevanceLabel.yes, confidence=0.9, rationale="x", evidence_refs=[0]
        ),
        reason="not_an_application",
        paper_class=sm.PaperClass(
            labels=[sm.PaperClassLabel.review], confidence=0.8, rationale="x", evidence_refs=[0]
        ),
        engine_version="ev",
        rubric_version="rv",
    )
    assert client.post(f"/api/papers/{job.id}/rerun").status_code == 200
    after = store.get(job.id)
    assert after.force_grade is True and after.relevance_override is None
    # the rerun override records what it overrode (the short-circuit) + the rubric, not just value
    from bayesify.core.validation.override_store import OverrideStore

    o = OverrideStore(tmp_path).all()[-1]
    assert o.kind == "relevance_rerun" and o.value == "force_grade"
    assert o.original_status == "not_an_application"  # the short-circuit it overrode
    assert o.rubric_profile == "synthesis"


def test_full_upload_without_credentials_falls_back_to_stub(tmp_path, monkeypatch) -> None:
    from bayesify.core import config

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("BAYESIFY_LLM_BACKEND", raising=False)
    monkeypatch.setattr(config, "claude_code_available", lambda: False)  # no key, no CLI → none
    job = Job(id="full3", mode="full", source_label="x.pdf", data=_HDDM_PDF, filename="x.pdf")
    asyncio.run(run_job(job))
    assert job.status == "done" and job.result is not None
    assert job.result.coverage is not None  # the labelled stub engine, unchanged sans credentials
    assert job.backend == "stub"  # the badge tells the UI this is NOT a live model run


# --- result caching (safe: success-only, visible, bypassable) -------------------------------------


def _full_cache_env(tmp_path, monkeypatch):
    from bayesify.core import config

    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setattr(config, "claude_code_available", lambda: False)  # backend "api"


def test_identical_rerun_is_served_from_cache_without_calling_the_model(tmp_path, monkeypatch):
    from bayesify.api import jobs as jobsmod
    from bayesify.core.llm import FakeLLMClient

    _full_cache_env(tmp_path, monkeypatch)
    monkeypatch.delenv("BAYESIFY_NO_CACHE", raising=False)

    f1 = _full_fake()
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: f1)
    j1 = Job(id="ca1", mode="full", source_label="p.pdf", data=_HDDM_PDF, filename="p.pdf")
    asyncio.run(run_job(j1))
    assert j1.from_cache is False and j1.result is not None
    assert "StepJudgment" in f1.calls  # the full pipeline really ran

    # same bytes → cache hit; the LLM client must NOT be called again
    f2 = FakeLLMClient()  # empty: would raise if invoked
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: f2)
    j2 = Job(id="ca2", mode="full", source_label="p.pdf", data=_HDDM_PDF, filename="p.pdf")
    asyncio.run(run_job(j2))
    assert j2.from_cache is True and j2.result is not None
    assert len(f2.calls) == 0  # served from cache, no model call
    assert j2.backend == "api"  # original backend preserved through the cache


def test_failed_run_is_not_cached_so_breakage_is_never_masked(tmp_path, monkeypatch):
    from bayesify.api import jobs as jobsmod
    from bayesify.core.llm import FakeLLMClient, LLMTransientError

    _full_cache_env(tmp_path, monkeypatch)
    monkeypatch.delenv("BAYESIFY_NO_CACHE", raising=False)

    # first run fails (transient ×3 → fail closed)
    f1 = FakeLLMClient(LLMTransientError("x"), LLMTransientError("y"), LLMTransientError("z"))
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: f1)
    j1 = Job(id="cf1", mode="full", source_label="p.pdf", data=_HDDM_PDF, filename="p.pdf")
    asyncio.run(run_job(j1))
    assert j1.status == "failed" and j1.result is None

    # a working rerun must actually RUN (nothing cached), not replay a phantom success
    f2 = _full_fake()
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: f2)
    j2 = Job(id="cf2", mode="full", source_label="p.pdf", data=_HDDM_PDF, filename="p.pdf")
    asyncio.run(run_job(j2))
    assert j2.status == "done" and j2.from_cache is False and "StepJudgment" in f2.calls


def test_no_cache_env_always_runs_fresh(tmp_path, monkeypatch):
    from bayesify.api import jobs as jobsmod

    _full_cache_env(tmp_path, monkeypatch)
    monkeypatch.setenv("BAYESIFY_NO_CACHE", "1")

    f1 = _full_fake()
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: f1)
    j1 = Job(id="cn1", mode="full", source_label="p.pdf", data=_HDDM_PDF, filename="p.pdf")
    asyncio.run(run_job(j1))

    f2 = _full_fake()
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: f2)
    j2 = Job(id="cn2", mode="full", source_label="p.pdf", data=_HDDM_PDF, filename="p.pdf")
    asyncio.run(run_job(j2))
    assert j2.from_cache is False and "StepJudgment" in f2.calls  # not cached: a real run each time


def test_local_report_json_and_md(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path))
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
