"""Live screen/classify accuracy gates over the labeled fixture set (M4 slice 4).

Makes real, paid cheap-model calls, so it is **opt-in**: it skips unless BAYESIFY_RUN_EVAL=1 (the
`pixi run eval` task sets it) and an LLM backend is configured. It runs under whatever backend the
app uses (agent-sdk / anthropic / openai) via `make_llm_client()`, loading `bayesify.env` for the
backend + model pins. It never runs during `pixi run check`. These thresholds gate development only;
the release measurement is the validation protocol (validation/protocol.md §3, M7) and the numbers
here are never quoted publicly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bayesify.api.env import load_env_file
from bayesify.core.detectors import run_detectors
from bayesify.core.pipeline import screen_and_classify
from bayesify.core.schema import ParsedDoc, RelevanceLabel
from bayesify.llm import config as llm_config
from bayesify.llm import make_llm_client

# Only when opted in (BAYESIFY_RUN_EVAL=1) load bayesify.env for the backend + model pins, so the
# run uses the app's configured backend. Guarded so `pixi run check` never pollutes the test env;
# existing process env always wins, so CI can still point it at an API backend.
if os.environ.get("BAYESIFY_RUN_EVAL") == "1":
    load_env_file()

pytestmark = pytest.mark.skipif(
    not (os.environ.get("BAYESIFY_RUN_EVAL") == "1" and llm_config.llm_backend() != "none"),
    reason="live eval — run via `pixi run eval` with an LLM backend configured (see bayesify.env)",
)

_CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "screen" / "cases.json").read_text(encoding="utf-8")
)


def _run_case(client, case: dict):
    parsed = ParsedDoc.model_validate(case["parsed"])
    evidence = run_detectors(parsed)
    relevance, paper_class, _ = screen_and_classify(parsed, evidence, client=client)
    return case, relevance, paper_class


def test_screen_classify_ship_gates() -> None:
    client = make_llm_client()
    # Cases are independent, so fan out — on the agent-sdk backend each call pays ~10s of CLI
    # session startup, which made the sequential loop take 10-15 min; parallel it is ~2. The client
    # is shared safely (same pattern as the app's parallel assess fan-out).
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda c: _run_case(client, c), _CASES))

    relevant = [r for r in rows if r[0]["expect_relevance"] in ("yes", "partial")]
    decoys = [r for r in rows if r[0]["expect_relevance"] == "no"]
    classed = [r for r in rows if r[0]["expect_labels"]]

    n_sens = sum(1 for _, rel, _ in relevant if rel.label is not RelevanceLabel.no)
    n_spec = sum(1 for _, rel, _ in decoys if rel.label is RelevanceLabel.no)
    n_acc = sum(
        1
        for c, _, cls in classed
        if cls and {label.value for label in cls.labels} == set(c["expect_labels"])
    )
    sensitivity = n_sens / len(relevant)
    specificity = n_spec / len(decoys)
    class_acc = n_acc / len(classed)

    # Surfaced for the dev audit; not a public claim.
    print(f"\nsens={sensitivity:.2f} spec={specificity:.2f} label_set_acc={class_acc:.2f}")
    for case, rel, cls in rows:
        got_class = ",".join(label.value for label in cls.labels) if cls else "-"
        expect_class = ",".join(case["expect_labels"]) or "-"
        got_sw = ",".join(cls.software_used) if cls else "-"
        print(
            f"  {case['id']:6} expect={case['expect_relevance']}/{expect_class}"
            f"  got={rel.label.value}/{got_class}  sw={got_sw}"
        )

    # Strict guards, COLLECTED rather than assert-per-case so one borderline flap never masks the
    # other guards' verdicts (each live run is expensive; a run should report everything it saw).
    strict_failures: list[str] = []

    # Over-emission guard (#75): cases flagged `strict_labels` must match their EXACT expected label
    # set individually — the 0.80 aggregate below would otherwise absorb a spurious extra label.
    for case, _, cls in rows:
        if case.get("strict_labels"):
            got = {label.value for label in cls.labels} if cls else set()
            if got != set(case["expect_labels"]):
                strict_failures.append(
                    f"{case['id']}: labels {sorted(got)}, expected {sorted(case['expect_labels'])}"
                )

    # Software over-labeling guard: cases with `expect_software` must match the EXACT set — the
    # grounded software channel (quote-verified, own-workflow scope) must neither pad nor drop.
    for case, _, cls in rows:
        if case.get("expect_software") is not None and cls is not None:
            got_sw = set(cls.software_used)
            if got_sw != set(case["expect_software"]):
                strict_failures.append(
                    f"{case['id']}: software {sorted(got_sw)}, "
                    f"expected {sorted(case['expect_software'])}"
                )

    assert not strict_failures, "strict guards failed:\n  " + "\n  ".join(strict_failures)

    assert sensitivity >= 0.95, f"relevance sensitivity {sensitivity:.2f} < 0.95"
    assert specificity >= 0.80, f"decoy specificity {specificity:.2f} < 0.80"
    assert class_acc >= 0.80, f"label-set accuracy {class_acc:.2f} < 0.80"
