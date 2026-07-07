"""The Archive: method-tag derivation, the Mongo `reports` store (upsert-merge, dedup replay, list
projection), and the read-only list endpoint. The archive is backed by MongoDB now — nothing is
written to local disk — so these exercise the store against an injected in-memory collection."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from bayesify.api.app import app
from bayesify.api.db import MongoDBService
from bayesify.api.jobs.reports import replayable_report
from bayesify.api.papers_store import (
    ArchivedPaper,
    methods_from_inventory,
    report_fields,
)
from bayesify.core import config
from bayesify.core.detectors import EvidenceInventory, InventoryFamily, InventoryHit
from bayesify.core.rubric import load_rubric
from bayesify.core.schema import EvidenceKind
from bayesify.core.stub import ENGINE_VERSION
from bayesify.core.validation.rating_store import bucket_key

client = TestClient(app)


# --- an in-memory stand-in for the `reports` collection -------------------------------------------


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def sort(self, key: str, direction: int) -> _FakeCursor:
        self._docs.sort(key=lambda d: d.get(key) or "", reverse=direction < 0)
        return self

    def limit(self, n: int) -> _FakeCursor:
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeReports:
    """Just enough of a pymongo collection for the report store: keyed upsert, find_one, projected
    find. Mirrors the semantics `upsert_report` / `find_report` / `list_reports` rely on."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def update_one(self, flt: dict, update: dict, upsert: bool = False) -> None:
        key = flt["_id"]
        doc = self.docs.get(key)
        if doc is None:
            if not upsert:
                return
            doc = {"_id": key, **update.get("$setOnInsert", {})}
            self.docs[key] = doc
        doc.update(update.get("$set", {}))

    def find_one(self, query: dict, sort=None) -> dict | None:
        matches = [d for d in self.docs.values() if all(d.get(k) == v for k, v in query.items())]
        if sort:
            k, direction = sort[0]
            matches.sort(key=lambda d: d.get(k) or "", reverse=direction < 0)
        return matches[0] if matches else None

    def find(self, query: dict, projection: dict | None = None) -> _FakeCursor:
        docs = [dict(d) for d in self.docs.values() if all(d.get(k) == v for k, v in query.items())]
        for k, keep in (projection or {}).items():
            if keep == 0:
                for d in docs:
                    d.pop(k, None)
        return _FakeCursor(docs)

    def create_index(self, *args, **kwargs) -> None:
        pass


def _ready_service(reports: _FakeReports) -> MongoDBService:
    svc = MongoDBService()
    svc._ready = True
    svc._reports = reports
    return svc


# --- method-tag derivation ------------------------------------------------------------------------


def _hit(detector_id: str, family: str) -> InventoryHit:
    return InventoryHit(
        detector_id=detector_id,
        family=family,
        kind=EvidenceKind.software_mention,
        section_id="s01",
        section_title="Methods",
        quote="…",
    )


def _inventory() -> EvidenceInventory:
    return EvidenceInventory(
        families=[
            InventoryFamily(
                family="software",
                found=[
                    _hit("software.stan", "software"),
                    _hit("software.bayesflow", "software"),
                    _hit("software.unknown", "software"),
                ],
            ),
            InventoryFamily(
                family="method",
                found=[
                    _hit("method.prior", "method"),
                    _hit("method.posterior", "method"),
                    _hit("method.credible_interval", "method"),
                    _hit("method.analytic", "method"),
                    _hit("method.mcmc", "method"),
                    _hit("method.variational", "method"),
                    _hit("method.sbi", "method"),
                    _hit("method.unknown", "method"),
                ],
            ),
            # sampler is deliberately excluded from the "methods & software" facet
            InventoryFamily(family="sampler", found=[_hit("sampler.chains", "sampler")]),
        ],
        n_hits=3,
    )


def test_methods_from_inventory_maps_and_filters_families() -> None:
    labels = methods_from_inventory(_inventory())
    assert labels == ["Stan", "BayesFlow"]  # software only; unknown ids skipped
    # inference-method detectors fire on any mention, so the method family is NOT a facet source
    assert not {"MCMC", "Variational inference", "SBI"} & set(labels)
    assert methods_from_inventory(None) == []


