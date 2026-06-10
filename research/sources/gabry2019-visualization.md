# Visualization in Bayesian workflow

**Citation:** Gabry J, Simpson D, Vehtari A, Betancourt M, Gelman A (2019). Visualization in Bayesian workflow. Journal of the Royal Statistical Society Series A 182(2):389-402. doi:10.1111/rssa.12378. arXiv:1709.01449.
**Links:** [Wiley (JRSS-A)](https://rss.onlinelibrary.wiley.com/doi/full/10.1111/rssa.12378); [DOI](https://doi.org/10.1111/rssa.12378); [arXiv:1709.01449](https://arxiv.org/abs/1709.01449)
**Type:** primary paper
**Role in the deep research:** Canonical source for graphical prior predictive and posterior predictive checking and for treating visualization as a first-class workflow component. Grounds rubric steps S3 and S5 — what a good predictive check looks like (simulation overlays, test quantities) — under the "Predictive checks & model comparison" angle.

## What it is
A read/discussion paper in JRSS Series A (2019, 182(2):389-402) by the core Stan development team (Gabry, Simpson, Vehtari, Betancourt, Gelman). It argues that Bayesian data analysis is an iterative process of model building, inference, checking/evaluation, and expansion, and that visualization is indispensable at every stage — not just trace plots at the end. It is the standard citation for graphical prior/posterior predictive checking and underlies the bayesplot R package.

## Key content for VeriBayes
- Frames visualization as integral to each workflow phase: exploratory data analysis, prior predictive checks, MCMC diagnostics, posterior predictive checks, and model comparison.
- Prior predictive checks: simulate datasets from the prior(+likelihood) BEFORE seeing data and plot them; implausible simulated data (e.g., physically impossible values) signals priors needing revision — the operational template for rubric S3.
- Distinguishes weakly informative priors from flat/vague defaults by what their simulations imply on the outcome scale, rather than by the prior density alone.
- Posterior predictive checks: overlay replicated datasets on observed data (density overlays, test quantities/statistics) and treat discrepancies as signals to investigate and expand the model — the template for rubric S5.
- Demonstrates visual HMC diagnostics (divergent-transition scatterplots revealing pathological posterior geometry) and graphical PSIS-LOO checks (pointwise Pareto-k plots) on a running PM2.5 air-pollution case study.
- Emphasizes the iterative loop: check, find misfit, expand model, re-check — checks are workflow steps, not one-off post-hoc validation.

## How VeriBayes uses it
- Grounds S3 (Prior predictive / prior pushforward checks): "simulations from prior shown/described BEFORE data; implausible implications caught & priors revised" is distilled from this paper (cited in rubric/steps.yaml alongside betancourt_workflow and schad2021).
- Grounds S5 (Posterior predictive checks): the done_well criterion "graphical overlays and/or test quantities, discrepancies discussed and acted on" follows this paper's PPC presentation (cited with gelman2020).
- Supports the S5 caveat that PPC discrepancies are signals to investigate, NOT auto-diagnoses of a specific defect.
- Contributes no numeric thresholds; its role is defining what a qualitatively adequate predictive check looks like.
