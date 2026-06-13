"""API transport: synchronous endpoints via TestClient + the async job machinery directly."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from veribayes.api.app import app
from veribayes.api.jobs import LOCAL_STAGES, STAGES, Job, event_stream, run_job

client = TestClient(app)


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


def test_event_stream_replays_for_a_late_subscriber() -> None:
    async def go() -> list[dict]:
        job = Job(id="t2", mode="full", source_label="paper.pdf")
        await run_job(job)  # job is already terminal before the stream opens
        return [json.loads(payload["data"]) async for payload in event_stream(job)]

    events = asyncio.run(go())
    assert events[-1]["type"] == "done"
    assert {e["seq"] for e in events} == {e["seq"] for e in events}  # seqs unique/monotonic
