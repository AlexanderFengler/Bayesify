"""M7 slice 2 — durable rating persistence + the assemble-goldset step.

Captured ratings survive on disk (a restart must not lose a 45-min expert rating); assembly groups
them by paper, derives the consensus, and writes only admissible gold records (skip-and-report).
"""

from __future__ import annotations

import fitz  # PyMuPDF — a tiny Bayesian PDF so local ingest yields detector evidence

from veribayes.core.schema import (
    EvidenceSpan,
    GateFacts,
    PaperClassLabel,
    RelevanceLabel,
    StepStatus,
)
from veribayes.core.validation.assemble import assemble
from veribayes.core.validation.human_report import (
    GoldOrigin,
    HumanReport,
    RaterRelationship,
    Rating,
    StepRating,
)
from veribayes.core.validation.rating_store import RatingStore, SubmittedRating

_SPAN = EvidenceSpan(section_id="s01", quote="a span")


def _rating(rater_id: str, rel: RelevanceLabel = RelevanceLabel.yes) -> Rating:
    no = rel is RelevanceLabel.no
    return Rating(
        rater_id=rater_id,
        relationship=RaterRelationship.independent,
        relevance_label=rel,
        relevance_rationale="r",
        paper_class_label=None if no else PaperClassLabel.empirical,
        gate_facts=None if no else GateFacts(),
        steps=[]
        if no
        else [
            StepRating(
                step_id="S1",
                applicable=True,
                status=StepStatus.adequate,
                confidence=0.9,
                evidence=[_SPAN],
                rationale="note",
            )
        ],
    )


def _sub(paper_id: str, rater_id: str, **over) -> SubmittedRating:
    base = dict(
        paper_id=paper_id,
        source_sha256="sha-" + paper_id,
        version_label="arXiv v1",
        rubric_version="0.1-draft",
        rating=_rating(rater_id, over.pop("rel", RelevanceLabel.yes)),
    )
    base.update(over)
    return SubmittedRating(**base)


def test_rating_store_round_trips_and_groups(tmp_path) -> None:
    store = RatingStore(tmp_path / "ratings")
    store.add(_sub("p1", "r1"))  # source_sha256 == "sha-p1"
    store.add(_sub("p1", "r2"))
    store.add(_sub("p2", "r1"))
    # buckets are keyed by the durable (sha, rubric), not the ephemeral paper_id
    assert store.count_for("sha-p1", "synthesis") == 2
    grouped = store.by_paper()
    assert set(grouped) == {"sha-p1__synthesis", "sha-p2__synthesis"}
    assert {s.rating.rater_id for s in grouped["sha-p1__synthesis"]} == {"r1", "r2"}
    # survives a fresh store instance (it's on disk, not in memory)
    assert RatingStore(tmp_path / "ratings").count_for("sha-p1", "synthesis") == 2


def test_same_paper_across_sessions_groups_into_one_bucket(tmp_path) -> None:
    store = RatingStore(tmp_path / "ratings")
    # two sessions (different ephemeral job ids) rate the SAME paper (same content sha): the durable
    # key groups them into one consensus instead of two single-rater papers that never assemble.
    store.add(_sub("sessionA", "r1", source_sha256="sha-x"))
    store.add(_sub("sessionB", "r2", source_sha256="sha-x"))
    grouped = store.by_paper()
    assert set(grouped) == {"sha-x__synthesis"}
    assert {s.rating.rater_id for s in grouped["sha-x__synthesis"]} == {"r1", "r2"}
    assert store.count_for("sha-x") == 2
    # the same rater re-rating in yet another session overwrites — never double-counted
    store.add(_sub("sessionC", "r1", source_sha256="sha-x"))
    assert store.count_for("sha-x") == 2


def test_assemble_writes_admissible_record(tmp_path) -> None:
    store = RatingStore(tmp_path / "ratings")
    store.add(_sub("p1", "r1"))
    store.add(_sub("p1", "r2"))
    out = tmp_path / "goldset"
    written, skipped = assemble(
        ratings_dir=tmp_path / "ratings", out_dir=out, origin=GoldOrigin.blind_human
    )
    assert written == ["sha-p1__synthesis"] and skipped == []
    hr = HumanReport.model_validate_json((out / "sha-p1__synthesis.json").read_text())
    assert hr.consensus is not None and hr.source_sha256 == "sha-p1"
    assert hr.work_id == "sha-p1__synthesis"
    assert hr.provenance.origin is GoldOrigin.blind_human
    assert hr.validate_admissible() == []


