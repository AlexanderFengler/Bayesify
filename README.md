# Bayesify

[![DOI](https://zenodo.org/badge/1251503879.svg)](https://zenodo.org/badge/latestdoi/1251503879)

**A tool for assessing how well academic papers follow Bayesian workflow best practices.**

Bayesify ingests an academic paper (PDF) and produces a structured, evidence-linked report
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
research/sources/  Annotated bibliography: one note per source (citation + how Bayesify uses it),
                   plus fetch_sources.sh to download the open-access PDFs locally.
rubric/            Machine-readable rubric (steps.yaml) — the single source of truth for scoring.
validation/        The A1 validation protocol (engine-vs-expert calibration) and its artifacts.
bayesify/core/    The engine (UI-agnostic, no web deps — import-linter enforced): ingest, parse,
                   detectors, screen, classify, assess, score, report, the rubric loader + stage
                   contracts (schema.py) + engine versioning, and validation/ (the calibration harness).
bayesify/api/     FastAPI app: upload → job → SSE progress → report, plus the blind-rating and
                   calibration endpoints. Serves the built web UI in one process (`pixi run app`).
web/               React/Vite/TypeScript single-page UI (upload, report, blind rating, calibration).
tests/             pytest suite for bayesify-core + the API.
```

## Scoring: coverage, quality & step weights

Each graded paper gets two summary numbers, both derived purely from the per-step judgments — no extra
magic (see [`rubric/synthesis.yaml`](rubric/synthesis.yaml) and [`bayesify/core/score.py`](bayesify/core/score.py)):

- **Coverage** — the share of *applicable* steps that are **present** (`adequate` or `partial`), reported
  as a strict–lenient range when some absences are low-confidence. **Unweighted** — an honest count where
  every step counts the same; not-applicable steps are excluded from the denominator and never penalise.
- **Quality** (the "Bayesify Score") — a **weighted mean** of per-step sub-scores
  (`adequate` = 1.0, `partial` = 0.5, `missing` = 0.0) over the applicable steps.

### Step weights

A step's weight is **how relevant that step is to this paper's type**, on a `[0, 1]` scale where
**1.0 = fully relevant** (the default) and **0.5 = secondary**. Because quality is a *normalized* weighted
mean (`Σ wᵢ·sᵢ / Σ wᵢ`), only the *ratios* between weights matter — so no weight ever needs to exceed 1.0:
paper-type fit is expressed purely by **down-weighting** the less-relevant steps.

Weights are recorded **per paper class** in `rubric/synthesis.yaml` under `scoring.weights` — one full
10-step vector for each of the six scorable classes (`review` short-circuits and has no vector). Rather than
hand-tuning 60 cells, the matrix is generated from **two rules**; a test
([`tests/test_rubric_weights.py`](tests/test_rubric_weights.py)) asserts the YAML matches them so they can't
silently drift:

| Rule | Applies to | Effect | Why |
| --- | --- | --- | --- |
| **R1** | development classes¹ | S3, S5, S8 → **0.5** | a methods paper's data work is illustrative, so the *data-understanding* steps (prior-predictive, posterior-predictive, sensitivity) are secondary |
| **R2** | `data_analysis` | S7 → **0.5** | SBC / parameter-recovery is recommended-not-essential for an applied claim |
| R0 | everything else | **1.0** | every step is fully relevant by default |

¹ `model_development`, `method_development`, `software_development`, `numerical_analysis`, `theoretical_analysis`.

The resulting vectors (S1…S10) are **development** = `1, 1, 0.5, 1, 0.5, 1, 1, 0.5, 1, 1` and **applied**
(`data_analysis`) = `1, 1, 1, 1, 1, 1, 0.5, 1, 1, 1`. Note **S4 (computational faithfulness) stays at full
weight for every class** — a missing convergence diagnostic always counts.

- **Multi-label papers** take the **maximum** weight per step across their classes (`mixing_rule: max`), so a
  step that is secondary for only one of a paper's classes is rescued to full weight.
- Each step's resolved weight is shown on its card in the report (and in the JSON / Markdown export); the
  report header shows whether the active scheme is `weighted` or `uniform`. **Weights feed only quality —
  coverage is always unweighted.**

> The weights are a **draft** (`rubric_version` `0.3-draft`), anchored to the workflow literature and to be
> refined and frozen before the M7 expert-validation run — not tuned to make any single paper score better.

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

Drop a PDF and choose **Local** mode for an on-device evidence inventory (no LLM, nothing
leaves the machine). PDF parsing uses PyMuPDF by default; `pixi run -e parse app` adds the richer
Docling parser (layout, tables, captions). (The two modes are **Connected** — text sent to an LLM
for grading — and **Local** — on-device detectors only; the wire value stays `full`/`local`.)

### Test deploy

The FastAPI app is still importable at `bayesify.api.app:app`, but construction now lives in
`bayesify.api.factory` with shared process state in `bayesify.api.runtime`. The root `main.py`
re-exports `app` so FastAPI Cloud's default `fastapi run` auto-discovery can find it. For a hosted
API smoke test, use:

```sh
fastapi run
```

Or provide the implementation path explicitly:

```sh
fastapi run bayesify/api/app.py --host 0.0.0.0 --port 8000
```

In Pixi, the same production-style command is available as:

```sh
pixi run serve
```

For FastAPI Cloud or another Python host, set these environment variables for a cheap test deploy:

| Variable | Suggested test value | Why |
| --- | --- | --- |
| `BAYESIFY_MONGODB_AUTOSTART` | `0` | Hosted runtimes should not try to start a local `mongod`. |
| `BAYESIFY_LLM_BACKEND` | `none` | Avoids live model calls; Connected mode uses the labelled stub. |
| `BAYESIFY_DATA_DIR` | host-writable path, if provided | Keeps uploaded blobs/cache outside the app source tree. |
| `BAYESIFY_MONGODB_URI` | Atlas URI, optional | Enables durable reports and audit events; omitted is OK for a smoke test. |

`GET /healthz` returns `{"status":"ok"}` for liveness checks. The React UI is served only when
`web/dist` exists. For this MVP test deploy, `web/dist` is intentionally committed so FastAPI Cloud's
default Python deploy can serve the UI without running a Node build step.

### Database (MongoDB / Atlas)

The API persists completed, relevance-passing reports in MongoDB (the `reports` collection) and
writes only sparse lifecycle/audit records to `events`. Persistence is **best-effort**: if MongoDB is
unreachable the app keeps serving, and the startup log reports which database it reached. Use the
**MongoDB Atlas** cluster for a team setup, or a **local** MongoDB for solo/offline work.

#### Connect to the shared Atlas cluster

Each collaborator authenticates as their **own** database user — an X.509 client certificate (the
team default) or a username + password — so nothing shared is ever committed to git. One-time setup:

1. **Get invited.** Ask a project owner to add you to the Atlas project. In the Atlas console,
   database users and the IP allowlist both live under **Security → Database & Network Access**.

2. **Allow your IP.** Database & Network Access → **Network Access** → **Add Current IP Address**.
   Atlas denies every IP by default — skipping this is the most common "can't connect" cause.

3. **Find your database user** under **Database Users** (e.g. `yourname_db_user`); the **auth method**
   column (X.509 or SCRAM) tells you which path below to follow.

4. **Get your credentials.**
   - **X.509 (certificate):** **Edit** your user → **Download certificate** (pick a validity, e.g.
     6–12 months). You receive one `.pem` containing the certificate *and* its private key — treat it
     as a secret. Save it in the gitignored `secrets/` folder and lock it down:
     ```sh
     mkdir -p secrets
     mv ~/Downloads/X509-cert-*.pem secrets/atlas-x509.pem
     chmod 600 secrets/atlas-x509.pem
     ```
   - **Password (SCRAM):** note your username and password (set one under **Edit** if you don't have
     it — never reuse another user's credentials).

5. **Create a local env file** — any `*.env` name, gitignored — e.g. `bayesify.env` at the repo root,
   holding the connection string for your auth method (your cluster host is shown in Atlas under
   **Connect → Drivers → Python**):
   ```sh
   # X.509 — identity comes from the cert (no user/password). Use the ABSOLUTE path to the .pem,
   # keep %24external url-encoded, and single-quote the whole value.
   MONGODB_URI='mongodb+srv://<cluster-host>.mongodb.net/?authSource=%24external&authMechanism=MONGODB-X509&appName=bayesify&tlsCertificateKeyFile=/abs/path/to/secrets/atlas-x509.pem'

   # Password (SCRAM) — url-encode special chars in the password (@ -> %40, : -> %3A, / -> %2F):
   # MONGODB_URI='mongodb+srv://<user>:<password>@<cluster-host>.mongodb.net/?appName=bayesify'
   ```

6. **Run.** The app **auto-loads** `bayesify.env` at startup (override the path with `BAYESIFY_ENV_FILE`)
   — no `source` needed, and a variable already set in your shell still takes precedence:
   ```sh
   pixi run app
   ```
   (Equivalent if you prefer to export it yourself: `set -a && source bayesify.env && set +a`.)

7. **Verify the startup log** reads:
   ```
   INFO:     Loaded 1 setting(s) from bayesify.env: MONGODB_URI
   INFO:     MongoDB status: connected; uri=mongodb+srv://<cluster-host>.mongodb.net/bayesify; db=bayesify; mode=atlas/remote; server_api=v1
   ```
   A `WARNING` means it did not connect — check, in order: (1) your IP is allowlisted, (2) the `.pem`
   path is correct and the cert hasn't expired, (3) a SCRAM password is url-encoded. The credential is
   redacted in the log, so it is safe to share.

8. **Confirm writes land.** Analyze a relevant paper or submit a complete relevant blind rating,
   then open Atlas **Database → Data Explorer → `bayesify` → `reports`**. The `events`
   collection should contain only small pointer/audit records such as `analysis_report_ready` or
   `blind_rating_submitted`.

#### Local MongoDB (solo / offline)

Without a configured URI the API falls back to `mongodb://localhost:27017` and database `bayesify`.
If a local `mongod` binary is installed it auto-starts with data under `~/.bayesify/mongodb`;
otherwise start MongoDB yourself, or set `BAYESIFY_MONGODB_AUTOSTART=0` to disable auto-start.

#### Configuration reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `MONGODB_URI` / `BAYESIFY_MONGODB_URI` | Connection string (the `BAYESIFY_` form wins) | `mongodb://localhost:27017` |
| `MONGODB_DATABASE` / `BAYESIFY_MONGODB_DB` | Database name | `bayesify` |
| `BAYESIFY_MONGODB_SERVER_API` | MongoDB Stable API version for hosted clusters (`0` disables) | `1` |
| `BAYESIFY_MONGODB_TIMEOUT_MS` | Server-selection timeout (ms) | `5000` remote / `500` local |
| `BAYESIFY_MONGODB_AUTOSTART` | Auto-start a local `mongod` for a localhost URI | enabled |
| `BAYESIFY_ENV_FILE` | Path to the local env file auto-loaded at startup | `bayesify.env` |

Query `reports` by `paper_id`, `_id` (`<source_sha256>__<rubric_profile>`), `identifier`, or
`rubric_profile`. Query `events` only for lifecycle/audit records by `event` or `paper_id`.

> **Never commit secrets.** `secrets/`, `*.pem`, and `*.env` are gitignored — confirm with
> `git check-ignore secrets/atlas-x509.pem bayesify.env`. The `.pem` holds a private key: keep it
> `chmod 600` and out of any build or Docker context. Atlas-managed X.509 certificates expire —
> re-download and replace the `.pem` when they lapse.

### LLM backend (Connected mode)

Connected mode (relevance + paper-type, with grading from M5) needs a model. Bayesify picks a backend
automatically (override with `BAYESIFY_LLM_BACKEND=agent-sdk|api|none`):

1. **Claude subscription** via the Claude Agent SDK — used when the `claude` CLI is installed and
   logged in (`claude login`). **No API key**; bills your Pro/Max plan. To use it, make sure
   `ANTHROPIC_API_KEY` is **unset** (if it's set, the Agent SDK bills that key instead).
2. **API key** — set `ANTHROPIC_API_KEY` (pay-as-you-go). Haiku screen+classify is ≈ $0.01/paper.
3. **Neither** → Connected mode falls back to the labelled stub engine; Local mode still works.

The active path is whatever `config.llm_backend()` resolves to. Run the live accuracy gates with
`ANTHROPIC_API_KEY=... pixi run eval` (or on the subscription backend, just `pixi run eval`).

## Status

Phase 1 (research → rubric) complete; Phase 2 (MVP) is built through **M6 plus the M7 validation
harness** — see [`plans/02-mvp-tool-plan.md`](plans/02-mvp-tool-plan.md) §5 for the milestone/gate
map. The end-to-end flow works in both modes: upload a PDF → ingest/parse/detect → (Connected mode)
screen/classify/assess/score → an evidence-linked, per-step report with coverage and quality scores,
downloadable as JSON/Markdown; Local mode runs the on-device detectors with nothing sent to a
model. There is a blind expert-rating flow and a `/calibration` page for engine-vs-expert agreement
(behind a FAKE-DATA firewall — no real ratings exist yet; that's the remaining M7 work: freeze the
rubric, recruit raters, run the live validation). Fetching a paper by identifier is not yet wired —
upload the PDF for now. See [`plans/00-master-plan.md`](plans/00-master-plan.md) for the summary.
