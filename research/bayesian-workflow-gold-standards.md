# Bayesian-Workflow Gold Standards — Research Synthesis

**Purpose:** Establish the methodological gold standard for the Bayesian workflow and decompose it
into discrete, assessable steps for the VeriBayes rubric.
**Method:** Executed via the deep-research harness (fan-out web search → 24 primary sources fetched →
falsifiable-claim extraction → 3-vote adversarial verification → cited synthesis). **24 of 25
verified claims confirmed** (1 killed). Date: 2026-06-10.

> **Read the caveats (§7) before fixing any threshold.** Two scope gaps matter: the LOO/WAIC/Pareto-k
> model-comparison numbers and the modern rank-normalized split-R-hat (<1.01) / bulk-tail-ESS (>400)
> thresholds were **not independently verified** in this claim set. Every threshold below is
> attributed to the specific source that states it — do not collapse them into one consensus number.

---

## 1. The convergent picture

Across three framework families the literature converges on a small, recurring set of decomposable
workflow steps that map cleanly onto a rubric:

1. **Principled prior specification** informed by domain knowledge
2. **Prior predictive / prior pushforward checks** (before data)
3. **Computational-faithfulness diagnostics** (R-hat, ESS, divergences, tree-depth, E-FMI, MCSE; and
   simulation-based calibration when self-diagnostics are insufficient)
4. **Model sensitivity / inferential adequacy**
5. **Posterior predictive (retrodictive) checks**
6. **Prior sensitivity analysis**
7. **Model comparison** (PSIS-LOO / WAIC, or a dedicated Bayes-factor sub-workflow)
8. **Transparent, reproducible reporting**

The frameworks are **complementary, not contradictory**. The main axis of *disagreement* is
**scope/necessity** — which steps are universally essential vs. context-dependent (§6).

---

## 2. Framework family A — conceptual workflow frameworks

**Strong agreement (confidence: high; merged from 6 claims, all 3-0).** Gelman et al. 2020, Betancourt's
principled workflow, and Schad, Betancourt & Vasishth 2021 agree on a canonical component set:
iterative model building/expansion, principled priors from domain knowledge, prior predictive checks,
computational-faithfulness diagnostics, model sensitivity/inferential adequacy, posterior predictive
(retrodictive) checks, and model comparison.

- **Gelman et al. 2020** (*Bayesian Workflow*, arXiv:2011.01808) frames the abstract around "iterative
  model building, model checking, validation and troubleshooting of computational problems, model
  understanding, and model comparison," stressing that "we will be fitting many models for any given
  problem" — the workflow is *not* single-model fitting.
- **Betancourt** (*Towards a Principled Bayesian Workflow*) evaluates a model via **four questions** —
  Domain Expertise Consistency, Computational Faithfulness, Inferential Adequacy, Model Adequacy — and
  is itself an explicit, **ordered 15-step "conceptual checklist"** in three phases (Steps 1–3
  Pre-Model/Pre-Data; 4–11 Post-Model/Pre-Data; 12–15 Post-Model/Post-Data). It states verbatim:
  "This workflow can be thought of as a sort of conceptual checklist." *(confidence: high, 3-0)* —
  this is the strongest direct evidence the workflow is intentionally checklist-shaped.
- **Schad, Betancourt & Vasishth 2021** (*Toward a principled Bayesian workflow in cognitive science*,
  arXiv:1904.12765, Psychological Methods 26(1):103–126) structures the workflow around **four basic
  questions**: prior predictive checks, computational faithfulness, model sensitivity, and posterior
  predictive checks — using "domain knowledge to inform prior distributions."

The Nicenboim *Introduction to Bayesian Data Analysis for Cognitive Science* textbook reproduces the
identical four-check sequence — useful corroboration in our target discipline.

---

## 3. Framework family B — reporting checklists

### 3.1 BARG — Bayesian Analysis Reporting Guidelines (Kruschke 2021)
*(Nature Human Behaviour 5:1282–1291, doi 10.1038/s41562-021-01177-7, open access; confidence: high,
merged 3-0.)* The most directly checklist-shaped source: a **preamble** (A. Why Bayesian; B. Goals)
plus **six ordered steps**:
1. Explain the model
2. Report details of computation
3. Describe the posterior
4. Report decisions and criteria
5. Report sensitivity analysis
6. Make it reproducible