def test_assemble_separates_one_paper_rated_under_two_rubrics(tmp_path) -> None:
    store = RatingStore(tmp_path / "ratings")
    # the SAME paper (sha-dual), rated under two rubrics by two raters each, becomes TWO clean gold
    # records — one per rubric — that share the paper identity but never get conflated.
    store.add(_sub("dual", "r1", source_sha256="sha-dual", rubric_profile="synthesis"))
    store.add(_sub("dual", "r2", source_sha256="sha-dual", rubric_profile="synthesis"))
    store.add(_sub("dual", "r1", source_sha256="sha-dual", rubric_profile="gelman"))
    store.add(_sub("dual", "r2", source_sha256="sha-dual", rubric_profile="gelman"))
    out = tmp_path / "goldset"
    written, skipped = assemble(ratings_dir=tmp_path / "ratings", out_dir=out)
    assert set(written) == {"sha-dual__synthesis", "sha-dual__gelman"} and skipped == []
    syn = HumanReport.model_validate_json((out / "sha-dual__synthesis.json").read_text())
    gel = HumanReport.model_validate_json((out / "sha-dual__gelman.json").read_text())
    assert syn.rubric_profile == "synthesis" and gel.rubric_profile == "gelman"
    assert syn.source_sha256 == gel.source_sha256 == "sha-dual"  # same paper, cleanly separated


def test_assemble_skips_single_rater_and_no_consensus(tmp_path) -> None:
    store = RatingStore(tmp_path / "ratings")
    store.add(_sub("solo", "r1"))  # only 1 rater → not admissible
    store.add(_sub("split", "r1", rel=RelevanceLabel.yes))  # raters disagree on relevance
    store.add(_sub("split", "r2", rel=RelevanceLabel.no))
    out = tmp_path / "goldset"
    written, skipped = assemble(ratings_dir=tmp_path / "ratings", out_dir=out)
    assert written == []
    assert set(skipped) == {"sha-solo__synthesis", "sha-split__synthesis"}
    assert not list(out.glob("*.json"))  # nothing written


def test_submit_persists_durably_and_assembles(tmp_path, monkeypatch) -> None:
    import asyncio

    from fastapi.testclient import TestClient

    from veribayes.api import jobs as jobsmod
    from veribayes.api.app import app, store
    from veribayes.api.jobs import Job, run_job

    client = TestClient(app)
    monkeypatch.setenv("VERIBAYES_DATA_DIR", str(tmp_path))
    # ingest a paper locally so it has a content_sha256/version_label the submit captures
    job = Job(id="rate-persist", mode="local", source_label="x.pdf", data=_HDDM, filename="x.pdf")
    store._jobs[job.id] = job
    asyncio.run(run_job(job))
    assert job.content_sha256

    def payload(rid: str) -> dict:
        r = _rating(rid)
        return {"paper_id": job.id, "rating": r.model_dump(mode="json")}

    assert client.post("/api/rate/submit", json=payload("r1")).json()["recorded"] is True
    assert client.post("/api/rate/submit", json=payload("r2")).json()["n_ratings"] == 2
    # it's on disk under the durable (sha, rubric) bucket, and assembles into one gold record
    bucket = f"{job.content_sha256}__synthesis"
    assert jobsmod._ratings_store().count_for(job.content_sha256 or "", "synthesis") == 2
    written, _ = assemble(ratings_dir=tmp_path / "ratings", out_dir=tmp_path / "goldset")
    assert written == [bucket]


def _pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    return doc.tobytes()


_HDDM = _pdf(
    [
        "A hierarchical drift-diffusion model",
        "We fit it with Bayesian inference in Stan using the NUTS sampler;",
        "convergence checked with R-hat and bulk-ESS.",
    ]
)
