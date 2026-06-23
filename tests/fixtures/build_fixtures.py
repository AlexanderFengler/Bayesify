"""Regenerate the committed component-c fixtures (run: ``pixi run python tests/fixtures/build_fixtures.py``).

Authors a realistic empirical ``ParsedDoc`` (a hierarchical drift-diffusion paper — a mix of
software / method / diagnostic / workflow / sampler / open-science signals, with a references section
that names Stan and R-hat to prove they are excluded) and records ``run_detectors`` output over it.
The pair is the contract fixture d-screen-classify and e-assess build against, and a regression
anchor for the detector catalog. Deterministic: ``fetched_at`` is fixed and the JSON is sorted.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from bayesify.core.detectors import evidence_json, run_detectors
from bayesify.core.schema import ParsedDoc, Section, SectionKind, SourceDoc

_HERE = Path(__file__).parent
_WHEN = datetime(2026, 1, 15, 9, 30, 0)


def _section(idx: int, kind: SectionKind, title: str, text: str, page: int) -> Section:
    from bayesify.core.schema import PageSpan

    return Section(
        id=f"s{idx:02d}",
        kind=kind,
        title=title,
        text=text,
        page_spans=[PageSpan(doc_sha256="f" * 64, page_start=page, page_end=page)],
    )


def build_parsed() -> ParsedDoc:
    src = SourceDoc(
        sha256="f" * 64,
        version_label="uploaded PDF",
        source="upload",
        fetched_at=_WHEN,
    )
    sections = [
        _section(
            1, SectionKind.abstract, "Abstract",
            "We fit a hierarchical drift-diffusion model to response-time data using Bayesian "
            "inference in Stan. Posterior predictive checks reproduced the observed RT "
            "distributions, and all R-hat < 1.01.",
            1,
        ),
        _section(
            2, SectionKind.body, "Methods",
            "Each participant's drift rate was given a weakly-informative prior. We drew samples "
            "from the posterior distribution with the NUTS sampler, running 4 chains of 2000 "
            "iterations after 1000 warm-up draws with a fixed random seed. Convergence was assessed "
            "with R-hat and bulk-ESS (minimum ESS was 1,200); there were no divergent transitions.",
            3,
        ),
        _section(
            3, SectionKind.body, "Results",
            "Model comparison used PSIS-LOO and WAIC. All Pareto-k values were < 0.7, indicating "
            "reliable estimates. A prior sensitivity analysis confirmed the conclusions were robust.",
            5,
        ),
        _section(
            4, SectionKind.caption, "Figure 2",
            "Figure 2: Posterior predictive checks overlaid on the empirical RT distribution for "
            "each condition.",
            6,
        ),
        _section(
            5, SectionKind.supplement, "Supplementary Methods",
            "Analysis code is available at github.com/lab/ddm-paper and archived on Zenodo. We also "
            "report trace plots for every parameter.",
            12,
        ),
        _section(
            6, SectionKind.references, "References",
            "Carpenter B et al. Stan: A probabilistic programming language. Vehtari A et al. "
            "Practical Bayesian model evaluation using leave-one-out cross-validation; all R-hat < 1.0.",
            14,
        ),
    ]
    return ParsedDoc(source=src, sections=sections, parser="docling", parser_version="docling-2.x")


def main() -> None:
    parsed = build_parsed()
    (_HERE / "parsed" / "empirical_hddm.json").write_text(
        json.dumps(parsed.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    )
    evidence = run_detectors(parsed)
    (_HERE / "evidence" / "empirical_hddm.json").write_text(evidence_json(evidence) + "\n")
    print(f"wrote parsed (6 sections) + {len(evidence)} evidence items")


if __name__ == "__main__":
    main()