Each step has lettered sub-items (e.g., 2.C MCMC chain resolution, 4.D Bayes factor, 6.D readable for
humans), giving granular assessable structure.

**BARG quantitative thresholds (verified, 3-0):** BARG mandates **two distinct MCMC diagnostics for
every parameter/derived value**:
- **Convergence** via a convergence statistic (PSRF / R-hat) — Step 2.B.
- **Resolution** via **effective sample size (ESS)** — Step 2.C, "distinct from, and in addition to,
  convergence." Threshold: **"ESS ≥ 10,000" for reasonably stable estimates of HDI limits**;
  equal-tailed-interval limits tolerate lower ESS.
- *Done well:* both PSRF/R-hat **and** ESS reported for all parameters, ESS ≥ 10,000 for HDI claims.
  *Missing:* only one diagnostic, or ESS without the convergence statistic.

### 3.2 WAMBS / WAMBS-v2 (Depaoli & van de Schoot 2017; van de Schoot et al. WAMBS-v2)
*(Psychological Methods; WAMBS-v2 tutorial doi 10.4324/9780429273872-4; confidence: high, merged 3-0.)*
A **10-point** checklist in **four stages**, targeting three failure modes: undue **prior influence**,
**misinterpretation** of Bayesian results, and **improper reporting**. The 10 points (verbatim from
WAMBS-v2):
1. Understand the priors *(before estimation)*
2. Trace-plot convergence *(after estimation, before results)*
3. Convergence after doubling iterations
4. Posterior histogram has enough information
5. ESS / autocorrelation
6. Posteriors and posterior predictions make substantive sense
7. Effect of variance-prior specifications *(prior influence)*
8. Effect vs non-informative priors
9. Sensitivity-analysis stability
10. Bayesian interpretation/reporting *(reporting)*

**WAMBS quantitative procedures (verified, 3-0), directly usable as rubric thresholds:**
- **Doubling-iterations relative-bias rule:** relative bias = 100·((doubled-iteration − initial)/
  initial); **< |5|% → acceptable; > |5|% → re-run with 4× iterations.**
- **Convergence:** Gelman-Rubin — the **point estimate AND the upper-CI limit of R-hat should both be
  close to 1** for all parameters.
- **Prior sensitivity:** **mandatory whenever informative/weakly-informative priors are used**;
  report the result *regardless of whether it changes conclusions*.
- *(Caveat: WAMBS phrases these as "we suggest"/"rule of thumb" — strong recommendation, not absolute.)*

### 3.3 van de Schoot et al. 2021
*Bayesian statistics and modelling* (Nature Reviews Methods Primers, doi 10.1038/s43586-020-00001-2) —
a field primer corroborating the same prior→fit→diagnose→check→report arc (fetched as a primary source).

---

## 4. Computational faithfulness & calibration (the diagnostics tier)

**Computational-faithfulness assessment is a distinct step** *(confidence: high, 3-0)* relying on
algorithm self-diagnostics — R-hat for MCMC generally, divergences for HMC/NUTS specifically —
supplemented by **simulation-based calibration (SBC)** when self-diagnostics are unavailable.

**Verified thresholds — Betancourt's `stan_utility.check_all_diagnostics`**, run on every fit:
- **R-hat > 1.1 flagged** (`check_rhat`)
- **n_eff / iter < 0.001 flagged** (`check_n_eff`)
- **divergence count > 0 flagged** (`check_div`)
- **max tree-depth (=10) saturation flagged** (`check_treedepth`)
- **E-FMI < 0.2 flagged** (`check_energy`)
- *Done well:* all five reported and passing on every fit. *Missing:* no convergence diagnostics,
  or ignored divergences.

