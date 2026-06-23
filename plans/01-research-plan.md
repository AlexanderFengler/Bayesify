# Phase 1 — Deep Research: Bayesian-Workflow Gold Standards → Assessment Rubric

**Status:** Plan + executed research (synthesis lands in `research/`)
**Feeds:** Phase 2 (`rubric/steps.yaml`) and Phase 3 (scoring of the corpus)
**Owner:** TBD

---

## 1. Objective

Produce a **defensible, cited decomposition of the Bayesian workflow into discrete, assessable
steps**, and turn it into a machine-usable **rubric** (`rubric/steps.yaml`). For each step we need:
(a) canonical citation(s), (b) concrete *signals of "done well" vs "done poorly"* detectable in a
paper, (c) recommended *quantitative thresholds* (R-hat, ESS, Pareto-k, …), and (d) *applicability*
flags (essential vs context-dependent, conditioned on paper type and inference method).

This document is both the **research methodology** and the **draft rubric**. The draft rubric below
is grounded in the canonical literature and is **reconciled against the executed deep-research
synthesis** (saved to `research/bayesian-workflow-gold-standards.md`) — see §6.

---

## 2. Research methodology (how the gold standard is established)

### 2.1 Source tiers
- **Tier 1 — workflow frameworks (define the steps):**
  - Gelman, Vehtari, Simpson, Margossian, Carpenter, Yao, Kennedy, Gabry, Bürkner, Modrák (2020).
    *Bayesian Workflow.* arXiv:2011.01808. — the master enumeration of workflow stages.
  - Betancourt, M. *Towards a Principled Bayesian Workflow.* (case-study/online.)
  - Schad, Betancourt, Vasishth (2021). *Toward a principled Bayesian workflow in cognitive science.*
    Psychological Methods 26(1). — workflow operationalized for our target disciplines.
- **Tier 2 — reporting checklists (define the assessable items):**
  - Kruschke (2021). *Bayesian Analysis Reporting Guidelines (BARG).* Nature Human Behaviour. — the
    most directly checklist-shaped source; maps almost 1:1 to report fields.
  - Depaoli & van de Schoot (2017). *When to Worry and How to Avoid the Misuse of Bayesian Statistics
    (WAMBS).* Psychological Methods; and **WAMBS-v2** (van de Schoot et al.).
  - van de Schoot et al. (2021). *Bayesian statistics and modelling.* Nature Reviews Methods Primers.
- **Tier 3 — diagnostics & evaluation primary sources (define the thresholds):**
  - Vehtari, Gelman, Simpson, Carpenter, Bürkner (2021). *Rank-normalization, folding, and
    localization: an improved R-hat.* Bayesian Analysis. — R-hat & ESS thresholds.
  - Vehtari, Gelman, Gabry (2017). *Practical Bayesian model evaluation using LOO-CV and WAIC.*
    Statistics and Computing; + Pareto-smoothed importance sampling (PSIS) and Pareto-k diagnostics.
  - Gabry, Simpson, Vehtari, Betancourt, Gelman (2019). *Visualization in Bayesian workflow.* JRSS-A.
    — prior/posterior predictive checks, graphical diagnostics.
  - Talts, Betancourt, Simpson, Vehtari, Gelman (2018). *Validating Bayesian Inference Algorithms with
    Simulation-Based Calibration.* arXiv:1804.06788; + Modrák et al. (2023) *SBC checking.*
  - Betancourt, M. *A Conceptual Introduction to HMC* (divergences, treedepth, BFMI).

### 2.2 Extraction template (applied to each source)
For every source, record into a structured note: workflow step(s) it defines or constrains;
verbatim recommended practice; any **numeric threshold**; whether it calls the step essential or
context-dependent; and a *detectable signal* (what a paper would contain if it did this well/poorly).
These notes compose the annotated bibliography in `research/`.

### 2.3 Reconciliation
Steps recur across sources under different names; §3 merges them into one canonical set, with each
canonical step carrying all supporting citations. Disagreements and context-dependence are recorded
explicitly (§5) rather than smoothed over.

### 2.4 Execution note
The deep-research harness (run this session) performs the fan-out search, source fetch, adversarial
claim-verification, and cited synthesis. Its output is saved to
`research/bayesian-workflow-gold-standards.md` and is the authority for thresholds/citations; the
draft rubric in §3 is updated to match before `rubric/steps.yaml` is frozen.

