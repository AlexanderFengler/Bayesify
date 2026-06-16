# Phase 2 — MVP Tool: PDF → Bayesian-Workflow Report + Scores (spine)

> **2026-06-12 — decisions from collaborator review (PR #1, S. Radev):** (1) the categorical badge
> is **dropped** — per-step profile + coverage/quality scores are the outputs (§4.2); (2) v0 ships
> a **single report view** + the meta-research JSON, multi-view layering deferred (§4.1); (3) the
> rubric gains **profiles** — our synthesis (default, to become "the gold standard") plus
> source-pure profiles, first `schad2021` (§2.3); (4) reports are **template-rendered from the
> result payload** — the LLM never writes the report (§4.1; this was already the architecture, now
> stated unambiguously).

**Status:** Plan — decomposed: this spine + eight component subplans in [`02-mvp/`](02-mvp/) + the
validation protocol in [`../validation/protocol.md`](../validation/protocol.md)
**Depends on:** Phase 1 (the rubric `rubric/steps.yaml` and scoring rule)
**Feeds:** Phase 3 (the engine here is the shared `veribayes-core` used at corpus scale)
**Stack (decided):** FastAPI (Python) backend + React/Vite (TypeScript) frontend, local-first.
**Engine (decided):** Hybrid — Claude API for rubric judgment, grounded by deterministic checks.

---

## 1. Goal & v0 scope

A user drops a PDF (or pastes an arXiv ID / DOI); the tool returns a **step-wise report** grading
the paper against the Bayesian-workflow rubric, with **suggestions**, **explicit what-was-done-well
notes**, a **paper-type classification**, a **relevance assessment**, and two transparent summary
scores — **coverage** (share of applicable workflow steps present) and **quality** (weighted mean
step score). No categorical badge (PR-#1 decision; §4.2).

The twelve improvement items promoted to v0 (decision 2026-06-12) are **scope, not stretch goals**:

| Group | v0 commitments | Where specified |
|-------|----------------|-----------------|
| Trustworthy instrument | **A1** validation protocol + public surfacing · **A3** dual grounding (paper **and** literature) · **A4** adversarial self-verification · **A5** override scaffolding (learning loop mocked) | [`validation/protocol.md`](../validation/protocol.md) + [`h-validate-harness`](02-mvp/h-validate-harness.md) · §3.5 + [`e-assess`](02-mvp/e-assess.md) · [`e-assess`](02-mvp/e-assess.md) · [`g-report-api-ui`](02-mvp/g-report-api-ui.md) |
| Practical engine | **C5** multi-format ingest · **C6** caching + cost discipline | [`a-ingest-fetch`](02-mvp/a-ingest-fetch.md) · §3.5 |
| The report | **D1** single report view + meta-research JSON in v0 (multi-view layering → v1) · **D2** prioritized suggestions · **D3** specific praise · **D5** relevance gate up front | [`g-report-api-ui`](02-mvp/g-report-api-ui.md) (D1–D3) · §2.1 + [`d-screen-classify`](02-mvp/d-screen-classify.md) (D5) |
| Governance | **F1** anti-gaming/anti-misuse stated openly · **F3** privacy + local-only mode | §7 |

Plus the baseline already committed: applicability gating + rubric-as-spec (B1/B2), deterministic
detectors + structure-aware parsing incl. supplements (C1/C3), transparent per-step scoring,
persisted structured result.

**Deliberately deferred** (tracked in `04-improvements-and-extensions.md`): figure/table vision
parsing (C2), artifact/repo fetching (C4), subfield-calibrated thresholds (B4), the *active* half of
the A5 learning loop, corpus features. The MVP must, however, **architect for** these — clean seams,
no rewrites.

---

## 2. The two required up-front determinations

These run *before* the full assessment and are first-class outputs (per your spec). Implementation:
[`d-screen-classify`](02-mvp/d-screen-classify.md).

### 2.1 Relevance assessment (D5)
A gated classifier returning `{label: yes/partial/no, confidence, rationale, evidence_refs[]}`. A
paper with no Bayesian statistical methodology is **flagged and short-circuited** with a clear
explanation — never forced into a misleading score. Borderline cases (e.g., a single Bayes-factor
t-test) are labeled `partial` — "partially relevant — limited Bayesian content."

### 2.2 Paper-type classification
One of **empirical data analysis** / **numerical experiments–simulation** / **methodological work**
(mixed allowed: primary + secondary), with confidence + rationale + evidence. The class **drives
rubric applicability** (e.g., SBC near-mandatory for methodological work; PPCs on real data central
for empirical work) — the context-conditional gating from improvements §B1.

Both outputs condition everything downstream and are shown at the top of the report; the **scores**
are computed at the *end* of the pipeline ([`f-score`](02-mvp/f-score.md), §4.2).

### 2.3 Rubric profiles (added 2026-06-12, PR-#1 point 3)
Assessment is always conditioned on a named **rubric profile**:
- **`synthesis` (default)** — our merged, provenance-tracked rubric (`rubric/steps.yaml`), which we
  develop over time into *the gold standard*.
- **Source-pure profiles** — the workflow of one specific methodological paper, compiled as a
  **filter over `steps.yaml`'s per-step/per-threshold source provenance** (steps and thresholds
  grounded in that source only, with its terminology). **First: `schad2021`** (Schad, Betancourt &
  Vasishth 2021), per the collaborator suggestion.
Mechanics: the profile selects which steps/thresholds compile into e-assess prompts and the f
scoring tables; `ScoredResult.rubric_profile` records it; Phase 3 stores it alongside
`rubric_version` so corpus slices are profile-explicit. v0 ships both profiles; **validation
(protocol + gold set) runs on `synthesis` only in v0** — source-pure profiles display "profile not
yet validated" in the footer.

---

## 3. Architecture

### 3.1 Component diagram

```
 React/Vite SPA  ──upload──▶  FastAPI  ──enqueue──▶  Job worker
   • dropzone + ID input      • POST /api/papers      │
   • progress / SSE           • GET  /api/papers/:id  │ async (LLM calls are slow)
   • report views             • SSE  events           │
        ▲                                             ▼
        └──── report JSON ◀── veribayes-core (pure Python pkg):
                              [a]ingest → [b]parse → [c]detect → [d]screen+classify
                              → [e]assess → [f]score      (letters = subplans in 02-mvp/)
                              uses: rubric/steps.yaml · Claude API · detectors · cache
```

### 3.2 The crucial design rule: a UI-agnostic core package
**All real logic lives in `veribayes-core`, a plain Python package with no FastAPI imports.** The
backend is a thin transport layer; Phase 3's batch pipeline imports the same package. One rubric,
one engine, one scoring rule — used identically by the interactive tool and the corpus pipeline.

### 3.3 Repo layout

```
veribayes/
  core/                  # the engine (no web deps): ingest.py fetcher.py parse.py detectors/
                         #   screen.py classify.py assess.py score.py cache.py schema.py rubric/
  api/                   # FastAPI app (thin): routes, job queue, SSE, persistence, overrides
  web/                   # React/Vite SPA (report views, calibration page, privacy modes)
  rubric/steps.yaml      # the Phase-1 rubric spec (single source of truth)
  validation/            # protocol.md, rating-guide.md, goldset/, reports/
  ETHICS.md  PRIVACY.md  # F1/F3 governance artifacts (shipped, not aspirational)
  tests/eval/            # harness that runs the engine over validation/goldset
```

### 3.4 Pipeline at a glance (one subplan per stage)

| Stage | Component subplan | Consumes → produces (§5 contracts) | v0 items |
|-------|-------------------|-------------------------------------|----------|
| 0–1. Cache check; ingest & fetch | [`a-ingest-fetch`](02-mvp/a-ingest-fetch.md) | upload/ID → `SourceDoc` | C5, C6 |
| 2. Parse (incl. supplements) | [`b-parse`](02-mvp/b-parse.md) | `SourceDoc` → `ParsedDoc` | C3 |
| 3. Deterministic detectors | [`c-detectors`](02-mvp/c-detectors.md) | `ParsedDoc` → `Evidence[]` | C1 |
| 4–5. Relevance gate; classify | [`d-screen-classify`](02-mvp/d-screen-classify.md) | `ParsedDoc`+`Evidence[]` → `Relevance`, `PaperClass` | D5 |
| 6. Assess (grounded + adversarial) | [`e-assess`](02-mvp/e-assess.md) | all above → `StepAssessment[]` | A3, A4 |
| 7. Score | [`f-score`](02-mvp/f-score.md) | `StepAssessment[]` + `Relevance`/`PaperClass` + rubric → `ScoredResult` | B1, B3 |
| Transport, report, UI | [`g-report-api-ui`](02-mvp/g-report-api-ui.md) | `ScoredResult` (local mode: `ParsedDoc`+`Evidence[]`) → report views | D1–D3, A5, F3-UI, C6 |
| Validation harness (M7) | [`h-validate-harness`](02-mvp/h-validate-harness.md) | goldset labels + `ScoredResult`s → validation reports, `VALIDATION.md` | A1 |

After stage 3 the **local-only mode** (F3) is shippable: parse + detectors produce an *evidence
inventory* — what was found (where), what was not detected, where the engine looked — with no LLM
judgments, no applicability gating (that needs `PaperClass`), and no scores ("detection only, not
graded").

### 3.5 Cross-cutting principles (bind every component)
- **Grounding in the sources, plural (A3):** every finding cites **the paper** (evidence spans;
  absence claims must enumerate *where the engine looked*) **and the methodological literature**
  (structured `standards[]` refs compiled from `rubric/steps.yaml`, with verified/unverified
  provenance status). The reader can always answer "where in *my paper*?" and "says *who*?".
- **Caching & cost (C6):** full-result cache key = `sha256(bytes) × engine_version × rubric_version
  × mode`; stage-level sub-caches survive engine upgrades (parse: `sha256 × parser ×
  parser_version`; detect: `× detector_versions`); cheap relevance screen gates expensive stages;
  every LLM call metered into a **cost ledger** (shown in the report footer); configurable budget
  guard. Cache hits are byte-identical replays → reproducible assessments.
- **Stubs-first additivity:** from M1 a stub engine returns a fixed `ScoredResult`, so the app is
  end-to-end demoable at all times; each component lands by replacing its stub, tested against
  recorded fixtures of its input contract — never requiring the live upstream chain.

---

## 4. Report, scores, and the result object

### 4.1 Report at a glance
Header: **coverage + quality scores, step profile, relevance, paper type, rubric profile** (with
rationale). Per applicable step:
status (+confidence) · **what was done well** (specific, evidence-cited — D3) · **what to improve**
(error/warning/info, ranked impact×ease — D2) · evidence spans · standards applied · [Disagree?]
override control. Footer: engine/rubric versions · cost · **development-set agreement metrics +
domain-validity line** (→ `/calibration`) · "formative report, not a verdict" (→ `ETHICS.md`).
**v0 ships one view** (PR-#1 decision): a single **report view** (author/reviewer-oriented) plus
the **meta-research JSON** export — the `ScoredResult` payload is stored complete so student/
multi-view layering (D1's full four-audience design) can be added later as pure presentation, and
downstream meta-research loses nothing. **Rendering rule, stated unambiguously (PR-#1 point 4):
the LLM never writes the report.** It fills structured `StepAssessment` fields; the report is a
fixed markdown/JSX template rendered programmatically from the result payload. Full spec:
[`g-report-api-ui`](02-mvp/g-report-api-ui.md).

### 4.2 Scoring (no badge — 2026-06-12 PR-#1 decision)
The categorical Verified/Shaky/Failed badge is **dropped**. Outputs, in order of primacy:
- **Step profile** — status per applicable step (`done_well | partial | missing | not_applicable`
  + confidence): the differentiated, per-step scoring the collaborator review asked for.
- **Coverage** — share of applicable steps *present* (done_well ∪ partial), reported as an
  **uncertainty-honest range** when low-confidence absences exist (e.g., "6–7 / 9") — a
  low-confidence absence never silently lowers the headline number.
- **Quality** — weighted mean step sub-score (weights per paper class from the rubric scoring
  block).
The rubric's "essential" flags become **expectation tiers** (expected/recommended) driving
suggestion *severity*, not a verdict; a **score-impact ranking** (re-scoring-verified deltas)
replaces the badge-era what-if explainer and feeds D2's ordering. Spec:
[`f-score`](02-mvp/f-score.md).

### 4.3 The result object & stage contracts (the spec that keeps components independent)
Defined once in `core/schema.py` (pydantic); every subplan codes against these, tests against
recorded fixtures of them. Phase 3 stores them as-is (`03-ingestion-corpus-plan.md` §4 mirrors this).

```
SourceDoc      {sha256, ids{doi?, arxiv_id?, openalex_id?}, version_label, source, fetched_at}
ParsedDoc      {source, sections[{id, kind: body|abstract|caption|supplement|references,
                title, text, page_spans}], parser, parser_version}
Evidence       {detector_id, detector_version,
                kind: software_mention|method_mention|diagnostic_value|diagnostic_mention|
                      workflow_signal|sampler_config|open_science|absence_search,
                value?, span{section_id, page, quote}}
                -- detectors (c) emit all kinds except absence_search, which e-assess mints
                -- for its where-looked enumeration
Relevance      {label: yes|partial|no, confidence, rationale, evidence_refs[]}
PaperClass     {primary, secondary?, confidence, rationale, evidence_refs[]}
StepAssessment {step_id, applicable, applicability_reason, status, confidence,
                evidence[], standards[], did_well[], suggestions[{severity, text, how_to, ease}],
                adversarial_verdict{challenged, refuted, notes}}
GateFacts      {inference_method: mcmc|hmc_nuts|variational|exact_analytic|unstated,
                n_models, bf_claimed, prior_informativeness}   -- emitted by e, consumed by f (G6)
ScoredResult   {relevance, paper_class, gate_facts, step_assessments[], profile,
                coverage{present, applicable, strict, lenient}, quality_score, score_impacts[],
                engine_version, rubric_version, rubric_profile, cost_ledger, validation_ref}
```
Overrides (A5) live in a **separate table keyed to the assessment** — engine output is never
mutated; expert corrections sit alongside it. On a relevance-`no` short-circuit, `paper_class` and
the scores are **null** and `step_assessments` empty: the g job loop persists that `ScoredResult`
directly from d's output (f is never invoked on irrelevant papers).

---

## 5. Components & build order

Each subplan follows one template: *header block (Milestone / v0 items covered / Contract / Depends
on & stubs) · Purpose · Design · Interface contract · Test plan · Definition of done · Out of scope
(deferred).* Components are **additive**: each is independently testable against fixture inputs and
lands behind the always-working stub app.

| Milestone | Builds | Component(s) |
|-----------|--------|--------------|
| **M1** | Skeleton & contracts: `schema.py`, rubric loader, API job loop + SSE, stub engine, dropzone, `ETHICS.md`/`PRIVACY.md` drafts | spine of [`g`](02-mvp/g-report-api-ui.md) |
| **M2** | Ingest + parse + cache | [`a`](02-mvp/a-ingest-fetch.md), [`b`](02-mvp/b-parse.md) |
| **M3** | Detectors → **local-only mode shippable** | [`c`](02-mvp/c-detectors.md) |
| **M4** | Screen + classify | [`d`](02-mvp/d-screen-classify.md) |
| **M5** | Assess (grounded + adversarial) + scoring (profile, coverage, quality) | [`e`](02-mvp/e-assess.md), [`f`](02-mvp/f-score.md) |
| **M6** | Full report UX (`g`) **+ the validation capstone built fake-harness-first** (V0–V6): the human-report contract, pure metric engine, report builder + 3-artifact emitter, harness + honesty firewall, blind rating producer, and calibration view — all shippable + critique-able on fabricated data **[done 2026-06-16]** | [`g`](02-mvp/g-report-api-ui.md), [`h`](02-mvp/h-validate-harness.md) |
| **M7** | The *live* validation run + its prerequisites: **auto-consensus assembly** (no human adjudication UI — see `h` revisions), real-engine pairing + sha256 hard-fail, test-retest κ, durable rating persistence, selection provenance (seeded draw), then **execute the protocol** over the real gold set → first `VALIDATION.md`. **Gated on rater recruitment (G4), not code.** | [`h`](02-mvp/h-validate-harness.md) per [`validation/protocol.md`](../validation/protocol.md) |

**v0 is not "done" until M7's live run executes.** The M6 fake-harness build means the engineering for M7 is mostly in place; the binding constraint is the human pipeline (recruit raters → blind-rate → assemble → run).

### Build gates (2026-06-12 three-lens review — [full report](reviews/2026-06-12-three-lens-review.md))

Verified conditions from the architecture / statistical-methodology / adversarial review. None
block M1; each must be resolved **before the milestone it names**. The review's consensus-strengths
list is equally binding: the decomposition, contracts, and validation-metric core are not to be
churned while closing these.

*Updated 2026-06-12 after the PR-#1 badge decision: G5 no longer needs badge bands (coverage/quality
definitions instead); G6's "essentialness" now means expectation tier/severity, not a Failed
verdict; G7 unchanged (a wrongful per-step "missing" still mis-scores VI papers). The gates' files
and milestones stand.*

| Gate | Resolve by | What |
|------|-----------|------|
| G1 | **M1** contract freeze | Define `engine_version` composition; **pin judge/cheap-tier model snapshot IDs** into it (or the cache key + `ScoredResult`); protocol rule: model change invalidates `VALIDATION.md` |
| G2 | **M2**, before cache.py | Cache key gains parser identity (or degraded-parser runs aren't cached) and a rerun-override dimension |
| G3 | **M2**, first fixture commit | Fixture licensing: committed fixtures CC-BY/CC0 with license manifest; everything else fetch-by-script + sha256 pin (incl. derived full-text fixtures) |
| G4 | **start by M2** (gates M7) | Name validation owner + expert-hours budget; **begin rater recruitment now** (months of lead time); ≥1 independent rater per paper; prompt author rates only a minority. (Consensus is now derived mechanically — no human adjudication — so the "never adjudicates own disagreements" rule is moot; the firewall against engine-anchoring is structural, not procedural.) |
| G5 | **M5** hard gate (start at M1) | Author the rubric machine-half: scoring block, machine-evaluable `na_when`/`mandatory_when` predicates, synonym lists, step→detector map |
| G6 | **M5** (schema field at M1/M2) | Evidence-conditioned essentialness (BF claim ⇒ S6/S8 mandatory) via a compact `gate_facts` object in §4.3 consumed by `score()` |
| G7 | **M5** / rubric freeze | VI-specific S4 criteria (ELBO convergence, PSIS k-hat — Yao et al. 2018, SBC sub-branch) so VI papers aren't wrongly Failed |
| G8 | before **M5** prompts; hard before any expert rates | Run the S4/S6 threshold citation pass; freeze rubric v1.0 |
| G9 | **M7**, before metrics | Protocol amendment: paper-level **cluster bootstrap** for pooled metrics; precise "mean step-κ" definition |

(G10 — misclassification-corrected prevalence estimators — gates **Phase-3 M1**, recorded in
`03-ingestion-corpus-plan.md` §2.2.)

---

## 6. Validation (A1)

The full protocol — tiered gold set, blind dual-expert rating, two-stage agreement metrics,
both-direction absence errors, CIs everywhere, dev-set honesty rule, and the calibration-page /
report-footer / `VALIDATION.md` surfacing — lives in
[`validation/protocol.md`](../validation/protocol.md). It is a v0 deliverable and the release gate.

---

## 7. Governance (F1 + F3 — shipped artifacts, not promises)

- **`ETHICS.md` (F1):** formative-not-verdict framing (the scores attest *workflow practice as
  detectable in the documents*, not correctness — reinforced by the 2026-06-12 removal of the
  categorical badge); the gaming surface documented — magic words
  without evidence are flagged **"asserted but not evidenced"** (≤ `partial` credit; detector-class
  hardening tracked as improvements §H6), and **prompt injection** is disclosed as an open attack
  surface until §H7 red-teaming closes it; misuse guidance (structured aid, not an auto-reject
  machine; no auto-published third-party scores); known biases disclosed (English/Stan-ecosystem
  centricity, text-only limits) with planned mitigations (F2, C2).
- **`PRIVACY.md` + UI (F3):** in full mode, extracted text goes to the Anthropic API — disclosed at
  point of use (first-run modal + persistent mode indicator); all storage local; no telemetry;
  **local-only mode** per paper (evidence inventory, no LLM, no scores); **per-paper purge** deletes
  everything derived.

---

## 8. Key risks → mitigations
- **Hallucinated absence claims** → detector grounding + enumerate-where-looked (A3) + adversarial
  pass (A4) + absence-FPR *and* absence-miss-rate tracked in validation (protocol §3).
- **Penalizing legitimate deviations** → applicability gating (B1); N/A and not-reported are
  distinct from not-done.
- **Diagnostics hidden in figures/supplements** → parse supplements now (C3); Tier-C probes make
  the text-only cost visible (protocol §1); vision parsing (C2) is the top post-v0 priority.
- **Privacy of unpublished manuscripts** → §7: disclosure + local-only mode + purge, all in v0.
- **Cost/latency** → §3.5: caching, cheap-screen-first, cost ledger + budget guard (C6).
- **Validation can't keep pace with iteration** → automated harness (M7); gold set grows via
  override-*nominated* papers re-rated blind (protocol §2.4); regression rule + dev-set/holdout
  split keep "validated" honest (protocol §3–4).
