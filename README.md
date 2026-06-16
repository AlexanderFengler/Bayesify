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
veribayes/core/    The engine (UI-agnostic, no web deps — import-linter enforced): ingest, parse,
                   detectors, screen, classify, assess, score, report, the rubric loader + stage
                   contracts (schema.py) + engine versioning, and validation/ (the calibration harness).
veribayes/api/     FastAPI app: upload → job → SSE progress → report, plus the blind-rating and
                   calibration endpoints. Serves the built web UI in one process (`pixi run app`).
web/               React/Vite/TypeScript single-page UI (upload, report, blind rating, calibration).
tests/             pytest suite for veribayes-core + the API.
```

## Development

Environments are managed with [pixi](https://pixi.sh) (conda-forge, Python 3.12); `pixi.lock` pins
exact versions for reproducibility.

```sh
pixi install        # provision the environment from pixi.lock
pixi run check      # ruff lint + import-contract + pytest
pixi run test       # just the tests
```

### Running the app

One process serves the UI and the API on a single port — build the frontend once, then run:

```sh
pixi run setup-web  # one-time: install the frontend's node_modules
pixi run app        # builds the UI and serves it + the API at http://localhost:8000
```

For frontend hot-reload during development, run the two dev servers instead (Vite proxies `/api`):

```sh
pixi run api        # FastAPI with --reload on :8000
pixi run web        # Vite dev server on http://localhost:5173 (in a second terminal)
```

Drop a PDF and choose **Local-only** mode for an on-device evidence inventory (no LLM, nothing
leaves the machine). PDF parsing uses PyMuPDF by default; `pixi run -e parse app` adds the richer
Docling parser (layout, tables, captions).

### LLM backend (Full mode)

Full mode (relevance + paper-type, with grading from M5) needs a model. VeriBayes picks a backend
automatically (override with `VERIBAYES_LLM_BACKEND=agent-sdk|api|none`):

1. **Claude subscription** via the Claude Agent SDK — used when the `claude` CLI is installed and
   logged in (`claude login`). **No API key**; bills your Pro/Max plan. To use it, make sure
   `ANTHROPIC_API_KEY` is **unset** (if it's set, the Agent SDK bills that key instead).
2. **API key** — set `ANTHROPIC_API_KEY` (pay-as-you-go). Haiku screen+classify is ≈ $0.01/paper.
3. **Neither** → Full mode falls back to the labelled stub engine; Local-only mode still works.

The active path is whatever `config.llm_backend()` resolves to. Run the live accuracy gates with
`ANTHROPIC_API_KEY=... pixi run eval` (or on the subscription backend, just `pixi run eval`).

## Status

Phase 1 (research → rubric) complete; Phase 2 (MVP) is built through **M6 plus the M7 validation
harness** — see [`plans/02-mvp-tool-plan.md`](plans/02-mvp-tool-plan.md) §5 for the milestone/gate
map. The end-to-end flow works in both modes: upload a PDF → ingest/parse/detect → (Full mode)
screen/classify/assess/score → an evidence-linked, per-step report with coverage and quality scores,
downloadable as JSON/Markdown; Local-only mode runs the on-device detectors with nothing sent to a
model. There is a blind expert-rating flow and a `/calibration` page for engine-vs-expert agreement
(behind a FAKE-DATA firewall — no real ratings exist yet; that's the remaining M7 work: freeze the
rubric, recruit raters, run the live validation). Fetching a paper by identifier is not yet wired —
upload the PDF for now. See [`plans/00-master-plan.md`](plans/00-master-plan.md) for the summary.
