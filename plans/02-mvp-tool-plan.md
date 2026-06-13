# Phase 2 — MVP Tool: PDF → Bayesian-Workflow Report + Badge

**Status:** Plan
**Depends on:** Phase 1 (the rubric `rubric/steps.yaml` and scoring rule)
**Feeds:** Phase 3 (the engine here is the shared `veribayes-core` used at corpus scale)
**Stack (decided):** FastAPI (Python) backend + React/Vite (TypeScript) frontend, local-first.
**Engine (decided):** Hybrid — Claude API for rubric judgment, grounded by deterministic checks.

---

## 1. Goal & scope of the MVP

A user drag-and-drops a PDF; the tool returns a **step-wise report** grading the paper against the
Bayesian-workflow rubric, with **suggestions**, **explicit what-was-done-well notes**, a **paper-type
classification**, a **relevance assessment**, and an overall **badge: Verified / Shaky / Failed**.

**In scope (v0).** The twelve improvement items promoted to v0 (decision 2026-06-12) are **scope,
not stretch goals**. Grouped:

| Group | v0 commitments | Where in this plan |
|-------|----------------|--------------------|
| Trustworthy instrument | **A1** validation protocol vs human experts + public surfacing · **A3** dual grounding (paper evidence **and** methodological sources) · **A4** adversarial self-verification · **A5** override scaffolding (learning loop mocked) | §7 · §3.5/§4.1 · §3.4 stage 6 · §8 |
| Practical engine | **C5** multi-format ingest (PDF / arXiv / DOI / OpenAlex) · **C6** caching + cost discipline | §3.4 stage 1 · §3.6 |
| The report | **D1** four layered views · **D2** prioritized severity-tiered suggestions · **D3** specific what-was-done-well · **D5** relevance gate up front | §4 (D1–D3) · §2.1 (D5) |
| Governance | **F1** anti-gaming/anti-misuse stated openly · **F3** privacy disclosure + local-only mode | §10 · §9 |

Plus the baseline: paper-type classification, badge with transparent thresholds, persisted
structured result (the object Phase 3 stores), and the already-committed B1/B2 (applicability
gating, rubric-as-spec) and C1/C3 (deterministic detectors, structure-aware parsing incl.
supplements).

**Deliberately deferred** (tracked in `04-improvements-and-extensions.md`): figure/table vision
parsing (C2), artifact/repo fetching (C4), subfield-calibrated thresholds (B4), the *active* half of
the A5 learning loop, corpus features. The MVP must, however, **architect for** these — clean seams,
no rewrites.

---

## 2. The two required up-front determinations

These run *before* the full assessment and are first-class outputs (per your spec):

### 2.1 Relevance assessment ("should this paper be analyzed as Bayesian workflow at all?")
A gated classifier returning `{relevant: yes/no, confidence, rationale}`. A paper with no Bayesian
statistical methodology is **flagged and short-circuited** with a clear explanation — never forced
into a misleading score. Grounded by deterministic signals (mentions of priors/posteriors, Bayesian
software, MCMC/VI) plus LLM judgment. Borderline cases (e.g., a single Bayes-factor t-test) are
labeled "partially relevant — limited Bayesian content" rather than a hard yes/no.

### 2.2 Paper-type classification (rigorous taxonomy)
Classify into one of (with confidence + rationale + evidence spans):
- **Empirical data analysis** — fits Bayesian models to real observed data to draw substantive
  conclusions.
- **Numerical experiments / simulation study** — evaluates methods/models on simulated or benchmark
  data (the "truth" is known/controlled).
- **Methodological work** — proposes/analyzes a new model, prior, algorithm, or diagnostic.
Allow **mixed** (primary + secondary type) — many papers are methodological *and* include an
empirical application. The class **drives rubric applicability** (e.g., SBC is near-mandatory for
methodological work, optional for routine empirical fits; predictive checks on real data are central
for empirical work). The full decision rules live with the rubric (Phase 1) — this is exactly the
context-conditional gating from improvements §B1.

### 2.3 These two outputs condition everything downstream
The relevance result can stop the pipeline; the paper-type result selects which rubric steps are
**applicable / weighted / N-A**. Both are shown prominently at the top of the report with their
rationale.

