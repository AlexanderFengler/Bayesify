# VeriBayes — Master Plan (Executive Summary)

**One line:** VeriBayes ingests an academic paper and returns an evidence-linked, step-by-step report
on how well it followed Bayesian-workflow best practices — a per-step score profile with two
transparent summary scores, **coverage** (share of applicable steps present) and **quality** — and,
at scale, charts how a whole field's practices evolve. *(The earlier Verified/Shaky/Failed badge was
dropped on 2026-06-12 after collaborator review — see §5.)*

**Audience for this doc:** collaborators who need to understand *what we're building and why* in five
minutes, then drill into the per-phase plans.

---

## 1. The problem & the bet

Bayesian methods are widespread in computational neuroscience and cognitive science, but adherence to
established workflow best practices (priors, predictive checks, convergence diagnostics, calibration,
sensitivity, transparent reporting) is uneven and rarely assessed systematically. There **is** a
mature, convergent methodological literature defining what "good" looks like (Gelman et al.'s
*Bayesian Workflow*; Schad, Betancourt & Vasishth; Kruschke's BARG; the WAMBS checklist; the
diagnostics work on R-hat/ESS, PSIS-LOO, and SBC). **The bet:** that literature can be distilled into
a concrete rubric, and a hybrid (LLM + deterministic-checks) engine can apply it to papers
reproducibly enough to (a) give authors/reviewers actionable feedback and (b) support field-level
meta-research.

---

## 2. What we're building, in three phases

| Phase | Deliverable | Plan |
|-------|-------------|------|
| **1. Research → rubric** | Cited synthesis of Bayesian-workflow gold standards, decomposed into an assessable rubric (`rubric/steps.yaml`). **Executed** — see `research/`. | [`01-research-plan.md`](01-research-plan.md) |
| **2. MVP tool (v0)** | PDF drag-drop **or arXiv/DOI/OpenAlex ID** → hybrid analysis → step-wise report + coverage/quality scores — **plus the v0 trust bar (below)**. FastAPI + React, local-first. | [`02-mvp-tool-plan.md`](02-mvp-tool-plan.md) (spine) + [`02-mvp/`](02-mvp/) component subplans + [`validation/protocol.md`](../validation/protocol.md) |
| **3. Corpus & meta-analysis** | Sampling-rigorous ingestion pipeline (DB + ontology + dedup) over a discipline; visualizations of quality/adoption over time, by subfield, by cluster. | [`03-ingestion-corpus-plan.md`](03-ingestion-corpus-plan.md) |

Cross-cutting: [`04-improvements-and-extensions.md`](04-improvements-and-extensions.md) — my best
suggestions for making this excellent (validation, evidence-grounding, anti-gaming, figure parsing,
governance). Read §G there for the post-v0 priorities and §H for the newest proposals.

**The v0 bar** (twelve improvement items promoted into MVP scope, 2026-06-12 — spec in `02`):
- *Trustworthy instrument:* expert-validation protocol **with public calibration surfacing** (A1) ·
  dual grounding of every claim in the paper **and** the methodological literature (A3) ·
  adversarial self-verification of negative findings (A4) · expert-override scaffolding, learning
  loop mocked (A5).
- *Practical engine:* multi-format ingest (C5) · caching + cost ledger + budget guard (C6).
- *The report:* four layered audience views (D1) · severity-tiered prioritized suggestions (D2) ·
  specific evidence-cited praise (D3) · graceful relevance gate (D5).
- *Governance, shipped not promised:* `ETHICS.md` + anti-gaming policy (F1) · privacy disclosure +
  local-only mode + purge (F3).

**Architectural keystone:** one engine, `veribayes-core` (pure Python, no web deps), applies one
versioned rubric. The MVP tool and the corpus pipeline both call it — so single-paper and
field-level results never drift, and Phase 3 is cheap to build on Phase 2.

---