**SBC** *(confidence: high, 3-0)*: the prescribed tool when self-diagnostics are insufficient (origin:
Talts et al. 2018). Schad, Nicenboim, Bürkner, Betancourt & Vasishth (arXiv:2103.08744, Psychological
Methods 2022) extend SBC to **Bayes-factor computation**: "We are the first to use simulation-based
calibration as a tool to test the accuracy of Bayes factor estimates… highly recommended to use SBC to
calibrate one's Bayes factor estimates," because "it is unknown whether Bayes factor estimates based on
bridge sampling are unbiased for complex analyses."

> ⚠️ **Not independently verified here (see §7):** the **modern rank-normalized split-R-hat < 1.01**
> and **bulk/tail-ESS > 400** thresholds of Vehtari, Gelman, Simpson, Carpenter & Bürkner 2021 — that
> paper was *fetched* (Stan now defaults to these) but no surviving verified claim cites those exact
> numbers. The verified R-hat/ESS thresholds above come from Betancourt (R-hat > 1.1), BARG (ESS ≥
> 10,000 for HDI), and WAMBS. **A 2026 rubric should treat R-hat < 1.01 as the modern pass line but
> cite Vehtari et al. 2021 directly, and note the historical 1.1 for judging older papers in context.**

---

## 5. Model comparison

Two verified routes:
- **Bayes-factor sub-workflow** *(confidence: high, 3-0)*: Schad et al. 2021 (arXiv:2103.08744) define a
  **6-step robust BF sub-workflow**: (1) define observational model; (2) define + verify priors via
  prior pushforward/predictive checks; (3) fit and estimate BFs via bridge sampling **on the same data
  at least twice** to check MCMC-draw sufficiency; (4) run **SBC** to check BF computation accuracy;
  (5) use simulations to assess data variability; (6) only use empirical BFs if SBC supports reliable
  estimation, else improve design or acknowledge limitations. **Key warning:** "the results of Bayes
  factor analyses are highly sensitive to and crucially depend on prior assumptions… the dependency of
  Bayes factors on the prior goes beyond the dependency of the posterior on the prior" → **prior
  sensitivity analysis is essential for any BF-based inference.**
- **Cross-validation (PSIS-LOO-CV / WAIC):** ⚠️ **under-covered — see §7.** Vehtari, Gelman & Gabry
  2017 and the Pareto-k diagnostic were in scope and the sources were fetched, but **no surviving
  verified claim cites that paper or the k > 0.7 flag.** The rubric's LOO/WAIC dimension (elpd
  differences **with** standard errors; Pareto-k thresholds k > 0.5 "ok but monitor" / k > 0.7 "bad")
  must be filled directly from Vehtari, Gelman & Gabry 2017 and the Stan `loo` documentation before
  freezing — those values are widely used but were not adversarially verified in this run.

---

## 6. Essential vs. context-dependent (the gating backbone)

**Verified (confidence: high, 3-0; grounded in Nicenboim, faithfully restating Schad et al. 2021):**
- **Universally essential:** prior specification, prior/posterior predictive checks, convergence
  diagnostics, transparent reporting.
- **Context-dependent:** **computational-faithfulness (SBC)** and **model-sensitivity analysis** are
  "crucial to do for complex, non-standard, or cognitive models, but may be less important for simpler
  and more standard models." Computational-faithfulness checks "might need to be performed only once
  for a given research program" for simple/standard models, but "become an important issue when dealing
  with more advanced/non-standard models."

