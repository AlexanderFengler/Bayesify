# Rank-normalization, folding, and localization: An improved R-hat for assessing convergence of MCMC (with Discussion)

**Citation:** Vehtari A, Gelman A, Simpson D, Carpenter B, Bürkner P-C (2021). Rank-normalization, folding, and localization: An improved R-hat for assessing convergence of MCMC (with discussion). Bayesian Analysis 16(2):667-718. doi:10.1214/20-BA1221. arXiv:1903.08008.
**Links:** [PDF (Gelman site)](https://sites.stat.columbia.edu/gelman/research/published/Vehtari_etal_2020_rhat_ess.pdf); [DOI](https://doi.org/10.1214/20-BA1221); [arXiv:1903.08008](https://arxiv.org/abs/1903.08008)
**Type:** primary paper
**Role in the deep research:** The modern convergence-diagnostics standard underlying VeriBayes's S4 thresholds (rank-normalized split-R-hat, bulk-ESS, tail-ESS). HONESTY NOTE: this source was fetched in the deep-research run, but its specific thresholds (R-hat < 1.01; ESS > 400) were NOT independently adversarially verified in the surviving claim set — a flagged scope gap. The rubric cites the paper directly and marks those thresholds verified:false pending a targeted confirmation pass; the verified historical threshold (R-hat > 1.1 flagged) comes from Betancourt instead.

## What it is
Peer-reviewed discussion paper in Bayesian Analysis (June 2021) by the core Stan/Aalto group, showing that the classic Gelman-Rubin (1992) R-hat fails for heavy-tailed targets and chains with unequal variances, and proposing the fix now implemented in Stan, ArviZ, and posterior. It introduces rank-normalized split-R-hat, folded R-hat (scale sensitivity), bulk-ESS and tail-ESS, quantile-based local efficiency measures, MCSE for quantiles, and rank plots as replacements for trace plots. It is the de facto modern standard for MCMC convergence assessment.

## Key content for VeriBayes
- Threshold tightened to R-hat < 1.01 — "only using the sample if R-hat < 1.01," explicitly much tighter than the original Gelman-Rubin recommendation; chains can dip below 1.1 well before convergence.
- Rank-normalized ESS should exceed 400 — "we recommend requiring that the rank-normalized ESS is greater than 400" for stable Monte Carlo standard error estimates (with at least 4 chains, i.e., average split-chain ESS of at least 50).
- Run at least four chains by default; multiple chains are essential for detecting multimodality and poor mixing.
- Distinguish bulk-ESS (central tendency) from tail-ESS (5%/95% quantiles); both must be checked, since heavy tails degrade them differently.
- Folded R-hat detects between-chain scale differences that ordinary split-R-hat misses entirely.
- Replace trace plots with rank plots from multiple chains; report MCSE for quantile estimates of interest.

## How VeriBayes uses it
- Grounds rubric step S4 (Computational faithfulness, rubric/steps.yaml): `rhat_modern: < 1.01` (2026 pass line) and `ess_bulk_tail: > 400` both cite this paper as `vehtari2021`.
- Both thresholds carry `verified: false` — fetched in the deep-research run but not adversarially verified in the surviving claim set; flagged scope gap, to be closed by a targeted confirmation pass. Direct verification against the fetched PDF text (this annotation pass) confirms both numbers appear as stated in the paper.
- The S4 historical threshold (`rhat_historical: > 1.1 flagged`, verified:true) is deliberately sourced from Betancourt, not this paper; do not swap attributions.
- Supports S4 "done_well" language requiring both R-hat AND ESS per parameter and >= 4 chains.
