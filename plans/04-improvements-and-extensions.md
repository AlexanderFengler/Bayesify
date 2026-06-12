# Improvements & Extensions — VeriBayes

This is my (Claude's) running list of suggestions to make VeriBayes excellent rather than merely
functional. It is opinionated on purpose. Items are tagged **[v0 — committed]** (in Phase-2 MVP
scope; `02-mvp-tool-plan.md` is authoritative for those — the twelve promoted by decision on
2026-06-12 carry a pointer blockquote to their spec there, while B1/B2/C1/C3 were committed from the
start), **[v1]** (near-term, high leverage), **[v2]** (after the corpus exists), or **[moonshot]**. Each item says *why* it matters and *how* to
approach it. The single most important meta-point:

> **VeriBayes is itself a measurement instrument, and it should be held to the same standard it
> holds papers to.** A tool that grades Bayesian rigor while being itself un-validated, over-confident,
> and un-auditable would be self-refuting. Several suggestions below exist to avoid that irony.

---

## A. Make the instrument trustworthy

### A1. Validate the tool against human experts **[v0 — committed]**
> Now fully specified — protocol (gold set, blind dual rating, adjudication, κ/absence-FPR metrics,
> regression gate) and surfacing (calibration page, per-report footer, `VALIDATION.md`):
> **`../validation/protocol.md`** (executed at Phase-2 M7).

Treat the engine as a classifier/measurement device with measurable error. Build a **gold-standard
set** (v0: 30 fully step-rated papers + cheap relevance-only probes, growing toward 100+ with a
sealed holdout by v1 — see `validation/protocol.md` §1) hand-scored on the rubric by 2+ domain
experts. Report:
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
not found, but check appendix"). Propagate this into the scores: a low-confidence absence widens
the coverage range rather than lowering the headline number (implemented this way in
`02-mvp/f-score.md`).

### A3. Ground every claim in the source**s** **[v0 — committed]**
> Upgraded per your note to grounding in the source**s**, plural: every finding cites both the
> **paper** (evidence spans) and the **methodological literature** (the `standards[]` rubric-provenance
> refs — "says who?"). **`02-mvp-tool-plan.md` §3.5 + `02-mvp/e-assess.md`.**

Every assessment must cite **evidence spans** (page, section, quoted sentence) from the PDF. This
(a) slashes hallucination, (b) makes the report auditable for reviewers, (c) lets the UI highlight
the relevant passage. "Convergence not reported" is a weak claim; "no R-hat/ESS/divergence mention
found in §3 Methods, §4 Results, or Supplement" is an auditable one. **Absence claims are the
dangerous ones** — require the engine to enumerate where it looked.

### A4. Adversarial self-verification **[v0 — committed]**
> Promoted from v1 into the v0 pipeline (assess stage runs a refutation pass on every negative
> finding before reporting). **`02-mvp/e-assess.md`.**

Reuse the deep-research pattern: after the first pass flags a step as missing/poor, a **second
independent pass argues the opposite** ("find evidence this step *was* done"). Only findings that
survive refutation are reported with high confidence. Kills the most damaging error mode —
confidently telling an author they omitted something they actually did (in a supplement, a figure,
or different wording).

### A5. Human-in-the-loop override + active learning **[v0 — committed (scaffolding); v1 (active loop)]**
> v0 ships the visible scaffolding — override storage, API, per-step "Disagree?" UI, export,
> honest "not yet learned from" labeling; the *active* learning loop stays v1.
> **`02-mvp/g-report-api-ui.md`.**

Let an expert correct any judgment in the UI. Corrections are stored and become (a) additional
eval/gold data and (b) few-shot exemplars. Over time the disagreement log shows where the rubric or
prompts are weakest. This is the cheapest path to continuous improvement.

---

## B. Get the rubric right (the hard scientific core)

### B1. Context-conditional applicability — "missing" ≠ "not applicable" ≠ "not reported" **[v0 — committed]**
The single biggest correctness risk is penalizing legitimate deviations. The rubric must distinguish:
- **Not applicable** — e.g., R-hat/ESS are meaningless for an *analytic/conjugate* posterior or a
  pure variational-inference paper; SBC is about method validation, central to methodological work
  but optional for a routine applied fit.
- **Not reported** — done but not described (a reporting gap).
- **Not done** — genuinely absent (a methodological gap).
Applicability is **conditioned on**: paper class (empirical / numerical-experiment / methodological),
inference method (MCMC vs. VI vs. exact), and model type. Encode this as **gating rules** in the
rubric spec, not as LLM vibes. Get this wrong and domain experts will (rightly) dismiss the tool.

### B2. Rubric as a versioned, declarative spec **[v0 — committed]**
The rubric lives in `rubric/steps.yaml` (steps, signals of good/poor, thresholds, applicability
gates, weights), not hardcoded in prompts. Benefits: auditable, diffable, community-governable,
and **`rubric_version` stamped on every assessment** so Phase-3 trends stay interpretable across
rubric changes. The engine compiles this spec into prompts + deterministic checks.

### B3. Don't collapse to one number too early — and design the scoring rule deliberately **[v0 — committed (profile-first, coverage/quality scores, `02` §4.2 + `02-mvp/f-score.md`); v1 (deliberate proper-scoring aggregation design)]**
> **2026-06-12 (PR-#1):** this item's strongest form was adopted — the categorical badge is dropped
> entirely; per-step profile + coverage/quality scores are the outputs. The what-if explainer became
> the score-impact ranking.

A single 0–100 invites **Goodhart's law** (optimize the score, not the science). Prefer:
- a **profile** (vector of per-step scores) as the primary object, with scalar summaries secondary;
- an explicitly documented, **proper-scoring-inspired** aggregation with per-context weights;
- **transparent scoring rules** with a score-impact ranking ("adding a posterior predictive check
  raises coverage to 8/9") — the scores should *teach*, not just label.
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

### C1. A library of deterministic detectors **[v0 — committed]**
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

### C3. Structure-aware parsing + supplements **[v0 — committed]**
Use **GROBID** (or similar) for TEI-structured parsing (sections, references, figure/table captions)
rather than flat text. Crucially, **parse supplements/appendices** — that's where diagnostics often
hide. The relevance/absence logic depends on having actually looked there.

### C4. Reach into the linked artifacts **[v2]**
When a paper links a repo (GitHub/OSF/Zenodo), optionally fetch it and check the *code* for what the
*paper* omitted: Stan/PyMC model files, seeds, `loo`/`bayesplot` calls, divergence handling. Many
"reporting gaps" are resolvable from artifacts and this bridges paper↔reproducibility.

### C5. Multi-format ingest **[v0 — committed]**
> Promoted from v1. ID input ships next to the dropzone; `fetcher.py` is shared verbatim with
> Phase 3. **`02-mvp/a-ingest-fetch.md`** (UI surface in `02-mvp/g-report-api-ui.md`).

Accept arXiv ID / DOI / OpenAlex ID (auto-fetch) in addition to PDF drag-drop — essential for Phase 3
batch ingestion anyway, so build the fetcher once and share it.

### C6. Caching & cost discipline **[v0 — committed]**
> Specified incl. cost ledger in the report footer and a budget guard. **`02-mvp-tool-plan.md` §3.5.**

Content-hash + `engine_version` + `rubric_version` cache key; a cheap relevance/classification screen
before the expensive full assessment. Makes both interactive use and corpus scale affordable, and
makes runs reproducible.

---

## D. Report & UX

### D1. Layered report for four audiences **[v0 — single report view + meta-research JSON (PR-#1 decision); v1 — full multi-view layering]** *(spec: `02-mvp/g-report-api-ui.md`)*
> The complete `ScoredResult` payload is persisted regardless of what the v0 UI shows, so the
> remaining views are pure presentation work later — and meta-research downstream loses nothing.
You named authors, reviewers, meta-researchers, and students. One report, layered views:
- **Coverage/quality scores + profile** (everyone, top).
- **Author mode:** prioritized, actionable fix-list (linter-style: error/warning/info), each with a
  concrete "how to fix" and a code/exemplar pointer.
- **Reviewer mode:** an exportable, evidence-cited critique block ready to paste into a review.
- **Student mode:** each step links to the methodological source and a "what good looks like"
  exemplar.
- **Meta-research mode:** the structured JSON (the same object Phase 3 stores).

### D2. Prioritized, severity-tiered suggestions **[v0 — committed]** *(spec: `02-mvp/g-report-api-ui.md`)*
Not a flat list. Rank by **impact × ease**. A missing posterior predictive check on the central model
is an *error*; an un-cited prior justification on a nuisance parameter is *info*. This is what makes
the report feel like a great linter rather than a nag.

### D3. Explicitly state what was done well, and why **[v0 — committed]** *(spec: `02-mvp/g-report-api-ui.md`)*
You asked for this and it matters beyond politeness: positive, *specific* reinforcement ("prior
predictive check in Fig 2 correctly revealed implausible effect sizes before fitting") teaches good
practice and builds author trust so the criticism lands. Generic praise is worse than none.

### D4. Re-check / diff mode **[v1]**
Re-upload a revised manuscript → show which issues resolved, which remain, coverage/quality delta. Directly
serves the author-self-check persona and creates a virtuous revise loop.

### D5. Relevance gate up front **[v0 — committed]** *(spec: `02` §2.1 + `02-mvp/d-screen-classify.md`)*
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

### E2. Field dashboards & opt-in certification **[v2]**
Public per-subfield dashboards could drive adoption — and a requestable, opt-in **certification**
for papers (à la reproducibility badges) gives authors a carrot. *(Note: v0 deliberately ships no
categorical verdict (2026-06-12); any future certification requires validated thresholds and
community governance first.)* Guard against misuse (F1).

### E3. Generalize beyond the Bayesian workflow **[moonshot]**
The architecture (declarative rubric spec + hybrid engine + corpus pipeline) is **workflow-agnostic**.
The same machine could score adherence to frequentist reporting standards, causal-inference
workflows, or ML-reproducibility checklists. VeriBayes is a first instance of a general
"methodology-conformance" instrument. Keep the core decoupled from the Bayesian specifics so this
stays reachable.

---

## F. Governance, ethics, and failure modes

### F1. Anti-gaming and anti-misuse, stated openly **[v0 — committed]** *(spec: `02` §7 — ships as `ETHICS.md` + report framing + "asserted-but-not-evidenced" policy)*
Scores can be (a) gamed (write the magic words without doing the work) and (b) weaponized (used to
bludgeon authors or gatekeep). Mitigations, documented up front: emphasize **formative feedback over
ranking**; require **evidence grounding** so keyword-stuffing is detectable; frame as a *report* not a
verdict; never auto-publish scores about third-party papers without care. Phase 3's public views need
an explicit ethics note.

### F2. Bias of the instrument **[v1]**
The tool may systematically favor certain tools/communities/languages (English, Stan-centric,
well-resourced labs with supplements). Audit engine error **by subfield and venue tier** (ties to A1)
and disclose. A meta-research tool that has un-audited bias would itself fail its own rubric's
"sensitivity analysis" step.

### F3. Privacy / local-first for unpublished work **[v0 — committed]** *(spec: `02` §7 — disclosure UI, local-only evidence-inventory mode, per-paper purge)*
Authors will upload **unpublished manuscripts**. Be explicit about what leaves the machine (PDF text
to the LLM API in the hybrid engine) and offer a clearer **local-only mode** (deterministic checks +
local model) for the privacy-sensitive. State the data handling plainly in the UI.

### F4. Full provenance/audit trail **[v1]**
Persist, per assessment: engine/rubric versions, model id, prompts, deterministic-check outputs,
evidence spans, and (if used) the adversarial verdicts. Anyone should be able to reconstruct *why*
the tool said what it said. This is the tool practicing the transparency it preaches.

---

## G. Post-v0 priorities (revised after the 2026-06-12 scope decision)

The v0 set is now: **A1, A3, A4, A5(scaffold), B1, B2, C1, C3, C5, C6, D1–D3, D5, F1, F3** — all
specified in the `02` spine + `02-mvp/` component subplans + `validation/protocol.md`. What remains,
in recommended order:

1. **C2 — figure/table vision parsing.** Now the single biggest *accuracy* lever left: a large share
   of diagnostics live only in trace plots, rank/ECDF plots, PPC overlays, and R-hat/ESS table
   columns. The gold set's Tier-C figure-only probes (`validation/protocol.md` §1) give *case-level*
   evidence of the cost (smoke tests, not rates); if C2 needs a quantified justification first, grow
   that stratum — labels there are cheap because only the figure-borne steps need rating.
2. **H3a (test-retest) + A2 + H1 — the reliability/uncertainty cluster.** First **test-retest
   reliability** (compute-only; runnable the day M7's harness lands — it bounds every engine-vs-human
   κ, so nothing else in this cluster is interpretable without it). Then make v0's per-judgment
   confidences *mean* something via the H1 calibration audit. Low-confidence absences already can't
   trigger Failed; this extends that discipline everywhere.
3. **A5 (active half) — close the learning loop.** The v0 scaffolding will have accumulated real
   overrides; turn them into gold-set growth, few-shot exemplars, and a release-time disagreement
   review.
4. **B3 + B5 — scoring-rule design + rigor-vs-reporting axes.** Best done with v0 experience: real
   reports will show where a single profile conflates "didn't do" with "didn't say."
5. **F4 — full provenance/audit trail.** v0's cache + cost ledger + `standards[]` already carry much
   of it; complete it (prompts, model ids, adversarial verdicts persisted per assessment).
6. **D4 — re-check / diff mode.** High author value, cheap once caching (C6) exists: re-upload →
   issue-level diff + score delta.
7. **F2 — bias audit.** Needs A1 data sliced by subfield/venue/language — schedule once the gold set
   passes ~50 papers.
8. **B4, E1, E2** — corpus-dependent; sequence with Phase 3.

## H. New suggestions (added with the v0 revision — future work)

### H1. Confidence calibration audit **[v1]**
A2 without this is decoration: check that stated confidences are *calibrated* (reliability diagrams,
Brier scores against gold-set correctness, per step). An engine that says "90% sure" and is right 60%
of the time is worse than no confidence at all. Cheap to compute once A1's harness exists; surfaces
on the calibration page next to κ.

### H2. Community gold-set consortium **[v1–v2, high leverage]**
The gold set is the project's scarcest asset and its best adoption vehicle. Recruit raters from the
communities that own these standards (Stan forums, Bayesian cog-sci lists, the workflow papers'
authors' orbits); in return, publish the labeled set + rating guide as a **citable community dataset**
(its own paper). Converts validation cost into credibility, co-authorship, and recruitment — and
de-risks the "two experts' idiosyncrasies" problem with a broader rater pool.

### H3. Engine reliability — test-retest first, then inter-model **[H3a: immediately post-M7; H3b: v1]**
The tool's own sensitivity analysis, in two stages:
- **H3a — test-retest (same engine, repeated runs).** LLM judgments vary run-to-run and across API
  model updates even at fixed prompts. Engine-self κ is the **noise floor under every engine-vs-human
  number in `validation/protocol.md` §3** — and it needs no human labels: two automated harness runs
  plus a κ. v0's harness already computes it (protocol §3); keep it tracked release-over-release.
- **H3b — inter-model agreement.** Run the identical rubric + prompts across ≥2 different LLMs on
  the gold set and report engine-model agreement (κ) alongside engine-human agreement. If judgments
  swing with the underlying model, that's measurement-instrument variance we must disclose — exactly
  the sensitivity analysis our own rubric (S8) demands of papers. Publish on the calibration page.

### H4. Golden-paper regression CI **[v1]**
Freeze a small, fixed mini-set (~5 papers spanning classes, plus a couple of decoys) and run the full
engine on every PR touching prompts, rubric, or engine code; diff the resulting reports structurally
(status/score changes) and block merges on unexplained regressions. This is the validation
protocol's regression rule (`validation/protocol.md` §3) made *continuous* instead of release-time,
and it doubles as living documentation of what each change does. **Leakage rule:** the mini-set must
be **disjoint from the (eventual) held-out gold set** — per-PR evaluation makes these papers a dev
set by construction, so they are either separately labeled or explicitly retired from validation
duty (cf. protocol §2.4: gold-set papers are likewise ineligible as few-shot exemplars).

### H5. LaTeX-source ingest for arXiv papers **[v1, cheap win]**
For arXiv IDs (C5 path), fetch the **source tarball** instead of (or alongside) the PDF: clean
section structure, exact equations and table values, no PDF-extraction noise — and figure *captions
+ included plot files* for later C2 use. Strictly better input for a large slice of our target
corpus at near-zero extra cost.

### H6. Harden "asserted-but-not-evidenced" into a detector class **[v1–v2]**
F1 (v0) states the policy; this builds the instrument: detectors that specifically look for
*named-but-unshown* practices ("we performed posterior predictive checks" with no figure, value, or
supplement reference) and feed a dedicated `asserted_not_evidenced` flag per step. As VeriBayes-like
tools become known, this is the gaming vector that will actually be probed — invest before it's
needed, and report its prevalence in Phase-3 corpus stats (it is itself an interesting
meta-research finding).

### H7. Prompt-injection robustness **[v1 — before E2's public dashboards/certification make the incentive real]**
The gaming surface in F1/H6 models *honest-language* gaming (magic words). The more potent attack on
an LLM judge reading author-controlled text is **embedded instructions targeting the judge**:
white-font text, PDF-comment payloads, "system:"-style strings in supplements coercing `done_well`
statuses or suppressing the adversarial pass. Once a VeriBayes score is worth anything, this is the
attack that will actually be tried. Build: (a) **injection red-teaming** — adversarial gold-set
variants with embedded instructions and an injection-success metric in the validation harness;
(b) mitigations — strict instruction/data separation in prompts, and the parser flags
invisible-text/comment spans as suspect evidence. v0 already discloses this as an open attack
surface in `ETHICS.md` (`02` §7); this item closes it.

### H8. Expand the rubric-profile family **[v1–v2]**
v0 ships two profiles (spine §2.3): `synthesis` (default; to be developed into *the gold standard*)
and `schad2021` (first source-pure profile, per the PR-#1 collaborator suggestion). Natural
expansions: `barg2021` (reporting-focused), `wambs` (checklist-style), `betancourt` (workflow-
phase-structured) — each a provenance filter over `steps.yaml`, cheap to add. Two real work items
beyond the filters: (a) **per-profile validation** — protocol metrics are profile-specific, so each
shipped profile eventually needs its own gold-set pass (until then it carries "profile not yet
validated"); (b) **cross-profile comparison view** — scoring one paper under several profiles
surfaces where the standards genuinely disagree, which is itself a meta-research finding (ties to
01 §5 "record, don't smooth").
