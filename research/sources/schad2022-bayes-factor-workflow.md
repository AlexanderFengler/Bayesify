# Workflow Techniques for the Robust Use of Bayes Factors

**Citation:** Schad, D. J., Nicenboim, B., Bürkner, P.-C., Betancourt, M., & Vasishth, S. (2022). Workflow techniques for the robust use of Bayes factors. *Psychological Methods*. https://doi.org/10.1037/met0000472 (arXiv:2103.08744)
**Links:** [arXiv abstract](https://arxiv.org/abs/2103.08744); [DOI](https://doi.org/10.1037/met0000472); [publisher PDF mirror (paulbuerkner.com)](https://paulbuerkner.com/publications/)
**Type:** primary paper
**Role in the deep research:** Grounded verified (3-0) claims defining the 6-step robust Bayes-factor sub-workflow in rubric S6, plus the verified warning that Bayes factor results depend on priors more strongly than the posterior does — making prior sensitivity (S8) mandatory for any BF claim. Also the source of the (self-reported) priority claim of being first to apply simulation-based calibration (SBC) to BF accuracy.

## What it is
A peer-reviewed methods paper in *Psychological Methods* by Schad, Nicenboim, Bürkner, Betancourt, and Vasishth that adapts the principled Bayesian workflow to hypothesis testing with Bayes factors. It shows that BF estimates are highly sensitive to data/model assumptions, prior choices, and computational noise, and provides a simulation-backed protocol (with reproducible code and OSF data) for checking whether a BF can be trusted before reporting it. It is a standard reference for robust BF practice in cognitive science and psycholinguistics.

## Key content for VeriBayes
- A 6-step robust Bayes-factor sub-workflow: (1) define the observational model; (2) define and verify priors via prior pushforward and prior predictive checks; (3) estimate BFs via bridge sampling on the same data at least twice (stability across MCMC draws); (4) run SBC to check the accuracy of the BF computation; (5) run simulations to assess variability of the BF under data variation; (6) only use empirical BFs if SBC supports reliable estimation.
- Demonstrates that BFs are more sensitive to prior specification than posterior estimates are — priors that barely move the posterior can flip the BF.
- Self-reports being the first work to apply simulation-based calibration to assessing Bayes factor computation accuracy (priority claim is the authors' own, not independently verified).
- Extends the workflow toward decision quality: assessing decision variability and optimizing decisions with utility functions.
- Ships reproducible code and data (OSF), making the protocol directly checkable.

## How VeriBayes uses it
- Grounds rubric S6 (verified 3-0): the six numbered steps above are the canonical checklist VeriBayes scores BF-reporting papers against, including the "run bridge sampling at least twice on the same data" stability requirement.
- Grounds the S8 linkage (verified): because BF results depend on priors more than the posterior does, any paper reporting a BF without a prior sensitivity analysis fails the S8 requirement.
- The SBC-gating rule (step 6) is the threshold condition: empirical BFs count as reliable only when SBC supports accurate estimation.
- HONESTY note: the "first to apply SBC to BF accuracy" claim is self-reported by the authors and carried as such, not as an independently verified fact.
- Volume/pages for the journal version were not confirmable from the fetched pages and are deliberately omitted from the citation.
