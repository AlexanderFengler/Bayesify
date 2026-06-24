"""MongoDB startup plumbing for report persistence.

The API maintains a singleton Mongo client and writes report/rating events to the `events` collection.
When MongoDB is unavailable, writes fail gracefully (logged) and the API continues serving requests.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from bayesify.core import config


class MongoDBService:
    """Process-wide MongoDB connection manager and event writer."""

    def __init__(self) -> None:
        self._log = logging.getLogger("bayesify.mongo")
        self._client = None
        self._mongod = None
        self._ready = False

    def start(self) -> None:
        """Create the process-wide Mongo client and best-effort ping the configured database."""
        if self._client is not None:
            if not self._ready and self._ping(config.mongodb_database()):
                self._ensure_indexes()
                self._ready = True
            return

        uri = config.mongodb_uri()
        database = config.mongodb_database()
        self._client = MongoClient(uri, serverSelectionTimeoutMS=500)
        if not self._ping(database):
            if self._try_start_local_mongod(uri):
                for _ in range(10):
                    if self._ping(database):
                        break
                    time.sleep(0.5)
            if not self._ping(database):
                self._log.warning(
                    "MongoDB client created, but no server answered at %s/%s. "
                    "Report events will not be saved to MongoDB until it is available.",
                    uri,
                    database,
                )
                self._ready = False
                return

        self._ensure_indexes()
        self._ready = True
        self._log.info("MongoDB client started for %s/%s", uri, database)

    def stop(self) -> None:
        """Close the process-wide Mongo client and any local ``mongod`` this service spawned."""
        self._ready = False
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._mongod is not None:
            self._mongod.terminate()
            try:
                self._mongod.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._mongod.kill()
                self._mongod.wait(timeout=5)
            self._mongod = None

    def save_event(self, payload: dict[str, Any]) -> str | None:
        """Persist one report event envelope. Returns the Mongo ``_id`` string when saved."""
        if not self._ready:
            now = time.monotonic()
            if now >= self._next_retry_monotonic:
                self.start()
                if not self._ready:
                    self._next_retry_monotonic = now + 5.0
        events = self._events_collection()
        event = payload.get("event")
        if events is None:
            self._log.warning("MongoDB unavailable; event %s was not saved.", event)
            return None
        doc = {"created_at": datetime.now(UTC), **payload}
        try:
            inserted = events.insert_one(doc)
        except PyMongoError as exc:
            self._log.warning("MongoDB save failed for event %s: %s", event, exc)
            return None
        event_id = str(inserted.inserted_id)
        self._log.info("MongoDB saved event %s as %s", event, event_id)
        return event_id

    @staticmethod
    def _is_local_uri(uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.scheme in ("mongodb", "mongodb+srv") and parsed.hostname in (
            "localhost",
            "127.0.0.1",
            "::1",
        )

    @staticmethod
    def _local_port(uri: str) -> int:
        return urlparse(uri).port or 27017

    @staticmethod
    def _mongodb_data_dir() -> Path:
        root = os.environ.get("BAYESIFY_MONGODB_DATA_DIR")
        if root:
            return Path(root)
        data_root = os.environ.get("BAYESIFY_DATA_DIR")
        if data_root:
            return Path(data_root).expanduser() / "mongodb"
        return Path.home() / ".bayesify" / "mongodb"

    def _ping(self, database: str) -> bool:
        if self._client is None:
            return False
        try:
            self._client[database].command("ping")
        except PyMongoError:
            return False
        return True

    def _try_start_local_mongod(self, uri: str) -> bool:
        if not config.mongodb_autostart() or not self._is_local_uri(uri):
            return False
        mongod = shutil.which("mongod")
        if mongod is None:
            self._log.warning(
                "MongoDB is not running at %s and 'mongod' is not installed. "
                "Start MongoDB locally, or set BAYESIFY_MONGODB_URI to a running server.",
                uri,
            )
            return False
        dbpath = self._mongodb_data_dir()
        try:
            dbpath.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._log.warning("Could not create MongoDB data directory %s: %s", dbpath, exc)
            return False
        self._mongod = subprocess.Popen(
            [
                mongod,
                "--dbpath",
                str(dbpath),
                "--bind_ip",
                "127.0.0.1",
                "--port",
                str(self._local_port(uri)),
                "--quiet",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._log.info("Started local MongoDB server at %s with dbpath %s", uri, dbpath)
        return True

    def _events_collection(self):
        if self._client is None or not self._ready:
            return None
        return self._client[config.mongodb_database()]["events"]

    def _ensure_indexes(self) -> None:
        if self._client is None:
            return
        events = self._client[config.mongodb_database()]["events"]
        events.create_index([("event", 1), ("created_at", -1)])
        events.create_index([("paper_id", 1), ("created_at", -1)])
        events.create_index([("source_sha256", 1), ("rubric_profile", 1), ("created_at", -1)])
        events.create_index([("submission.source_sha256", 1), ("submission.rubric_profile", 1)])


@lru_cache(maxsize=1)
def mongodb() -> MongoDBService:
    """Singleton MongoDB service for the API process."""
    return MongoDBService()


def start_mongodb() -> None:
    mongodb().start()


def save_event(payload: dict[str, Any]) -> str | None:
    return mongodb().save_event(payload)


def stop_mongodb() -> None:
    mongodb().stop()
