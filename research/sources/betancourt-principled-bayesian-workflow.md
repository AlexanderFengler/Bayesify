# Towards A Principled Bayesian Workflow

**Citation:** Betancourt M. Towards a Principled Bayesian Workflow. Online case study, betanalpha.github.io, April 2020.
**Links:** [Case study (betanalpha.github.io)](https://betanalpha.github.io/assets/case_studies/principled_bayesian_workflow.html)
**Type:** author case study
**Role in the deep research:** Tier-1 framework source; grounded 5 verified claims (all 3-0), including the strongest direct evidence that the workflow is intentionally checklist-shaped: an ordered 15-step "conceptual checklist" in three phases, evaluated via four questions. Also the source of the verified stan_utility diagnostic thresholds used in rubric S4, and grounds SBC as the fallback when self-diagnostics are unavailable (S7) and prior pushforward checks (S3).

## What it is
Michael Betancourt's long-form online case study (dated April 2020 on the page) laying out a complete, ordered Bayesian model-building workflow, with worked Stan examples and full code. It is one of the most-cited workflow references in applied Bayesian statistics and a direct precursor to the Gelman et al. "Bayesian Workflow" program. The page itself sources a companion `stan_utility.R` script and runs `util$check_all_diagnostics(fit)` repeatedly to gate each fit.

## Key content for VeriBayes
- An ordered 15-step workflow checklist in three phases (confirmed on page): Pre-Model, Pre-Data (1 Conceptual Analysis; 2 Define Observational Space; 3 Construct Summary Statistics); Post-Model, Pre-Data (4 Model Development; 5 Construct Summary Functions; 6 Simulate Bayesian Ensemble; 7 Prior Checks; 8 Configure Algorithm; 9 Fit Simulated Ensemble; 10 Algorithmic Calibration; 11 Inferential Calibration); Post-Model, Post-Data (12 Fit the Observation; 13 Diagnose Posterior Fit; 14 Posterior Retrodictive Checks; 15 Celebrate).
- Four guiding evaluation questions, all named on the page: Domain Expertise Consistency, Computational Faithfulness, Inferential Adequacy, Model Adequacy.
- A concrete MCMC diagnostic gate via `check_all_diagnostics`: R-hat, n_eff/iter, divergent transitions, max-treedepth saturation, and E-FMI checked after every fit (diagnostic output printed on page, e.g. "E-FMI indicated no pathological behavior", "0 of 4000 iterations saturated the maximum tree depth of 10").
- Prior pushforward checks and prior predictive checks as the mechanism for eliciting and validating domain expertise before seeing data.
- Simulation-based calibration (SBC) as the algorithm-validation tool, including its practical caveats (requires exact posterior samples; MCMC chains must be thinned to remove autocorrelation; only assesses accuracy within the context of the assumed model).
- Posterior retrodictive checks (Step 14) as the model-adequacy test against the observed data.

## How VeriBayes uses it
- S3 (Prior predictive / prior pushforward checks): grounds the prior pushforward check requirement (verified 3-0).
- S4 (Computational faithfulness): source of the VERIFIED stan_utility thresholds — R-hat > 1.1 flagged; n_eff/iter < 0.001 flagged; divergences > 0 flagged; max-treedepth saturation flagged; E-FMI < 0.2 flagged. Note: the numeric cutoffs live in the companion `stan_utility.R` script the case study sources, not verbatim in the page prose; the page shows the resulting pass/fail output.
- S7 (Simulation-based calibration): grounds SBC as the fallback validation when sampler self-diagnostics are unavailable (verified 3-0), with the page's caveats about exact samples and thinning.
- Overall rubric ordering: the 15-step / three-phase / four-question structure is the strongest direct evidence that the workflow is intentionally checklist-shaped, supporting VeriBayes scoring papers step-by-step (S1-S10).