---

## 3. Draft rubric — canonical workflow steps

> **Draft, grounded in the Tier-1/2/3 sources above; thresholds/citations to be confirmed against
> `research/`.** Each step: *what it is* · *done-well signals* · *done-poorly signals* · *thresholds*
> · *applicability*. Status values used by the engine: `done_well | partial | missing | not_applicable`.

### S1. Model specification & justification *(essential, all types)*
- **What:** the likelihood/data-generating model and its structure are stated and motivated by the
  scientific question and data.
- **Done well:** explicit generative model; assumptions stated; structure justified by domain/theory.
- **Missing:** model appears with no rationale; key assumptions unstated.
- **Applicability:** essential everywhere.

### S2. Prior specification *(essential when priors are non-trivial)*
- **What:** priors stated for all parameters, with justification (weakly-informative vs informative,
  and why).
- **Done well:** every prior listed; choice justified; informative priors sourced; scale considered.
- **Missing:** "we used default priors" with no statement of what they are; priors absent;
  implausible flat priors used unexamined.
- **Applicability:** essential when priors materially affect inference; lighter for large-data
  empirical fits where the likelihood dominates (still report).

### S3. Prior predictive checks *(essential for methodological & small-data empirical; recommended generally)*
- **What:** simulate from the prior (× likelihood) to check that implied data/quantities are
  plausible **before** seeing data.
- **Done well:** prior predictive simulations shown/described; implausible implications caught and
  priors revised.
- **Missing:** no prior predictive reasoning; priors never sanity-checked.
- **Citation:** Gabry et al. 2019; Gelman et al. 2020.
- **Applicability:** high for methodological/new-model and weak-data settings; optional for routine
  large-data fits.

### S4. Computational faithfulness — convergence & sampling diagnostics *(essential whenever inference is approximate/MCMC)*
- **What:** evidence the inference algorithm actually worked.
- **Done well (MCMC/HMC-NUTS):** reports **R-hat**, **ESS**, **divergent transitions** (count, ideally
  zero), and treedepth/E-FMI/MCSE as relevant; multiple chains; warmup/iterations stated.
- **Missing:** no convergence diagnostics; single chain; ignored divergences.
- **Thresholds — attributed per source (each carries different provenance/stringency; do not collapse):**
  - **R-hat:** modern pass line **< 1.01** (Vehtari et al. 2021, rank-normalized split-R-hat — *fetched
    but not independently verified in this run; cite directly when freezing*). Historical line
    **R-hat > 1.1 = flagged** (Betancourt `stan_utility`, **verified 3-0**) — used to judge older papers
    fairly in context.
  - **ESS:** **n_eff/iter < 0.001 flagged** (Betancourt, verified); **ESS ≥ 10,000 for stable HDI
    limits** (BARG / Kruschke 2021, verified 3-0; lower tolerable for equal-tailed intervals); modern
    bulk/tail-ESS **> 400** (Vehtari et al. 2021 — *not independently verified; cite directly*).
  - **Divergences:** count **> 0 flagged** (Betancourt, verified). **E-FMI < 0.2 flagged**; **max
    tree-depth saturation flagged** (Betancourt, verified).
  - **Doubling-iterations rule (WAMBS, verified 3-0):** relative bias **< |5|%** acceptable; **> |5|%**
    → re-run with 4× iterations.
  - **Two distinct diagnostics required (BARG):** report convergence (PSRF/R-hat) **and** resolution
    (ESS) for *every* parameter/derived value — not one or the other.
- **Citation:** Betancourt (`stan_utility`); Kruschke 2021 (BARG ESS); WAMBS-v2; Vehtari et al. 2021.
- **Applicability:** essential for MCMC/HMC/VI; **not applicable** for exact/analytic posteriors
  (mark N/A, do not penalize) — this gating is critical. SBC (S7) substitutes when self-diagnostics
  are unavailable.

### S5. Posterior predictive checks (model adequacy) *(essential for empirical; recommended otherwise)*
- **What:** does the fitted model reproduce salient features of the observed data?
- **Done well:** PPCs shown (graphical overlays and/or test quantities); discrepancies discussed and
  acted on.
- **Missing:** no PPC; model fit asserted without checking; obvious misfit ignored.
- **Citation:** Gabry et al. 2019; Gelman et al. 2020.
- **Applicability:** essential for empirical data analysis; for methodological work, calibration
  (S7) may substitute.

