"""MongoDB startup plumbing for report persistence.

The API maintains a singleton Mongo client and writes report/rating events to the `events`
collection.
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

    def __init__(self):
        self._log = logging.getLogger("bayesify.mongo")
        self._client = None
        self._events = None
        self._mongod = None
        self._ready = False
        self._next_retry_monotonic = 0.0

    def start(self):
        """Create the process-wide Mongo client and best-effort ping the configured database."""
        database = config.mongodb_database()
        if self._client is not None:
            if not self._ready and self._ping(database):
                self._events = self._client[database]["events"]
                self._ensure_indexes()
                self._ready = True
            return

        uri = config.mongodb_uri()
        self._client = MongoClient(uri, serverSelectionTimeoutMS=500)
        ping_ok = self._ping(database)
        if not ping_ok and self._try_start_local_mongod(uri):
            for _ in range(10):
                if self._ping(database):
                    ping_ok = True
                    break
                time.sleep(0.5)
        if not ping_ok:
            self._log.warning(
                f"MongoDB client created, but no server answered at {uri}/{database}. "
                f"Report events will not be saved to MongoDB until it is available."
            )
            self._ready = False
            return

        self._events = self._client[database]["events"]
        self._ensure_indexes()
        self._ready = True
        self._log.info(f"MongoDB client started for {uri}/{database}")

    def stop(self):
        """Close the process-wide Mongo client and any local ``mongod`` this service spawned."""
        self._ready = False
        if self._client is not None:
            self._client.close()
            self._client = None
            self._events = None
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
                f"MongoDB is not running at {uri} and 'mongod' is not installed. "
                f"Start MongoDB locally, or set BAYESIFY_MONGODB_URI to a running server."
            )
            return False
        dbpath = self._mongodb_data_dir()
        try:
            dbpath.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._log.warning(f"Could not create MongoDB data directory {dbpath}: {exc}")
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
        self._log.info(f"Started local MongoDB server at {uri} with dbpath {dbpath}")
        return True

    def _ensure_indexes(self):
        if self._events is None:
            return
        self._events.create_index([("event", 1), ("created_at", -1)])
        self._events.create_index([("paper_id", 1), ("created_at", -1)])
        self._events.create_index(
            [("source_sha256", 1), ("rubric_profile", 1), ("created_at", -1)]
        )
        self._events.create_index(
            [("submission.source_sha256", 1), ("submission.rubric_profile", 1)]
        )


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
