# Detector catalog (component c / gate C1)

One row per `detector_id`. This file is the **review surface**: no detector ships without an entry,
and any pattern/version change must be reflected here. `catalog_fingerprint()` (id + version +
pattern + flags for every detector) feeds `engine_version` (gate G1) and the detect sub-cache key
(gate G2), so bumping a `version` below invalidates cached detect results without re-parsing.

**Precision-first.** A missed mention is recoverable (e-assess reads the full sections); a false hit
poisons grounding. Acronyms that collide with English words are matched **case-sensitively**; the
spelled-out phrases beside them stay case-insensitive via inline `(?i:...)` groups. All detectors
skip `kind: references`. Precision is gated (≥ 0.95 per family on the dev audit); recall is recorded
here but never gated.

Catalog version: **0.1.0** (all detectors at this revision).

## software — emits `software_mention`

| id | version | pattern intent | case | notes / known failure modes |
|----|---------|----------------|------|-----------------------------|
| `software.stan` | 0.1.0 | `Stan` (the PPL) | sensitive | excludes "standard", "Stanford", "instance" via `\bStan\b` + case |
| `software.brms` | 0.1.0 | `brms` | insensitive | low collision risk |
| `software.rstanarm` | 0.1.0 | `rstanarm` | insensitive | |
| `software.pymc` | 0.1.0 | `PyMC`, `PyMC3/4/5` | insensitive | `PyMC\d*` captures the version digit |
| `software.numpyro` | 0.1.0 | `NumPyro` | insensitive | |
| `software.tfp` | 0.1.0 | `TensorFlow Probability`, `TFP` | acronym sensitive | bare `TFP` must be upper-case |
| `software.jags` | 0.1.0 | `JAGS` | sensitive | |
| `software.bugs` | 0.1.0 | `BUGS`, `WinBUGS`, `OpenBUGS` | sensitive | excludes "debugs", "bugs" |
| `software.hddm` | 0.1.0 | `HDDM` | insensitive | the package is lower-case in code |
| `software.hssm` | 0.1.0 | `HSSM` | insensitive | |
| `software.turing` | 0.1.0 | `Turing.jl` | insensitive | requires `.jl` (bare "Turing" too generic) |
| `software.bayesflow` | 0.1.0 | `BayesFlow` | insensitive | software proper name |
| `software.sbi` | 0.1.0 | `sbi package/toolbox/library/software/toolkit`, `import sbi`, `sbi.inference` | insensitive | high-precision Python package mentions |
| `software.neuralestimators` | 0.1.0 | `NeuralEstimators`, `NeuralEstimators.jl` | insensitive | Julia package |
| `software.pyabc` | 0.1.0 | `pyABC` | insensitive | grounds ABC software-method implication |

## method — emits `method_mention` (the d-screen relevance floor keys on these)

Without this family a purely analytic/conjugate Bayesian paper — no software, no sampler diagnostics
— would yield zero hits and look irrelevant.

| id | version | pattern intent | case | notes |
|----|---------|----------------|------|-------|
| `method.prior` | 0.1.0 | "prior distribution/on/over/for", "(weakly-/non-/un)informative prior" | insensitive | requires a qualifier, not bare "prior" |
| `method.posterior` | 0.1.0 | "posterior distribution", "posterior parameter distribution", "posterior mean/.../predictive", "the posterior" | insensitive | requires a qualifier or article |
| `method.credible_interval` | 0.1.0 | "credible interval", "highest (posterior) density", `HPD(I)`, `HDI(s)` | acronym sensitive | |
| `method.bayes_factor` | 0.1.0 | "Bayes factor(s)" | insensitive | |
| `method.mcmc` | 0.1.0 | `MCMC`, "Markov chain Monte Carlo", `NUTS`, "Hamiltonian Monte Carlo", `HMC`, "Gibbs sampl" | acronym sensitive | `NUTS` upper-case avoids "nuts" |
| `method.variational` | 0.1.0 | "variational inference/Bayes", `ADVI`, `ELBO` | acronym sensitive | |
| `method.sbi` | 0.1.0 | "simulation-based inference", "amortized Bayesian inference", "neural posterior/likelihood/ratio estimation", `SBI` | acronym sensitive | grounds the `sbi` method chip |
| `method.analytic` | 0.1.0 | "conjugate prior", "analytic(al) posterior", "closed-form posterior" | insensitive | drives S4 N/A gate facts |
| `method.smc` | 0.1.0 | "sequential Monte Carlo", `SMC`, "particle filter(s)" | acronym sensitive | grounds the `smc` method chip |
| `method.abc` | 0.1.0 | "approximate Bayesian computation", `ABC` | acronym sensitive | grounds the `abc` method chip |
| `method.laplace_inla` | 0.1.0 | `INLA`, "integrated nested Laplace", "Laplace approximation" | acronym sensitive | grounds the `laplace_inla` method chip |

