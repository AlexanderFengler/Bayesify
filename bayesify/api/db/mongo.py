"""MongoDB connection plumbing for event and report persistence.

The API maintains a singleton Mongo client. Report bodies live in the `reports` collection; the
`events` collection is a sparse audit log. When MongoDB is unavailable, writes fail gracefully
(logged) and the API continues serving requests.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi


@dataclass(frozen=True)
class MongoDBStatus:
    """Lifespan-visible MongoDB connection state."""

    ready: bool
    uri: str
    database: str
    mode: str
    server_api: str | None
    message: str


class MongoDBService:
    """Process-wide MongoDB connection manager for sparse events and report documents."""

    def __init__(self):
        self._log = logging.getLogger("bayesify.mongo")
        self._client = None
        self._events = None
        self._reports = None
        self._ready = False
        self._last_ping_error: str | None = None
        self._next_retry_monotonic = 0.0
        self._last_status: MongoDBStatus | None = None

    def connect(self) -> MongoDBStatus:
        """Create the process-wide Mongo client and best-effort ping the configured database."""
        uri = self.mongodb_uri()
        database = self.mongodb_database()

        if self._client is not None:
            if not self._ready and self._ping(database):
                self._events = self._client[database]["events"]
                self._reports = self._client[database]["reports"]
                self._ensure_indexes()
                self._ready = True

            message = "connected" if self._ready else "unavailable; will retry on writes"
            self._last_status = self._make_status(uri, database, message=message)
            return self._last_status

        try:
            self._client = self._create_client(uri)
        except PyMongoError as exc:
            location = self._safe_uri(uri)
            self._ready = False
            self._last_status = self._make_status(
                uri,
                database,
                message=f"client creation failed: {exc}",
            )
            self._log.warning(
                f"MongoDB client could not be created for {location}/{database}: {exc}. "
                f"Report events will not be saved to MongoDB until it is available."
            )
            return self._last_status

        ping_ok = self._ping(database)
        if not ping_ok:
            location = self._safe_uri(uri)
            reason = f" Last ping error: {self._last_ping_error}." if self._last_ping_error else ""
            self._log.warning(
                f"MongoDB client created, but no server answered at {location}/{database}. "
                f"Report events will not be saved to MongoDB until it is available.{reason}"
            )
            self._ready = False
            self._last_status = self._make_status(
                uri,
                database,
                message=self._unavailable_message(),
            )
            return self._last_status

        self._events = self._client[database]["events"]
        self._reports = self._client[database]["reports"]
        self._ensure_indexes()
        self._ready = True
        self._log.info(f"MongoDB client connected for {self._safe_uri(uri)}/{database}")
        self._last_status = self._make_status(uri, database, message="connected")
        return self._last_status

    def close(self):
        """Close the process-wide Mongo client."""
        self._ready = False
        if self._client is not None:
            self._client.close()
            self._client = None
            self._events = None
            self._reports = None

    def save_event(self, payload: dict[str, Any]) -> str | None:
        """Persist one sparse event envelope. Returns the Mongo ``_id`` string when saved."""
        if not self._ready:
            now = time.monotonic()
            if now >= self._next_retry_monotonic:
                self.connect()
                if not self._ready:
                    self._next_retry_monotonic = now + 5.0
        events = self._events if self._ready else None
        event = payload.get("event")
        if events is None:
            self._log.warning(f"MongoDB unavailable; event {event} was not saved.")
            return None
        doc = {"created_at": datetime.now(UTC), **payload}
        try:
            inserted = events.insert_one(doc)
        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB save failed for event {event}: {exc}")
            return None
        event_id = str(inserted.inserted_id)
        self._log.info(f"MongoDB saved event {event} as {event_id}")
        return event_id

    def find_trusted_step_overrides(self, rubric_profile: str) -> list[dict[str, Any]] | None:
        """All **trusted** step-status overrides for one rubric — the global correction bank the
        override-review pass reads. Newest first, capped. ``None`` when Mongo is unavailable (caller
        falls back to the local log), ``[]`` when reachable but empty."""
        if not self._ready:
            now = time.monotonic()
            if now >= self._next_retry_monotonic:
                self.connect()
                if not self._ready:
                    self._next_retry_monotonic = now + 5.0
        events = self._events if self._ready else None
        if events is None:
            return None
        try:
            cursor = (
                events.find(
                    {
                        "event": "override_recorded",
                        "kind": "step_status",
                        "trusted": True,
                        "rubric_profile": rubric_profile,
                    }
                )
                .sort("created_at", -1)
                .limit(200)
            )
            return list(cursor)

        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB override read failed: {exc}")
            return None

    def find_latest_job_state(self, paper_id: str) -> dict[str, Any] | None:
        """Newest coarse job state for one paper id, or None when absent/unavailable."""
        return self._find_latest_event("job_state", paper_id)

    def _find_latest_event(self, event: str, paper_id: str) -> dict[str, Any] | None:
        if not self._ready:
            now = time.monotonic()
            if now >= self._next_retry_monotonic:
                self.connect()
                if not self._ready:
                    self._next_retry_monotonic = now + 5.0
        events = self._events if self._ready else None
        if events is None:
            return None
        try:
            return events.find_one(
                {"event": event, "paper_id": paper_id},
                sort=[("created_at", -1)],
            )
        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB {event} read failed for {paper_id}: {exc}")
            return None

    def _reports_collection(self):
        """The `reports` collection when Mongo is reachable, else None (with a lazy reconnect)."""
        if not self._ready:
            now = time.monotonic()
            if now >= self._next_retry_monotonic:
                self.connect()
                if not self._ready:
                    self._next_retry_monotonic = now + 5.0
        return self._reports if self._ready else None

    def upsert_report(self, key: str, fields: dict[str, Any]) -> None:
        """Insert or update one report entry, keyed by ``bucket_key`` (``<sha>__<profile>``). Only
        the fields the caller supplies are written, so a later Human rating (no ``result``) can
        refresh metadata without wiping the AI report's ``result`` / auto-tags. ``created_at`` is
        set once, on insert."""
        reports = self._reports_collection()
        if reports is None:
            self._log.warning(f"MongoDB unavailable; report {key} was not saved.")
            return
        now = datetime.now(UTC)
        try:
            reports.update_one(
                {"_id": key},
                {"$set": {**fields, "updated_at": now}, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB report upsert failed for {key}: {exc}")

    def find_report(self, key: str) -> dict[str, Any] | None:
        """The report entry for one ``bucket_key`` (content+rubric); None if absent/unavailable."""
        reports = self._reports_collection()
        if reports is None:
            return None
        try:
            return reports.find_one({"_id": key})
        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB report read failed for {key}: {exc}")
            return None

    def find_report_by_paper_id(self, paper_id: str) -> dict[str, Any] | None:
        """The newest report entry for a job id; None if absent/unavailable."""
        reports = self._reports_collection()
        if reports is None:
            return None
        try:
            return reports.find_one({"paper_id": paper_id}, sort=[("updated_at", -1)])
        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB report read failed for paper_id {paper_id}: {exc}")
            return None

    def find_report_by_identifier(
        self, identifier: str, rubric_profile: str
    ) -> dict[str, Any] | None:
        """The newest report for a submitted identifier under one rubric — the identifier-first
        short-circuit that lets a resubmitted arXiv/DOI/URL replay without refetching the PDF."""
        reports = self._reports_collection()
        if reports is None:
            return None
        try:
            return reports.find_one(
                {"identifier": identifier, "rubric_profile": rubric_profile},
                sort=[("updated_at", -1)],
            )
        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB report read failed for identifier {identifier}: {exc}")
            return None

    def list_reports(self) -> list[dict[str, Any]] | None:
        """Every archived report, newest-updated first, with the heavy ``result`` / ``inventory``
        projected out (the Archive list only needs metadata + tags). ``None`` when Mongo is down so
        the caller can tell "no archive" from "empty archive"."""
        reports = self._reports_collection()
        if reports is None:
            return None
        try:
            cursor = (
                reports.find({}, {"result": 0, "inventory": 0, "human_rating": 0})
                .sort("updated_at", -1)
                .limit(1000)
            )
            return list(cursor)
        except PyMongoError as exc:
            self._ready = False
            self._log.warning(f"MongoDB report list failed: {exc}")
            return None

    @staticmethod
    def _is_local_uri(uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.scheme in ("mongodb", "mongodb+srv") and parsed.hostname in (
            "localhost",
            "127.0.0.1",
            "::1",
        )

    @staticmethod
    def mongodb_uri() -> str:
        return (
            os.environ.get("BAYESIFY_MONGODB_URI")
            or os.environ.get("MONGODB_URI")
            or "mongodb://localhost:27017"
        )

    @staticmethod
    def mongodb_database() -> str:
        return (
            os.environ.get("BAYESIFY_MONGODB_DB")
            or os.environ.get("MONGODB_DATABASE")
            or os.environ.get("MONGO_DATABASE")
            or "bayesify"
        )

    @staticmethod
    def mongodb_server_api() -> str | None:
        value = os.environ.get("BAYESIFY_MONGODB_SERVER_API", "1").strip()
        return None if value.lower() in ("", "0", "false", "no") else value

    @classmethod
    def _create_client(cls, uri: str) -> MongoClient:
        kwargs: dict[str, Any] = {
            "serverSelectionTimeoutMS": cls._server_selection_timeout_ms(uri),
        }
        api_version = cls.mongodb_server_api()
        if api_version is not None and not cls._is_local_uri(uri):
            kwargs["server_api"] = ServerApi(api_version)
        return MongoClient(uri, **kwargs)

    @staticmethod
    def _server_selection_timeout_ms(uri: str) -> int:
        configured = os.environ.get("BAYESIFY_MONGODB_TIMEOUT_MS")
        if configured:
            try:
                return max(1, int(configured))
            except ValueError:
                return 5000
        return 500 if MongoDBService._is_local_uri(uri) else 5000

    @staticmethod
    def _safe_uri(uri: str) -> str:
        parsed = urlparse(uri)
        if "@" not in parsed.netloc:
            return uri
        userinfo, hosts = parsed.netloc.rsplit("@", 1)
        username = userinfo.split(":", 1)[0]
        return parsed._replace(netloc=f"{username}:***@{hosts}").geturl()

    @classmethod
    def _mode(cls, uri: str) -> str:
        if cls._is_local_uri(uri):
            return "local"
        return "atlas/remote" if urlparse(uri).scheme == "mongodb+srv" else "remote"

    def _make_status(self, uri: str, database: str, *, message: str) -> MongoDBStatus:
        return MongoDBStatus(
            ready=self._ready,
            uri=self._safe_uri(uri),
            database=database,
            mode=self._mode(uri),
            server_api=self.mongodb_server_api() if not self._is_local_uri(uri) else None,
            message=message,
        )

    def _ping(self, database: str) -> bool:
        if self._client is None:
            self._last_ping_error = "client is not initialized"
            return False
        try:
            self._client[database].command("ping")
        except PyMongoError as exc:
            self._last_ping_error = f"{type(exc).__name__}: {exc}"
            return False
        self._last_ping_error = None
        return True

    def _unavailable_message(self) -> str:
        base = "server did not answer ping; will retry on writes"
        return f"{base}; {self._last_ping_error}" if self._last_ping_error else base

    def _ensure_indexes(self):
        if self._events is None:
            return

        self._events.create_index([("event", 1), ("created_at", -1)])
        self._events.create_index([("paper_id", 1), ("created_at", -1)])
        self._events.create_index([("rubric_profile", 1), ("event", 1), ("created_at", -1)])

        if self._reports is not None:
            self._reports.create_index([("updated_at", -1)])
            self._reports.create_index([("paper_id", 1), ("updated_at", -1)])
            self._reports.create_index(
                [("identifier", 1), ("rubric_profile", 1), ("updated_at", -1)]
            )


mongo = MongoDBService()
