# Simulation-Based Calibration Checking for Bayesian Computation: The Choice of Test Quantities Shapes Sensitivity

**Citation:** Modrák M, Moon AH, Kim S, Bürkner P-C, Huurre N, Faltejsková K, Gelman A, Vehtari A (2025). Simulation-Based Calibration Checking for Bayesian Computation: The Choice of Test Quantities Shapes Sensitivity. Bayesian Analysis 20(2):461–488. doi:10.1214/23-BA1404. (Advance publication 2023; the research run cited it under the 2023 advance-publication date.)
**Links:** [Project Euclid (Bayesian Analysis)](https://projecteuclid.org/journals/bayesian-analysis/volume-20/issue-2/Simulation-Based-Calibration-Checking-for-Bayesian-Computation-The-Choice/10.1214/23-BA1404.full); [DOI](https://doi.org/10.1214/23-BA1404); [arXiv:2211.02383](https://arxiv.org/abs/2211.02383)
**Type:** primary paper
**Role in the deep research:** Modernizes SBC practice — its central result is that the choice of test quantities shapes SBC's sensitivity to miscalibration. Fetched under the convergence & calibration diagnostics angle; supports rubric S7 (SBC / algorithm validation) alongside Talts et al. 2018.

## What it is
A peer-reviewed Bayesian Analysis paper by Modrák, Moon, Kim, Bürkner, Huurre, Faltejsková, Gelman, and Vehtari that refines simulation-based calibration (SBC) checking, the rank-uniformity procedure introduced by Talts et al. (2018). It is the current methodological reference on which quantities SBC should be run over, with theory, multivariate-normal and HMC case studies, and an accompanying R package (SBC). Several of the authors overlap with the original SBC paper, making this the de facto successor recommendation from the Stan/Bayesian-workflow community.

## Key content for Bayesify
- Shows SBC's sensitivity depends critically on the test quantities checked: SBC over individual parameters alone can miss serious failures — in the extreme, a "posterior" equal to the prior passes parameter-only SBC.
- Recommends adding data-dependent test quantities; the joint log likelihood of the data is singled out as a particularly useful default that, combined with parameter quantities, can in principle detect any discrepancy from the correct posterior.
- Provides theoretical analysis of what SBC can and cannot detect for a given set of test quantities, upgrading SBC from a heuristic to a check with characterized power.
- Demonstrates the recommendations on multivariate normal examples and Hamiltonian Monte Carlo implementations; tooling is packaged in the SBC R package.
- Positions SBC as validation of the whole inference pipeline (model implementation + algorithm), not just the sampler.

## How Bayesify uses it
- Grounds rubric S7 (rubric/steps.yaml): "Simulation-based calibration / algorithm validation" — essential for methodological and numerical-experiment papers, recommended for empirical ones — as the modern companion to Talts et al. 2018 (see research/sources/talts2018-sbc.md).
- Sharpens the S7 "done well" criterion (SBC rank-uniformity or parameter-recovery study reported): state-of-the-art SBC should include data-dependent test quantities such as the joint log likelihood, not parameter ranks alone.
- Supports treating parameter-only SBC as weaker evidence than SBC with well-chosen test quantities when scoring S7.
- No numeric thresholds from this paper are encoded in the rubric; its contribution is qualitative (which quantities to check), and the role notes record no specific verified vote results tied to it.
