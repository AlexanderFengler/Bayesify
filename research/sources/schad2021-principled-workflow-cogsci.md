# Toward a principled Bayesian workflow in cognitive science

**Citation:** Schad DJ, Betancourt M, Vasishth S (2021). Toward a principled Bayesian workflow in cognitive science. Psychological Methods 26(1):103-126. doi:10.1037/met0000275. arXiv:1904.12765.
**Links:** [arXiv:1904.12765](https://arxiv.org/abs/1904.12765); [DOI](https://doi.org/10.1037/met0000275)
**Type:** primary paper
**Role in the deep research:** Tier-1 framework source and the discipline anchor for Bayesify's target fields (computational cognitive science). Grounded verified (3-0) claims that the workflow is structured around four basic questions — prior predictive checks, computational faithfulness, model sensitivity, posterior predictive checks — and that domain knowledge is used to inform priors. The Nicenboim et al. textbook restates this workflow, reinforcing it as the field standard.

## What it is
A peer-reviewed Psychological Methods paper (published version of arXiv:1904.12765, confirmed via CrossRef; the arXiv page lists only the preprint metadata) that adapts Betancourt's principled Bayesian workflow for cognitive science audiences. It is among the most-cited workflow papers in psycholinguistics and computational cognitive science, demonstrated end-to-end on hierarchical models of reading-time data fit in Stan/brms. The authors emphasize that the analyst is responsible for verifying the utility of a model before trusting its inferences.

## Key content for Bayesify
- Organizes model validation around four questions: (1) prior predictive checks — are model and priors consistent with domain expertise?; (2) computational faithfulness — do the sampling tools reliably fit the model?; (3) model sensitivity — can the data inform the parameters, and how strongly?; (4) posterior predictive checks — does the fitted model adequately capture the data?
- Prior predictive checks: simulate datasets from the prior and inspect summary statistics against domain knowledge; priors should be informed by what is substantively plausible (e.g., realistic reading-time magnitudes), not left at defaults.
- Computational faithfulness assessed via simulation-based calibration (SBC: rank-uniformity of the true parameter under posteriors fit to prior-simulated data), alongside standard convergence diagnostics.
- Model sensitivity assessed by fitting to simulated data and examining posterior z-scores (parameter recovery / bias) and posterior contraction (how much the data inform parameters beyond the prior).
- Posterior predictive (retrodictive) checks compare model-simulated data to the observed data to reveal misfit.
- Frames the full pipeline as iterative model development under domain expertise, worked through a concrete hierarchical reading-time case study.

## How Bayesify uses it
- Grounds rubric step S3 (Prior predictive / prior pushforward checks): the paper's question 1 and its domain-knowledge-informed prior simulation procedure (claim verified 3-0).
- Grounds S4 (Computational faithfulness / convergence & sampling diagnostics): question 2, including SBC and convergence diagnostics (verified 3-0).
- Grounds S5 (Posterior predictive checks): question 4 (verified 3-0).
- Grounds S8 (Prior / model sensitivity analysis): question 3 via posterior z-score and contraction (verified 3-0).
- Grounds the essential-vs-context-dependent gating in rubric/steps.yaml: as the discipline anchor for computational cognitive science it defines which checks the field treats as core workflow components; the Nicenboim textbook chapter restates the same four-question structure, so the gating does not rest on this source alone.
