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
    from veribayes.core.validation import harness as harnessmod

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
    assert "done_well" in body["steps"][0]  # the per-step prose a rater is guided by (V3)


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
    from veribayes.core.stub import build_stub_result

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
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
    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    job = store.create(mode="local", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))
    rating = {
        "rater_id": "r1",
        "relationship": "independent",
        "relevance_label": "yes",
        "relevance_rationale": "fits a hierarchical Bayesian model",
        "paper_class_label": "empirical",
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
                "status": "done_well",
                "confidence": 0.9,
                "evidence": [{"section_id": "s01", "quote": "hierarchical drift-diffusion model"}],
                "rationale": "the model is specified and justified",
            }
        ],
    }
    ok = client.post("/api/rate/submit", json={"paper_id": job.id, "rating": rating})
    assert ok.status_code == 200 and ok.json()["recorded"] is True
    # the Rating contract is enforced at the boundary: 'partial' relevance needs a paper_class
    bad = {**rating, "relevance_label": "partial", "paper_class_label": None}
    r = client.post("/api/rate/submit", json={"paper_id": job.id, "rating": bad})
    assert r.status_code == 422


def test_override_is_recorded_but_not_yet_learned_from() -> None:
    r = client.post(
        "/api/assessments/abc/steps/S4/override",
        data={"corrected_status": "partial", "rationale": "supplement has it"},
    )
    body = r.json()
    assert body["recorded"] is True
    assert "not yet used" in body["note"]


# --- async job machinery --------------------------------------------------------------------------


def test_run_job_emits_every_stage_then_done_and_attaches_result(monkeypatch) -> None:
    # Full mode with bytes but NO credentials → the labelled stub: all stages, then a stub result.
    # (monkeypatch is scoped, so forcing the backend off here does not affect other tests.)
    monkeypatch.setenv("VERIBAYES_LLM_BACKEND", "none")
    job = Job(id="t1", mode="full", source_label="paper.pdf", data=b"%PDF-stub-bytes")
    asyncio.run(run_job(job))
    stages_done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert stages_done == list(STAGES)
    assert job.events[-1]["type"] == "done"
    assert job.status == "done"
    assert job.result is not None and job.result.coverage is not None
    assert job.backend == "stub"


def test_no_bytes_shows_honest_needs_upload_notice() -> None:
    # An identifier (or no file) carries no bytes; fetch-by-id isn't wired, so BOTH modes must show
    # an honest notice — never a fabricated stub report, and never simulated pipeline stages.
    for mode in ("local", "full"):
        job = Job(id=f"t3-{mode}", mode=mode, source_label="2011.01808")
        asyncio.run(run_job(job))
        assert job.status == "done"
        assert job.result is None  # no fabricated report for a paper we never fetched
        assert job.local_notice is not None and "wired" in job.local_notice.lower()
        assert [e for e in job.events if e["type"] == "stage"] == []  # no simulated stages


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


def _full_fake(relevance: str = "yes", judge_status: str = "done_well"):
    """A schema-aware fake for the whole full pipeline: Relevance for screen, PaperClass for
    classify, StepJudgment for each assess judge call, RefuterVerdict for refuters. Records the
    schema name of every call so tests can assert what ran."""
    from veribayes.core.assess import RefuterVerdict, StepJudgment
    from veribayes.core.llm import LLMResponse
    from veribayes.core.schema import PaperClass, PaperClassLabel, Relevance, RelevanceLabel

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
                    primary=PaperClassLabel.empirical,
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
    from veribayes.api import jobs as jobsmod
    from veribayes.core import config
    from veribayes.core.schema import PaperClassLabel, RelevanceLabel

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")  # makes run_job route to the full pipeline
    monkeypatch.setattr(config, "claude_code_available", lambda: False)  # deterministic backend
    fake = _full_fake()
    monkeypatch.setattr(jobsmod, "_llm_client", lambda: fake)

    job = Job(id="full1", mode="full", source_label="ddm.pdf", data=_HDDM_PDF, filename="ddm.pdf")
    asyncio.run(run_job(job))

    r = job.result
    assert job.status == "done" and r is not None
    assert r.relevance.label is RelevanceLabel.yes  # real screen
    assert r.paper_class.primary is PaperClassLabel.empirical  # real classify
    assert len(r.step_assessments) == 10 and r.profile is not None  # real assess + score (no stub)
    assert r.coverage is not None and r.quality_score is not None
    assert job.backend == "api"
    assert {"screen", "classify", "assess"} <= {e.stage for e in r.cost_ledger.entries}
    done = [e["stage"] for e in job.events if e["type"] == "stage" and e["state"] == "done"]
    assert done == ["ingest", "parse", "detect", "screen", "classify", "assess", "score"]


def test_full_upload_short_circuits_on_no(tmp_path, monkeypatch) -> None:
    from veribayes.api import jobs as jobsmod
    from veribayes.core.schema import RelevanceLabel

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
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
    from veribayes.api import jobs as jobsmod
    from veribayes.core.schema import RelevanceLabel

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
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


# --- result caching (safe: success-only, visible, bypassable) -------------------------------------


def _full_cache_env(tmp_path, monkeypatch):
    from veribayes.core import config

    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setattr(config, "claude_code_available", lambda: False)  # backend "api"


def test_identical_rerun_is_served_from_cache_without_calling_the_model(tmp_path, monkeypatch):
    from veribayes.api import jobs as jobsmod
    from veribayes.core.llm import FakeLLMClient

    _full_cache_env(tmp_path, monkeypatch)
    monkeypatch.delenv("VERIBAYES_NO_CACHE", raising=False)

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
    from veribayes.api import jobs as jobsmod
    from veribayes.core.llm import FakeLLMClient, LLMTransientError

    _full_cache_env(tmp_path, monkeypatch)
    monkeypatch.delenv("VERIBAYES_NO_CACHE", raising=False)

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
    from veribayes.api import jobs as jobsmod

    _full_cache_env(tmp_path, monkeypatch)
    monkeypatch.setenv("VERIBAYES_NO_CACHE", "1")

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
