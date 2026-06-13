# Validating Bayesian Inference Algorithms with Simulation-Based Calibration

**Citation:** Talts S, Betancourt M, Simpson D, Vehtari A, Gelman A (2018). Validating Bayesian Inference Algorithms with Simulation-Based Calibration. arXiv:1804.06788.
**Links:** [arXiv abstract](https://arxiv.org/abs/1804.06788); [DOI](https://doi.org/10.48550/arXiv.1804.06788)
**Type:** primary paper
**Role in the deep research:** The origin paper for simulation-based calibration (rank-uniformity checking). It grounds rubric step S7, where SBC is essential for methodological and simulation papers and is the prescribed tool when sampler self-diagnostics are insufficient. The run fetched it via a ResearchGate mirror; the arXiv original is cited here.

## What it is
The paper that introduced simulation-based calibration (SBC) in its modern rank-based form, by Talts, Betancourt, Simpson, Vehtari, and Gelman (19 pages, 13 figures; stat.ME; v1 April 2018, v2 October 2020). SBC verifies any Bayesian computational algorithm that produces posterior samples by exploiting the self-consistency of the Bayesian joint distribution. It is a foundational reference for algorithm validation in the Bayesian-workflow literature and the basis of later refinements (e.g., Modrák et al. 2023).

## Key content for VeriBayes
- Core procedure: draw parameters from the prior, simulate data from those draws, fit the posterior, and compute the rank of each prior draw among thinned posterior samples; if the algorithm is correct, ranks are uniform.
- Visual diagnostics: rank histograms whose characteristic deviation shapes (U-shaped, cup/hill, asymmetric) indicate specific failure modes — over-/under-dispersed or biased posteriors.
- Identifies not just computational errors but inconsistencies in model implementations (e.g., mismatched simulator and fitted model).
- Requires many independent fits (one per prior draw) and thinning to mitigate autocorrelation in posterior samples — a real cost that explains why SBC is reserved for cases where cheaper self-diagnostics do not suffice.
- Positions SBC explicitly as "a critical part of a robust Bayesian workflow," useful to both practitioners and algorithm developers.

## How VeriBayes uses it
- Grounds rubric S7 (rubric/steps.yaml, citation key `talts2018`): "Simulation-based calibration / algorithm validation" — essential for methodological and numerical-experiment papers, recommended for empirical ones.
- S7 "done well" = SBC (rank-uniformity) or a parameter-recovery study reported; "done poorly" = a new method/model with no recovery or calibration evidence.
- S7 may be scored N/A only for routine fits with reliable self-diagnostics (S4) on simple/standard models; this paper is the prescribed remedy when those self-diagnostics are insufficient.
- HONESTY note: the deep-research run actually fetched a ResearchGate mirror of this paper; the citation here points to the arXiv original as instructed.
