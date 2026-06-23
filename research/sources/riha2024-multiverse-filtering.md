# Supporting Bayesian modelling workflows with iterative filtering for multiverse analysis

**Citation:** Riha AE, Siccha N, Oulasvirta A, Vehtari A (2024). Supporting Bayesian modelling workflows with iterative filtering for multiverse analysis. arXiv:2404.01688 [stat.ME]. doi:10.48550/arXiv.2404.01688.
**Links:** [arXiv:2404.01688](https://arxiv.org/abs/2404.01688); [DOI](https://doi.org/10.48550/arXiv.2404.01688); [HTML v1 (as fetched)](https://arxiv.org/html/2404.01688v1)
**Type:** primary paper
**Role in the deep research:** Fetched under the "Disagreements & essential vs context-dependent steps" search angle; the verified claim "The Bayesian workflow as presented in this chapter…" (3-0) likely derives from it. HONESTY: the arXiv page and HTML v1 show a standalone preprint (no journal reference, no "to appear in" comment), and the paper never describes itself as a chapter — the "this chapter" phrasing in the verified claim may be a paraphrase or trace to a different source; treat that attribution with caution.

## What it is
A 2024 arXiv preprint (submitted 2 April 2024; stat.ME, stat.CO) from Aki Vehtari's group at Aalto University. It addresses the practical problem that iterative Bayesian model building generates many candidate models, and proposes combining multiverse analysis with established Bayesian workflow checks: an iterative filtering procedure that uses computational diagnostics, predictive ability, and causal constraints to narrow a multiverse of models toward higher-quality ones. Demonstrated on realistic examples with real data; not (yet) journal-published.

## Key content for Bayesify
- Frames workflow steps as context-dependent filters rather than a fixed checklist: which models survive depends on the modelling context, data, and causal constraints — directly relevant to the "essential vs context-dependent steps" question.
- Concrete computational filtering criteria: divergent transitions in HMC-NUTS (any divergences problematic), R-hat convergence diagnostic, bulk and tail ESS.
- PSIS-LOO-CV reliability: Pareto-k̂ > 0.7 indicates unreliable elpd estimates.
- Model comparison via elpd differences reported with uncertainty (±2·SE intervals); |Δelpd| < 4 treated as models with similar predictive performance.
- Posterior predictive checks and predictive ability (elpd) as the central quality criteria for filtering candidate models.
- Causal constraints used to exclude models that predictive metrics alone would not — comparison criteria are not purely predictive.

## How Bayesify uses it
- S4 (Computational faithfulness): corroborates the diagnostic set (divergences flagged, R-hat, bulk/tail ESS). The rubric's specific numeric lines rhat_modern "< 1.01" and ess_bulk_tail "> 400" remain sourced to vehtari2021 with verified: false — this paper uses those diagnostics but does not substitute for verifying the primary source.
- S6 (Model comparison): corroborates pareto_k "k>0.7 bad" and "elpd differences WITH standard errors" (both verified: false in rubric/steps.yaml; S6 SCOPE GAP says fill from Vehtari 2017 + Stan loo docs before v1.0). Its |Δelpd| < 4 similarity heuristic is a candidate addition, currently not in the rubric and not adversarially verified.
- Applicability gating (essential_for / recommended_for / na_when across S1-S10): supports the design choice that step importance is context-dependent, per the search angle this source was fetched under.
- Caveat from role notes: only one verified claim (3-0) likely derives from this source, and its "this chapter" wording does not match the paper's self-description — do not cite this paper as a book chapter.
