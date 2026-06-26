"""The recorded screen/classify OUTPUT fixtures M5 (e-assess / f-score) builds against.

Guards that the committed Relevance/PaperClass outputs are schema-valid and that their evidence_refs
resolve against the recorded Evidence[] of the empirical_hddm golden fixture (the d DoD).
"""

from __future__ import annotations

import json
from pathlib import Path

from bayesify.core.schema import PaperClass, Relevance, RelevanceLabel

_FIX = Path(__file__).parent / "fixtures"
_SCREEN = _FIX / "screen"
_EVIDENCE = json.loads((_FIX / "evidence" / "empirical_hddm.json").read_text(encoding="utf-8"))


def test_relevant_output_is_valid_and_refs_resolve() -> None:
    data = json.loads((_SCREEN / "empirical_hddm.screen.json").read_text(encoding="utf-8"))
    rel = Relevance.model_validate(data["relevance"])
    cls = PaperClass.model_validate(data["paper_class"])
    assert rel.label is RelevanceLabel.yes and rel.evidence_refs
    # refs index into the recorded Evidence[] for this paper
    assert all(0 <= i < len(_EVIDENCE) for i in rel.evidence_refs)
    assert all(0 <= i < len(_EVIDENCE) for i in cls.evidence_refs)


def test_short_circuit_output_is_valid() -> None:
    data = json.loads((_SCREEN / "nonbayesian.screen.json").read_text(encoding="utf-8"))
    rel = Relevance.model_validate(data["relevance"])
    assert rel.label is RelevanceLabel.no  # 'no' may carry empty refs
    assert data["paper_class"] is None  # classify skipped on short-circuit
