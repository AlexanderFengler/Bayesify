# VeriBayes

**A tool for assessing how well academic papers follow Bayesian workflow best practices.**

VeriBayes ingests an academic paper (PDF) and produces a structured, evidence-linked report
that grades the paper against a rubric of Bayesian-workflow components derived from the
methodological literature (Gelman et al. *Bayesian Workflow*; Schad, Betancourt & Vasishth;
Kruschke's BARG; the WAMBS checklist; van de Schoot et al.; and the diagnostics literature on
R-hat, ESS, PSIS-LOO, and SBC). Each paper receives per-step grades, actionable suggestions,
and an overall badge: **Verified / Shaky / Failed**.

The project has three phases:

1. **Research** — a synthesis of methodological gold standards for the Bayesian workflow, turned
   into an assessable rubric. (`plans/01-research-plan.md`, output in `research/`.)
2. **MVP tool** — drag-and-drop PDF upload → hybrid (LLM + deterministic checks) analysis →
   step-wise report + badge. (`plans/02-mvp-tool-plan.md`.)
3. **Corpus & meta-analysis** — an ingestion pipeline (database + ontology + sampling
   methodology + deduplication) over a discipline's literature (starting with computational
   neuroscience and computational cognitive science), with visualizations of adoption and
   quality over time, by subfield, and by cluster. (`plans/03-ingestion-corpus-plan.md`.)

## Repository layout

```
plans/             Planning documents. See plans/00-master-plan.md for the executive summary.
plans/02-mvp/      Phase-2 component subplans (a-ingest … h-validate-harness) — one per pipeline
                   seam, each independently testable; plans/02-mvp-tool-plan.md is the spine.
research/          Output of the Phase-1 deep research (cited synthesis).
research/sources/  Annotated bibliography: one note per source (citation + how VeriBayes uses it),
                   plus fetch_sources.sh to download the open-access PDFs locally.
rubric/            Machine-readable rubric (steps.yaml) — the single source of truth for scoring.
validation/        The A1 validation protocol (engine-vs-expert calibration) and its artifacts.
```

## Status

Planning. See [`plans/00-master-plan.md`](plans/00-master-plan.md) for the executive summary and
the per-phase plans alongside it.
