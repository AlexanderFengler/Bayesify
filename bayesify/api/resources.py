"""Process-local resources used by API jobs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import httpx

from bayesify.api import config
from bayesify.core.cache import BlobStore
from bayesify.core.fetcher import Fetcher
from bayesify.core.validation.override_store import OverrideStore
from bayesify.core.validation.rating_store import RatingStore
from bayesify.llm import LLMClient, make_llm_client

blob_dir: Path | None = None


def data_root() -> Path:
    return Path(os.environ.get("BAYESIFY_DATA_DIR", str(Path.home() / ".bayesify")))


def blob_store() -> BlobStore:
    global blob_dir
    if blob_dir is None:
        blob_dir = Path(tempfile.mkdtemp(prefix="bayesify-blobs-"))
    return BlobStore(blob_dir)


def ratings_store() -> RatingStore:
    return RatingStore(data_root() / "ratings")


def overrides_store() -> OverrideStore:
    return OverrideStore(data_root())


def cache_enabled() -> bool:
    return os.environ.get("BAYESIFY_NO_CACHE", "").strip().lower() not in ("1", "true", "yes")


def fetcher() -> Fetcher:
    return Fetcher(
        httpx.Client(),
        blob_store(),
        openalex_api_key=config.openalex_api_key(),
        unpaywall_email=config.unpaywall_email(),
    )


def llm_client() -> LLMClient:
    return make_llm_client()
