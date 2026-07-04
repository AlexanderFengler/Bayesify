"""Content-addressed blob store for document bytes.

The manuscript bytes are held here only transiently while a job runs (ingest writes them; parse and
the engine read them by sha256). The store is content-addressed — the handle *is* the sha256 — so
identical bytes are written once. Report persistence and the cross-user dedup cache live in MongoDB
(see ``bayesify.api.db``): nothing about a paper is kept on local disk beyond the run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from bayesify.core.atomic import atomic_write_bytes


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class BlobStore:
    """Content-addressed storage for document bytes. The handle is the sha256; the schema carries
    no bytes (see ``SourceDoc.sha256``). Used by ingest (write), the engine, and per-paper purge."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sha256: str) -> Path:
        return self.root / f"{sha256}.bin"

    def put(self, data: bytes) -> str:
        digest = sha256_bytes(data)
        path = self._path(digest)
        if not path.exists():  # content-addressed: identical bytes are stored once
            # Atomic: a crash mid-write never leaves a truncated blob carrying the (correct) sha
            # name, which exists() would then trust forever and get() would replay as corrupt bytes.
            atomic_write_bytes(path, data)
        return digest

    def get(self, sha256: str) -> bytes:
        return self._path(sha256).read_bytes()

    def exists(self, sha256: str) -> bool:
        return self._path(sha256).exists()

    def delete(self, sha256: str) -> bool:
        path = self._path(sha256)
        if path.exists():
            path.unlink()
            return True
        return False
