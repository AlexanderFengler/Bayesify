# Introduction to Bayesian Data Analysis for Cognitive Science — chapter "Workflow"

**Citation:** Nicenboim B, Schad DJ, Vasishth S. Introduction to Bayesian Data Analysis for Cognitive Science. Online textbook (draft), chapter F "Workflow"; print edition published by CRC Press. No DOI shown on the page.
**Links:** [Chapter F: Workflow](https://bruno.nicenboim.me/bayescogsci/ch-workflow.html); [book home](https://bruno.nicenboim.me/bayescogsci/)
**Type:** textbook chapter (online)
**Role in the deep research:** Corroborates the Schad et al. four-check workflow sequence in Bayesify's exact target discipline (cognitive science), and is the verified (3-0) grounding for the essential-vs-context-dependent split used in rubric gating: sensitivity/computational-faithfulness checks are "crucial for complex, non-standard, or cognitive models" but may be "performed only once for a given research program" for simple standard models. One claim drawn from it was KILLED in adversarial verification (1-2): that PPC summary-stat disparities "point to specific diagnosable model deficiencies."

## What it is
A chapter of the open online textbook by Nicenboim, Schad, and Vasishth — the standard Bayesian-data-analysis text for cognitive science (print edition from CRC Press; the online version is marked DRAFT). The chapter states verbatim that it is "an abbreviated version" of the principled Bayesian workflow introduced to cognitive science by Schad, Betancourt, and Vasishth, so it is a faithful discipline-specific restatement of that paper rather than an independent source.

## Key content for Bayesify
- Four-check workflow sequence: (1) prior predictive checks, (2) computational faithfulness via simulation-based calibration (SBC), (3) sensitivity analysis (true-parameter recovery; prior-to-posterior uncertainty reduction), (4) posterior predictive checks with summary statistics.
- Prior predictive checks: simulate data from the priors, "define extremity thresholds (shaded areas), beyond which one does not expect a lot of data," and compare against domain expertise.
- Context-dependent gating: "checking computational faithfulness can become an important issue when dealing with more advanced/non-standard models" and "might need to be performed only one time for a given research program, where different experiments are rather similar."
- On PPC discrepancies, the chapter lists three possible readings: the model overlooks important processes; low-probability observations occurred anyway; or the model misses details of less critical processes — i.e., discrepancies are ambiguous between causes.
- Explicitly grounds the workflow in cognitive-science modeling practice, Bayesify's target corpus.

## How Bayesify uses it
- Grounds the applicability gating of S7 (SBC/algorithm validation) and S8 (sensitivity analysis) in rubric/steps.yaml: recommended-not-essential for simple standard empirical fits, with S7's na_when "may be done once per research program" taken from this source (VERIFIED 3-0).
- Corroborates the ordering and content of S3 (prior predictive), S4 (computational faithfulness), S5 (posterior predictive) for the cognitive-science paper class.
- HONESTY caveat: the claim that PPC summary-stat disparities "point to specific diagnosable model deficiencies" was KILLED in adversarial verification (1-2). Bayesify therefore treats PPC discrepancies as signals to investigate, not auto-diagnoses — encoded in S5's note in rubric/steps.yaml.
- HONESTY caveat (synthesis): the essential-vs-context-dependent weighting rests substantially on this single textbook source, which by its own statement faithfully restates Schad et al. 2021; it is corroboration within the discipline, not independent evidence.
