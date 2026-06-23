# Deep-Research Sources — Annotated Bibliography

The sources used by the Phase-1 deep research run (2026-06-10) that produced
[`../bayesian-workflow-gold-standards.md`](../bayesian-workflow-gold-standards.md). One note per
work: what it is, full citation, and exactly how Bayesify uses it (which rubric steps in
[`../../rubric/steps.yaml`](../../rubric/steps.yaml) it grounds, with verified / not-verified status
for every threshold).

**Why notes instead of the papers themselves:** several sources are paywalled (APA, Wiley, Springer),
so committing PDFs would redistribute copyrighted material. Run
[`fetch_sources.sh`](fetch_sources.sh) to download the open-access PDFs into `pdfs/` (gitignored);
the notes link every source.

**Provenance note:** each note's "Role in the deep research" reflects the adversarial-verification
outcome of the run (claims passed 3-0 / 2-1, or "fetched but no claims survived"). Each note was
written by an agent that re-fetched the source and confirmed the citation metadata; a separate audit
pass checked all 19 files for structure and citation red flags.

## Workflow frameworks (Tier 1 — define the steps)

| Note | Citation (short) | Used for |
|------|------------------|----------|
| [gelman2020-bayesian-workflow](gelman2020-bayesian-workflow.md) | Gelman et al. 2020, *Bayesian Workflow*, arXiv:2011.01808 | Canonical component enumeration; iterative "many models" framing; S1/S3/S5/S8 |
| [schad2021-principled-workflow-cogsci](schad2021-principled-workflow-cogsci.md) | Schad, Betancourt & Vasishth 2021, *Psych Methods* 26(1) | Four-question workflow; discipline anchor for comp-cog-sci; S3/S4/S5/S8 + gating |
| [betancourt-principled-bayesian-workflow](betancourt-principled-bayesian-workflow.md) | Betancourt, online case study | 15-step checklist; **verified** stan_utility thresholds (R-hat>1.1, divergences>0, E-FMI<0.2…) for S4; S7 |
| [nicenboim-bayescogsci-workflow-chapter](nicenboim-bayescogsci-workflow-chapter.md) | Nicenboim, Schad & Vasishth, online textbook | Essential-vs-context-dependent gating; *also source of the one killed claim (PPC over-interpretation)* |
| [gelman-statmodeling-blog-2020](gelman-statmodeling-blog-2020.md) | Gelman 2020, blog post | Secondary corroboration only (the run's sole non-primary source) |
| [riha2024-multiverse-filtering](riha2024-multiverse-filtering.md) | Riha et al. 2024, arXiv:2404.01688 | Multiverse/iterative-filtering perspective under the context-dependence angle |

## Reporting checklists (Tier 2 — define the assessable items)

| Note | Citation (short) | Used for |
|------|------------------|----------|
| [kruschke2021-barg](kruschke2021-barg.md) | Kruschke 2021, *BARG*, Nat Hum Behav 5:1282 | Preamble + 6 steps; **verified** two-distinct-diagnostics rule + ESS ≥ 10,000 (HDI); S2/S4/S9/S10 |
| [depaoli-vandeschoot2017-wambs](depaoli-vandeschoot2017-wambs.md) | Depaoli & van de Schoot 2017, *Psych Methods* 22(2) | WAMBS origin: 10 points, 4 stages, 3 failure modes; S2/S4/S8/S9 |
| [wambs-v2-tutorial](wambs-v2-tutorial.md) | van de Schoot et al. 2020, Routledge (OA) | **Verified** thresholds: \|5\|% doubling rule, R-hat point+upper-CI ≈ 1, mandatory prior sensitivity; S4/S8 |
| [vandeschoot2021-bayes-primer](vandeschoot2021-bayes-primer.md) | van de Schoot et al. 2021, *Nat Rev Methods Primers* | Field-primer corroboration of the workflow arc; S2/S8/S10 |
| [kelter2024-basis-framework](kelter2024-basis-framework.md) | Kelter 2024, *Biometrical Journal* 66(1) (BASIS) | Supplementary (reporting of Bayesian *simulation studies*); no claims survived verification |

## Diagnostics & calibration (Tier 3 — define the thresholds)

| Note | Citation (short) | Used for |
|------|------------------|----------|
| [vehtari2021-improved-rhat](vehtari2021-improved-rhat.md) | Vehtari et al. 2021, *Bayesian Analysis* 16(2) | Modern rank-normalized R-hat < 1.01, bulk/tail-ESS > 400 — **⚠ not independently verified in the run** (scope gap; cite directly) |
| [talts2018-sbc](talts2018-sbc.md) | Talts et al. 2018, arXiv:1804.06788 | SBC origin (rank-uniformity); S7 |
| [modrak2023-sbc-checking](modrak2023-sbc-checking.md) | Modrák et al., *Bayesian Analysis* (adv. 2023; 20(2) 2025) | Modern SBC practice (test-quantity choice); S7 |
| [stan-diagnostics-warnings-docs](stan-diagnostics-warnings-docs.md) | Stan docs, mc-stan.org | Practitioner-facing diagnostics catalog; detector phrasing model for S4 |

## Model comparison

| Note | Citation (short) | Used for |
|------|------------------|----------|
| [vehtari2017-psis-loo-waic](vehtari2017-psis-loo-waic.md) | Vehtari, Gelman & Gabry 2017, *Stat Comput* 27 | PSIS-LOO/WAIC/elpd±SE — **⚠ not verified in the run** (scope gap; fill before rubric v1.0); S6 |
| [stan-loo-pareto-k-docs](stan-loo-pareto-k-docs.md) | loo package docs, mc-stan.org | Pareto-k threshold bands incl. min(1−1/log10(S), 0.7); S6 scope-gap fill source |
| [schad2022-bayes-factor-workflow](schad2022-bayes-factor-workflow.md) | Schad et al. 2022, *Psych Methods* | **Verified** 6-step robust Bayes-factor sub-workflow; BF→prior-sensitivity mandate; S6/S8 |

## Predictive checks

| Note | Citation (short) | Used for |
|------|------------------|----------|
| [gabry2019-visualization](gabry2019-visualization.md) | Gabry et al. 2019, *JRSS-A* 182(2) | Graphical prior/posterior predictive checking; S3/S5 |

---

*19 sources. Run stats: 5 search angles, 24 URLs fetched (some are alternate URLs of the same work,
merged into single notes here), 119 claims extracted, 25 adversarially verified → 24 confirmed,
1 killed.*
