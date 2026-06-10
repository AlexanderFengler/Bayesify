# A tutorial on using the WAMBS checklist to avoid the misuse of Bayesian statistics

**Citation:** van de Schoot R, Veen D, Smeets L, Winter SD, Depaoli S (2020). A tutorial on using the WAMBS checklist to avoid the misuse of Bayesian statistics. In: Small Sample Size Solutions, 1st ed. Routledge, London, pp 30-49. doi:10.4324/9780429273872-4. Open access (CC BY-NC-ND 4.0).
**Links:** [Taylor & Francis](https://www.taylorfrancis.com/chapters/oa-edit/10.4324/9780429273872-4/tutorial-using-wambs-checklist-avoid-misuse-bayesian-statistics-rens-van-de-schoot-duco-veen-laurent-smeets-sonja-winter-sarah-depaoli); [DOI](https://doi.org/10.4324/9780429273872-4)
**Type:** textbook chapter
**Role in the deep research:** The WAMBS-v2 update of the original 2017 checklist. Grounded verified (3-0) quantitative procedures used verbatim as rubric thresholds in S4 and S8: the 10 checklist points, the doubling-iterations relative-bias rule, the Gelman-Rubin criterion, and the mandatory prior sensitivity analysis under informative/weakly-informative priors.

## What it is

Open-access tutorial chapter in the Routledge volume *Small Sample Size Solutions* (2020) presenting the updated WAMBS checklist (WAMBS-v2), with a worked example and concrete diagnostic procedures. Written by the original WAMBS authors plus collaborators, it is the operational companion to Depaoli & van de Schoot (2017), turning the checklist's stages into step-by-step procedures with explicit numeric rules of thumb.

## Key content for VeriBayes

- The 10 WAMBS points, enumerated: (1) understand the priors; (2) trace-plot convergence; (3) convergence retained after doubling the number of iterations; (4) posterior histogram resolution; (5) effective sample size / autocorrelation; (6) posteriors make substantive sense; (7) effects of variance priors; (8) estimated effect compared against non-informative priors; (9) stability under sensitivity analysis; (10) correct interpretation and reporting.
- Doubling-iterations relative-bias rule: rerun with double the iterations and compute relative bias of parameter estimates; |relative bias| up to 5% is acceptable, above |5|% rerun with 4x the iterations.
- Gelman-Rubin convergence criterion: both the point estimate AND the upper confidence-interval limit should be close to 1 for all parameters.
- Prior sensitivity analysis is mandatory whenever informative or weakly-informative priors are used, and must be reported regardless of outcome.
- Comparison against non-informative priors (point 8) as a distinct check from the broader sensitivity analysis (point 9).

## How VeriBayes uses it

- S4 (Computational faithfulness): grounds the convergence-diagnostic items (points 2, 3, 4, 5) and the two numeric thresholds taken verbatim — the |5|% relative-bias rule after doubling iterations (verified 3-0) and the Gelman-Rubin point-estimate-AND-upper-CI-close-to-1 criterion (verified 3-0).
- S8 (Prior / model sensitivity analysis): grounds the rubric's mandatory-sensitivity-analysis requirement when informative/weakly-informative priors are used, reported regardless of outcome (verified 3-0), plus the non-informative-prior comparison (point 8).
- The verbatim 10-point enumeration (verified 3-0) anchors the rubric's mapping from WAMBS items to steps.
- Caveat (HONESTY): WAMBS phrases these as "we suggest" / "rule of thumb" — VeriBayes treats them as strong recommendations, not absolute requirements.
