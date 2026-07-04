"""MongoDBService: the event-write envelope, graceful degradation, the reconnect backoff, and the
pure URI/index helpers — all without a real MongoDB server (an injected fake collection).

mongo.py is live-wired (lifespan connect/close, save_event on every analysis/rating), but its
promise — "persist events; when Mongo is down, fail gracefully and keep serving" — was previously
untested.
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace

from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi

from bayesify.api.db import MongoDBService


class _FakeCollection:
    """Stand-in for the `events` collection: records inserts/indexes, can fail the insert."""

    def __init__(self, *, raise_on_insert: bool = False) -> None:
        self.docs: list[dict] = []
        self.indexes: list[list[tuple[str, int]]] = []
        self._raise = raise_on_insert

    def insert_one(self, doc: dict):
        if self._raise:
            raise PyMongoError("boom")
        self.docs.append(doc)
        return SimpleNamespace(inserted_id="abc123")

    def create_index(self, keys: list[tuple[str, int]]) -> None:
        self.indexes.append(keys)

    def find_one(self, query: dict, sort=None):
        matches = [doc for doc in self.docs if all(doc.get(k) == v for k, v in query.items())]
        if not matches:
            return None
        if sort == [("created_at", -1)]:
            matches.sort(
                key=lambda doc: (doc.get("created_at"), self.docs.index(doc)), reverse=True
            )
        return matches[0]


def _ready_service(collection: _FakeCollection) -> MongoDBService:
    svc = MongoDBService()
    svc._ready = True
    svc._events = collection
    return svc


# --- save_event: envelope + return value ----------------------------------------------------------


def test_save_event_writes_envelope_and_returns_id() -> None:
    fake = _FakeCollection()
    svc = _ready_service(fake)
    out = svc.save_event({"event": "analysis_report_ready", "paper_id": "p1"})
    assert out == "abc123"  # the inserted _id, stringified
    assert len(fake.docs) == 1
    doc = fake.docs[0]
    assert doc["event"] == "analysis_report_ready" and doc["paper_id"] == "p1"  # payload preserved
    assert doc["created_at"].tzinfo is not None  # a UTC-aware timestamp was stamped on


# --- graceful degradation -------------------------------------------------------------------------


def test_save_event_returns_none_when_not_ready(caplog) -> None:
    svc = MongoDBService()
    svc._ready = False
    svc._next_retry_monotonic = time.monotonic() + 100  # inside the backoff window → no reconnect
    with caplog.at_level(logging.WARNING, logger="bayesify.mongo"):
        out = svc.save_event({"event": "blind_rating_submitted"})
    assert out is None  # dropped, not raised
    assert any("not saved" in r.getMessage() for r in caplog.records)


def test_save_event_swallows_pymongo_error_and_marks_not_ready(caplog) -> None:
    svc = _ready_service(_FakeCollection(raise_on_insert=True))
    with caplog.at_level(logging.WARNING, logger="bayesify.mongo"):
        out = svc.save_event({"event": "analysis_report_ready"})
    assert out is None  # a failed insert never propagates to the request path
    assert svc._ready is False  # degraded, so the next call re-pings before trying again


def test_save_event_backoff_does_not_reconnect_storm(monkeypatch) -> None:
    svc = MongoDBService()
    svc._ready = False
    svc._next_retry_monotonic = 0.0  # eligible to retry now
    calls: list[int] = []
    monkeypatch.setattr(svc, "connect", lambda: calls.append(1))  # a reconnect that stays down

    assert svc.save_event({"event": "x"}) is None
    assert calls == [1]  # attempted exactly one reconnect
    assert svc._next_retry_monotonic > time.monotonic()  # armed the ~5s backoff
    assert svc.save_event({"event": "y"}) is None
    assert calls == [1]  # the immediate next call must NOT retry again


def test_find_latest_job_state_reads_newest_matching_event() -> None:
    fake = _FakeCollection()
    svc = _ready_service(fake)
    svc.save_event({"event": "job_state", "paper_id": "p1", "status": "queued"})
    svc.save_event({"event": "analysis_report_ready", "paper_id": "p1"})
    svc.save_event({"event": "job_state", "paper_id": "p1", "status": "running"})

    doc = svc.find_latest_job_state("p1")

    assert doc is not None
    assert doc["event"] == "job_state"
    assert doc["status"] == "running"


# --- pure helpers ---------------------------------------------------------------------------------


def test_is_local_uri() -> None:
    local = MongoDBService._is_local_uri
    assert local("mongodb://localhost:27017")
    assert local("mongodb://127.0.0.1/bayesify")
    assert local("mongodb://[::1]:27017")
    assert not local("mongodb://db.example.com:27017")  # a remote host is not local
    assert not local("http://localhost:27017")  # not a mongodb scheme


def test_remote_uris_use_longer_timeout() -> None:
    assert MongoDBService._server_selection_timeout_ms("mongodb://localhost:27017") == 500
    assert (
        MongoDBService._server_selection_timeout_ms(
            "mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify"
        )
        == 5000
    )


def test_timeout_override(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_TIMEOUT_MS", "42")
    assert MongoDBService._server_selection_timeout_ms("mongodb://localhost:27017") == 42


def test_safe_uri_masks_password() -> None:
    safe = MongoDBService._safe_uri(
        "mongodb+srv://atlas_user:secret@example.mongodb.net/?appName=bayesify"
    )
    assert safe == "mongodb+srv://atlas_user:***@example.mongodb.net/?appName=bayesify"
    assert "secret" not in safe


def test_status_masks_atlas_uri_and_reports_mode(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_SERVER_API", "1")
    svc = MongoDBService()
    svc._ready = True
    status = svc._make_status(
        "mongodb+srv://atlas_user:secret@example.mongodb.net/?appName=bayesify",
        "bayesify",
        message="connected",
    )
    assert status.ready is True
    assert status.uri == "mongodb+srv://atlas_user:***@example.mongodb.net/?appName=bayesify"
    assert status.database == "bayesify"
    assert status.mode == "atlas/remote"
    assert status.server_api == "1"
    assert "secret" not in status.uri


def test_mongodb_uri_accepts_atlas_style_alias(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_MONGODB_URI", raising=False)
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify")
    assert (
        MongoDBService.mongodb_uri()
        == "mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify"
    )


def test_mongodb_uri_prefers_bayesify_override(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_URI", "mongodb://localhost:27018")
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://user:pass@example.mongodb.net")
    assert MongoDBService.mongodb_uri() == "mongodb://localhost:27018"


def test_mongodb_database_accepts_common_aliases(monkeypatch) -> None:
    monkeypatch.delenv("BAYESIFY_MONGODB_DB", raising=False)
    monkeypatch.setenv("MONGODB_DATABASE", "atlas_db")
    assert MongoDBService.mongodb_database() == "atlas_db"


def test_mongodb_server_api_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_MONGODB_SERVER_API", "0")
    assert MongoDBService.mongodb_server_api() is None


def test_create_client_uses_stable_api_for_atlas(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_client(uri: str, **kwargs):
        calls.append((uri, kwargs))
        return object()

    monkeypatch.setattr("bayesify.api.db.mongo.MongoClient", fake_client)
    MongoDBService._create_client("mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify")

    _, kwargs = calls[0]
    assert kwargs["serverSelectionTimeoutMS"] == 5000
    assert isinstance(kwargs["server_api"], ServerApi)


def test_create_client_skips_stable_api_for_local(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_client(uri: str, **kwargs):
        calls.append((uri, kwargs))
        return object()

    monkeypatch.setattr("bayesify.api.db.mongo.MongoClient", fake_client)
    MongoDBService._create_client("mongodb://localhost:27017")

    _, kwargs = calls[0]
    assert kwargs == {"serverSelectionTimeoutMS": 500}


def test_ensure_indexes_builds_the_query_indexes() -> None:
    fake = _FakeCollection()
    svc = MongoDBService()
    svc._events = fake
    svc._ensure_indexes()
    assert len(fake.indexes) == 3
    assert [("event", 1), ("created_at", -1)] in fake.indexes  # query-by-event (README)
    assert [("paper_id", 1), ("created_at", -1)] in fake.indexes  # query-by-paper
    # the global override-bank read (override-review pass)
    assert [("rubric_profile", 1), ("event", 1), ("created_at", -1)] in fake.indexes


def test_ensure_indexes_noops_without_a_collection() -> None:
    MongoDBService()._ensure_indexes()  # _events is None → must not raise
