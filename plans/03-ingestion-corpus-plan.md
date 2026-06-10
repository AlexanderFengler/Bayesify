# Phase 3 — Corpus Ingestion, Sampling, Ontology & Meta-Analysis

**Status:** Plan
**Depends on:** Phase 1 (rubric & scoring rule), Phase 2 (analysis engine `veribayes-core`)
**Owner:** TBD

---

## 1. Goal

Turn the single-paper analyzer from Phase 2 into a **corpus-scale meta-research instrument**. We
ingest a defensibly-sampled set of papers from a discipline (starting with **computational
neuroscience** and **computational cognitive science**), run each through the Phase-2 engine, store
the structured results in a queryable database with a light **ontology**, and expose
**visualizations** of how Bayesian-workflow quality and adoption vary over **time**, across
**subfields**, and in **clusters**.

The two hard requirements you set are treated as first-class design problems, not afterthoughts:

- **A corroborated, citable sampling methodology** (so corpus-level claims are statistically
  defensible and reproducible).
- **A deduplication mechanism** robust to the sampler being run repeatedly over time.

---

## 2. Why sampling rigor matters here

A corpus claim like *"42% of computational-cognitive-science papers using Bayesian methods report
convergence diagnostics"* is only meaningful if (a) the denominator is a **well-defined, reproducible
population**, (b) the sample is **drawn by a documented probabilistic mechanism** (so it generalizes
and has quantifiable uncertainty), and (c) repeated draws don't silently re-count the same papers.
This is the standard meta-research / metascience bar. We adopt established guidance rather than
inventing our own.

### 2.1 Sampling frame and population definition

1. **Define the population precisely.** Discipline → venue set → time window → inclusion/exclusion
   criteria, all written down before sampling. Follow **PRISMA 2020** (Page et al. 2021, *BMJ*) and
   the search-reporting extension **PRISMA-S** (Rethlefsen et al. 2021, *Systematic Reviews*) for
   transparent, reproducible specification of the search and screening pipeline. Even though we are
   not doing a clinical systematic review, PRISMA's identification → screening → eligibility →
   inclusion flow is the recognized standard for reproducible corpus construction, and the PRISMA
   flow diagram is a clean way to report counts at each stage.
2. **Operationalize the venue set.** Start with a curated journal/venue list per subfield
   (e.g., *PLOS Computational Biology*, *Journal of Mathematical Psychology*, *Computational Brain &
   Behavior*, *eLife* neuro, *Journal of Neuroscience* computational sections, NeurIPS/CogSci
   proceedings, etc.). The exact list is a reviewed artifact checked into the repo
   (`corpus/venues.yaml`) so the frame is auditable and versioned.
3. **Source of record.** Use a metadata provider with stable IDs and programmatic access —
   **OpenAlex** (open, no key, rich concept tagging and citation graph) as primary; **Crossref**
   and **Semantic Scholar** as cross-checks. Record the query, provider, and snapshot date for
   every retrieval.

### 2.2 The sampling design

We do **not** analyze "all papers." We draw a **probability sample** so estimates carry
confidence intervals and the cost stays bounded.

- **Stratified random sampling** is the workhorse: stratify by **subfield × time-bin × venue-tier**,
  then draw at random within strata. Stratification guarantees coverage of small-but-important
  cells (e.g., early years, niche subfields) and reduces variance of subgroup estimates. This mirrors
  established large-scale meta-research practice — e.g., stratified random samples of tens of
  thousands of papers across disciplines and years are a documented design in metascience.
