"""Record downstream screen/classify OUTPUT fixtures (run: pixi run python tests/fixtures/build_screen_outputs.py).

These are the contract M5's e-assess / f-score build against: a representative post-screen state
(Relevance + PaperClass) plus a short-circuit (relevance 'no' → classify skipped, scores null). The
evidence_refs index into the recorded Evidence[] of the empirical_hddm golden fixture
(evidence/empirical_hddm.json), so they resolve against real detector output (the d DoD).
"""

from __future__ import annotations

import json
from pathlib import Path

from veribayes.core.schema import PaperClass, PaperClassLabel, Relevance, RelevanceLabel

_HERE = Path(__file__).parent


def main() -> None:
    relevant = {
        "relevance": Relevance(
            label=RelevanceLabel.yes,
            confidence=0.96,
            rationale="Fits a hierarchical Bayesian (HDDM) model in Stan with MCMC; reports R-hat, "
            "ESS, divergences, and posterior predictive checks — squarely a Bayesian-workflow paper.",
            evidence_refs=[0, 3, 13],
        ).model_dump(mode="json"),
        "paper_class": PaperClass(
            primary=PaperClassLabel.empirical,
            confidence=0.9,
            rationale="Fits a Bayesian model to real reaction-time data to draw substantive "
            "conclusions; no simulated-truth or methods-contribution framing.",
            evidence_refs=[0],
        ).model_dump(mode="json"),
    }
    short_circuit = {
        "relevance": Relevance(
            label=RelevanceLabel.no,
            confidence=0.95,
            rationale="Searched for priors, posteriors, Bayesian software, MCMC/VI, and convergence "
            "diagnostics; none were found. The analysis is frequentist (OLS, p-values, CIs).",
            evidence_refs=[],
        ).model_dump(mode="json"),
        "paper_class": None,  # classify is skipped on a short-circuit
    }
    out = _HERE / "screen"
    (out / "empirical_hddm.screen.json").write_text(
        json.dumps(relevant, indent=2, sort_keys=True) + "\n"
    )
    (out / "nonbayesian.screen.json").write_text(
        json.dumps(short_circuit, indent=2, sort_keys=True) + "\n"
    )
    print("wrote 2 downstream screen/classify output fixtures")


if __name__ == "__main__":
    main()
