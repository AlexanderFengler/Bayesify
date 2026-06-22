# Diagnostics for Pareto smoothed importance sampling (PSIS)

**Citation:** Vehtari, A., Gabry, J., Magnusson, M., Yao, Y., Bürkner, P.-C., Paananen, T., & Gelman, A. "Diagnostics for Pareto smoothed importance sampling (PSIS)" (pareto-k-diagnostic). loo R package reference documentation, v2.9.0, mc-stan.org. Accessed 2026-06-10.
**Links:** [loo Pareto-k diagnostic reference](https://mc-stan.org/loo/reference/pareto-k-diagnostic.html)
**Type:** software documentation
**Role in the deep research:** Reference documentation for Pareto-k diagnostic interpretation in the loo package — the practical source for the k-threshold bands practitioners use. Identified as one of the two fill-from sources (with Vehtari et al. 2017) for closing the S6 scope gap before rubric v1.0.

## What it is
The official reference page for PSIS diagnostics in the loo R package (v2.9.0), the standard implementation of PSIS-LOO cross-validation in the Stan ecosystem. It documents `pareto_k_table()`, `pareto_k_ids()`, `pareto_k_values()`, `pareto_k_influence_values()`, `psis_n_eff_values()`, and `mcse_loo()`, and states the canonical interpretation bands for the Pareto shape parameter k. Its references are Vehtari, Gelman & Gabry (2017, Statistics and Computing 27(5):1413-1432) and Vehtari, Simpson, Gelman, Yao & Gabry (2024, JMLR 25(72):1-58).

## Key content for Bayesify
- Threshold bands as stated on the page (k per left-out observation, S = sample size):
  - k < min(1 - 1/log10(S), 0.7): PSIS estimate and its Monte Carlo SE are reliable.
  - 1 - 1/log10(S) <= k < 0.7: not reliable, but increasing (effective) sample size S above 2200 may help (then the bias-specific threshold 0.7 dominates).
  - 0.7 <= k < 1: large bias; estimate and Monte Carlo SE not reliable.
  - k >= 1: target distribution estimated to have non-finite mean; PSIS estimate and Monte Carlo SE not well defined.
- The modern threshold is sample-size-dependent — min(1 - 1/log10(S), 0.7) — replacing the older flat 0.5/0.7 heuristic.
- Remedies for high k: `loo_moment_match()`, direct sampling from leave-one-out posteriors or K-fold CV, or a more robust model.
- High k means the full posterior and the LOO posteriors differ substantially, i.e., importance sampling is unreliable for those observations.

## How Bayesify uses it
- Grounds S6 (model comparison / selection): "done_well" requires PSIS-LOO/WAIC reported with SE and Pareto-k, interpreted with uncertainty; "done_poorly" includes high Pareto-k ignored.
- S6 threshold record: rubric/steps.yaml currently stores `pareto_k: "k>0.5 monitor, k>0.7 bad"` flagged SCOPE GAP / verified: false. This page's actual bands (above) are now recorded; the 0.7 bad-bias threshold is confirmed, but the lower bound is min(1 - 1/log10(S), 0.7), not a flat 0.5 — the rubric entry should be updated accordingly for v1.0.
- HONESTY: the pareto_k thresholds were NOT verified during the research run itself; this note is the designated fill-from source closing that gap, paired with Vehtari et al. 2017.
- Also supports S6's elpd_diff guidance indirectly via `mcse_loo()` (Monte Carlo SE for PSIS-LOO).