- **Two-phase / double sampling** for expensive labels: cheaply classify a large phase-1 sample
  with the LLM screen (is it Bayesian at all? which subfield?), then draw a phase-2 subsample for
  the full, costly workflow assessment, and use the phase-1 data to correct estimates (double
  sampling with imputation; cf. Chen et al. 2015, *PLOS ONE*, "Double Sampling with Multiple
  Imputation"). This is how you answer corpus questions without running the full engine on every
  paper.
- **Pre-register the design.** Sample size per stratum, RNG seed, and the estimand (what proportion
  / mean we're estimating, with target CI width) are fixed in `corpus/sampling_plan.yaml` before
  drawing, and the realized draw is logged. Reproducible-by-seed.
- **General sampling hygiene** follows Baltes & Ralph 2022 ("Sampling in Software Engineering
  Research", *Empirical Software Engineering*) — a clear, citable treatment of probability vs.
  non-probability sampling, sampling frames, and how to report them, applicable beyond SE.

> **Estimands we can defend with this design:** prevalence of Bayesian-method use over time;
> per-step adoption rates (e.g., % reporting posterior predictive checks) with CIs; mean per-step
> scores by subfield; trend slopes around landmark methodological publications.

### 2.3 Deduplication (robust to repeated sampling)

Because the sampler is **run repeatedly** as the literature grows, we must never double-count a
paper, and we must recognize the *same work* across providers and versions (preprint vs. published,
DOI variants, arXiv vs. journal).

Layered matching, strongest signal first (mirrors validated systematic-review dedup tooling such as
**SRA-DM**, Rathbone et al. 2015, *Systematic Reviews* — 84% sensitivity / 100% specificity, and
the more recent **ASySD**, Hair et al. 2023, which removes >95% of duplicates at >0.999 specificity):

1. **Exact key match** on normalized **DOI** (lowercased, de-versioned), arXiv ID, OpenAlex ID,
   PMID. A unique persistent identifier is the cornerstone of reliable dedup.
2. **Preprint↔publication linking** via provider cross-references (OpenAlex/Crossref relations) and
   matching titles+authors+year.
3. **Fuzzy match** fallback for records lacking IDs: normalized-title similarity (token-sorted
   Levenshtein / Jaro-Winkler) above a tuned threshold **AND** first-author surname + year match, to
   keep precision high. Borderline pairs are queued for human confirmation rather than
   auto-merged — we bias toward precision so we never silently merge two distinct papers.
4. **Stable `work_id`** (a content+identifier hash) is assigned once and reused; re-ingestion checks
   this table first. A `dedup_decisions` audit log records every merge with the rule that fired, so
   decisions are reviewable and reversible.

We will report dedup performance (precision/recall on a hand-labeled validation set of ~200 pairs)
the way the dedup-tooling literature does, so our pipeline's accuracy is itself documented.

---

## 3. Architecture

```
                ┌─────────────────────────────────────────────────────────┐
                │  Sampling service                                        │
                │  • build frame from OpenAlex/Crossref (venues × years)   │
                │  • stratified draw (seeded)  → candidate list            │
                └───────────────┬─────────────────────────────────────────┘
                                │ work records (metadata)
                ┌───────────────▼──────────┐
                │  Dedup / identity service │  ── work_id, dedup_decisions
                └───────────────┬──────────┘
                                │ new works only
                ┌───────────────▼──────────┐     ┌──────────────────────────┐
                │  Acquisition              │────▶│  PDF/text store (local)   │
                │  • OA full text / PDF     │     └──────────────────────────┘
                └───────────────┬──────────┘
                                │
                ┌───────────────▼─────────────────────────┐
                │  Phase-2 engine (veribayes-core)         │  ← SAME code path as the single-paper tool
                │  relevance screen → classify → assess    │
                └───────────────┬─────────────────────────┘
                                │ structured results (per-step assessments, scores, badge)
                ┌───────────────▼──────────┐
                │  Corpus DB (DuckDB/SQLite)│  + ontology tables
                └───────────────┬──────────┘
                                │
                ┌───────────────▼──────────┐
                │  Meta-analysis API + viz  │  (React dashboards; reuses Phase-2 frontend shell)
                └──────────────────────────┘
```

**Key principle:** the corpus pipeline calls the **exact same `veribayes-core`** engine as the
single-paper tool. There is one definition of the rubric and scoring, used in both phases — no drift.

---

## 4. Data model

A relational store (DuckDB for analytics-friendly columnar queries locally; SQLite acceptable for the
MVP corpus). Schema is intentionally **rubric-agnostic**: workflow steps are *rows*, not columns, so
the schema never changes when the Phase-1 rubric evolves.

```
work(work_id PK, doi, arxiv_id, openalex_id, pmid, title, abstract,
     year, venue, venue_tier, authors_json, oa_status, retrieved_at, source_provider)

sampling_draw(draw_id PK, sampling_plan_version, stratum_key, seed,
              drawn_at, work_id FK)              -- which draw pulled this work, for reproducibility

dedup_decision(id PK, work_id FK, merged_into_work_id, rule, score, decided_at, decided_by)

assessment(assessment_id PK, work_id FK, engine_version, rubric_version,
           created_at, relevance_label, relevance_rationale,
           paper_class,            -- empirical | numerical-experiment | methodological (Phase 2 classifier)
           overall_score, badge)   -- badge: verified | shaky | failed

step_assessment(id PK, assessment_id FK, step_id, applicable BOOL,
                status,             -- e.g. done_well | partial | missing | not_applicable
                score, weight, evidence_json, suggestions_text)
                -- step_id references the Phase-1 rubric step registry (rubric/steps.yaml)

ontology_term(term_id PK, kind, label, parent_id)     -- kind: subfield | method | software | model_family
work_term(work_id FK, term_id FK, confidence, source) -- tags linking works to ontology
```

`engine_version` + `rubric_version` are stored on every assessment so corpus trends remain
interpretable when the rubric is updated (we can filter to a fixed rubric version, or re-run).

---

## 5. Ontology / memory system

A pragmatic, lightweight ontology — enough structure for meaningful slicing, not a full OWL effort:

- **Dimensions:** `subfield` (comp-neuro, comp-cog-sci, and their sub-areas — e.g.
  reinforcement-learning models, drift-diffusion / evidence-accumulation, Bayesian models of
  cognition, neural population models), `method`/`model_family` (hierarchical GLMM, DDM, GP, state-space,
  etc.), `software` (Stan, brms, PyMC, JAGS, TensorFlow Probability, NumPyro, HDDM), and
  `inference` (MCMC/NUTS, variational, etc.).
- **Population of terms:** seed manually + extend semi-automatically from OpenAlex concepts and from
  software/method mentions detected by the Phase-2 deterministic checks (e.g., a Stan detection
  auto-tags `software:Stan`). Every auto-tag is stored with `confidence` and `source` and is
  reviewable.
- **"Memory" angle:** the ontology + assessment store *is* the project's accumulating knowledge base.
  Re-ingestion enriches existing works (new evidence, newer engine version) rather than overwriting —
  assessments are append-only and versioned, giving a longitudinal record per work and per field.

---

## 6. Visualizations (meta-analysis dashboards)

All are corpus queries over the schema above, rendered in the React app (D3 / deck.gl / Observable
Plot — chosen with Phase-2's frontend already in React).

1. **Quality-over-time** — papers binned on a time axis; y = mean overall score (or per-step adoption
   rate) with CIs from the sampling design. **Landmark overlay:** key methodological publications
   (Gelman et al. *Bayesian Workflow* 2020; Vehtari et al. R-hat 2021; Kruschke BARG 2021; WAMBS;
   Schad et al. 2021; PSIS-LOO 2017; SBC 2018) placed as dated vertical markers, so the viewer can
   eyeball whether adoption inflects after a standard is published. (Causal claims stay cautious —
   this is descriptive.)
2. **Subfield scorecards** — small-multiples / bar charts of mean per-step scores by subfield, to see
   which communities are strong on, say, posterior predictive checks but weak on prior sensitivity.
3. **Per-step adoption heatmap** — steps (rows) × time-bins or subfields (cols), cell = % of relevant
   papers doing that step well. Quickly surfaces systematically-skipped steps.
4. **Clusters** — embed papers (workflow-fingerprint vector of per-step statuses, optionally
   concatenated with a text embedding) and project (UMAP/t-SNE) to reveal "practice profiles."
   Cluster membership is itself a finding (e.g., a cluster that converges but never does PPCs).
5. **Relevance prevalence** — % of sampled papers that are "Bayesian-relevant at all," over time and
   by subfield, **with CIs** (this is exactly what the probability sample buys us). Directly answers
   "is Bayesian methodology spreading in this field?"
6. **Corpus map / DB explorer** — an interactive table + citation-graph view (works as nodes, edges
   from the citation graph) colored by badge, for drilling from a field-level pattern down to
   individual papers and their reports.

Every chart links back to the underlying papers and their Phase-2 reports (drill-down), and exposes
the sampling/CI caveats inline so meta-researchers don't over-read noise.

---

## 7. Reproducibility & provenance

- Everything seeded and versioned: `sampling_plan.yaml`, `venues.yaml`, RNG seed, provider snapshot
  dates, `engine_version`, `rubric_version`.
- A **PRISMA-style flow report** auto-generated per corpus build (identified → deduped → screened →
  assessed → included counts), exportable for a methods section.
- The corpus build is a **reproducible pipeline** (e.g., a `make corpus` / DVC or simple task runner)
  so a collaborator can reconstruct the exact sample from the config + seed.

---

## 8. Build order (Phase 3)

1. **M1 — Frame + sampler.** OpenAlex venue/year frame builder; stratified seeded draw; `sampling_plan.yaml`. Output: candidate list + PRISMA counts.
2. **M2 — Dedup/identity service.** ID-key + fuzzy matching; `work_id` assignment; validation set + precision/recall report.
3. **M3 — Acquisition + batch engine.** OA full-text fetch; batch-run `veribayes-core`; persist assessments. Two-phase sampling wired in (cheap screen → costly subsample).
4. **M4 — Corpus DB + ontology.** Schema, ontology seeding, auto-tagging from deterministic checks.
5. **M5 — Dashboards.** Quality-over-time + landmarks, subfield scorecards, adoption heatmap, relevance prevalence, cluster view, DB explorer.
6. **M6 — Reproducibility wrapper.** `make corpus`, PRISMA report generator, docs.

---

## 9. Open questions / risks

- **Full-text access:** paywalled PDFs limit the frame. Mitigation: restrict estimands to the
  open-access subset and *report that boundary*, or integrate institutional access where permitted.
  OA-only sampling introduces a known bias to disclose.
- **LLM cost at corpus scale:** controlled by two-phase sampling + caching keyed on `work_id` +
  `engine_version` (never re-assess unchanged work/engine pairs).
- **Engine reliability as a measurement instrument:** corpus claims are only as good as the engine's
  accuracy. Phase 2 must ship a validation set (human-vs-engine agreement per step); corpus reports
  cite that accuracy as measurement error. See improvements doc §"Calibration & validation."
- **Subfield taxonomy contention:** subfield boundaries are fuzzy; the ontology is versioned and
  decisions documented.

---

### Citations (Phase-3 methodology)

- Page MJ et al. (2021). *The PRISMA 2020 statement.* BMJ 372:n71.
- Rethlefsen ML et al. (2021). *PRISMA-S.* Systematic Reviews 10:39.
- Rathbone J et al. (2015). *Better duplicate detection… SRA-DM.* Systematic Reviews 4:6.
- Hair K et al. (2023). *ASySD: Automated Systematic Search Deduplicator.* BMC Biology / preprint.
- Chen Q et al. (2015). *Double Sampling with Multiple Imputation…* PLOS ONE.
- Baltes S, Ralph P (2022). *Sampling in Software Engineering Research.* Empirical Software Engineering 27:94.

> Exact citation strings to be finalized against the Phase-1 reference manager export.
