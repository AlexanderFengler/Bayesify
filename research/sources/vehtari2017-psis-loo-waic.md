# Practical Bayesian model evaluation using leave-one-out cross-validation and WAIC

**Citation:** Vehtari A, Gelman A, Gabry J (2017). Practical Bayesian model evaluation using leave-one-out cross-validation and WAIC. Statistics and Computing 27(5):1413-1432. doi:10.1007/s11222-016-9696-4. arXiv:1507.04544.
**Links:** [Springer article](https://link.springer.com/article/10.1007/s11222-016-9696-4); [DOI](https://doi.org/10.1007/s11222-016-9696-4); [arXiv:1507.04544](https://arxiv.org/abs/1507.04544)
**Type:** primary paper
**Role in the deep research:** The canonical PSIS-LOO-CV / WAIC model-comparison source. HONESTY NOTE: it was fetched in the run but NO surviving verified claim cites it or its Pareto-k thresholds (k > 0.5 monitor / k > 0.7 bad) — a flagged scope gap. The thresholds in rubric S6 are marked verified:false pending direct confirmation from this paper and the Stan loo docs.

## What it is
The standard reference for practical Bayesian model comparison via approximate leave-one-out cross-validation. Vehtari, Gelman, and Gabry introduce Pareto-smoothed importance sampling (PSIS), a procedure for regularizing importance weights, to compute LOO efficiently from existing posterior draws, and they derive approximate standard errors for estimated predictive errors and for differences between models. It is the methods paper behind the widely used `loo` R package for Stan, and PSIS-LOO has largely displaced WAIC and DIC as the default Bayesian model-comparison tool.

## Key content for Bayesify
- PSIS-LOO: efficient LOO-CV computed from posterior draws by Pareto-smoothing the importance weights, avoiding n refits.
- WAIC is asymptotically equal to LOO, but PSIS-LOO is more robust in finite samples with weak priors or influential observations — a reason to prefer LOO over WAIC in scoring.
- The estimated Pareto shape parameter k serves as a per-observation reliability diagnostic for the importance-sampling approximation; large k flags observations where PSIS-LOO cannot be trusted (commonly cited thresholds: k > 0.5 monitor, k > 0.7 bad — NOT yet verified against this paper, see below).
- Provides approximate standard errors for elpd estimates and for elpd differences between two models, enabling uncertainty-aware comparison instead of point rankings.
- Methods are implemented in the `loo` R package and demonstrated with Stan models, so reported PSIS-LOO output (elpd_loo, SE, Pareto-k counts) is a checkable artifact in papers.

## How Bayesify uses it
- Grounds rubric step S6 (Model comparison / selection) in `rubric/steps.yaml`: done_well requires PSIS-LOO/WAIC reported with SE and Pareto-k, interpreted with uncertainty; missing includes ignoring high Pareto-k.
- S6 threshold `pareto_k` (k > 0.5 monitor, k > 0.7 bad) — verified: FALSE. SCOPE GAP: must be confirmed directly from this paper plus the Stan loo documentation before rubric v1.0.
- S6 threshold `elpd_diff` (report elpd differences WITH standard errors, never point values alone) — verified: FALSE; same confirmation needed.
- Caveat: although this is the authoritative source for S6, no surviving verified claim in the deep-research run cites it, so all S6 numeric criteria currently rest on the research-run record rather than verified extraction.
