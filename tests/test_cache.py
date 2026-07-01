"""Content-addressed blob store. Report persistence + dedup live in MongoDB (see test_archive)."""

from __future__ import annotations

from pathlib import Path

from bayesify.core.cache import BlobStore, sha256_bytes


def test_blob_store_is_content_addressed(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    a = store.put(b"%PDF- hello")
    b = store.put(b"%PDF- hello")  # identical bytes -> same handle, stored once
    assert a == b == sha256_bytes(b"%PDF- hello")
    assert store.get(a) == b"%PDF- hello"
    assert store.delete(a) and not store.exists(a)