def test_inference_method_tags_maps_smc_and_covers_the_enum() -> None:
    from bayesify.api.papers_store import inference_method_tags
    from bayesify.core.schema import InferenceMethod, PaperClass, PaperClassLabel

    def _pc(methods: list) -> PaperClass:
        return PaperClass(
            labels=[PaperClassLabel.data_analysis], confidence=0.8, rationale="r",
            evidence_refs=[0], methods_used=methods,
        )

    assert inference_method_tags(_pc([InferenceMethod.smc, InferenceMethod.mcmc])) == [
        "SMC", "MCMC",
    ]
    assert inference_method_tags(None) == []
    # every displayable member maps to a label, so no classifier-emitted method silently vanishes
    for m in InferenceMethod:
        if m is not InferenceMethod.unstated:
            assert inference_method_tags(_pc([m])), f"{m} has no friendly label"


# --- report_fields: the $set payload drops empties so a merge preserves ---------------------------


def test_report_fields_drops_empty_values() -> None:
    fields = report_fields(
        ArchivedPaper(
            key="k",
            source_sha256="ab" * 32,
            paper_type=["data_analysis"],
            methods=[],  # empty → dropped so an existing value is preserved on merge
            paper_title=None,  # None → dropped
            quality_score=0.0,  # a real 0 is kept (not "empty")
        )
    )
    assert fields["paper_type"] == ["data_analysis"]
    assert "methods" not in fields and "paper_title" not in fields
    assert fields["quality_score"] == 0.0
    assert "created_at" not in fields  # timestamps are owned by the Mongo upsert


# --- the Mongo report store: upsert-merge + list projection ---------------------------------------


def test_report_store_upsert_merges_and_lists() -> None:
    reports = _FakeReports()
    svc = _ready_service(reports)
    key = bucket_key("ab" * 32, "synthesis")

    # 1) an AI analysis lands with auto tags + the full result
    ai = ArchivedPaper(
        key=key,
        source_sha256="ab" * 32,
        rubric_profile="synthesis",
        paper_title="A paper",
        paper_type=["data_analysis"],
        discipline=["neuroscience"],
        methods=["Stan", "MCMC"],
        result={"quality_score": 0.7},
    )
    svc.upsert_report(key, report_fields(ai))

    # 2) a later human rating of the SAME paper carries no inventory/discipline and no result
    human = ArchivedPaper(
        key=key,
        source_sha256="ab" * 32,
        rubric_profile="synthesis",
        mode="local",
        paper_type=["data_analysis"],
        human_rating={"rating": {"rater_id": "r1"}},
    )
    svc.upsert_report(key, report_fields(human))

    stored = svc.find_report(key)
    assert stored is not None
    assert stored["mode"] == "local"  # refreshed by the human upsert
    assert stored["discipline"] == ["neuroscience"]  # auto tags preserved (upsert omitted them)
    assert stored["methods"] == ["Stan", "MCMC"]
    assert stored["result"] == {"quality_score": 0.7}  # the AI result is never wiped
    assert len(reports.docs) == 1  # one entry, keyed by sha+profile

    # list projects the heavy result/inventory out
    listed = svc.list_reports()
    assert listed is not None and len(listed) == 1
    assert "result" not in listed[0] and "inventory" not in listed[0]
    assert "human_rating" not in listed[0]


def test_report_store_reads_by_paper_id() -> None:
    reports = _FakeReports()
    svc = _ready_service(reports)
    old_key = bucket_key("aa" * 32, "synthesis")
    new_key = bucket_key("bb" * 32, "synthesis")

    svc.upsert_report(old_key, {"paper_id": "p1", "source_sha256": "aa" * 32})
    svc.upsert_report(new_key, {"paper_id": "p1", "source_sha256": "bb" * 32})
    reports.docs[old_key]["updated_at"] = 1
    reports.docs[new_key]["updated_at"] = 2

    stored = svc.find_report_by_paper_id("p1")

    assert stored is not None
    assert stored["_id"] == new_key


def test_report_store_reads_none_when_mongo_down() -> None:
    svc = MongoDBService()  # never started → not ready
    # hold off the lazy reconnect so the test stays "down" even when a real Mongo URI is in the env
    svc._next_retry_monotonic = time.monotonic() + 3600
    assert svc.find_report("x") is None
    assert svc.list_reports() is None
    svc.upsert_report("x", {"key": "x"})  # no-op, no raise


