# VeriBayes — Master Plan (Executive Summary)

**One line:** VeriBayes ingests an academic paper and returns an evidence-linked, step-by-step report
on how well it followed Bayesian-workflow best practices, culminating in a badge —
**Verified / Shaky / Failed** — and, at scale, charts how a whole field's practices evolve.

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
| **2. MVP tool** | Drag-and-drop PDF → hybrid analysis → step-wise report (suggestions + what-was-done-well + paper-type classification + relevance gate) + badge. FastAPI + React, local-first. | [`02-mvp-tool-plan.md`](02-mvp-tool-plan.md) |
| **3. Corpus & meta-analysis** | Sampling-rigorous ingestion pipeline (DB + ontology + dedup) over a discipline; visualizations of quality/adoption over time, by subfield, by cluster. | [`03-ingestion-corpus-plan.md`](03-ingestion-corpus-plan.md) |

Cross-cutting: [`04-improvements-and-extensions.md`](04-improvements-and-extensions.md) — my best
suggestions for making this excellent (validation, evidence-grounding, anti-gaming, figure parsing,
governance). Read §G there for the recommended next-iteration priorities.

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
(linter-style error/warning/info with concrete how-to), and **evidence spans** linking back to the
PDF. Plus three up-front determinations you required: a **relevance gate** (is this even a Bayesian
paper? if not, flagged and short-circuited with reasons), a **rigorous paper-type classification**,
and the overall **badge** with transparent, explainable thresholds. One report, four **layered views**
(author / reviewer / student / meta-research JSON).

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

---

## 6. Build order (high level)

```
Phase 1 ✅ research executed → rubric drafted (steps.yaml v0.1)  [scope gaps S6/S4 to close]
Phase 2  M1 skeleton+contracts → M2 parse+detect → M3 screen+classify
         → M4 assess+score+badge → M5 report UX → M6 validation harness
Phase 3  M1 frame+sampler → M2 dedup → M3 acquire+batch-engine
         → M4 corpus DB+ontology → M5 dashboards → M6 reproducibility wrapper
```

Highest-leverage early investments (from improvements §G): applicability gating + rubric-as-spec;
evidence grounding + adversarial self-check; deterministic detectors + structured (incl. supplement)
parsing; a validation harness from day one so we *know* the tool's accuracy.

---

## 7. Top risks → how we handle them

- **Hallucinated "missing" claims** → detector grounding + "enumerate where we looked" + an adversarial
  refutation pass before any negative finding is reported with confidence.
- **Penalizing legitimate deviations** → applicability gating by paper-type/method (not-done ≠
  not-reported ≠ N-A).
- **Tool is itself un-validated** → ship an engine-vs-human agreement harness in the MVP; corpus claims
  cite that measurement error. *(A Bayesian-rigor auditor must meet its own bar.)*
- **Diagnostics hidden in figures/supplements** → parse supplements now; figure-vision parsing is the
  planned upgrade.
- **Badge gaming / misuse** → formative-feedback framing, evidence grounding, transparency; public
  views carry an explicit ethics note.
- **Privacy of unpublished manuscripts** → clear data-handling disclosure + a local-only mode on the
  roadmap.

---

## 8. Where to go next

- New collaborator → read this, then `01`–`04` in order.
- Implementer → `02-mvp-tool-plan.md` §3 (architecture) and `rubric/steps.yaml`.
- Methodologist → `research/bayesian-workflow-gold-standards.md` (esp. §7 caveats) and `01-research-plan.md`.
- Skeptic / reviewer → `04-improvements-and-extensions.md` (validation, bias, governance).

*Status: planning branch `plans`. Phase-1 research executed this session; nothing committed yet —
review the `plans/`, `research/`, and `rubric/` files, then we iterate.*
