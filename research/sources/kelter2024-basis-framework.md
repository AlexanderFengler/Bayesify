# The Bayesian simulation study (BASIS) framework for simulation studies in statistical and methodological research

**Citation:** Kelter, R. (2024). The Bayesian simulation study (BASIS) framework for simulation studies in statistical and methodological research. Biometrical Journal, 66(1), e2200095. https://doi.org/10.1002/bimj.202200095 (first published online January 15, 2023)
**Links:** [Wiley Online Library](https://onlinelibrary.wiley.com/doi/full/10.1002/bimj.202200095); [DOI](https://doi.org/10.1002/bimj.202200095)
**Type:** primary paper
**Role in the deep research:** Fetched under the "Reporting checklists & guidelines" search angle, with 5 claims extracted at the fetch stage. HONESTY NOTE: none of those claims survived into the final verified findings of the synthesis. Its role for VeriBayes is supplementary corroboration of Bayesian reporting-guideline practice in biostatistics, not a grounding source for any verified finding.

## What it is
A single-author methods paper by Riko Kelter (University of Siegen) in Biometrical Journal proposing BASIS, a structured framework for planning, coding, executing, analyzing, and reporting Bayesian simulation studies in biometric and computational-statistics research. It responds to documented reporting deficiencies in published Bayesian simulation studies and folds in current best-practice Bayesian analysis guidelines. Note the slug's "2022" reflects the DOI/manuscript number and research-run record; the article's print publication year is 2024 (online 2023).

## Key content for VeriBayes
- A phase-structured checklist (planning through reporting) for Bayesian simulation studies, analogous in spirit to reporting checklists like BARG/WAMBS but targeted at method-evaluation studies rather than applied data analyses.
- Explicit requirement to report algorithmic choices (sampler, software, tuning) rather than treating MCMC as a black box.
- MCMC convergence diagnostics as a mandatory, reported component of any Bayesian simulation study.
- Sensitivity analyses (e.g., to prior and algorithmic settings) as a standing framework element.
- Monte Carlo standard error calculation and reporting for simulation estimates.
- Advocacy of neutral (impartial) comparison studies when benchmarking methods against each other.

## How VeriBayes uses it
- Supplementary corroboration only: it independently echoes practices behind S4 (convergence diagnostics), S7 (simulation-based algorithm validation), S8 (sensitivity analysis), and S9 (reporting & reproducibility) in rubric/steps.yaml, but no rubric step or threshold is grounded on this source.
- No specific thresholds from this paper carry verified status; none of its 5 fetch-stage claims passed verification, so nothing here should be cited as a verified finding.
- Scope caveat: BASIS targets simulation studies evaluating statistical methods, not applied Bayesian data analyses — the primary object VeriBayes scores — so its checklist transfers only partially.
