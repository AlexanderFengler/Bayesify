# Bayesian Workflow

**Citation:** Gelman A, Vehtari A, Simpson D, Margossian CC, Carpenter B, Yao Y, Kennedy L, Gabry J, Bürkner P-C, Modrák M (2020). Bayesian Workflow. arXiv:2011.01808. doi:10.48550/arXiv.2011.01808.
**Links:** [arXiv abstract](https://arxiv.org/abs/2011.01808); [DOI](https://doi.org/10.48550/arXiv.2011.01808)
**Type:** primary paper
**Role in the deep research:** Tier-1 conceptual framework for the run. Grounded the verified (3-0) finding that the three foundational frameworks agree on a canonical component set: iterative model building/expansion, principled priors from domain knowledge, prior predictive checks, computational-faithfulness diagnostics, model sensitivity, posterior predictive checks, and model comparison. Its abstract framing ("iterative model building, model checking, validation and troubleshooting…", "we will be fitting many models") anchors the iterative-not-single-model view.

## What it is
A 77-page, 35-figure monograph (stat.ME, submitted 3 November 2020) by the core Stan development and research group, led by Andrew Gelman and Aki Vehtari. It is the most widely cited articulation of Bayesian workflow as a discipline broader than Bayesian inference: an iterative process of model building, checking, validation, troubleshooting, and comparison. It serves as the de facto reference framework that later workflow papers, case studies, and software documentation position themselves against.

## Key content for VeriBayes
- Frames applied Bayesian analysis as iterative: in realistic problems "we will be fitting many models," with model expansion and revision as expected, not exceptional — the core anti-single-model stance.
- Prescribes principled prior choice informed by domain knowledge, with prior predictive checks to vet what priors imply on the observable scale before seeing data.
- Treats computational faithfulness as a workflow step: convergence/sampling diagnostics, fake-data simulation, and validation of the fitting algorithm before trusting inferences.
- Prescribes posterior predictive (retrodictive) checking to evaluate model adequacy against observed data.
- Covers model comparison and the role of comparing many fitted models in reaching final conclusions, plus sensitivity of conclusions to model and prior choices.
- Decomposes the workflow into named, ordered components — the template for VeriBayes's step-level rubric decomposition.

## How VeriBayes uses it
- Grounds the framing of rubric steps S1 (model specification & justification), S3 (prior predictive / prior pushforward checks), S5 (posterior predictive checks), and S8 (prior/model sensitivity analysis) in rubric/steps.yaml, and the overall S1-S10 step decomposition.
- Primary citation for the verified (3-0) canonical component set shared across the three foundational frameworks (see Role above).
- Used for conceptual/structural grounding, not numeric cutoffs: no thresholds from this source carry a verified status in the run record.
