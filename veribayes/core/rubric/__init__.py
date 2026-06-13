"""Rubric loading and compilation.

``rubric/steps.yaml`` is the single source of truth (B2). This package loads it into typed models
(``models.py``) and selects a **rubric profile** (``loader.py``): ``synthesis`` (the whole file, the
default that we develop into the gold standard) or a source-pure profile such as ``schad2021``,
compiled by filtering steps/thresholds on their ``citations`` provenance (PR-#1 decision; plans 02
§2.3).

This is the M1 half of gate **G5**: it pins the YAML *shape* so the loader isn't finalized against
an undefined schema. The full scoring block (sub-score map, per-class weights, low-confidence
threshold, mixing rule) is authored before M5 — the models below already reserve a place for it
(``RubricSpec.scoring``), defaulting to ``None`` until then.
"""

from veribayes.core.rubric.loader import (
    DEFAULT_RUBRIC_PATH,
    RubricProfileError,
    load_rubric,
)
from veribayes.core.rubric.models import RubricSpec, RubricStep, ThresholdEntry

__all__ = [
    "DEFAULT_RUBRIC_PATH",
    "RubricProfileError",
    "RubricSpec",
    "RubricStep",
    "ThresholdEntry",
    "load_rubric",
]
