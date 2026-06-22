"""Live screen/classify accuracy gates over the labeled fixture set (M4 slice 4).

Makes real, paid cheap-model calls, so it is **opt-in**: it skips unless both ANTHROPIC_API_KEY is
set and BAYESIFY_RUN_EVAL=1 (the `pixi run eval` task sets the latter). It never runs during
`pixi run check`. These thresholds gate development only; the release measurement is the validation
protocol (validation/protocol.md §3, M7) and the numbers here are never quoted publicly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bayesify.core.detectors import run_detectors
from bayesify.core.llm import AnthropicClient
from bayesify.core.pipeline import screen_and_classify
from bayesify.core.schema import ParsedDoc, RelevanceLabel

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("BAYESIFY_RUN_EVAL") == "1"),
    reason="live eval — set ANTHROPIC_API_KEY and run via `pixi run eval`",
)

_CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "screen" / "cases.json").read_text()
)


def test_screen_classify_ship_gates() -> None:
    client = AnthropicClient()
    rows = []
    for case in _CASES:
        parsed = ParsedDoc.model_validate(case["parsed"])
        evidence = run_detectors(parsed)
        relevance, paper_class, _ = screen_and_classify(parsed, evidence, client=client)
        rows.append((case, relevance, paper_class))

    relevant = [r for r in rows if r[0]["expect_relevance"] in ("yes", "partial")]
    decoys = [r for r in rows if r[0]["expect_relevance"] == "no"]
    classed = [r for r in rows if r[0]["expect_primary"]]

    n_sens = sum(1 for _, rel, _ in relevant if rel.label is not RelevanceLabel.no)
    n_spec = sum(1 for _, rel, _ in decoys if rel.label is RelevanceLabel.no)
    n_acc = sum(1 for c, _, cls in classed if cls and cls.primary.value == c["expect_primary"])
    sensitivity = n_sens / len(relevant)
    specificity = n_spec / len(decoys)
    class_acc = n_acc / len(classed)

    # Surfaced for the dev audit; not a public claim.
    print(f"\nsens={sensitivity:.2f} spec={specificity:.2f} class_acc={class_acc:.2f}")
    for case, rel, cls in rows:
        got_class = cls.primary.value if cls else "-"
        print(f"  {case['id']:6} expect={case['expect_relevance']}/{case['expect_primary']}"
              f"  got={rel.label.value}/{got_class}")

    assert sensitivity >= 0.95, f"relevance sensitivity {sensitivity:.2f} < 0.95"
    assert specificity >= 0.80, f"decoy specificity {specificity:.2f} < 0.80"
    assert class_acc >= 0.80, f"primary-class accuracy {class_acc:.2f} < 0.80"
