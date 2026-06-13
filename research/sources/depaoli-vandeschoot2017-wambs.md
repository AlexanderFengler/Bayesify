# Improving transparency and replication in Bayesian statistics: The WAMBS-Checklist

**Citation:** Depaoli S, van de Schoot R (2017). Improving transparency and replication in Bayesian statistics: The WAMBS-Checklist. Psychological Methods 22(2):240-261. doi:10.1037/met0000065. PMID 26690773.
**Links:** [PubMed](https://pubmed.ncbi.nlm.nih.gov/26690773/); [DOI](https://doi.org/10.1037/met0000065)
**Type:** primary paper
**Role in the deep research:** Origin of the WAMBS checklist. Grounded verified claims (one passing 2-1 over paraphrased stage labels, the rest 3-0): a structured 10-point guideline organized in four stages (before estimation; after estimation but before interpreting; understanding prior influence; after interpretation), explicitly targeting three failure modes — undue prior influence, misinterpretation of Bayesian results, and improper reporting. Grounds rubric steps S2, S4, S8, S9.

## What it is

Peer-reviewed methods paper in Psychological Methods (Epub December 21, 2015; in print June 2017) introducing the WAMBS checklist — "When to Worry and how to Avoid the Misuse of Bayesian Statistics." It is one of the most widely cited applied-Bayesian reporting guidelines in psychology and adjacent fields, and a standard reference for structured review of Bayesian analyses.

## Key content for VeriBayes

- A 10-point checklist of items "that should be thoroughly checked when applying Bayesian analysis," intended as a systematic quality-evaluation protocol.
- Four-stage organization: (1) issues to check before model estimation; (2) issues to check after estimation but before interpreting results; (3) understanding the influence of priors; (4) actions after interpreting results.
- Explicitly motivated by three failure modes of applied Bayesian work: undue prior influence, misinterpretation of Bayesian results/features, and improper or inadequate reporting.
- Requires explicit specification and justification of priors before estimation, including the source/rationale for hyperparameters.
- Prescribes convergence and sampling checks (e.g., trace-plot inspection, re-running with more iterations, checking posterior distributions) before any interpretation.
- Prescribes prior-sensitivity comparison (re-estimating under alternative priors and comparing posteriors) and full, transparent reporting of the entire estimation workflow.

## How VeriBayes uses it

- S2 (Prior specification): grounds the requirement that priors be stated and justified up front (WAMBS pre-estimation stage; verified 3-0).
- S4 (Computational faithfulness): grounds the requirement for convergence/sampling diagnostics after estimation but before interpretation (verified 3-0).
- S8 (Prior / model sensitivity analysis): grounds the "understanding prior influence" stage — comparing posteriors under alternative priors (verified 3-0).
- S9 (Reporting & reproducibility): grounds the improper-reporting failure mode and the transparency/openness emphasis (verified 3-0).
- Caveat: the four stage labels used in the research run are paraphrases of the paper's wording and passed verification only 2-1; the 10-point count and three failure modes passed 3-0. No numeric thresholds (e.g., specific R-hat cutoffs) are taken from this source.