This directly grounds a rubric that **conditions step weight on model complexity and on paper type**
(empirical data analysis vs. methodological/simulation work) — the applicability gating in the
VeriBayes rubric. *(Corroboration caveat: this rests substantially on the Nicenboim textbook; would be
stronger with Gelman et al. 2020's own discussion of when steps apply.)*

---

## 7. Caveats, scope gaps & open questions (honest boundaries)

**Source quality:** strong — every finding rests on primary sources (original papers, author case
studies, authors' own tutorials); 23/24 confirmed 3-0, one (WAMBS stage-labeling) 2-1 over paraphrased
category names, not substance. One claim was **killed (1-2)**: a specific phrasing that PPC summary-stat
disparities "point to specific diagnosable model deficiencies" — so we treat PPC discrepancies as
*signals to investigate*, not auto-diagnoses.

**Two scope gaps to fill before freezing the rubric:**
1. **Cross-validation model comparison (PSIS-LOO-CV, WAIC, elpd ± SE, Pareto-k > 0.5/0.7):** named in
   scope but absent from the verified claim set. Fill from **Vehtari, Gelman & Gabry 2017** (Stat
   Comput 27:1413–1432) + Stan `loo` docs.
2. **Modern R-hat/ESS thresholds (rank-normalized split-R-hat < 1.01, bulk/tail-ESS > 400):** not
   independently verified; cite **Vehtari et al. 2021** (Bayesian Analysis 16(2):667–718) directly.

**Open questions carried forward to rubric design:**
- Which R-hat line is the 2026 pass/fail — historical 1.1 (verified, Betancourt) or modern 1.01
  (fetched, not verified)? *Recommendation:* 1.01 as pass line, cite Vehtari 2021; flag 1.1 as
  historical context for older papers.
- Exact LOO/WAIC/Pareto-k reporting conventions (fill from Vehtari 2017).
- Genuine *disagreements* (not emphasis) — e.g., whether to use Bayes factors at all; default/reference
  vs. weakly-informative-prior philosophy — so the rubric doesn't penalize a paper for legitimately
  following one school.
- How to differentiate scoring for empirical vs. methodological/simulation papers (SBC central to the
  latter; PPC + reporting universal).

---

## 8. Sources (primary unless noted)

> **Annotated bibliography:** every source below has a dedicated note in
> [`sources/`](sources/README.md) — full confirmed citation, what the work is, and exactly which
> rubric steps/thresholds it grounds (with verified / not-verified status). Use
> `sources/fetch_sources.sh` to download the open-access PDFs locally.

| # | Source | Angle |
|---|--------|-------|
| 1 | Gelman et al. 2020, *Bayesian Workflow*, arXiv:2011.01808 | Frameworks |
| 2 | Schad, Betancourt & Vasishth 2021, *Psychological Methods* 26(1), arXiv:1904.12765 | Frameworks |
| 3 | Betancourt, *Towards a Principled Bayesian Workflow* (case study) | Frameworks |
| 4 | Schad et al. 2022 (Bayes factors + SBC), arXiv:2103.08744 | Frameworks / model comparison |
| 5 | Nicenboim, *Bayesian Data Analysis for Cognitive Science* (ch. workflow) | Frameworks / context |
| 6 | Kruschke 2021, *BARG*, Nature Human Behaviour 5:1282 (doi 10.1038/s41562-021-01177-7) | Reporting |
| 7 | Depaoli & van de Schoot 2017, *WAMBS*, PubMed 26690773 | Reporting |
| 8 | van de Schoot et al., *WAMBS-v2 tutorial* (doi 10.4324/9780429273872-4) | Reporting |
| 9 | van de Schoot et al. 2021, *Bayesian statistics and modelling*, Nat Rev Methods Primers (doi 10.1038/s43586-020-00001-2) | Reporting |
| 10 | Vehtari et al. 2021, *Improved R-hat*, Bayesian Analysis 16(2) | Diagnostics *(fetched; thresholds to confirm)* |
| 11 | Modrák et al. 2023, *SBC Checking*, Bayesian Analysis (Project Euclid) | Diagnostics |
| 12 | Talts et al. 2018, *Validating Bayesian Inference with SBC*, arXiv:1804.06788 | Diagnostics |
| 13 | Stan diagnostics/warnings docs (mc-stan.org) | Diagnostics |
| 14 | Vehtari, Gelman & Gabry 2017, *Practical Bayesian model evaluation (LOO/WAIC)*, Stat Comput 27 | Model comparison *(to fill)* |
| 15 | Stan `loo` Pareto-k diagnostic docs (mc-stan.org/loo) | Model comparison *(to fill)* |
| 16 | Gabry et al. 2019, *Visualization in Bayesian workflow*, JRSS-A (rss.onlinelibrary doi 10.1111/rssa.12378) | Predictive checks |

*(Full URL list and per-claim evidence in the run output:
`tasks/wxvs862b0.output`. Stats: 5 angles, 24 sources fetched, 119 claims extracted, 25 verified,
24 confirmed, 1 killed, 106 agent calls.)*