## 3. The rubric at a glance (output of Phase 1, executed)

The deep research (24/25 claims confirmed via 3-vote adversarial verification, 24 primary sources)
converged on **~10 assessable workflow steps**. Universally essential ones are marked **★**:

1. ★ Model specification & justification
2. ★ Prior specification
3. Prior predictive checks *(essential for methodological/small-data)*
4. ★ Computational faithfulness — convergence & sampling diagnostics *(N/A for analytic posteriors)*
5. ★ Posterior predictive checks *(essential for empirical)*
6. Model comparison — PSIS-LOO/WAIC or a robust Bayes-factor sub-workflow *(only when ≥2 models / a BF)*
7. Simulation-based calibration / recovery *(essential for methodological & simulation work)*
8. Prior / model sensitivity analysis *(mandatory with informative priors or any BF)*
9. ★ Reporting & reproducibility
10. ★ Posterior summary & honest inference communication

**Key design principle — applicability gating:** the rubric distinguishes **not-done** vs.
**not-reported** vs. **not-applicable**, conditioned on **paper type** (empirical / numerical-experiment
/ methodological) and **inference method**. This is what keeps the tool from penalizing legitimate
deviations — the single biggest correctness risk. Verified threshold provenance is preserved (e.g.,
R-hat > 1.1 historical vs < 1.01 modern; BARG ESS ≥ 10,000 for HDI limits; WAMBS |5|% doubling rule;
divergences = 0; E-FMI < 0.2). Full detail: `rubric/steps.yaml` and
`research/bayesian-workflow-gold-standards.md`.

**Two honest scope gaps to close before the rubric is frozen v1.0** (both flagged by the research's own
verification): the LOO/WAIC/Pareto-k model-comparison thresholds, and the modern R-hat/ESS numbers —
each needs its primary source (Vehtari 2017; Vehtari et al. 2021) confirmed directly. A short targeted
research pass closes both.

---

## 4. What a report contains (Phase 2 deliverable)

For each applicable workflow step: a **status** (done-well / partial / missing / N-A) with a
**confidence**, an **explicit "what was done well, and why"**, **prioritized suggestions**
(linter-style error/warning/info with concrete how-to), **evidence spans** linking back to the PDF,
and the **standards applied** (the literature behind each judgment — "says who?"). Plus two
up-front determinations you required — a **relevance gate** (is this even a Bayesian paper? if not,
flagged and short-circuited with reasons) and a **rigorous paper-type classification** — and, at the
end of the pipeline, the **coverage and quality scores** (no categorical badge; uncertainty-honest
coverage ranges when absences are low-confidence). v0 ships **one report view** (author/reviewer-
oriented) plus the meta-research JSON; the full four-audience layering is v1 presentation work over
the same stored payload. Every report carries a **provenance footer**: engine &
rubric versions, cost, and the engine's current validated accuracy (gold-set κ, absence-claim FPR)
linking to a full **calibration page**.

---

## 5. Key decisions already made

- **Engine:** hybrid — Claude API for rubric judgment, **grounded by deterministic detectors**
  (software, R-hat/ESS/divergence/Pareto-k values, prior/PPC/SBC mentions) to cut hallucination and
  make every claim auditable.
- **Stack:** **FastAPI (Python) + React/Vite (TypeScript)**, local-first (uvicorn + SQLite). Python
  for the PDF/NLP/ingestion ecosystem; React for the report UI and Phase-3 dashboards.
- **Audiences:** authors (self-check), reviewers/editors, meta-researchers, students — served by the
  layered report.
- **Sampling rigor (Phase 3):** probability sampling (stratified, seeded) per PRISMA-style reproducible
  frames; layered deduplication (persistent IDs → fuzzy match) validated like SRA-DM/ASySD. Citable
  methodology, not ad hoc.
