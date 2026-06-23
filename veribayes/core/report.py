"""Report-derived views over a ``ScoredResult`` (component g, M6) — pure, server-side.

The SPA stays dumb: it renders what this computes. Two helpers:
- ``fix_list`` — the D2 prioritised fix-list across all steps, ordered **severity → step weight →
  ease** (a linter, not a nag), each item carrying the verified score-impact of fixing it.
- ``uncited_praise`` — the D3 lint: ``did_well`` entries that cite no evidence (a bug — praise must
  be specific and evidence-cited).

Neither mutates the ``ScoredResult`` (the Phase-3 contract): both are derived at serve time.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from veribayes.core.schema import Ease, ScoredResult, Severity

_SEVERITY_RANK = {Severity.error: 0, Severity.warning: 1, Severity.info: 2}
_EASE_RANK = {Ease.low: 0, Ease.medium: 1, Ease.high: 2}  # easy wins first
# A did_well entry "cites evidence" if it points at the paper: a section/page/figure/table marker
# or a quoted span. Generic praise (none of these) is flagged (D3).
_CITED = re.compile(r"§|\bp\.\s*\d|\bpage\b|\bfig\b|\btable\b|\bsec\b|[\"“”]", re.IGNORECASE)


class FixItem(BaseModel):
    step_id: str
    severity: Severity
    text: str
    how_to: str
    ease: Ease
    weight: float
    coverage_delta: float  # verified gain from bringing this step to adequate (0 if present)
    quality_delta: float


def fix_list(result: ScoredResult) -> list[FixItem]:
    """All suggestions across applicable steps, ranked severity → step weight (desc) → ease (easy
    first). Each carries its step's score-impact so the UI can show how much fixing it would lift
    coverage."""
    weights = {p.step_id: p.weight for p in result.profile.steps} if result.profile else {}
    impacts = {i.step_id: i for i in result.score_impacts}
    items: list[FixItem] = []
    for assessment in result.step_assessments:
        impact = impacts.get(assessment.step_id)
        for suggestion in assessment.suggestions:
            items.append(
                FixItem(
                    step_id=assessment.step_id,
                    severity=suggestion.severity,
                    text=suggestion.text,
                    how_to=suggestion.how_to,
                    ease=suggestion.ease,
                    weight=weights.get(assessment.step_id, 1.0),
                    coverage_delta=impact.coverage_delta if impact else 0.0,
                    quality_delta=impact.quality_delta if impact else 0.0,
                )
            )
    items.sort(
        key=lambda f: (_SEVERITY_RANK[f.severity], -f.weight, _EASE_RANK[f.ease], f.step_id)
    )
    return items


def uncited_praise(result: ScoredResult) -> list[tuple[str, str]]:
    """``(step_id, text)`` for every ``did_well`` entry that cites no evidence — the D3 lint. Empty
    is healthy; a non-empty result is a praise-quality bug."""
    return [
        (a.step_id, text)
        for a in result.step_assessments
        for text in a.did_well
        if not _CITED.search(text)
    ]
