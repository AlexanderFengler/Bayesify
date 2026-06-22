# Bayesian statistics and modelling

**Citation:** van de Schoot R, Depaoli S, King R, Kramer B, Märtens K, Tadesse MG, Vannucci M, Gelman A, Veen D, Willemsen J, Yau C (2021). Bayesian statistics and modelling. Nature Reviews Methods Primers 1:1. doi:10.1038/s43586-020-00001-2.
**Links:** [Nature Reviews Methods Primers](https://www.nature.com/articles/s43586-020-00001-2); [DOI](https://doi.org/10.1038/s43586-020-00001-2)
**Type:** primary paper
**Role in the deep research:** Field primer corroborating the same prior -> fit -> diagnose -> check -> report arc as the workflow checklists; fetched as a primary source under the reporting-guidelines angle. Serves as tier-2 support for rubric steps S2, S8, and S10. No unique thresholds were taken from it.

## What it is
The inaugural article (volume 1, article 1, published 14 January 2021) of Nature Reviews Methods Primers, written by an eleven-author team spanning Bayesian methodology, applied statistics, and open science (including Rens van de Schoot, Sarah Depaoli, and Andrew Gelman). It is a discipline-agnostic primer walking through the full Bayesian analysis cycle: prior specification and elicitation, likelihood, posterior inference, MCMC and variational computation, prior/posterior predictive checking, and reporting. It is widely cited as the canonical entry-point reference for the modern Bayesian workflow across applied fields.

## Key content for Bayesify
- Frames Bayesian analysis as a staged workflow — specify priors, combine with the likelihood, compute the posterior, diagnose, check predictively, report — matching the arc Bayesify scores.
- Treats prior specification as a first-class design decision: priors should be stated, classified by informativeness (informative / weakly informative / diffuse), and justified or elicited, not left as unexamined defaults.
- Covers prior and posterior predictive checking as standard model-evaluation steps, and recommends sensitivity analysis to assess how much conclusions depend on prior and model choices.
- Surveys computation (MCMC, variational inference) and the need for convergence assessment before interpreting posteriors.
- Emphasizes reproducibility and transparent reporting, pointing to the updated WAMBS checklist as a concrete reporting vehicle.
- Demonstrates the workflow across applications (social sciences, ecology, genetics, medicine), supporting Bayesify's claim that the rubric is field-general.

## How Bayesify uses it
- S2 (Prior specification): tier-2 corroboration that every prior must be listed, classified, and justified; cited in rubric/steps.yaml as `vandeschoot2021` alongside barg2021 and wambs2017.
- S8 (Prior / model sensitivity analysis): tier-2 support for requiring sensitivity checks on prior and model choices.
- S10 (Posterior summary & inference communication): tier-2 support for transparent posterior reporting norms.
- HONESTY: no unique numeric thresholds were taken from this source; all pass/flag values in the rubric are attributed to other sources (e.g., betancourt_workflow, barg2021, vehtari2021). It corroborates the workflow arc rather than supplying cut-offs.
