"""Content-addressed blob store + result cache (C6), with the gate-G2 cache key.

Gate **G2** (three-lens review): the full-result cache key must include a **rerun-override
dimension** (so a forced-relevance rerun does not collide with the persisted short-circuit) and
stage sub-caches must include **parser / detector identity** (so a degraded PyMuPDF result while
GROBID is down does not replay forever under the same key). This module pins those keys.

- **Full-result key** = ``sha256 x engine_version x rubric_version x mode x relevance_override``.
- **Parse sub-cache key** = ``sha256(bytes) x parser x parser_version``.
- **Detect sub-cache key** = ``sha256(bytes) x detector_catalog_version``.

Everything is local, file-based, and content-addressed — cache hits are byte-identical replays,
which is what makes assessments reproducible. The store is M2-scale (a directory of JSON + blobs);
the SQLite index is a later concern.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _key_digest(parts: tuple[str, ...]) -> str:
    # Join with a separator that cannot appear in the parts (NUL) so distinct tuples never collide.
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FullResultKey:
    content_sha256: str
    engine_version: str
    rubric_version: str
    mode: str  # "full" | "local"
    relevance_override: str | None = None  # G2: a rerun under a forced relevance is a distinct key

    def digest(self) -> str:
        return _key_digest(
            (
                self.content_sha256,
                self.engine_version,
                self.rubric_version,
                self.mode,
                self.relevance_override or "",
            )
        )


def parse_cache_key(content_sha256: str, parser: str, parser_version: str) -> str:
    """Stage-2 (parse) sub-cache key — G2: includes parser identity so a degraded-parser run is not
    cached under the same key as a GROBID run."""
    return _key_digest((content_sha256, "parse", parser, parser_version))


def detect_cache_key(content_sha256: str, detector_catalog_version: str) -> str:
    """Stage-3 (detect) sub-cache key — bumping the detector catalog invalidates it without
    re-parsing."""
    return _key_digest((content_sha256, "detect", detector_catalog_version))


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
            path.write_bytes(data)
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


class ResultCache:
    """Stage-0 full-result cache: ``FullResultKey`` -> stored ``ScoredResult`` JSON. A hit is
    returned verbatim (reproducible). Stored as JSON so it is engine-agnostic and inspectable."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: FullResultKey) -> Path:
        return self.root / f"{key.digest()}.json"

    def get(self, key: FullResultKey) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, key: FullResultKey, result_json: dict) -> None:
        self._path(key).write_text(json.dumps(result_json), encoding="utf-8")

    def delete(self, key: FullResultKey) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False
