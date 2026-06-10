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

**In scope (MVP):** single-PDF upload; relevance gate; paper-type classification; per-step
assessment with evidence grounding; prioritized suggestions; badge with transparent thresholds;
layered report (author / reviewer / student views); persisted structured result (the object Phase 3
will store).

**Deliberately deferred** (tracked in `04-improvements-and-extensions.md`): figure/table vision
parsing (C2), artifact/repo fetching (C4), subfield-calibrated thresholds (B4), corpus features.
The MVP must, however, **architect for** these — clean seams, no rewrites.

---

## 2. The three required up-front determinations

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
    ingest.py               #   PDF/arXiv/DOI → raw bytes/text
    parse.py                #   GROBID/structure-aware → sections, captions, refs, supplements
    detectors/              #   deterministic checks (software, diagnostics, workflow signals)
    screen.py               #   relevance gate (§2.1)
    classify.py             #   paper-type classifier (§2.2)
    assess.py               #   per-step LLM judgment, grounded by detectors + adversarial check
    score.py                #   applicability gating + scoring rule + badge
    schema.py               #   pydantic models for the result object
    rubric/                 #   loads rubric/steps.yaml; compiles to prompts + checks
  api/                      # FastAPI app (thin): routes, job queue, SSE, persistence
  web/                      # React/Vite SPA
  rubric/steps.yaml         # the Phase-1 rubric spec (single source of truth)
  tests/
    eval/                   # gold-standard set + engine-vs-human agreement harness (improvements A1)
```

### 3.4 Pipeline stages (inside `veribayes-core`)
1. **Ingest** — accept PDF (MVP) and, sharing Phase-3 code, arXiv/DOI fetch. Content-hash for caching.
2. **Parse** — GROBID (or fallback PyMuPDF) → structured sections incl. **supplements/appendices**,
   figure/table captions, references. Structure matters because absence claims depend on having
   looked in the right places.
3. **Detect** — run deterministic detectors → structured evidence (software, R-hat/ESS/divergences/
   Pareto-k values, prior mentions, PPC/SBC mentions, seeds, data/code statements). Each with the
   span where it was found.
4. **Screen** — relevance gate (§2.1). May short-circuit.
5. **Classify** — paper type (§2.2). Selects applicable rubric steps.
6. **Assess** — for each applicable step, the LLM judges good/partial/missing/NA **conditioned on**
   the detector evidence, citing spans. Then an **adversarial pass** (improvements A4) tries to refute
   each negative finding; only survivors keep high confidence. Each judgment carries a **confidence**.
7. **Score** — apply the rubric's applicability gates + weights → per-step scores → profile →
   aggregate → **badge**, with the threshold logic recorded for the "what-if" explainer.

### 3.5 Engine grounding (anti-hallucination)
- The LLM is **never asked "did they report R-hat?" in a vacuum** — it receives the detector hits and
  the relevant parsed sections, and must reconcile/cite. Detectors give precision on hard signals;
  the LLM gives judgment on soft ones (was the prior *justified*? was the PPC *informative*?).
- **Absence requires enumeration:** the engine reports *where it looked* before claiming a step is
  missing (improvements A3).

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
  • What was done well (specific, evidence-cited)   ← required, not just criticism
  • What to improve (prioritized: error/warning/info) + concrete how-to + exemplar link
  • Evidence spans (clickable → PDF location)
```

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
(`step_id, applicable, status, score, weight, confidence, evidence[], did_well, suggestions[]`),
`overall_score`, `badge`, `engine_version`, `rubric_version`. This *is* what `assessment` /
`step_assessment` store in Phase 3 (see `03-ingestion-corpus-plan.md` §4). Define it once, here.

---

## 5. API surface (FastAPI)
- `POST /api/papers` — multipart upload (or `{arxiv_id|doi}`); returns `paper_id`; enqueues job.
- `GET /api/papers/:id` — status + result (when ready).
- `GET /api/papers/:id/events` — **SSE** stream of stage progress (parse → screen → classify →
  assess → score) so the UI shows live progress on slow LLM calls.
- `GET /api/papers/:id/report.json|.md` — exports.
- Persistence: SQLite locally; result JSON on disk keyed by content hash (cache).
Async job handling (a simple in-process worker / `arq`/`rq` if needed) because assessment is
multi-second to minutes.

## 6. Frontend (React/Vite)
- Dropzone + upload; live progress via SSE; report rendering with the four view modes; PDF panel that
  highlights evidence spans; badge + profile visualization; export buttons. Keep components dumb;
  all logic server-side.

---

## 7. Validation harness (ship in MVP, even if small — improvements A1)
`tests/eval/` holds a growing gold-standard set (start ~15–30 papers hand-scored) and computes
**engine-vs-human agreement per step** (κ) + badge confusion. This tells us how good the tool is and
becomes the credibility basis for Phase-3 corpus claims. Treat it as part of "done," not extra.

---

## 8. Build order (Phase 2)
1. **M1 — Skeleton & contracts.** Repo layout; `schema.py` result object; `rubric/steps.yaml` loader;
   FastAPI upload→job→status→SSE; React dropzone + progress; stub engine returns a fixed report.
2. **M2 — Parse + detect.** GROBID/PyMuPDF parsing incl. supplements; deterministic detector library
   (C1); evidence spans.
3. **M3 — Screen + classify.** Relevance gate (§2.1) and paper-type classifier (§2.2), both grounded
   + evidence-cited.
4. **M4 — Assess + score.** Per-step LLM judgment grounded by detectors; adversarial refutation pass;
   applicability gating + scoring rule + badge; confidences.
5. **M5 — Report UX.** Layered views, prioritized suggestions, evidence highlighting, what-if badge
   explainer, exports.
6. **M6 — Validation harness.** Gold set + agreement metrics; iterate prompts/rubric against it.

---

## 9. Key risks → mitigations
- **Hallucinated absence claims** → detector grounding (C1) + enumerate-where-looked (A3) +
  adversarial pass (A4).
- **Penalizing legitimate deviations** → applicability gating by paper-type/method (B1); "not
  applicable" and "not reported" are distinct from "not done."
- **Diagnostics hidden in figures/supplements** → parse supplements now (C3); flag figure-only
  diagnostics as a known MVP limitation; vision parsing (C2) is the planned fix.
- **Privacy of unpublished manuscripts** → state data handling; local-only mode on the roadmap (F3).
- **Cost/latency** → content-hash caching + cheap relevance screen before full assessment (C6).

> The full report-content per step (what "done well" looks like, thresholds, applicability) is
> defined by the Phase-1 rubric — see `01-research-plan.md` and `rubric/steps.yaml`.