## diagnostic — emits `diagnostic_value` (with number) or `diagnostic_mention` (without)

`value = {metric, op?, value|count}`. A metric mentioned without a number degrades to
`diagnostic_mention` (we never invent a `count: 0`). The number must be introduced by a comparator
(`< > = ≤ ≥`) or a connector word (`was`, `of`, `is`, `:` …) — a bare adjacent number is *not*
extracted, so "ESS for 4 parameters" stays a mention (precision-first); `op` defaults to `=`.

| id | version | pattern intent | value | notes |
|----|---------|----------------|-------|-------|
| `diag.rhat` | 0.1.0 | `R-hat`/`Rhat`/`R̂` (+ optional `op num`) | `{metric:rhat, op, value}` | `\bR-hat\b` excludes "rhattan" |
| `diag.ess` | 0.1.0 | "effective sample size", bulk/tail-ESS, `ESS`, `n_eff` (+ optional `op num`) | `{metric:ess, op, value}` | `ESS` case-sensitive → not "assess" |
| `diag.divergences` | 0.1.0 | "(no/zero/N) divergent transitions/divergences" | `{metric:divergences, count}` | "no"/"zero" → 0; bare mention → `diagnostic_mention` |
| `diag.pareto_k` | 0.1.0 | `Pareto-k(-hat/values)` (+ optional `op num`) | `{metric:pareto_k, op, value}` | |
| `diag.treedepth` | 0.1.0 | "(max) tree-depth" | — | mention only |
| `diag.bfmi` | 0.1.0 | `BFMI`, `E-BFMI`, `E-FMI`, "energy fraction of missing information" | — | acronym sensitive |
| `diag.loo_waic` | 0.1.0 | `PSIS-LOO`, `LOO-CV`, `LOO`, `WAIC`, `elpd`, "leave-one-out" | — | acronym sensitive |
| `diag.mcse` | 0.1.0 | `MCSE`, "Monte Carlo standard error" | — | acronym sensitive |
| `diag.trace_plot` | 0.1.0 | "trace plot(s)" | — | text-only; figure-borne traces are improvement C2 |
| `diag.rank_plot` | 0.1.0 | "rank plot(s)", "rank histogram(s)" | — | |

## workflow — emits `workflow_signal`

| id | version | pattern intent | notes |
|----|---------|----------------|-------|
| `workflow.prior_predictive` | 0.1.0 | "prior predictive" | |
| `workflow.posterior_predictive` | 0.1.0 | "posterior predictive", `PPC(s)` | `PPC` case-sensitive |
| `workflow.sensitivity` | 0.1.0 | "sensitivity analysis", "prior sensitivity", "robustness check/analysis" | |
| `workflow.sbc` | 0.1.0 | "simulation-based calibration", `SBC` | `SBC` case-sensitive |
| `workflow.recovery` | 0.1.0 | "parameter recovery" | |

## sampler — emits `sampler_config` (the number is mandatory)

| id | version | pattern intent | value | notes |
|----|---------|----------------|-------|-------|
| `sampler.chains` | 0.1.0 | "N chains" | `{metric:chains, count}` | |
| `sampler.iterations` | 0.1.0 | "N iterations/samples/draws" | `{metric:iterations, count}` | N ≥ 2 digits |
| `sampler.warmup` | 0.1.0 | "N warm-up/burn-in" | `{metric:warmup, count}` | N ≥ 2 digits |
| `sampler.seed` | 0.1.0 | "(random) seed(s)" | — | mention only; some FP risk in non-Bayesian "seed" usage |

## open_science — emits `open_science`

| id | version | pattern intent | notes |
|----|---------|----------------|-------|
| `open.data` | 0.1.0 | "data are/is available", "data availability" | |
| `open.code` | 0.1.0 | "code is/are available", "code availability", "analysis code/scripts" | |
| `open.osf` | 0.1.0 | `osf.io`, `OSF`, "Open Science Framework" | `OSF` case-sensitive |
| `open.github` | 0.1.0 | `github.com` | |
| `open.zenodo` | 0.1.0 | `zenodo` | |

## Changelog
- **0.1.0** — initial catalog (M3): all six families (software, method [the d-screen relevance
  floor], diagnostic, workflow, sampler, open_science); numeric
  extraction for R-hat / ESS / divergences / Pareto-k / chains / iterations / warmup.
  Later added `method.sbi` / `method.smc` / `method.abc` / `method.laplace_inla` plus software
  detectors for BayesFlow / sbi / NeuralEstimators.jl / pyABC. The classifier corroborates
  `methods_used` with detector hits, software-method implications, and own-use context.

## Out of scope (deferred — see c-detectors.md)
- Asserted-but-not-evidenced flagging → improvement **H6** (v1–v2); policy in `ETHICS.md` (F1) for v0.
- Vision-based detection of figure/table diagnostics → improvement **C2** (v1).
- Soft judgments (was the prior *justified*?) → never detector work; e-assess's job, grounded here.
