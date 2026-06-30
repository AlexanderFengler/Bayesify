"""Content cache + gate-G2 key dimensions."""

from __future__ import annotations

from pathlib import Path

from bayesify.core.cache import (
    BlobStore,
    FullResultKey,
    ResultCache,
    detect_cache_key,
    parse_cache_key,
    sha256_bytes,
)


def _key(**over) -> FullResultKey:
    base = dict(
        content_sha256="a" * 64, engine_version="ev1", rubric_version="0.1-draft", mode="full"
    )
    base.update(over)
    return FullResultKey(**base)


def test_blob_store_is_content_addressed(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    a = store.put(b"%PDF- hello")
    b = store.put(b"%PDF- hello")  # identical bytes -> same handle, stored once
    assert a == b == sha256_bytes(b"%PDF- hello")
    assert store.get(a) == b"%PDF- hello"
    assert store.delete(a) and not store.exists(a)


def test_full_result_key_changes_with_every_dimension() -> None:
    base = _key().digest()
    assert _key(mode="local").digest() != base  # mode
    assert _key(engine_version="ev2").digest() != base  # engine
    assert _key(rubric_version="1.0").digest() != base  # rubric
    assert _key(relevance_override="partial").digest() != base  # G2: rerun dimension
    assert _key(force_grade=True).digest() != base  # forced-grade dimension
    assert _key(rubric_profile="gelman").digest() != base  # different rubrics grade differently


def test_rerun_override_does_not_collide_with_short_circuit() -> None:
    short_circuit = _key(relevance_override=None)
    rerun = _key(relevance_override="partial")
    assert short_circuit.digest() != rerun.digest()


def test_parse_key_includes_parser_identity() -> None:
    # G2: a degraded PyMuPDF run must not share a key with a GROBID run on the same bytes.
    grobid = parse_cache_key("sha", "grobid", "0.8.1")
    pymupdf = parse_cache_key("sha", "pymupdf", "1.24")
    assert grobid != pymupdf


def test_detect_key_changes_with_catalog_version() -> None:
    assert detect_cache_key("sha", "c1") != detect_cache_key("sha", "c2")


def test_result_cache_round_trips(tmp_path: Path) -> None:
    cache = ResultCache(tmp_path)
    key = _key()
    assert cache.get(key) is None
    cache.put(key, {"badge": "gone", "coverage": [6, 8]})
    assert cache.get(key) == {"badge": "gone", "coverage": [6, 8]}
    assert cache.delete(key) and cache.get(key) is None