# --- dedup replay eligibility ---------------------------------------------------------------------


def test_replayable_requires_current_full_report() -> None:
    rubric = load_rubric(profile="synthesis")
    base = {
        "result": {"quality_score": 0.5},
        "mode": "full",
        "engine_version": ENGINE_VERSION,
        "rubric_version": rubric.rubric_version,
        "grading_strategy": config.grading_strategy(),
    }
    assert replayable_report(base, rubric) is True
    assert replayable_report(None, rubric) is False
    assert replayable_report({**base, "result": None}, rubric) is False  # no result to replay
    assert replayable_report({**base, "mode": "local"}, rubric) is False  # human/inventory entry
    assert replayable_report({**base, "engine_version": "old"}, rubric) is False  # stale engine


# --- the read-only list endpoint (Mongo-backed) ---------------------------------------------------


def _archive_docs() -> list[dict]:
    return [
        {
            "_id": bucket_key("11" * 32, "synthesis"),
            "key": bucket_key("11" * 32, "synthesis"),
            "paper_id": "p1",
            "paper_title": "Hierarchical DDM",
            "paper_authors": ["Ada Lovelace"],
            "mode": "full",
            "paper_type": ["data_analysis"],
            "discipline": ["neuroscience"],
            "methods": ["Stan"],
        },
        {
            "_id": bucket_key("22" * 32, "synthesis"),
            "key": bucket_key("22" * 32, "synthesis"),
            "paper_id": "p2",
            "paper_title": "A new sampler",
            "paper_authors": [],
            "mode": "full",
            "paper_type": ["method_development"],
            "discipline": ["statistics"],
            "methods": ["MCMC"],
        },
    ]


def test_list_papers_endpoint_filters(monkeypatch) -> None:
    monkeypatch.setattr("bayesify.api.routes.archive.mongo.list_reports", lambda: _archive_docs())

    # unfiltered: both, plus facet vocabularies over the whole archive; the Mongo _id is stripped
    body = client.get("/api/papers").json()
    assert body["total"] == 2 and len(body["papers"]) == 2
    assert all("_id" not in p for p in body["papers"])
    assert "data_analysis" in body["facets"]["paper_type"]
    assert "neuroscience" in body["facets"]["discipline"]
    assert "tags" not in body["facets"]  # manual tags dropped

    # free-text matches title/authors
    assert len(client.get("/api/papers", params={"q": "lovelace"}).json()["papers"]) == 1

    # free-text also matches tags — a method tag, and a paper-type tag with separators normalised
    assert len(client.get("/api/papers", params={"q": "stan"}).json()["papers"]) == 1
    got_tag = client.get("/api/papers", params={"q": "data analysis"}).json()["papers"]
    assert [p["paper_title"] for p in got_tag] == ["Hierarchical DDM"]

    # facet AND-filter
    got = client.get("/api/papers", params={"discipline": "statistics"}).json()["papers"]
    assert [p["paper_title"] for p in got] == ["A new sampler"]


def test_list_papers_fills_missing_array_fields(monkeypatch) -> None:
    # the store drops empty arrays on upsert; the endpoint must still return them so the client
    # (which does p.paper_type.length etc.) never crashes on a sparse paper.
    sparse = {"_id": "k1", "key": "k1", "paper_id": "p1", "paper_title": "Bare", "mode": "full"}
    monkeypatch.setattr("bayesify.api.routes.archive.mongo.list_reports", lambda: [sparse])
    p = client.get("/api/papers").json()["papers"][0]
    for arr in ("paper_authors", "paper_type", "discipline", "methods"):
        assert p[arr] == []


def test_list_papers_empty_when_mongo_down(monkeypatch) -> None:
    monkeypatch.setattr("bayesify.api.routes.archive.mongo.list_reports", lambda: None)
    body = client.get("/api/papers").json()
    assert body == {
        "papers": [],
        "facets": {"paper_type": [], "discipline": [], "methods": []},
        "total": 0,
    }


def test_tag_edit_endpoint_removed() -> None:
    # the inline tag editor is gone — the route no longer exists
    assert client.patch("/api/papers/whatever/tags", json={"tags": []}).status_code in (404, 405)
