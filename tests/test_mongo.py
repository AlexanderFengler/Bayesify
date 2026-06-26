"""MongoDBService: the event-write envelope, graceful degradation, the reconnect backoff, and the
pure URI/path/index helpers — all without a real MongoDB server (an injected fake collection).

mongo.py is live-wired (lifespan start/stop, save_event on every analysis/rating) but its promise —
"persist events; when Mongo is down, fail gracefully and keep serving" — was previously untested.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from types import SimpleNamespace

from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi

from bayesify.api.mongo import MongoDBService


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
    monkeypatch.setattr(svc, "start", lambda: calls.append(1))  # a reconnect that stays down

    assert svc.save_event({"event": "x"}) is None
    assert calls == [1]  # attempted exactly one reconnect
    assert svc._next_retry_monotonic > time.monotonic()  # armed the ~5s backoff
    assert svc.save_event({"event": "y"}) is None
    assert calls == [1]  # the immediate next call must NOT retry again


# --- pure helpers ---------------------------------------------------------------------------------


def test_is_local_uri() -> None:
    local = MongoDBService._is_local_uri
    assert local("mongodb://localhost:27017")
    assert local("mongodb://127.0.0.1/bayesify")
    assert local("mongodb://[::1]:27017")
    assert not local("mongodb://db.example.com:27017")  # a remote host is not local
    assert not local("http://localhost:27017")  # not a mongodb scheme


def test_local_port() -> None:
    assert MongoDBService._local_port("mongodb://localhost:27018") == 27018
    assert MongoDBService._local_port("mongodb://localhost") == 27017  # default port


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


def test_create_client_uses_stable_api_for_atlas(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_client(uri: str, **kwargs):
        calls.append((uri, kwargs))
        return object()

    monkeypatch.setattr("bayesify.api.mongo.MongoClient", fake_client)
    MongoDBService._create_client("mongodb+srv://user:pass@example.mongodb.net/?appName=bayesify")

    _, kwargs = calls[0]
    assert kwargs["serverSelectionTimeoutMS"] == 5000
    assert isinstance(kwargs["server_api"], ServerApi)


def test_create_client_skips_stable_api_for_local(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_client(uri: str, **kwargs):
        calls.append((uri, kwargs))
        return object()

    monkeypatch.setattr("bayesify.api.mongo.MongoClient", fake_client)
    MongoDBService._create_client("mongodb://localhost:27017")

    _, kwargs = calls[0]
    assert kwargs == {"serverSelectionTimeoutMS": 500}


def test_mongodb_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("BAYESIFY_DATA_DIR", raising=False)
    monkeypatch.setenv("BAYESIFY_MONGODB_DATA_DIR", str(tmp_path / "explicit"))
    assert MongoDBService._mongodb_data_dir() == tmp_path / "explicit"  # explicit override wins

    monkeypatch.delenv("BAYESIFY_MONGODB_DATA_DIR")
    monkeypatch.setenv("BAYESIFY_DATA_DIR", str(tmp_path / "data"))
    assert MongoDBService._mongodb_data_dir() == tmp_path / "data" / "mongodb"  # under the data dir

    monkeypatch.delenv("BAYESIFY_DATA_DIR")
    assert MongoDBService._mongodb_data_dir() == Path.home() / ".bayesify" / "mongodb"  # default


def test_ensure_indexes_builds_the_query_indexes() -> None:
    fake = _FakeCollection()
    svc = MongoDBService()
    svc._events = fake
    svc._ensure_indexes()
    assert len(fake.indexes) == 4
    assert [("event", 1), ("created_at", -1)] in fake.indexes  # query-by-event (README)
    assert [("paper_id", 1), ("created_at", -1)] in fake.indexes  # query-by-paper


def test_ensure_indexes_noops_without_a_collection() -> None:
    MongoDBService()._ensure_indexes()  # _events is None → must not raise
