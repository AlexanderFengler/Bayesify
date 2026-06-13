# VeriBayes

**A tool for assessing how well academic papers follow Bayesian workflow best practices.**

VeriBayes ingests an academic paper (PDF) and produces a structured, evidence-linked report
that grades the paper against a rubric of Bayesian-workflow components derived from the
methodological literature (Gelman et al. *Bayesian Workflow*; Schad, Betancourt & Vasishth;
Kruschke's BARG; the WAMBS checklist; van de Schoot et al.; and the diagnostics literature on
R-hat, ESS, PSIS-LOO, and SBC). Each paper receives per-step grades, actionable suggestions, and
two transparent summary scores: **coverage** (share of applicable workflow steps present) and
**quality** (weighted mean step score). Assessment can be conditioned on a **rubric profile** — the
default synthesis rubric, or a source-pure profile such as `schad2021`.

The project has three phases:

1. **Research** — a synthesis of methodological gold standards for the Bayesian workflow, turned
   into an assessable rubric. (`plans/01-research-plan.md`, output in `research/`.)
2. **MVP tool** — drag-and-drop PDF upload → hybrid (LLM + deterministic checks) analysis →
   step-wise report + coverage/quality scores. (`plans/02-mvp-tool-plan.md`.)
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
veribayes/core/    The engine (Phase 2, in progress): stage contracts (schema.py), engine versioning,
                   rubric loader. UI-agnostic — no web deps (enforced by an import-linter contract).
tests/             pytest suite for veribayes-core.
```

## Development

Environments are managed with [pixi](https://pixi.sh) (conda-forge, Python 3.12); `pixi.lock` pins
exact versions for reproducibility.

```sh
pixi install        # provision the environment from pixi.lock
pixi run check      # ruff lint + import-contract + pytest
pixi run test       # just the tests
```

## Status

Phase 1 (research → rubric) complete; Phase 2 (MVP) under way — see
[`plans/02-mvp-tool-plan.md`](plans/02-mvp-tool-plan.md) §5 for the milestone/gate map. The current
branch builds **M1 (skeleton & contracts)**: the §4.3 stage contracts, `engine_version` composition
+ model pinning (gate G1), the `gate_facts` schema field (G6), and the rubric loader with profile
support. See [`plans/00-master-plan.md`](plans/00-master-plan.md) for the executive summary.
