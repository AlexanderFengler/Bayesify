"""Per-class step weights are rule-derived (synthesis 0.3-draft).

The loaded weight matrix must match two documented rules, so the recorded numbers can never
silently drift from them:
  R1  development classes down-weight the data-understanding steps S3/S5/S8 to 0.5.
  R2  data_analysis down-weights SBC/recovery S7 to 0.5; everything else stays 1.0.
We also pin the worked-example (self-consistency paper) quality at 0.50.
"""

from __future__ import annotations

import pytest

from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import PaperClassLabel, StepStatus
from bayesify.core.score import (
    StepCalc,
    coverage_quality_from_weighted_steps,
    step_weight,
    step_weight_for_labels,
)

_RUBRIC = load_rubric()
_SUB = _RUBRIC.scoring.sub_score
_LOW = _RUBRIC.scoring.low_confidence_threshold

_STEP_IDS = [f"S{i}" for i in range(1, 11)]
_DEVELOPMENT = frozenset(
    {
        PaperClassLabel.model_development,
        PaperClassLabel.method_development,
        PaperClassLabel.software_development,
        PaperClassLabel.numerical_analysis,
        PaperClassLabel.theoretical_analysis,
    }
)
_DATA_UNDERSTANDING = frozenset({"S3", "S5", "S8"})
_SCORED = [c for c in PaperClassLabel if c is not PaperClassLabel.review]


def _expected_weight(label: PaperClassLabel, step_id: str) -> float:
    """The 2-rule weight model the YAML must encode (R0 base 1.0; R1; R2)."""
    if label in _DEVELOPMENT and step_id in _DATA_UNDERSTANDING:
        return 0.5  # R1
    if label is PaperClassLabel.data_analysis and step_id == "S7":
        return 0.5  # R2
    return 1.0  # R0


def test_weight_matrix_matches_the_rule_set() -> None:
    # Every (scored class, step) cell of the loaded rubric equals the rule-derived weight.
    for label in _SCORED:
        for step_id in _STEP_IDS:
            assert step_weight(_RUBRIC, step_id, label) == _expected_weight(label, step_id), (
                f"{label.value}/{step_id}"
            )


def test_weights_recorded_fully_for_every_scored_class() -> None:
    # Systematic recording: each scored class carries a complete 10-step vector (no empty dicts);
    # `review` short-circuits and has no weight vector.
    weights = _RUBRIC.scoring.weights
    for label in _SCORED:
        assert set(weights.get(label.value, {})) == set(_STEP_IDS), f"{label.value} incomplete"
    assert "review" not in weights


def test_multi_label_uses_max_weight() -> None:
    # A development + applied paper takes the per-step max across its labels (mixing_rule: max):
    # a step secondary for only one of its classes is rescued to full weight.
    labels = [PaperClassLabel.method_development, PaperClassLabel.data_analysis]
    assert step_weight_for_labels(_RUBRIC, "S3", labels) == 1.0  # dev 0.5, applied 1.0 -> 1.0
    assert step_weight_for_labels(_RUBRIC, "S7", labels) == 1.0  # dev 1.0, applied 0.5 -> 1.0
    assert step_weight_for_labels(_RUBRIC, "S5", labels) == 1.0


def test_methods_paper_quality_is_half() -> None:
    # Worked example: the self-consistency paper (method_development + numerical_analysis, S6 N/A)
    # scores quality 0.50 -- S3/S8 (missing) now count half, S7/SBC (adequate) full, while S4
    # (missing) stays at full weight 1.0 and still bites. Coverage is untouched by weights.
    labels = [PaperClassLabel.method_development, PaperClassLabel.numerical_analysis]
    statuses = {
        "S1": StepStatus.adequate, "S2": StepStatus.partial, "S3": StepStatus.missing,
        "S4": StepStatus.missing, "S5": StepStatus.partial, "S6": None,
        "S7": StepStatus.adequate, "S8": StepStatus.missing, "S9": StepStatus.partial,
        "S10": StepStatus.partial,
    }
    calcs = []
    for step_id, status in statuses.items():
        if status is None:  # S6 not applicable (single model, no BF)
            calcs.append(StepCalc(False, StepStatus.not_applicable, 1.0, 1.0))
            continue
        weight = step_weight_for_labels(_RUBRIC, step_id, labels)
        calcs.append(StepCalc(True, status, weight, 0.9))  # confident (>low_conf) statuses
    cov, quality = coverage_quality_from_weighted_steps(calcs, _SUB, _LOW)
    assert quality == pytest.approx(0.5)
    assert cov is not None and cov.applicable == 9 and cov.present == 6