- **From collaborator review (PR #1, S. Radev, 2026-06-12):** (a) **no categorical badge** — per-step
  profile + coverage/quality scores (any future verdict/certification only with validated thresholds,
  v2+); (b) **single report view in v0** + meta-research JSON, multi-view layering later as pure
  presentation; (c) **rubric profiles** — our synthesis stays the default and grows into *the gold
  standard*, with source-pure profiles alongside, first `schad2021`; (d) reports are
  **template-rendered from the result payload** — the LLM fills structured fields, never writes the
  report.

---

## 6. Build order (high level)

```
Phase 1 ✅ research executed → rubric drafted (steps.yaml v0.1)  [scope gaps S6/S4 to close]
Phase 2  M1 skeleton+contracts → M2 ingest+parse+cache → M3 detect (local mode shippable)
         → M4 screen+classify → M5 assess+score → M6 report UX
         → M7 validation protocol+calibration page   ← v0 isn't done until M7 runs
Phase 3  M1 frame+sampler → M2 dedup → M3 acquire+batch-engine
         → M4 corpus DB+ontology → M5 dashboards → M6 reproducibility wrapper
```

The v0 bar above is binding scope for Phase 2; post-v0 sequencing lives in improvements §G
(next up: figure/table vision parsing, calibrated confidences, closing the override learning loop).

---

## 7. Top risks → how we handle them

- **Hallucinated "missing" claims** → detector grounding + "enumerate where we looked" + an adversarial
  refutation pass before any negative finding is reported with confidence.
- **Penalizing legitimate deviations** → applicability gating by paper-type/method (not-done ≠
  not-reported ≠ N-A).
- **Tool is itself un-validated** → a full expert-validation protocol ships **in v0** (blind dual
  rating, κ + absence-claim FPR, regression gate) and is **surfaced** on a calibration page + every
  report's footer + a citable `VALIDATION.md`. *(A Bayesian-rigor auditor must meet its own bar.)*
- **Diagnostics hidden in figures/supplements** → parse supplements now; the gold set quantifies the
  text-only cost; figure-vision parsing is the top post-v0 priority.
- **Score gaming / misuse** → no categorical verdict to weaponize (2026-06-12 decision), formative-feedback framing, dual grounding, "asserted-but-not-evidenced"
  policy, `ETHICS.md` shipped in v0; public Phase-3 views carry their own ethics note.
- **Privacy of unpublished manuscripts** → **in v0:** plain disclosure, a local-only
  evidence-inventory mode, and per-paper purge.

---

## 8. Where to go next

- New collaborator → read this, then `01`–`04` in order.
- Implementer → `02-mvp-tool-plan.md` (spine: architecture + contracts), then the `02-mvp/`
  component subplan you're building, and `rubric/steps.yaml`.
- Methodologist → `research/bayesian-workflow-gold-standards.md` (esp. §7 caveats) and `01-research-plan.md`.
- Skeptic / reviewer → `04-improvements-and-extensions.md` (validation, bias, governance).

*Status: Phase-1 research executed; plans, research synthesis, annotated sources, and draft rubric
live on the `plans` branch (PR into `main`). 2026-06-12 (branch `plan-extensions-1`): twelve
improvement items promoted into v0 scope; post-v0 priorities revised in `04` §G–§H. 2026-06-12
(branch `plan-extensions-2`): MVP plan decomposed into a spine + eight independently testable
component subplans (`02-mvp/`) + the extracted validation protocol (`validation/protocol.md`).
Three-lens review (architecture / methodology / adversarial, all findings adversarially verified)
returned **ready-with-conditions** — implementation may begin at M1; ten milestone-attached gates
recorded in `02-mvp-tool-plan.md` §5 and [`reviews/2026-06-12-three-lens-review.md`](reviews/2026-06-12-three-lens-review.md).
Same day: four decisions from S. Radev's PR-#1 review folded in (badge → scores; single v0 view;
rubric profiles incl. `schad2021`; template-rendered reports) — see §5.*
