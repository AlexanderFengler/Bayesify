"""Validation (component h) — the human side of report-to-report validation.

VeriBayes validates by comparing two reports of the same paper: the engine's ``ScoredResult`` and a
``HumanReport`` a blind expert authored by walking the same rubric. This package holds the
human-side contracts (here) and, later, the pure metric layer + harness CLI. It is deliberately
decoupled from the engine output shape — see ``human_report`` for why that asymmetry matters.
"""

from veribayes.core.validation.consensus import (
    ConsensusResult,
    assemble_human_report,
    consensus_from_ratings,
)
from veribayes.core.validation.human_report import (
    GoldOrigin,
    GoldProvenance,
    GoldTier,
    HumanReport,
    MissingSubtag,
    RaterRelationship,
    Rating,
    StepDefect,
    StepDefectKind,
    StepRating,
)
from veribayes.core.validation.report import (
    ValidationReport,
    build_report,
    to_calibration_payload,
    to_markdown,
)

__all__ = [
    "ConsensusResult",
    "GoldOrigin",
    "GoldProvenance",
    "GoldTier",
    "HumanReport",
    "MissingSubtag",
    "Rating",
    "RaterRelationship",
    "StepDefect",
    "StepDefectKind",
    "StepRating",
    "ValidationReport",
    "assemble_human_report",
    "build_report",
    "consensus_from_ratings",
    "to_calibration_payload",
    "to_markdown",
]