---

## 3. Architecture

### 3.1 Component diagram

```
 React/Vite SPA  ──upload──▶  FastAPI  ──enqueue──▶  Job worker
   • dropzone                 • POST /api/papers      │
   • progress / SSE           • GET  /api/papers/:id  │ async (LLM calls are slow)
   • report views             • SSE  /api/papers/:id/events
        ▲                                             │
        └──────────────── report JSON ◀──────────────┘
                                                      ▼
                       ┌─────────────  veribayes-core (pure Python pkg)  ─────────────┐
                       │  ingest → parse → detect → screen → classify → assess → score │
                       └──────────────────────────────────────────────────────────────┘
                                   │ uses                         │ uses
                          rubric/steps.yaml (Phase 1)     Claude API + detectors
```

### 3.2 The crucial design rule: a UI-agnostic core package
**All real logic lives in `veribayes-core`, a plain Python package with no FastAPI imports.** The
backend is a thin transport layer; Phase 3's batch pipeline imports the same package. One rubric, one
engine, one scoring rule — used identically by the interactive tool and the corpus pipeline. This is
what makes Phase 3 cheap and keeps corpus results consistent with single-paper results.

### 3.3 Repo layout

```
veribayes/
  core/                     # veribayes-core — the engine (no web deps)
    ingest.py               #   multi-format ingest: PDF bytes | arXiv ID | DOI | OpenAlex ID (C5)
    fetcher.py              #   ID → OA PDF resolution (arXiv API, OpenAlex/Unpaywall, Crossref) — shared verbatim with Phase 3
    parse.py                #   GROBID/structure-aware → sections, captions, refs, supplements
    detectors/              #   deterministic checks (software, diagnostics, workflow signals)
    screen.py               #   relevance gate (§2.1)
    classify.py             #   paper-type classifier (§2.2)
    assess.py               #   per-step LLM judgment, grounded by detectors + adversarial check
    score.py                #   applicability gating + scoring rule + badge
    cache.py                #   content-hash × engine_version × rubric_version × mode cache + cost ledger (C6)
    schema.py               #   pydantic models for the result object
    rubric/                 #   loads rubric/steps.yaml; compiles to prompts + checks
  api/                      # FastAPI app (thin): routes, job queue, SSE, persistence, overrides (A5)
  web/                      # React/Vite SPA (report views, calibration page, privacy modes)
  rubric/steps.yaml         # the Phase-1 rubric spec (single source of truth)
  validation/               # A1: protocol.md, rating-guide.md, goldset/ labels, reports/ per engine version
  ETHICS.md                 # F1: responsible-use & anti-gaming statement (shipped, not aspirational)
  PRIVACY.md                # F3: data-handling statement mirrored in the UI
  tests/
    eval/                   # harness code that runs the engine over validation/goldset
```

### 3.4 Pipeline stages (inside `veribayes-core`)
0. **Cache check (C6)** — key = `sha256(document bytes) × engine_version × rubric_version × mode`.
   Hit → return stored result instantly (reproducible by construction). Stage outputs (parse, detect)
   are cached independently of LLM stages so an engine upgrade re-judges without re-parsing.
1. **Ingest (C5)** — accept a dropped **PDF** *or* a pasted **arXiv ID / DOI / OpenAlex ID / URL**.
   `fetcher.py` resolves IDs to an OA PDF (arXiv API → OpenAlex/Unpaywall OA location → Crossref
   metadata) and is the **same module Phase 3's acquisition step imports** — built once, here.
2. **Parse** — GROBID (or fallback PyMuPDF) → structured sections incl. **supplements/appendices**,
   figure/table captions, references. Structure matters because absence claims depend on having
   looked in the right places.
3. **Detect** — run deterministic detectors → structured evidence (software, R-hat/ESS/divergences/
   Pareto-k values, prior mentions, PPC/SBC mentions, seeds, data/code statements). Each with the
   span where it was found.
4. **Screen** — relevance gate (§2.1). May short-circuit. Cheap model; runs before any expensive
   stage (C6 cost discipline).
