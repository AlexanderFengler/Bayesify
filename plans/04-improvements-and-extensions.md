# Improvements & Extensions — VeriBayes

This is my (Claude's) running list of suggestions to make VeriBayes excellent rather than merely
functional. It is opinionated on purpose. Items are tagged **[MVP]** (fold into Phase 2 now),
**[v1]** (near-term, high leverage), **[v2]** (after the corpus exists), or **[moonshot]**.
Each item says *why* it matters and *how* to approach it. The single most important meta-point:

> **VeriBayes is itself a measurement instrument, and it should be held to the same standard it
> holds papers to.** A tool that grades Bayesian rigor while being itself un-validated, over-confident,
> and un-auditable would be self-refuting. Several suggestions below exist to avoid that irony.

---

## A. Make the instrument trustworthy

### A1. Validate the tool against human experts **[MVP-critical]**
Treat the engine as a classifier/measurement device with measurable error. Build a **gold-standard
set** of, say, 50–100 papers hand-scored on the rubric by 2+ domain experts. Report:
- **Inter-rater reliability** among humans (Cohen's/Fleiss' κ) — establishes the ceiling; if humans
  disagree on a step, the tool can't be expected to be crisp there either.
- **Engine-vs-human agreement per step** (κ, and confusion on done-well/partial/missing).
Without this, no corpus claim in Phase 3 is defensible — the tool's error *is* the measurement error.
This is not optional polish; it's the credibility backbone. Wire the harness for it in the MVP even
if the labeled set starts small.

### A2. The tool should quantify its *own* uncertainty **[v1]**
It would be embarrassing for a Bayesian-workflow auditor to emit false-precision point scores. Each
per-step judgment should carry a **confidence** (e.g., the engine is sure a PPC is absent vs. it
might be in an unparsed supplement). Surface low-confidence judgments distinctly ("possibly missing —
not found, but check appendix"). Propagate this into the badge: a paper shouldn't be "Failed" on the
basis of low-confidence absences.

### A3. Ground every claim in the source **[MVP]**
Every assessment must cite **evidence spans** (page, section, quoted sentence) from the PDF. This
(a) slashes hallucination, (b) makes the report auditable for reviewers, (c) lets the UI highlight
the relevant passage. "Convergence not reported" is a weak claim; "no R-hat/ESS/divergence mention
found in §3 Methods, §4 Results, or Supplement" is an auditable one. **Absence claims are the
dangerous ones** — require the engine to enumerate where it looked.

### A4. Adversarial self-verification **[v1]**
Reuse the deep-research pattern: after the first pass flags a step as missing/poor, a **second
independent pass argues the opposite** ("find evidence this step *was* done"). Only findings that
survive refutation are reported with high confidence. Kills the most damaging error mode —
confidently telling an author they omitted something they actually did (in a supplement, a figure,
or different wording).

### A5. Human-in-the-loop override + active learning **[v1]**
Let an expert correct any judgment in the UI. Corrections are stored and become (a) additional
eval/gold data and (b) few-shot exemplars. Over time the disagreement log shows where the rubric or
prompts are weakest. This is the cheapest path to continuous improvement.

---

## B. Get the rubric right (the hard scientific core)

### B1. Context-conditional applicability — "missing" ≠ "not applicable" ≠ "not reported" **[MVP]**
The single biggest correctness risk is penalizing legitimate deviations. The rubric must distinguish:
- **Not applicable** — e.g., R-hat/ESS are meaningless for an *analytic/conjugate* posterior or a
  pure variational-inference paper; SBC is about method validation, central to methodological work
  but optional for a routine applied fit.
- **Not reported** — done but not described (a reporting gap).
- **Not done** — genuinely absent (a methodological gap).
Applicability is **conditioned on**: paper class (empirical / numerical-experiment / methodological),
inference method (MCMC vs. VI vs. exact), and model type. Encode this as **gating rules** in the
rubric spec, not as LLM vibes. Get this wrong and domain experts will (rightly) dismiss the tool.

### B2. Rubric as a versioned, declarative spec **[MVP]**
The rubric lives in `rubric/steps.yaml` (steps, signals of good/poor, thresholds, applicability
gates, weights), not hardcoded in prompts. Benefits: auditable, diffable, community-governable,
and **`rubric_version` stamped on every assessment** so Phase-3 trends stay interpretable across
rubric changes. The engine compiles this spec into prompts + deterministic checks.

### B3. Don't collapse to one number too early — and design the scoring rule deliberately **[v1]**
A single 0–100 invites **Goodhart's law** (optimize the badge, not the science). Prefer:
- a **profile** (vector of per-step scores) as the primary object, with the scalar/badge as a summary;
- an explicitly documented, **proper-scoring-inspired** aggregation with per-context weights;
- **transparent badge thresholds** with a "what-if" explainer ("add a posterior predictive check →
  Shaky → Verified"). The badge should *teach*, not just label.
Discuss the gaming surface openly in the docs (see F1).

### B4. Subfield-calibrated thresholds **[v2]**
Communities have different (sometimes legitimate) conventions. Avoid privileging Stan-ecosystem
norms. Once the corpus exists, calibrate "expected" practice per subfield so a paper is judged
against relevant peers as well as against the absolute gold standard — and show both.

### B5. Separate "rigor" from "reporting" as distinct axes **[v1]**
Two papers can fail the same step for opposite reasons (didn't do it vs. did it but didn't say).
Tracking these as separate axes makes suggestions sharper (author fix differs) and makes corpus
findings more interesting ("the field *does* the work but under-reports it").

---

## C. Engine capabilities

### C1. A library of deterministic detectors **[MVP]**
The grounding half of the hybrid engine. A versioned catalog of high-precision detectors:
- **Software/tooling:** Stan, brms, rstanarm, PyMC, NumPyro, TFP, JAGS, BUGS, HDDM, Turing.jl.
- **Diagnostics:** R-hat values, ESS (bulk/tail), divergent transitions, max-treedepth, BFMI,
  Pareto-k, WAIC/LOO/elpd, MCSE, trace/rank-plot mentions.
- **Workflow signals:** "prior predictive", "posterior predictive", "sensitivity analysis", "SBC"/
  "simulation-based calibration", number of chains/iterations/warmup, seed reporting.
- **Open-science:** data/code availability statements, OSF/GitHub/Zenodo links.
Each detector yields structured evidence the LLM must reconcile with — and each is independently
testable, unlike prompt behavior.

### C2. Figures and tables carry the diagnostics **[v1, high value]**
A large share of Bayesian diagnostics live in **figures** (trace plots, rank/ECDF plots, PPC
overlays, pair plots) and **tables** (R-hat/ESS columns). Text-only parsing misses them and will
produce false "missing" flags. Use a **vision-capable model** on rendered figure/table regions to
detect these. This is distinctive and directly improves accuracy — and pairs with A3 (the figure
becomes the evidence span).

### C3. Structure-aware parsing + supplements **[MVP]**
Use **GROBID** (or similar) for TEI-structured parsing (sections, references, figure/table captions)
rather than flat text. Crucially, **parse supplements/appendices** — that's where diagnostics often
hide. The relevance/absence logic depends on having actually looked there.

### C4. Reach into the linked artifacts **[v2]**
When a paper links a repo (GitHub/OSF/Zenodo), optionally fetch it and check the *code* for what the
*paper* omitted: Stan/PyMC model files, seeds, `loo`/`bayesplot` calls, divergence handling. Many
"reporting gaps" are resolvable from artifacts and this bridges paper↔reproducibility.

### C5. Multi-format ingest **[v1]**
Accept arXiv ID / DOI / OpenAlex ID (auto-fetch) in addition to PDF drag-drop — essential for Phase 3
batch ingestion anyway, so build the fetcher once and share it.

### C6. Caching & cost discipline **[MVP]**
Content-hash + `engine_version` + `rubric_version` cache key; a cheap relevance/classification screen
before the expensive full assessment. Makes both interactive use and corpus scale affordable, and
makes runs reproducible.

---

## D. Report & UX

### D1. Layered report for four audiences **[MVP]**
You named authors, reviewers, meta-researchers, and students. One report, layered views:
- **Badge + profile** (everyone, top).
- **Author mode:** prioritized, actionable fix-list (linter-style: error/warning/info), each with a
  concrete "how to fix" and a code/exemplar pointer.
- **Reviewer mode:** an exportable, evidence-cited critique block ready to paste into a review.
- **Student mode:** each step links to the methodological source and a "what good looks like"
  exemplar.
- **Meta-research mode:** the structured JSON (the same object Phase 3 stores).

### D2. Prioritized, severity-tiered suggestions **[MVP]**
Not a flat list. Rank by **impact × ease**. A missing posterior predictive check on the central model
is an *error*; an un-cited prior justification on a nuisance parameter is *info*. This is what makes
the report feel like a great linter rather than a nag.

### D3. Explicitly state what was done well, and why **[MVP]**
You asked for this and it matters beyond politeness: positive, *specific* reinforcement ("prior
predictive check in Fig 2 correctly revealed implausible effect sizes before fitting") teaches good
practice and builds author trust so the criticism lands. Generic praise is worse than none.

### D4. Re-check / diff mode **[v1]**
Re-upload a revised manuscript → show which issues resolved, which remain, badge delta. Directly
serves the author-self-check persona and creates a virtuous revise loop.

### D5. Relevance gate up front **[MVP]**
If the paper isn't a Bayesian-methodology paper, **short-circuit gracefully** with a clear "this
doesn't appear to apply, here's why" rather than forcing a misleading score. This is one of your
explicit requirements and should be a visible, well-explained gate, not a silent zero.

---

## E. Corpus / meta-research extensions (build on Phase 3)

### E1. Careful causal designs around landmark publications **[v2]**
The time-axis + landmarks view invites causal reading. Strengthen it with **interrupted time series**
/ **regression-discontinuity-in-time** around standard-setting publications — while loudly flagging
confounds (general trends, venue policy changes). Descriptive by default; causal only with the design
to back it.

### E2. Field dashboards & opt-in badges **[v2]**
Public per-subfield dashboards could drive adoption — and a requestable **"VeriBayes badge"** for
papers (à la reproducibility badges) gives authors a carrot. Guard against misuse (F1).

### E3. Generalize beyond the Bayesian workflow **[moonshot]**
The architecture (declarative rubric spec + hybrid engine + corpus pipeline) is **workflow-agnostic**.
The same machine could score adherence to frequentist reporting standards, causal-inference
workflows, or ML-reproducibility checklists. VeriBayes is a first instance of a general
"methodology-conformance" instrument. Keep the core decoupled from the Bayesian specifics so this
stays reachable.

---

## F. Governance, ethics, and failure modes

### F1. Anti-gaming and anti-misuse, stated openly **[MVP doc]**
Badges can be (a) gamed (write the magic words without doing the work) and (b) weaponized (used to
bludgeon authors or gatekeep). Mitigations, documented up front: emphasize **formative feedback over
ranking**; require **evidence grounding** so keyword-stuffing is detectable; frame as a *report* not a
verdict; never auto-publish scores about third-party papers without care. Phase 3's public views need
an explicit ethics note.

### F2. Bias of the instrument **[v1]**
The tool may systematically favor certain tools/communities/languages (English, Stan-centric,
well-resourced labs with supplements). Audit engine error **by subfield and venue tier** (ties to A1)
and disclose. A meta-research tool that has un-audited bias would itself fail its own rubric's
"sensitivity analysis" step.

### F3. Privacy / local-first for unpublished work **[MVP]**
Authors will upload **unpublished manuscripts**. Be explicit about what leaves the machine (PDF text
to the LLM API in the hybrid engine) and offer a clearer **local-only mode** (deterministic checks +
local model) for the privacy-sensitive. State the data handling plainly in the UI.

### F4. Full provenance/audit trail **[v1]**
Persist, per assessment: engine/rubric versions, model id, prompts, deterministic-check outputs,
evidence spans, and (if used) the adversarial verdicts. Anyone should be able to reconstruct *why*
the tool said what it said. This is the tool practicing the transparency it preaches.

---

## G. Suggested priority for the next iteration

If we tighten scope to the highest-leverage subset for a credible MVP:
1. **B1** (applicability gating) + **B2** (rubric-as-spec) — without these the scores are wrong.
2. **A3** (evidence grounding) + **A4** (adversarial check) — without these the scores aren't trusted.
3. **C1** (deterministic detectors) + **C3** (structured parsing incl. supplements) — the grounding.
4. **A1** (validation harness) — even with a tiny labeled set, so we *know* how good we are.
5. **D1–D3, D5** (layered, prioritized, evidence-cited report + relevance gate) — the deliverable.

Everything else is real but sequenceable after a trustworthy core exists.
