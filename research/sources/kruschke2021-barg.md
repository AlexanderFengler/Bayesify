# Bayesian Analysis Reporting Guidelines

**Citation:** Kruschke JK (2021). Bayesian Analysis Reporting Guidelines. Nature Human Behaviour 5(10):1282-1291. doi:10.1038/s41562-021-01177-7. Open access (CC-BY 4.0); also available via the author companion site and PMC8526359.
**Links:** [Nature Human Behaviour article](https://www.nature.com/articles/s41562-021-01177-7); [DOI](https://doi.org/10.1038/s41562-021-01177-7); [author companion site](https://kruschke.github.io/johnkruschke/BARG.html); [PMC8526359](https://pmc.ncbi.nlm.nih.gov/articles/PMC8526359/)
**Type:** primary paper (plus author companion site)
**Role in the deep research:** The most directly checklist-shaped reporting guideline used in the run; grounded 5+ verified claims, all passing adversarial verification 3-0. Its MCMC-diagnostic requirements are the VERIFIED thresholds behind rubric step S4, and it grounds rubric steps S2, S4, S9, and S10.

## What it is
A consensus-style reporting checklist for Bayesian analyses, written by John K. Kruschke and published as open-access guidance in Nature Human Behaviour (2021). It distills what a published Bayesian analysis must report so reviewers and readers can assess and reproduce it, and is the closest thing the field has to a CONSORT-style checklist for Bayesian workflows. The author maintains a companion site with the checklist and a worked supplementary example (OSF).

## Key content for VeriBayes
- Structure: a preamble (A. Why Bayesian; B. Goals of analysis) followed by six ordered steps, each with lettered sub-items: 1 Explain the model; 2 Report details of computation; 3 Describe the posterior; 4 Report decisions and criteria; 5 Report sensitivity analysis; 6 Make it reproducible.
- Step 1 covers data variables, likelihood, parameters, priors, formal model specification, and prior predictive checks.
- Step 2 requires two DISTINCT MCMC diagnostics for every parameter or derived value: convergence (PSRF/R-hat, Step 2.B) AND resolution (effective sample size, Step 2.C).
- ESS >= 10,000 is recommended for stable HDI (highest-density interval) limits; lower ESS is tolerable for equal-tailed intervals.
- Step 4 requires explicit decision criteria (loss functions, ROPE limits, Bayes-factor thresholds); the paper suggests a posterior model probability of 0.95 as an example decision criterion.
- Step 6 requires full reproducibility: software versions, scripts and data, human-readable code, saved MCMC chains, and reproducible random seeds.

## How VeriBayes uses it
- Grounds rubric steps S2, S4, S9, and S10 in rubric/steps.yaml.
- S4 thresholds are VERIFIED against this source (3-0): two distinct MCMC diagnostics required for every parameter/derived value — convergence via PSRF/R-hat (BARG Step 2.B) and resolution via ESS (BARG Step 2.C).
- The ESS >= 10,000 recommendation applies specifically to stable HDI limits; the rubric should not treat it as a hard floor when papers report equal-tailed intervals, where lower ESS is tolerable per BARG.
- Its sensitivity-analysis step (Step 5: broad, informed, and default priors; effects on Bayes factors and decisions) and reproducibility step (Step 6) supply the checklist language for the corresponding rubric items.
