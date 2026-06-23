# How to Diagnose and Resolve Convergence Problems

**Citation:** Stan Development Team. How to Diagnose and Resolve Convergence Problems (Stan documentation, mc-stan.org). Formerly titled "Runtime warnings and convergence problems"; no publication date shown on page.
**Links:** [Stan documentation page](https://mc-stan.org/learn-stan/diagnostics-warnings.html)
**Type:** software documentation
**Role in the deep research:** Practitioner-facing reference for what Stan itself flags (divergent transitions, max treedepth, BFMI/E-BFMI, R-hat, ESS) and the remediation advice users actually see. Used as corroboration for the S4 diagnostics catalog and as a model for how Bayesify deterministic detectors should phrase findings.

## What it is
The official Stan documentation page explaining every runtime warning Stan emits during/after sampling and how to resolve it. It is the de facto first-stop reference practitioners are pointed to when Stan prints convergence warnings, maintained by the Stan Development Team on mc-stan.org. It covers divergent transitions after warmup, rejected Hamiltonian proposals (exceptions), R-hat, Bulk/Tail ESS, maximum treedepth, and low BFMI warnings.

## Key content for Bayesify
- Cataloged warnings: divergent transitions after warmup, exceptions from rejected Hamiltonian proposals, R-hat, Bulk-ESS and Tail-ESS, maximum treedepth exceeded, and low E-BFMI.
- R-hat thresholds: below 1.01 recommended for full trust in results; below 1.1 acceptable in early workflow stages.
- ESS thresholds: Bulk-ESS greater than 100x the number of chains recommended (e.g., at least 400 for four chains); ESS > 20 sufficient early in the workflow. Tail-ESS is the minimum of the 5% and 95% quantile ESS.
- E-BFMI: nominal threshold of 0.3 (example warning text: "The E-BFMI 0.2786 is below the nominal threshold of 0.3").
- Remediation advice shown to users: reduce model complexity, use stronger priors, visualize diagnostics, check parameter identifiability, cautiously adjust `adapt_delta` and `stepsize`, reparameterize (especially non-centered parameterization), simulate data with known parameters, and increase iterations for R-hat/ESS issues.
- States that Stan reports R-hat as the maximum of rank-normalized split-R-hat and rank-normalized folded-split-R-hat (robust to thick-tailed distributions), citing the Vehtari et al. rank-normalization paper ("Rank-normalization, folding, and localization: An improved R-hat", arXiv 2019, published in Bayesian Analysis 2021).

## How Bayesify uses it
- Corroborates the S4 (computation/diagnostics) catalog in rubric/steps.yaml: the set of diagnostics Bayesify checks for (divergences, max treedepth, E-BFMI, R-hat, Bulk/Tail ESS) matches what Stan itself flags.
- Verified thresholds from the page: R-hat < 1.01 (strict) / < 1.1 (early workflow), Bulk-ESS > 100x chains, E-BFMI nominal threshold 0.3 — all confirmed on the fetched page.
- Serves as the phrasing model for Bayesify deterministic detectors: findings should mirror the warning text and remediation framing users actually see from Stan.
- Per the role notes: Stan now applies the rank-normalized R-hat/ESS defaults of Vehtari et al. 2021, confirmed on the page (which cites the paper's 2019 arXiv version).