### S6. Model comparison / selection (when multiple models) *(context-dependent)*
- **What:** principled comparison if multiple models are entertained.
- **Done well:** **PSIS-LOO-CV** / WAIC with standard errors and **Pareto-k** diagnostics reported;
  comparison interpreted with uncertainty. For **Bayes-factor** inference: a robust BF sub-workflow
  (Schad et al. 2022, **verified 3-0**) — verify priors via prior pushforward/predictive checks,
  estimate BFs via bridge sampling **≥ twice** on the same data, **run SBC to check BF accuracy**, and
  only report empirical BFs if SBC supports reliability. Because BFs depend on priors *more* than the
  posterior does, **prior sensitivity (S8) is mandatory for any BF claim.**
- **Missing:** model chosen with no comparison, or by an inappropriate criterion; high Pareto-k
  values ignored; BFs reported without prior justification, stability, or SBC.
- **Thresholds — ⚠️ FILL FROM PRIMARY SOURCE before freezing:** the LOO/WAIC/Pareto-k numbers
  (elpd differences **with** SE; Pareto-**k > 0.5** "monitor", **k > 0.7** "bad") are widely used but
  were **NOT independently verified** in this research run (scope gap — see
  `research/bayesian-workflow-gold-standards.md` §5, §7). Confirm against **Vehtari, Gelman & Gabry
  2017** (Stat Comput 27:1413) + Stan `loo` docs before assigning pass/fail.
- **Citation:** Vehtari, Gelman, Gabry 2017 (LOO/WAIC/PSIS); Schad et al. 2022 (BF sub-workflow).
- **Applicability:** only when ≥2 models compared (or a BF is reported); otherwise N/A.

### S7. Simulation-based calibration / algorithm validation *(essential for methodological; optional for applied)*
- **What:** verify the inference recovers known parameters / is calibrated, on simulated data.
- **Done well:** SBC (rank-uniformity) or parameter-recovery study reported.
- **Missing:** new method/model with no recovery or calibration evidence.
- **Citation:** Talts et al. 2018; Modrák et al. 2023.
- **Applicability:** **essential for methodological & numerical-experiment papers**; optional for
  routine empirical fits.

### S8. Prior / model sensitivity analysis *(context-dependent, often essential)*
- **What:** how much do conclusions depend on prior or modeling choices?
- **Done well:** alternative priors/specifications tried; robustness (or lack of) reported.
- **Missing:** single specification; no sensitivity check despite influential priors.
- **Citation:** WAMBS; van de Schoot et al. 2021; Gelman et al. 2020.
- **Applicability:** essential when priors/structure are influential (small data, informative
  priors); lighter when likelihood clearly dominates.

### S9. Reporting & reproducibility *(essential, all types)*
- **What:** enough detail to reproduce — software + versions, sampler settings (chains, iterations,
  warmup, seed), data/code availability, and the diagnostics above reported in text/tables.
- **Done well (per BARG):** model, priors, software/version, sampler settings, convergence
  diagnostics, and posterior summaries with uncertainty all reported; data/code shared.
- **Missing:** opaque "we fit a Bayesian model"; missing settings; point estimates with no
  uncertainty.
- **Citation:** Kruschke 2021 (BARG); WAMBS.
- **Applicability:** essential everywhere.

### S10. Posterior summary & inference communication *(essential, all types)*
- **What:** posteriors summarized honestly with uncertainty; claims matched to evidence.
- **Done well:** point + interval (CrI/HDI) with the interval defined; decisions tied to posterior
  quantities; no over-claiming beyond the posterior.
- **Missing:** point estimates only; "significance"-style misreadings; intervals undefined.
- **Citation:** BARG; van de Schoot et al. 2021.

> **Cross-cutting applicability matrix** (paper-type × step) and the exact threshold values are
> finalized in `rubric/steps.yaml` against `research/`. The Phase-2 classifier (empirical /
> numerical-experiment / methodological) selects the applicable subset and weights per this matrix.

---

## 4. From rubric to scoring rule

- Each **applicable** step gets a status → numeric sub-score; **N/A steps are excluded** from the
  denominator (no penalty for legitimately-inapplicable steps).
