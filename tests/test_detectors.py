"""Deterministic detectors (component c). Pure-Python — runs in the light default env.

Precision is the ship gate (c-detectors.md), so the false-positive corpus carries equal weight with
the positive snippet tables: every FP found later in real use becomes a permanent case here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from bayesify.core.detectors import (
    catalog_fingerprint,
    evidence_inventory,
    evidence_json,
    run_detectors,
)
from bayesify.core.detectors.catalog import CATALOG, DETECTOR_FAMILY
from bayesify.core.schema import EvidenceKind, ParsedDoc, Section, SectionKind, SourceDoc

_FIXTURES = Path(__file__).parent / "fixtures"

_WHEN = datetime(2026, 1, 1, 12, 0, 0)


def _parsed(*sections: tuple[SectionKind, str]) -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="t", source="upload", fetched_at=_WHEN)
    secs = [
        Section(id=f"s{i:02d}", kind=kind, title=kind.value.title(), text=text)
        for i, (kind, text) in enumerate(sections, start=1)
    ]
    return ParsedDoc(source=src, sections=secs, parser="test", parser_version="0")


def _body(text: str) -> ParsedDoc:
    return _parsed((SectionKind.body, text))


def _ids(text: str) -> set[str]:
    return {e.detector_id for e in run_detectors(_body(text))}


# --- catalog integrity ----------------------------------------------------------------------------


def test_detector_ids_unique() -> None:
    ids = [d.id for d in CATALOG]
    assert len(ids) == len(set(ids))


def test_every_detector_has_a_family_and_version() -> None:
    for d in CATALOG:
        assert DETECTOR_FAMILY[d.id] == d.family
        assert d.version


# --- positive snippet tables ----------------------------------------------------------------------

_POSITIVE = [
    # software
    ("We fit the model in Stan via cmdstanr.", "software.stan"),
    ("Models were specified with brms.", "software.brms"),
    ("Estimation used PyMC3 on the GPU.", "software.pymc"),
    ("We used NumPyro for inference.", "software.numpyro"),
    ("Sampling used TensorFlow Probability.", "software.tfp"),
    ("The model ran in JAGS.", "software.jags"),
    ("Posterior sampling used WinBUGS.", "software.bugs"),
    ("Drift-diffusion fitting used HDDM.", "software.hddm"),
    ("Response times were modelled with HSSM.", "software.hssm"),
    ("Implemented with Turing.jl in Julia.", "software.turing"),
    ("Amortized inference used BayesFlow.", "software.bayesflow"),
    # method
    ("We placed a prior distribution on the slope.", "method.prior"),
    ("We used a weakly-informative prior for sigma.", "method.prior"),
    ("The posterior distribution was summarised by its mean.", "method.posterior"),
    ("We report 95% credible intervals.", "method.credible_interval"),
    ("The HPD interval excluded zero.", "method.credible_interval"),
    ("We computed a Bayes factor of 12.", "method.bayes_factor"),
    ("Inference used MCMC with four chains.", "method.mcmc"),
    ("Sampling used the NUTS algorithm.", "method.mcmc"),
    ("We used variational inference (ADVI).", "method.variational"),
    ("Posteriors were obtained with simulation-based inference (SBI).", "method.sbi"),
    ("A conjugate prior yields an analytic posterior.", "method.analytic"),
    ("Inference used sequential Monte Carlo (SMC) samplers.", "method.smc"),
    ("We tracked the latent state with a particle filter.", "method.smc"),
    ("Parameters were estimated via approximate Bayesian computation (ABC).", "method.abc"),
    ("We used INLA for fast approximate inference.", "method.laplace_inla"),
    ("Parameters were obtained via maximum a posteriori estimation.", "method.map"),
    ("A Laplace approximation to the posterior was used.", "method.laplace_inla"),
    # workflow
    ("We performed prior predictive checks.", "workflow.prior_predictive"),
    ("Posterior predictive checks matched the data.", "workflow.posterior_predictive"),
    ("We ran PPCs for each subject.", "workflow.posterior_predictive"),
    ("A prior sensitivity analysis is reported in the appendix.", "workflow.sensitivity"),
    ("We validated with simulation-based calibration.", "workflow.sbc"),
    ("Parameter recovery confirmed identifiability.", "workflow.recovery"),
    # diagnostics (mention)
    ("We inspected trace plots for each parameter.", "diag.trace_plot"),
    ("Rank plots indicated good mixing.", "diag.rank_plot"),
    ("Model comparison used WAIC and PSIS-LOO.", "diag.loo_waic"),
    ("We checked the max treedepth.", "diag.treedepth"),
    ("The E-BFMI was acceptable.", "diag.bfmi"),
    ("We report the MCSE for each estimate.", "diag.mcse"),
    # open science
    ("All data are available on the OSF.", "open.osf"),
    ("Analysis code is available at github.com/lab/repo.", "open.github"),
    ("Code and data are archived on Zenodo.", "open.zenodo"),
    ("A data availability statement is included.", "open.data"),
    ("The analysis code is available online.", "open.code"),
    # sampler
    ("We ran 4 chains.", "sampler.chains"),
    ("Each chain had 2000 iterations.", "sampler.iterations"),
    ("We discarded 1000 warm-up draws.", "sampler.warmup"),
    ("Results used a fixed random seed.", "sampler.seed"),
]


@pytest.mark.parametrize("snippet,expected_id", _POSITIVE)
def test_positive_snippets(snippet: str, expected_id: str) -> None:
    assert expected_id in _ids(snippet), f"{expected_id!r} should fire on {snippet!r}"


# --- false-positive corpus (must yield ZERO hits for the named family) ----------------------------

_FALSE_POSITIVES = [
    ("We report the standard deviation of the residuals.", "software.stan"),
    ("The first author is at Stanford University.", "software.stan"),
    ("For instance, the effect was small.", "software.stan"),
    ("We will debug the simulation code.", "software.bugs"),
    ("The estimate of rhattan was excluded.", "diag.rhat"),
    ("We drove through Manhattan to the lab.", "diag.rhat"),
    ("We assess the model fit qualitatively.", "diag.ess"),
    ("The process converged after ten steps.", "diag.ess"),
    ("Participants cracked nuts during the task.", "method.mcmc"),
    ("The looser threshold was preferred.", "diag.loo_waic"),
    ("The sbi scores stayed below threshold.", "method.sbi"),  # lowercase, case-sensitive SBI
    ("We validated with simulation-based calibration.", "method.sbi"),  # SBC != SBI
    (
        "The ABCD study recruited thousands of children.",
        "method.abc",
    ),  # ABCD != ABC (word boundary)
    ("The smc pathway was upregulated.", "method.smc"),  # lowercase, case-sensitive SMC
    ("Consult the map of cortical regions.", "method.map"),  # lowercase "map" != MAP
]


@pytest.mark.parametrize("snippet,forbidden_id", _FALSE_POSITIVES)
def test_false_positive_corpus(snippet: str, forbidden_id: str) -> None:
    assert forbidden_id not in _ids(snippet), f"{forbidden_id!r} wrongly fired on {snippet!r}"


# --- numeric value extraction ---------------------------------------------------------------------


def _one(text: str, detector_id: str):
    hits = [e for e in run_detectors(_body(text)) if e.detector_id == detector_id]
    assert hits, f"expected a {detector_id} hit in {text!r}"
    return hits[0]


def test_rhat_value_and_comparator() -> None:
    e = _one("All parameters had R-hat < 1.01.", "diag.rhat")
    assert e.kind is EvidenceKind.diagnostic_value
    assert e.value == {"metric": "rhat", "op": "<", "value": 1.01}


def test_rhat_equals() -> None:
    e = _one("The maximum Rhat = 1.002 across chains.", "diag.rhat")
    assert e.value == {"metric": "rhat", "op": "=", "value": 1.002}


def test_ess_value() -> None:
    e = _one("The bulk-ESS was 1,500 for all parameters.", "diag.ess")
    assert e.value == {"metric": "ess", "op": "=", "value": 1500.0}


def test_divergence_count() -> None:
    assert _one("There were 12 divergent transitions.", "diag.divergences").value == {
        "metric": "divergences",
        "count": 12,
    }


def test_no_divergences_is_zero() -> None:
    assert _one("There were no divergent transitions.", "diag.divergences").value == {
        "metric": "divergences",
        "count": 0,
    }


def test_bare_divergence_mention_has_no_count() -> None:
    e = _one("We monitored divergences throughout sampling.", "diag.divergences")
    assert e.kind is EvidenceKind.diagnostic_mention
    assert e.value is None


def test_pareto_k_threshold() -> None:
    assert _one("All Pareto-k values were < 0.7.", "diag.pareto_k").value == {
        "metric": "pareto_k",
        "op": "<",
        "value": 0.7,
    }


def test_sampler_counts() -> None:
    p = _body("We ran 4 chains of 2000 iterations with 1000 warmup samples.")
    by_id = {e.detector_id: e.value for e in run_detectors(p)}
    assert by_id["sampler.chains"] == {"metric": "chains", "count": 4}
    assert by_id["sampler.iterations"] == {"metric": "iterations", "count": 2000}
    assert by_id["sampler.warmup"] == {"metric": "warmup", "count": 1000}


def test_rhat_mention_without_number_degrades_to_mention() -> None:
    e = _one("We confirmed convergence using R-hat.", "diag.rhat")
    assert e.kind is EvidenceKind.diagnostic_mention
    assert e.value is None


# --- span guarantees, ordering, dedup -------------------------------------------------------------


def test_quote_is_verbatim_substring_of_section() -> None:
    p = _parsed(
        (SectionKind.abstract, "We fit a model in Stan and report R-hat < 1.01."),
        (SectionKind.body, "Posterior predictive checks used 4 chains."),
    )
    by_section = {s.id: s.text for s in p.sections}
    for e in run_detectors(p):
        assert e.span.quote in by_section[e.span.section_id]


def test_canonical_ordering_by_section_then_offset() -> None:
    p = _parsed(
        (SectionKind.abstract, "We used Stan."),
        (SectionKind.body, "We report R-hat and ESS = 800."),
    )
    order = [(e.span.section_id, e.span.quote) for e in run_detectors(p)]
    sections = [sid for sid, _ in order]
    assert sections == sorted(sections)  # section order preserved (s01 before s02)


def test_repeated_mention_collapses() -> None:
    p = _body("The posterior distribution is wide. Later, the posterior distribution narrows.")
    hits = [e for e in run_detectors(p) if e.detector_id == "method.posterior"]
    assert len(hits) == 1


def test_distinct_values_are_kept() -> None:
    p = _body("Chain one had R-hat = 1.01 while chain two had R-hat = 1.05.")
    values = sorted(e.value["value"] for e in run_detectors(p) if e.detector_id == "diag.rhat")
    assert values == [1.01, 1.05]


# --- references are skipped -----------------------------------------------------------------------


def test_references_section_is_skipped() -> None:
    p = _parsed(
        (SectionKind.body, "We describe the model."),
        (SectionKind.references, "Carpenter et al. Stan: a probabilistic language. R-hat = 1.0."),
    )
    ids = {e.detector_id for e in run_detectors(p)}
    assert "software.stan" not in ids
    assert "diag.rhat" not in ids


def test_supplement_is_scanned() -> None:
    p = _parsed((SectionKind.supplement, "Supplementary: we ran 4 chains in Stan."))
    ids = {e.detector_id for e in run_detectors(p)}
    assert {"software.stan", "sampler.chains"} <= ids


# --- determinism ----------------------------------------------------------------------------------


def test_determinism_byte_identical() -> None:
    p = _parsed(
        (SectionKind.abstract, "We fit a hierarchical model in Stan with NUTS."),
        (SectionKind.body, "4 chains, 2000 iterations, all R-hat < 1.01, no divergences."),
    )
    assert evidence_json(run_detectors(p)) == evidence_json(run_detectors(p))


def test_catalog_fingerprint_is_stable_and_nonempty() -> None:
    assert catalog_fingerprint() == catalog_fingerprint()
    assert "software.stan" in catalog_fingerprint()


# --- inventory (the F3 local-only view) -----------------------------------------------------------


def test_inventory_found_not_detected_and_where_looked() -> None:
    p = _parsed(
        (SectionKind.abstract, "We fit the model in Stan."),
        (SectionKind.body, "We report R-hat < 1.01 and ran 4 chains."),
        (SectionKind.supplement, "Extra detail on priors."),
        (SectionKind.references, "Gelman et al. Bayesian Workflow. Stan reference."),
    )
    inv = evidence_inventory(p, run_detectors(p))

    families = {f.family: f for f in inv.families}
    sw_found = {h.detector_id for h in families["software"].found}
    assert "software.stan" in sw_found
    # a catalog entry with zero hits is reported as not-detected, not as "not done"
    assert "software.pymc" in families["software"].not_detected
    assert "workflow.sbc" in families["workflow"].not_detected

    # where-looked enumerates scanned sections (incl. supplement) and excludes references
    scanned = {s.kind for s in inv.where_looked}
    assert SectionKind.references not in scanned
    assert SectionKind.supplement in scanned
    assert all(s.kind is SectionKind.references for s in inv.skipped)
    assert inv.n_hits == len(run_detectors(p))


def test_inventory_hit_carries_section_title_and_page() -> None:
    p = _parsed((SectionKind.body, "We fit the model in Stan."))
    inv = evidence_inventory(p, run_detectors(p))
    hit = next(h for f in inv.families for h in f.found if h.detector_id == "software.stan")
    assert hit.section_title == "Body"
    assert hit.quote in "We fit the model in Stan."


# --- golden fixture (the contract d-screen-classify and e-assess build against) -------------------


def _load_parsed() -> ParsedDoc:
    return ParsedDoc.model_validate_json(
        (_FIXTURES / "parsed" / "empirical_hddm.json").read_text(encoding="utf-8")
    )


def test_golden_evidence_fixture_matches() -> None:
    """The committed ``Evidence[]`` must reproduce from the committed ``ParsedDoc``. A catalog
    change that shifts output is caught here; regenerate via ``build_fixtures.py`` on purpose."""
    expected = (_FIXTURES / "evidence" / "empirical_hddm.json").read_text(encoding="utf-8")
    assert evidence_json(run_detectors(_load_parsed())) + "\n" == expected


def test_golden_fixture_excludes_references_and_is_relevant() -> None:
    parsed = _load_parsed()
    evidence = run_detectors(parsed)
    # nothing detected inside the references section (it names Stan + R-hat, a precision trap)
    ref_ids = {s.id for s in parsed.sections if s.kind is SectionKind.references}
    assert not any(e.span.section_id in ref_ids for e in evidence)
    # the method-mention floor fires, so d's relevance gate sees a Bayesian paper
    assert any(e.kind is EvidenceKind.method_mention for e in evidence)
