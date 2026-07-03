"""``engine_version`` composition — gate G1 (three-lens review, 2026-06-12).

``engine_version`` is load-bearing: it is a dimension of the full-result cache key
(``sha256(bytes) x engine_version x rubric_version x mode``, plans 02 §3.5), it names validation
reports (``validation/reports/<engine_version>.json``), it drives the regression gate, and it keeps
Phase-3 trends interpretable. Yet no plan defined *what it is composed of* — so this module pins it.

Composition (per the review resolution): **package version + prompt-set hash + detector-catalog
hash + pinned model snapshot IDs**. Any change to the code package, the prompt set, the detector
catalog, or the judge/screen model produces a different ``engine_version`` — which invalidates the
full-result cache and forces re-judging (not re-parsing — those are separate stage sub-caches).

At M1 the prompt set and detector catalog do not exist yet, so their hashes default to the sentinel
``"none"``. They become real when components c (detectors) and e (assess prompts) land; bumping
either hash then flows through here automatically.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from bayesify import __version__
from bayesify.llm import config as llm_config

_SENTINEL = "none"


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class EngineVersion:
    """The structured components of an engine version. ``compact`` is the cache-key dimension."""

    package_version: str
    prompt_set_hash: str
    detector_catalog_hash: str
    model_ids: tuple[str, ...]

    @property
    def compact(self) -> str:
        """A stable, human-readable string — identical components yield identical output, so it is
        safe to use directly as a cache-key dimension and a validation-report filename stem."""
        models = "+".join(self.model_ids)
        return (
            f"pkg={self.package_version}"
            f";prompts={self.prompt_set_hash}"
            f";detectors={self.detector_catalog_hash}"
            f";models={models}"
        )

    def __str__(self) -> str:
        return self.compact


def compute_engine_version(
    *,
    package_version: str | None = None,
    prompt_set: str | None = None,
    detector_catalog: str | None = None,
    model_ids: tuple[str, ...] | None = None,
) -> EngineVersion:
    """Compose the engine version from its parts.

    ``prompt_set`` / ``detector_catalog`` are the *contents* to hash (e.g. a concatenation of prompt
    templates, or the detector ``CATALOG.md``); pass ``None`` until they exist (→ sentinel hash).
    ``model_ids`` defaults to the pinned judge + screen models (G1).
    """
    return EngineVersion(
        package_version=package_version or __version__,
        prompt_set_hash=_short_hash(prompt_set) if prompt_set is not None else _SENTINEL,
        detector_catalog_hash=(
            _short_hash(detector_catalog) if detector_catalog is not None else _SENTINEL
        ),
        model_ids=model_ids if model_ids is not None else llm_config.model_ids(),
    )
