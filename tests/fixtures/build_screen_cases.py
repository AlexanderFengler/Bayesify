"""Regenerate the labeled screen/classify fixture set.

Run: pixi run python tests/fixtures/build_screen_cases.py

A development-only set of synthetic ParsedDocs + expected labels, disjoint from the validation
gold set (validation/protocol.md). The deterministic test (test_screen_fixtures.py) and the live
eval harness (tests/eval/) both load cases.json; detector Evidence[] is computed from the text at
load time via run_detectors, so the fixtures stay tied to the real detector catalog.

Coverage (d-screen-classify.md test plan): >=9 relevant spanning the core graded labels with at
least one multi-label case, >=3 partial/borderline, >=4 non-Bayesian decoys (incl. one whose only
"Bayes" mention is in the references).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bayesify.core.schema import ParsedDoc, Section, SectionKind, SourceDoc

_OUT = Path(__file__).parent / "screen" / "cases.json"
_WHEN = datetime(2026, 1, 10, 12, 0, 0)


def _doc(abstract: str, body: str, references: str | None = None) -> ParsedDoc:
    src = SourceDoc(sha256="0" * 64, version_label="fixture", source="upload", fetched_at=_WHEN)
    secs = [
        Section(id="s01", kind=SectionKind.abstract, title="Abstract", text=abstract),
        Section(id="s02", kind=SectionKind.body, title="Methods", text=body),
    ]
    if references:
        secs.append(
            Section(id="s03", kind=SectionKind.references, title="References", text=references)
        )
    return ParsedDoc(source=src, sections=secs, parser="fixture", parser_version="0")


# (id, abstract, body, references, expect_relevance, expect_labels, note)
_CASES = [
    # Relevant: data analysis.
    (
        "emp1",
        "We fit a hierarchical Bayesian drift-diffusion model to reaction-time data.",
        "Inference used Stan with 4 chains of 2000 iterations; all R-hat < 1.01 and "
        "posterior predictive checks reproduced the data.",
        None,
        "yes",
        ["data_analysis"],
        "clear empirical Bayesian fit",
    ),
    (
        "emp2",
        "We estimate a Bayesian regression of crop yield on rainfall using PyMC.",
        "We report posterior means with 95% credible intervals; weakly-informative priors were "
        "used throughout.",
        None,
        "yes",
        ["data_analysis"],
        "empirical, software+method",
    ),
    (
        "emp3",
        "A Bayesian hierarchical model of clinical outcomes fit with brms.",
        "We summarise the posterior distribution and report bulk-ESS and R-hat for every "
        "parameter.",
        None,
        "yes",
        ["data_analysis"],
        "empirical, diagnostics",
    ),
    # Relevant: numerical analysis.
    (
        "num1",
        "We benchmark NUTS against variational inference on simulated data with known parameters.",
        "Parameter recovery was assessed across 100 simulated datasets; R-hat and divergent "
        "transitions were monitored.",
        None,
        "yes",
        ["numerical_analysis"],
        "method comparison on simulated data",
    ),
    (
        "num2",
        "We evaluate a new sampler implemented in Stan on synthetic benchmarks.",
        "We measure effective sample size per gradient evaluation and the number of divergent "
        "transitions; no real data are used.",
        None,
        "yes",
        ["method_development", "numerical_analysis"],
        "sampler benchmark, software+diagnostics",
    ),
    (
        "num3",
        "We validate a posterior approximation via simulation-based calibration in NumPyro.",
        "Across 1000 simulated datasets we check calibration of the posterior; rank plots are "
        "reported.",
        None,
        "yes",
        ["numerical_analysis"],
        "SBC validation study",
    ),
    # Relevant: method/theory development, including mixed papers.
    (
        "meth1",
        "We propose a new weakly-informative prior for hierarchical variance parameters.",
        "We derive properties of the resulting posterior distribution and study posterior "
        "contraction.",
        None,
        "yes",
        ["method_development", "theoretical_analysis"],
        "analytic methodological - method family only",
    ),
    (
        "meth2",
        "We introduce a new MCMC algorithm and a convergence diagnostic.",
        "We implement it in Stan and demonstrate improved effective sample size and lower R-hat "
        "on standard models.",
        None,
        "yes",
        ["method_development", "numerical_analysis"],
        "new algorithm + diagnostics",
    ),
    (
        "meth3",
        "We develop a new prior for spatial models and apply it to real census data.",
        "Using PyMC we fit the model; posterior predictive checks and 95% credible intervals are "
        "reported for the census application.",
        None,
        "yes",
        ["method_development", "data_analysis"],
        "mixed: method contribution + real-data application",
    ),
    # Partial / borderline.
    (
        "part1",
        "A primarily frequentist ANOVA study of memory performance.",
        "As a supplementary analysis we additionally report a Bayes factor for the main contrast.",
        None,
        "partial",
        [],
        "lone Bayes factor in a frequentist paper",
    ),
    (
        "part2",
        "We analyse survey data with frequentist mixed-effects models.",
        "As a robustness check, we refit the key model in a Bayesian framework with a "
        "weakly-informative prior.",
        None,
        "partial",
        [],
        "one Bayesian robustness check",
    ),
    (
        "part3",
        "Main analyses are frequentist regressions of housing prices.",
        "A single Bayesian logistic regression with priors on the coefficients appears in the "
        "appendix.",
        None,
        "partial",
        [],
        "peripheral Bayesian sub-analysis",
    ),
    # Non-Bayesian decoys.
    (
        "dec1",
        "We estimate the effect of schooling on wages using ordinary least squares.",
        "We report p-values and 95% confidence intervals. Code at github.com/lab/wages.",
        None,
        "no",
        [],
        "frequentist OLS; only open-science hit",
    ),
    (
        "dec2",
        "A randomized controlled trial of a new drug analysed with mixed-effects models.",
        "Significance was assessed at alpha = 0.05 with Bonferroni correction.",
        "Gelman A, Carlin J. Bayesian Data Analysis. CRC Press, 2013.",
        "no",
        [],
        "decoy: 'Bayes' only in the reference list",
    ),
    (
        "dec3",
        "We train a convolutional neural network for image classification.",
        "The model was optimised with stochastic gradient descent; test accuracy reached 92 percent.",
        None,
        "no",
        [],
        "ML paper, no Bayesian statistics",
    ),
    (
        "dec4",
        "We examine the association between sleep and academic performance.",
        "Pearson correlation coefficients and two-sample t-tests were computed across cohorts.",
        None,
        "no",
        [],
        "classical statistics, no Bayesian content",
    ),
]


def main() -> None:
    out = []
    for cid, abstract, body, refs, rel, labels, note in _CASES:
        out.append(
            {
                "id": cid,
                "parsed": _doc(abstract, body, refs).model_dump(mode="json"),
                "expect_relevance": rel,
                "expect_labels": labels,
                "note": note,
            }
        )
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    rel = sum(1 for c in out if c["expect_relevance"] == "yes")
    part = sum(1 for c in out if c["expect_relevance"] == "partial")
    dec = sum(1 for c in out if c["expect_relevance"] == "no")
    print(f"wrote {len(out)} cases -> {_OUT}  (relevant={rel}, partial={part}, decoy={dec})")


if __name__ == "__main__":
    main()
