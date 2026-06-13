"""Load and profile-filter ``rubric/steps.yaml``.

``load_rubric(path, profile=...)`` returns a validated :class:`RubricSpec`:

- ``profile="synthesis"`` (default) — the whole rubric; our merged, provenance-tracked standard.
- a **source id** present in the rubric's ``citations`` table (e.g. ``"schad2021"``) — a
  *source-pure* profile: only the steps and thresholds grounded in that source, all else filtered
  (plans 02 §2.3, PR-#1 point 3). A step survives if it cites the source; within a surviving step,
  thresholds not attributed to the source are dropped.

A profile that names a source the rubric doesn't know raises :class:`RubricProfileError`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from veribayes.core.rubric.models import RubricSpec, RubricStep

# Repo-root ``rubric/steps.yaml`` (this file lives at veribayes/core/rubric/loader.py).
DEFAULT_RUBRIC_PATH = Path(__file__).resolve().parents[3] / "rubric" / "steps.yaml"

SYNTHESIS = "synthesis"


class RubricProfileError(ValueError):
    """Raised when a requested rubric profile names a source not present in the rubric."""


def load_rubric(
    path: str | Path | None = None,
    *,
    profile: str = SYNTHESIS,
) -> RubricSpec:
    raw_path = Path(path) if path is not None else DEFAULT_RUBRIC_PATH
    data: dict[str, Any] = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    spec = RubricSpec.model_validate(data)
    spec = spec.model_copy(update={"profile": SYNTHESIS})
    if profile == SYNTHESIS:
        return spec
    return _apply_source_profile(spec, profile)


def _apply_source_profile(spec: RubricSpec, source_id: str) -> RubricSpec:
    if source_id not in spec.citations:
        raise RubricProfileError(
            f"unknown rubric profile {source_id!r}; "
            f"known source ids: {sorted(spec.citations)}"
        )
    filtered_steps: list[RubricStep] = []
    for step in spec.steps:
        if source_id not in step.citations:
            continue  # this step is not grounded in the named source -> excluded from the profile
        kept_thresholds = {
            name: t for name, t in step.thresholds.items() if t.source == source_id
        }
        filtered_steps.append(
            step.model_copy(update={"thresholds": kept_thresholds})
        )
    return spec.model_copy(
        update={
            "steps": filtered_steps,
            "citations": {source_id: spec.citations[source_id]},
            "profile": source_id,
        }
    )