5. **Classify** — paper type (§2.2). Selects applicable rubric steps.
6. **Assess** — for each applicable step, the LLM judges good/partial/missing/NA **conditioned on**
   the detector evidence, citing spans. Then an **adversarial pass** (A4, a v0 commitment — not
   optional) independently tries to **refute every negative finding** ("find evidence this step *was*
   done — check supplements, figures, captions, alternative wording") before anything is reported:
   refuted findings are dropped or downgraded; survivors keep high confidence. Each judgment carries
   a **confidence**.
7. **Score** — apply the rubric's applicability gates + weights → per-step scores → profile →
   aggregate → **badge**, with the threshold logic recorded for the "what-if" explainer.

Every LLM call is metered into the **cost ledger** (tokens, model, $ estimate, stage) stored on the
assessment and shown in the report footer (C6).

### 3.5 Engine grounding (anti-hallucination) — grounding in the *sources*, plural (A3)
Every finding must be grounded **twice**:
- **In the paper:** evidence spans (page/section/quote). The LLM is **never asked "did they report
  R-hat?" in a vacuum** — it receives the detector hits and the relevant parsed sections, and must
  reconcile/cite. Detectors give precision on hard signals; the LLM gives judgment on soft ones (was
  the prior *justified*? was the PPC *informative*?). **Absence requires enumeration:** the engine
  reports *where it looked* before claiming a step is missing.
- **In the methodological literature:** every judgment also cites the **standard being applied** —
  the rubric-provenance reference behind it (e.g., "two distinct diagnostics: BARG Step 2.B/2.C";
  "prior sensitivity mandatory with informative priors: WAMBS-v2 point 9"), carried as structured
  `standards[]` refs compiled from `rubric/steps.yaml`, each with its verified/unverified provenance
  status. The reader can always answer both "where in *my paper*?" and "says *who*?".

### 3.6 Caching & cost discipline (C6) — summary
- **Cache key:** `sha256(bytes) × engine_version × rubric_version × mode` → full-result reuse;
  stage-level sub-caches (parse, detect) survive engine upgrades.
- **Cheap-before-expensive:** relevance screen on a small model gates the costly assessment.
- **Cost ledger:** every LLM call metered (stage, model, tokens, $) → stored per assessment, shown in
  the report footer, aggregated on the calibration page. A configurable **budget guard** warns before
  starting an assessment whose estimate exceeds the threshold.
- **Why this is v0:** it makes interactive use affordable, Phase-3 batch runs feasible, and — because
  cache hits are byte-identical replays — assessments **reproducible**.

---

## 4. The report (deliverable)

### 4.1 Structure
```
┌ Header ───────────────────────────────────────────────┐
│ BADGE: Verified | Shaky | Failed   + score profile     │
│ Relevance: <yes/no + rationale>                        │
│ Paper type: <empirical | numerical-exp | methodological> + rationale │
└────────────────────────────────────────────────────────┘
For each workflow step (from rubric):
  • Status: done-well | partial | missing | not-applicable   (+ confidence)
  • What was done well (specific, evidence-cited)   ← required, not just criticism (D3)
  • What to improve (prioritized: error/warning/info) + concrete how-to + exemplar link (D2)
  • Evidence spans (clickable → PDF location)                                  ← grounding 1 (A3)
  • Standards applied (e.g. "BARG Step 2.B–C; Vehtari et al. 2021") + links    ← grounding 2 (A3)
  • [Disagree?] control → records an expert override (A5)
┌ Footer ───────────────────────────────────────────────┐
│ Engine vX · rubric vY · cost $Z                        │
│ Validation: agrees with expert consensus on N-paper    │
│ gold set: step κ=…, absence-claim FPR=… (date) → /calibration │
│ "Formative report, not a verdict" → ETHICS.md          │
└────────────────────────────────────────────────────────┘
```
**D2 in practice:** suggestions ranked by **impact × ease** — impact derives from the step's
weight/essential flag in `rubric/steps.yaml`; ease is LLM-assigned (low/med/high) anchored by
examples in the prompt; ordering = severity, then weight, then ease. Severities are capped (a
missing PPC on the central model = *error*; an uncited nuisance-prior justification = *info*) so
the report reads like a great linter, not a nag. **D3 in practice:** praise must be *specific and evidence-cited* ("prior
predictive check, Fig 2, correctly caught implausible effect sizes pre-fit — this is exactly what
Gabry et al. 2019 recommend"); generic praise is treated as a bug.

### 4.2 Layered views (one report, four audiences — improvements D1)
- **Author mode** — prioritized fix-list (linter severities) with concrete how-to + brms/Stan/PyMC
  exemplars.
- **Reviewer mode** — exportable, evidence-cited critique block.
- **Student mode** — each step links to its methodological source + a "what good looks like" example.
- **Meta-research mode** — raw structured JSON (the Phase-3 storage object).

### 4.3 Badge semantics (transparent, explainable)
- **Verified** — all *essential* applicable steps done well; no critical gaps.
- **Shaky** — essential steps present but with notable gaps, or important steps missing.
- **Failed** — one or more essential applicable steps absent/incorrect (e.g., MCMC inference with no
  convergence diagnostics at all).
Exact thresholds come from the Phase-1 scoring rule and are shown with a **what-if explainer** so the
badge teaches. Low-confidence absences must not by themselves cause **Failed** (improvements A2).

### 4.4 The result object (shared with Phase 3)
A single pydantic schema (`schema.py`) — `relevance`, `paper_class`, `step_assessments[]`
(`step_id, applicable, status, score, weight, confidence, evidence[], standards[], did_well,
suggestions[], adversarial_verdict`), `overall_score`, `badge`, `engine_version`, `rubric_version`,
`cost_ledger`, `validation_ref` (which calibration report applies). Overrides (A5) live in a
**separate table keyed to the assessment** — the engine's output is never mutated, expert corrections
sit alongside it. This *is* what `assessment` / `step_assessment` store in Phase 3 (see
`03-ingestion-corpus-plan.md` §4). Define it once, here.

---

## 5. API surface (FastAPI)
- `POST /api/papers` — multipart upload **or** `{arxiv_id | doi | openalex_id | url}` (C5); returns
  `paper_id`; enqueues job. Accepts `mode: full | local` (F3).
- `GET /api/papers/:id` — status + result (when ready).
- `GET /api/papers/:id/events` — **SSE** stream of stage progress (parse → screen → classify →
  assess → score) so the UI shows live progress on slow LLM calls.
- `GET /api/papers/:id/report.json|.md` — exports.
- `DELETE /api/papers/:id` — purge the paper and **all** derived artifacts (F3).
- `POST /api/assessments/:id/steps/:step_id/override` — record an expert correction (A5):
  `{corrected_status, rationale, author}`. `GET /api/overrides/export` → JSONL (future eval/few-shot
  data).
- `GET /api/calibration` — current engine's validation metrics (A1 surfacing, §7.4).
- Persistence: SQLite locally; result JSON on disk keyed by content hash (cache).
Async job handling (a simple in-process worker / `arq`/`rq` if needed) because assessment is
multi-second to minutes.

## 6. Frontend (React/Vite)
- Dropzone **+ ID input field** (arXiv/DOI/OpenAlex/URL — C5); live progress via SSE; report
  rendering with the four view modes; PDF panel that highlights evidence spans; badge + profile
  visualization; export buttons.
- **Privacy surface (F3):** first-run modal + persistent indicator of the active mode
  (full vs local-only); per-paper delete.
- **Override control (A5):** per-step "Disagree?" → small form (corrected status + rationale);
  overridden steps show an "expert override recorded" chip. Labeled honestly: *"recorded for the
  v1 learning loop — not yet used to change judgments."*
- **Calibration page (A1):** see §7.4.
- Keep components dumb; all logic server-side.

---

## 7. Validation against human experts (A1 — protocol + surfacing, a v0 deliverable)

> The engine is a measurement instrument; this section is its calibration procedure. It ships *with*
> v0 — a tool that grades Bayesian rigor without knowing its own error rate fails its own rubric.

### 7.1 Gold-standard set (tiered — expensive labels only where they're needed)
- **Tier A — fully step-rated: 30 papers** (10 per paper class: empirical / numerical-experiment /
  methodological), comp-neuro + comp-cog-sci; grow toward 100+ by v1 (then drawn via the Phase-3
  sampler so the set inherits sampling rigor).
- **Tier B — relevance-only probes: 20–30 papers** (non-Bayesian decoys + borderline cases). These
  need only a cheap yes/no/partial relevance label (minutes each, no step rating) — that's what
  gives relevance-gate sensitivity/specificity a usable CI; 3 decoys cannot.
- **Tier C — qualitative smoke tests:** ≥2 analytic/conjugate-posterior papers (N/A gating) and ≥2
  papers whose diagnostics live only in figures/supplements. Until these strata grow they are
  *probes, not measurements* — reported as case results, never as rates.
- **Selection rule (fixed before any engine run):** a **seeded random draw from a stated candidate
  frame** per class; the list is frozen with date + criteria recorded *prior to the first engine run
  on it*, and any exclusion is logged. No hand-picking after seeing engine output.
- **Version pinning:** each `validation/goldset/<work_id>.json` stores paper identifiers, labels,
  **and the `sha256` of the exact rated document bytes** (+ version, e.g. arXiv v2). `veribayes
  validate` verifies the hash of what it fetches and **hard-fails on mismatch** — metrics are never
  silently computed against a different version than the raters saw. PDFs themselves are never
  committed.

### 7.2 Expert rating protocol
1. **Raters:** 2 independent domain experts per paper (a 3rd on escalation), **blind to engine
   output**; **at least one rater per paper has no role in engine/prompt development**, and
   rater–project relationships are recorded in the validation report.
2. **Instrument:** `validation/rating-guide.md`, compiled from `rubric/steps.yaml` — same statuses
   (`done_well | partial | missing | not_applicable`), same applicability-gating rules the engine
   uses. Raters record, per step: applicability, status, an evidence pointer, and their own
   confidence; plus relevance and paper-class labels. For `missing`, raters optionally sub-tag
   **not-done vs not-reported(-suspected)** — v0 metrics collapse these, but the sub-label is stored
   so the v1 rigor-vs-reporting split (improvements B5) won't require relabeling everything.
3. **Adjudication:** disagreements resolved in a recorded discussion → **consensus label**; both
   original ratings are retained (never overwritten).
4. **Versioning:** the protocol and guide are frozen per `rubric_version`; relabeling is triggered
   only by rubric changes that alter step semantics. Gold-set papers are **ineligible as few-shot
   exemplars** in any prompt (no leakage from the measuring stick into the instrument).

### 7.3 Metrics (computed by `veribayes validate`, written to `validation/reports/<engine_version>.json`)
**Two-stage agreement** — `not_applicable` is a different *kind* of judgment, not a fourth ordinal
level, so agreement is decomposed to mirror the engine's own architecture:
- **Stage 1 — applicability agreement:** binary applicable-vs-N/A over *all* step×paper cells:
  unweighted κ plus sensitivity/specificity. (Engine-"missing" vs human-"N/A" is an applicability
  error and lands here, not in the FPR.)
- **Stage 2 — status agreement:** weighted κ on the genuinely ordinal 3-level scale
  (`done_well > partial > missing`), restricted to cells **both** judges deem applicable.
  Computed human-vs-human (pairwise, blind) and engine-vs-consensus.
- **Prevalence robustness:** κ is prevalence-sensitive and most steps have skewed marginals (κ can
  look terrible at 95% raw agreement). Report **% agreement and Gwet's AC1/AC2** alongside every κ;
  the caveat rule below keys on the *pair*, not κ alone.
- **Both directions of the absence error** (one-sided FPR would be gamed by A4 simply never saying
  "missing"):
  - **Absence-FPR** — of engine `missing` claims: *strict* (consensus `done_well`) and *broad*
    (consensus ∈ {`done_well`, `partial`}), reported with raw counts (x/n).
  - **Absence-miss-rate** — of consensus-`missing` steps, the share the engine failed to flag.
  - The full confusion matrix for the `missing` row *and* column goes on the calibration page so
    the trade-off is visible.
- **Engine accuracy, rest:** badge confusion matrix; relevance sensitivity/specificity (Tier B);
  paper-class accuracy.
- **Test-retest reliability (compute-only, free):** the harness runs the engine **twice** on Tier A
  and reports engine-self κ — the engine's own noise floor, below which no engine-vs-human number is
  interpretable.
- **Evidence-span validity:** a **seeded random sample of ~30 spans per validation run**, audited by
  someone other than the prompt author where feasible; pass-rate + CI in the report like every other
  metric — A3's central promise is measured, not assumed.
- **Uncertainty on everything:** bootstrap (or analytic) CIs on every κ, binomial CIs on every rate.
  Per-step metrics show **"insufficient data"** below an n-floor (e.g., 15 applicable papers) instead
  of a number.
- **Regression rule:** a change that worsens absence-FPR, absence-miss-rate, or mean step-κ beyond
  the **bootstrap variability** of the metric does not ship (tolerances defined relative to noise,
  not as raw point deltas).

### 7.4 Surfacing (how validation is shown — the suggestion you asked for)
> **Honesty caveat that governs all surfacing:** because the regression rule evaluates every change
> against this set, it functions as a **development set** — so all v0 numbers are labeled
> **"development-set agreement"**, not "accuracy." When the set grows at v1 (Phase-3 sampler), a
> **sealed holdout** is reserved — never used for release gating or prompt iteration — and becomes
> the source of the headline number. The same train/test hygiene we'd flag in a paper.
1. **A `/calibration` page in the app** — the instrument's spec sheet: per-step two-stage agreement
   table (engine-vs-consensus with **inter-expert agreement (pairwise, blind)** alongside — labeled
   exactly so, *not* "ceiling": consensus is built by those raters, so the engine can legitimately
   score above pairwise-human κ), absence-FPR + miss-rate with confusion matrix, badge confusion,
   test-retest κ, gold-set size & composition per tier, last-validated date, engine/rubric versions,
   override count (A5) feeding the next round — **every number with its n and CI**.
2. **A provenance footer on every report** (see §4.1): engine & rubric version, "development-set
   agreement: κ=… [CI], absence-FPR …/… , absence-miss …/…", validation date → `/calibration`.
   **Per-metric honesty:** any metric whose CI is wide or n below floor renders as "preliminary —
   interpret with care," rather than one global cliff. Plus one sentence of **domain validity**:
   *"validated on comp-neuro / comp-cog-sci samples; accuracy outside this domain is unmeasured."*
3. **Per-step reliability caveats:** steps where κ *and* raw agreement are both low (or n is below
   floor) carry an inline caveat marker in *every* report — low instrument reliability is disclosed
   at the point of use, not buried.
4. **`VALIDATION.md` in the repo,** auto-generated from the latest validation report — public and
   citable; Phase-3 corpus outputs quote it as their measurement-error statement.

---

## 8. Override scaffolding & the (mocked) learning loop (A5 — v0)

The full active-learning loop is v1, but the **scaffolding ships in v0 so the seam is visible**:
- **Storage:** `override(id, assessment_id, step_id, original_status, corrected_status, rationale,
  author, created_at)` — append-only, never mutates the engine's output.
- **API + UI:** the endpoints and per-step "Disagree?" control above (§5, §6).
- **Outflow (designed now, activated v1):** overrides export as (a) **nominations** for gold-set
  growth — *nominations only*: override labels are made while looking at engine output (anchored,
  non-blind), so nominated papers must be **fully re-rated from scratch under the §7.2 blind
  protocol** before any label enters `validation/goldset/`; importing override statuses as labels
  would mechanically inflate agreement; (b) few-shot exemplar candidates for prompts — **excluding
  gold-set papers** (§7.2-4); (c) a standing **disagreement log** that shows where the rubric/prompts
  are weakest — reviewed each release alongside the calibration report.
- **Honest labeling:** the UI says corrections are recorded but not yet learned from. No silent
  mock-magic.

## 9. Privacy & local-first (F3 — v0)

Authors *will* upload unpublished manuscripts. v0 ships:
- **Plain disclosure, at point of use:** first-run modal + persistent mode indicator + `PRIVACY.md`:
  in **full mode**, extracted document text goes to the Anthropic API; nothing else leaves the
  machine; all storage (SQLite, parsed artifacts, reports) is local; no telemetry.
- **Local-only mode (selectable per paper):** parse + deterministic detectors + applicability gating
  only — produces an **evidence inventory** ("what we found, where; what we could not find") with
  *no LLM judgments and no badge*, clearly labeled "detection only, not graded." Useful in itself,
  and it makes the privacy promise concrete rather than aspirational.
- **Right to forget:** per-paper delete purges everything derived (§5 DELETE).

## 10. Responsible use & anti-gaming (F1 — v0, stated openly)

`ETHICS.md` ships with v0 and the report links it (§4.1 footer):
- **Formative, not a verdict.** The badge attests *workflow practice as detectable in the
  document(s)* — not correctness of results. Wording in the UI reflects this.
- **Gaming surface, documented:** writing the magic words without doing the work. Counter: every
  positive credit requires **evidence spans** (A3) — naming a check without showing/quantifying it is
  flagged **"asserted but not evidenced"** and scores as `partial` at best. (Hardening this into a
  dedicated detector class is tracked as future work, improvements §H.) We also disclose **prompt
  injection** as an open attack surface: the judge is an LLM reading author-controlled text
  (hidden/white-font instructions, PDF-comment payloads); red-teaming + mitigations are scheduled
  future work (improvements §H7) and the limitation is stated in `ETHICS.md` until then.
- **Misuse guidance:** for reviewers/editors — a structured aid, not an auto-reject machine; never
  auto-publish scores about third-party work (v0 is single-user local anyway); Phase-3 public views
  get their own ethics note before launch.
- **Known biases disclosed:** English-language and Stan-ecosystem centricity; text-only limits
  (figure-borne diagnostics) — each listed with its planned mitigation (F2 audit, C2 vision).

---

## 11. Build order (Phase 2)
1. **M1 — Skeleton & contracts.** Repo layout; `schema.py` result object (incl. `standards[]`, cost
   ledger, override table); `rubric/steps.yaml` loader; FastAPI upload→job→status→SSE + override/
   calibration/delete endpoint stubs; React dropzone + progress; stub engine returns a fixed report;
   `ETHICS.md` + `PRIVACY.md` first drafts.
2. **M2 — Ingest + parse + cache.** Multi-format ingest & fetcher (C5); GROBID/PyMuPDF parsing incl.
   supplements; content-hash caching + cost-ledger plumbing (C6).
3. **M3 — Detect → local-only mode shippable.** Deterministic detector library (C1) + evidence
   spans; the F3 evidence-inventory report comes free here.
4. **M4 — Screen + classify.** Relevance gate (§2.1, D5) and paper-type classifier (§2.2), grounded +
   evidence-cited.
5. **M5 — Assess + score.** Per-step LLM judgment grounded by detectors (A3 both groundings);
   adversarial refutation pass (A4); applicability gating + scoring rule + badge; confidences.
6. **M6 — Report UX.** Layered views (D1), prioritized suggestions (D2), did-well notes (D3),
   evidence + standards rendering, what-if badge explainer, override controls (A5), privacy surface
   (F3), exports.
7. **M7 — Validation.** §7 protocol executed on the v0 gold set; `veribayes validate` harness;
   calibration page + report footer + `VALIDATION.md` (A1). **v0 is not "done" until M7 runs.**

---

## 12. Key risks → mitigations
- **Hallucinated absence claims** → detector grounding (C1) + enumerate-where-looked (A3) +
  adversarial pass (A4) + absence-FPR tracked as the headline validation metric (§7.3).
- **Penalizing legitimate deviations** → applicability gating by paper-type/method (B1); "not
  applicable" and "not reported" are distinct from "not done."
- **Diagnostics hidden in figures/supplements** → parse supplements now (C3); figure-only probes in
  the gold set quantify the limitation (§7.1); vision parsing (C2) is the planned fix.
- **Privacy of unpublished manuscripts** → §9: disclosure + local-only mode + purge, all in v0.
- **Cost/latency** → §3.6: caching, cheap-screen-first, cost ledger + budget guard (C6).
- **Validation can't keep pace with iteration** → the harness is automated (M7); the gold set grows
  via override-*nominated* papers re-rated blind (§8); the regression rule (§7.3) makes "validated"
  a release gate, not a vibe — and the dev-set/holdout split (§7.4) keeps the public number honest.

> The full report-content per step (what "done well" looks like, thresholds, applicability) is
> defined by the Phase-1 rubric — see `01-research-plan.md` and `rubric/steps.yaml`.