- Steps carry **weights** and an **essential** flag, **conditioned on paper type**.
- The aggregate is a **profile** (vector) plus two documented summary scores *(updated 2026-06-12,
  PR-#1 decision — the earlier Verified/Shaky/Failed badge is dropped)*:
  - **Coverage** — share of applicable steps present (`done_well` ∪ `partial`), reported as an
    uncertainty range when absences are low-confidence;
  - **Quality** — weighted mean step sub-score (weights per paper class).
  The per-class `essential` flags become **expectation tiers** driving suggestion severity, not a
  verdict.
- Per improvements §B3/A2: avoid false precision (single number), keep all scoring rules transparent
  in the rubric spec, and never let a **low-confidence** absence alone lower the headline coverage
  number (it widens the range instead).

## 5. Disagreements & context-dependence (record, don't smooth)

*(Reconciled with the verified research synthesis — `research/bayesian-workflow-gold-standards.md`.)*

- **R-hat threshold:** historical **1.1** (Betancourt `stan_utility`, verified) vs modern **< 1.01**
  (Vehtari et al. 2021, *fetched but not independently verified this run*). Use 1.01 as the 2026 pass
  line, cite Vehtari 2021 directly, and flag 1.1 as historical context for older papers.
- **ESS targets differ by purpose:** BARG **≥ 10,000** for stable *HDI limits* vs the lighter
  bulk/tail-ESS **> 400** (Vehtari 2021) for stable *point/interval estimates*. These serve different
  goals — cite the specific source per claim, don't average them.
- **WAIC vs LOO:** LOO (PSIS) generally preferred; WAIC still common — accept either, prefer LOO.
  *(LOO/Pareto-k thresholds are a verified scope gap — fill from Vehtari 2017, see S6.)*
- **The frameworks are complementary, not contradictory** — the real axis of disagreement is
  **scope/necessity**: SBC/computational-faithfulness and model-sensitivity are *context-dependent*
  (essential for complex/non-standard/cognitive models, "once per research program" or skippable for
  simple standard ones), while prior specification, predictive checks, convergence diagnostics, and
  transparent reporting are *universally essential*. This is the backbone of the applicability gating
  (improvements §B1). *(Grounded substantially in Nicenboim restating Schad et al. 2021.)*
- **Genuine open disagreements** (don't penalize a paper for picking a legitimate school): whether to
  use **Bayes factors at all**; **default/reference vs weakly-informative-prior** philosophy.
- **Default priors:** acceptable if *stated and appropriate*; the failure is silence, not defaults
  per se.
- **PPC discrepancies are signals to investigate, not auto-diagnoses** (the one claim killed 1-2 in
  verification over-stated this) — the rubric flags misfit for follow-up, not a specific defect.

## 6. Deliverables of Phase 1

1. `research/bayesian-workflow-gold-standards.md` — the executed deep-research synthesis (cited).
2. `research/sources/` — per-source annotated notes (§2.2 template): one file per source with
   confirmed citation, key content, and exactly which rubric steps/thresholds it grounds; plus
   `fetch_sources.sh` for the open-access PDFs. **Delivered.**
3. `rubric/steps.yaml` — the machine-usable rubric: steps, signals, thresholds, applicability gates,
   weights, essential flags, source citations, `rubric_version`.
4. `validation/rating-guide.md` *(Phase-2 handoff)* — the expert rating instrument for the A1
   validation protocol (`validation/protocol.md` §2) is **compiled from `steps.yaml`**, so the humans
   and the engine are scored against the *same* operationalization of this research.
5. This plan, reconciled with the synthesis once it lands.

> **Reconciliation status — DONE for this session (2026-06-10).** The deep research executed and its
> synthesis is in `research/bayesian-workflow-gold-standards.md` (24/25 claims verified 3-0). §3–§5
> above are reconciled with it: thresholds re-attributed per source (S4), Bayes-factor sub-workflow
> added (S6), disagreements updated (§5), and a draft machine rubric written to `rubric/steps.yaml`.
>
> **Two known scope gaps to close before freezing `rubric/steps.yaml` v1.0** (both flagged in the
> synthesis §7): (1) **LOO/WAIC/Pareto-k** thresholds — fill from Vehtari, Gelman & Gabry 2017 + Stan
> `loo` docs; (2) **modern R-hat < 1.01 / bulk-tail-ESS > 400** — cite Vehtari et al. 2021 directly.
> A short targeted follow-up research pass on these two primary sources will close both.
