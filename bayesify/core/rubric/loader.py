"""Load a rubric from the registry of self-contained rubric files in ``rubric/``.

Each ``rubric/<id>.yaml`` is one complete, self-contained rubric (its own steps, scoring block,
citations, version, label and preamble ``summary``). The registry is the directory: drop a new
``rubric/<id>.yaml`` and it is available as ``load_rubric("<id>")`` — no code change. ``synthesis``
is the default. ``available_rubrics()`` lists them for the pickers.

An unknown rubric id raises :class:`RubricProfileError`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bayesify.core.rubric.models import RubricInfo, RubricSpec

# Repo-root ``rubric/`` (this file lives at bayesify/core/rubric/loader.py).
RUBRIC_DIR = Path(__file__).resolve().parents[3] / "rubric"

SYNTHESIS = "synthesis"


class RubricProfileError(ValueError):
    """Raised when a requested rubric id is not in the registry."""


def _registry() -> dict[str, Path]:
    """Map rubric id (file stem) -> path for every ``rubric/<id>.yaml``."""
    return {p.stem: p for p in sorted(RUBRIC_DIR.glob("*.yaml"))}


def load_rubric(profile: str = SYNTHESIS) -> RubricSpec:
    """Load the rubric registered under ``profile`` (its file stem). Unknown id -> error."""
    registry = _registry()
    path = registry.get(profile)
    if path is None:
        raise RubricProfileError(
            f"unknown rubric {profile!r}; available: {sorted(registry)}"
        )
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = RubricSpec.model_validate(data)
    return spec.model_copy(update={"profile": profile})


def available_rubrics() -> list[RubricInfo]:
    """Every registered rubric (for the pickers), synthesis first then the rest alphabetically."""
    infos = [
        RubricInfo(
            id=rid,
            label=spec.label or rid,
            summary=spec.summary,
            rubric_version=spec.rubric_version,
        )
        for rid in sorted(_registry())
        for spec in (load_rubric(rid),)
    ]
    infos.sort(key=lambda r: (r.id != SYNTHESIS, r.id))
    return infos
