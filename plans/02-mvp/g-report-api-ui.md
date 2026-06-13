# g. Report, API & UI — VeriBayes v0 component

**Milestone:** M1 (skeleton & contracts) + M6 (full report UX) — two slices, separated below
**v0 items covered:** D1 (v0 slice: single report view + meta-research JSON; multi-view layering → v1, PR-#1 decision) · D2 prioritized suggestions · D3 specific praise · A5 override scaffolding · F3 privacy/UI surfaces · C6 cost & budget surfaces
**Contract:** consumes `ScoredResult` (full mode) or `ParsedDoc` + `Evidence[]` (local mode) → produces rendered report views, `report.json|.md` exports, `override` records   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** none at M1 — g *creates* `core/schema.py` and the stub engine every other component lands behind. At M6, only the §4.3 contracts: all views and API tests run against recorded `ScoredResult` fixtures + the stub engine, never the live a–f chain. `GET /api/calibration` serves a fixture validation report until M7.

## Purpose
The transport and presentation layer: FastAPI job loop, SSE progress, persistence, overrides, and the React SPA that renders a `ScoredResult` as the report. **The LLM never writes the report** (PR-#1 point 4, stating what was already the architecture): e fills structured `StepAssessment` fields; this component renders them through a fixed markdown/JSX template, programmatically. It owns the shared contracts (`schema.py`) and the stub engine, so the app is end-to-end demoable from M1 and every component a–f can land additively behind it.

## Design

### M1 slice — skeleton & contracts (the always-working app)
- Repo layout per spine §3.3; `core/schema.py` pydantic models for **all** §4.3 types; `rubric/steps.yaml` loader.
- FastAPI: upload→job→status→SSE loop with an in-process async worker (LLM stages are multi-second to minutes; escalate to `arq`/`rq` only if the in-process worker proves insufficient); override / calibration / delete / export endpoints as stubs; persistence = SQLite locally, result JSON on disk keyed by content hash (the C6 cache location).
- **Stub engine** returning a fixed, hand-authored `ScoredResult` fixture — the canonical fixture all components demo behind (spine §3.5 stubs-first rule).
- React: dropzone (**multi-file**: primary + optional supplement PDFs, per [`a-ingest-fetch`](a-ingest-fetch.md)) **+ ID input field** (arXiv/DOI/OpenAlex/URL — C5 entry point), live progress via SSE, raw-JSON report page. **Components stay dumb; all logic server-side** — the SPA renders `ScoredResult`, it never computes.
- `ETHICS.md` + `PRIVACY.md` first drafts (F1/F3 — shipped artifacts, not promises).

### M6 slice — full report UX
**Report structure** (carried from reviewed spec, spine §4.1):
```
┌ Header ────────────────────────────────────────────────────────────┐
│ COVERAGE x–y/n + QUALITY score + step profile + rubric profile     │
│ Relevance: <yes/partial/no + rationale> · Paper type: <primary     │
│   empirical | numerical-exp | methodological (+secondary)> + rationale │
└────────────────────────────────────────────────────────────────────┘
Per applicable workflow step (from rubric):
  • Status: done_well | partial | missing | not_applicable  (+ confidence)
  • What was done well (specific, evidence-cited)  ← required, not just criticism (D3)
  • What to improve (error/warning/info) + concrete how_to + exemplar link (D2)
  • Evidence spans (clickable → PDF panel highlight)              ← grounding 1 (A3)
  • Standards applied ("BARG Step 2.B–C; Vehtari et al. 2021") + links ← grounding 2 (A3)
  • [Disagree?] control → records an expert override (A5)
┌ Footer ────────────────────────────────────────────────────────────┐
│ Engine vX · rubric vY · cost $Z (from cost_ledger)                 │
│ Validation: development-set agreement on N-paper gold set:         │
│   step κ=… [CI], absence-FPR x/n, absence-miss x/n (date) → /calibration │
│ "Formative report, not a verdict" → ETHICS.md                      │
└────────────────────────────────────────────────────────────────────┘
```
**D2 in practice:** suggestions ranked by **impact × ease** — impact derives from the step's weight/essential flag in `rubric/steps.yaml`; ease is LLM-assigned (low/med/high, anchored by examples in the assess prompt; arrives on `suggestions[].ease`); ordering = **severity, then step weight, then ease**. Severities are capped (a missing PPC on the central model = *error*; an uncited nuisance-prior justification = *info*) so the report reads like a great linter, not a nag. **D3 in practice:** praise must be *specific and evidence-cited* ("prior predictive check, Fig 2, correctly caught implausible effect sizes pre-fit — exactly what Gabry et al. 2019 recommend"); **generic praise is treated as a bug** — the renderer flags any `did_well[]` entry lacking an evidence citation (dev-mode assertion + snapshot lint).

**Views (D1, v0 slice per the PR-#1 decision):** v0 ships **one report view** — author/reviewer-oriented: prioritized fix-list (linter severities) with concrete `how_to` + brms/Stan/PyMC exemplars, plus the exportable evidence-cited critique block — and the **meta-research JSON** (the raw `ScoredResult`, byte-identical to what Phase 3 stores; the complete payload is persisted regardless of what the UI shows, so downstream meta-research loses nothing). The four-audience layering (student mode with `standards[]` learn-links, separate author/reviewer modes) is **deferred to v1 as pure presentation** over the same payload — no backend change.

**Override scaffolding (A5 — scaffolding only; loop mocked):** table `override(id, assessment_id, step_id, original_status, corrected_status, rationale, author, created_at)` — **append-only, never mutates engine output**; overridden steps show an "expert override recorded" chip, labeled honestly: *"recorded for the v1 learning loop — not yet used to change judgments."* Outflow designed now, activated v1: (a) **nominations** for gold-set growth — nominations only: override labels are engine-anchored (made while looking at engine output), so nominated papers must be **fully re-rated from scratch under the blind protocol** (../../validation/protocol.md §2.4) before any label enters `validation/goldset/`; (b) few-shot exemplar candidates — **excluding gold-set papers** (no leakage from the measuring stick into the instrument); (c) a standing **disagreement log** reviewed each release alongside the calibration report.

**Privacy surface (F3):** first-run modal + persistent indicator of the active mode (full vs local-only) — in full mode extracted text goes to the Anthropic API, disclosed at point of use; per-paper delete; local-mode results render as an **evidence inventory** ("what we found, where; what we could not find"), clearly labeled "detection only, not graded" — no LLM judgments, no scores.

**Cost & budget surfaces (C6):** footer cost line rendered from `cost_ledger` (stage, model, tokens, $); **budget guard** (logic in core, spine §3.5) surfaces as a pre-flight confirm — SSE `budget_warning` event pauses the job, UI shows estimate + proceed/cancel; calibration page aggregates cost per assessment.

**Calibration page (`/calibration`):** renders ../../validation/protocol.md §4 — per-step two-stage agreement table with inter-expert pairwise agreement alongside (labeled exactly so, *not* "ceiling"), absence-FPR + miss-rate with full confusion matrix, coverage/quality score agreement, test-retest κ, gold-set size & composition per tier, last-validated date, engine/rubric versions, override count — **every number with its n and CI**, all labeled **"development-set agreement"**, plus the domain-validity line (*"validated on comp-neuro / comp-cog-sci samples; accuracy outside this domain is unmeasured"*). **Per-metric honesty:** any metric with a wide CI or n below floor renders "preliminary — interpret with care," not one global cliff; per-step low-reliability caveat markers propagate into every report.

## Interface contract
**API surface (FastAPI, thin — no engine logic):**
- `POST /api/papers` — multipart upload (primary PDF + optional supplement PDFs) **or** `{arxiv_id | doi | openalex_id | url}`; accepts `mode: full | local`; returns `paper_id`, enqueues job.
- `POST /api/papers/:id/rerun` — `{relevance_override: "partial"}`: the gate page's **"Run full assessment anyway"** escape hatch ([`d-screen-classify`](d-screen-classify.md) short-circuit spec). Recorded as an override-type record, re-enqueues the job with relevance forced to `partial`; the resulting report carries the "user-overridden relevance" banner.
- `GET /api/papers/:id` — status (`queued | running(stage) | awaiting_budget_confirm | done | failed(stage, reason)`) + result when ready.
- `GET /api/papers/:id/events` — SSE: stage events `ingest→parse→detect→screen→classify→assess→score`, plus `budget_warning` and terminal `done | failed` (stream closes after terminal).
- `GET /api/papers/:id/report.json|.md` — exports. `DELETE /api/papers/:id` — purges the paper and **all** derived artifacts (SQLite rows, cache entries, parsed artifacts, exports, overrides).
- `POST /api/assessments/:id/steps/:step_id/override` — `{corrected_status ∈ done_well|partial|missing|not_applicable, rationale, author}`; 404 on unknown ids; append-only. `GET /api/overrides/export` → JSONL.
- `GET /api/calibration` — latest `validation/reports/<engine_version>.json`; explicit `not_yet_validated` payload pre-M7.

**Edge semantics:** `Relevance.label = no` short-circuit → report renders the gate page (label, confidence, rationale, evidence_refs, searched-inventory, explicit "not graded" statement, and the **"Run full assessment anyway"** escape hatch wired to the rerun endpoint) — never a score forced onto an irrelevant paper; `partial` renders the "limited Bayesian content" banner above a normal report. `StepAssessment.applicable = false` steps render collapsed under "Not applicable" with `applicability_reason`. Local mode renders from `ParsedDoc` + `Evidence[]` only. The meta-research view must round-trip: `parse(report.json) == ScoredResult` exactly.

## Test plan
All tests run against the **stub engine + recorded fixtures** — never the live a–f chain (spine §3.5 additivity).
- **API integration (M1, stub engine):** upload→job→SSE event sequence→report JSON equals stub fixture; same via ID input and via multi-file upload; `mode=local` returns the evidence-inventory payload; override round-trip (POST → report shows chip, engine output unmutated → appears in `/api/overrides/export` JSONL); short-circuit fixture → gate page → `rerun {relevance_override}` → job re-enqueued as `partial` with the override recorded; DELETE then `GET` → 404 and cache/artifacts/exports verifiably gone; `budget_warning` → confirm → job resumes.
- **Snapshot tests (M6):** the report view + meta-research JSON rendered from recorded `ScoredResult` fixtures — one high-coverage empirical, one low-coverage with overrides, one uncertain-range, one relevance-`no` short-circuit, one local-mode inventory. D2 ordering (severity→score-impact→ease) unit-tested on a shuffled fixture; D3 lint test proves an uncited `did_well[]` entry is flagged.
- **Footer honesty states:** fixture validation reports — healthy metric renders numbers + CI; wide-CI/below-floor renders "preliminary — interpret with care"; absent report renders "not yet validated."
- **Fixtures recorded for others:** the M1 stub `ScoredResult` fixture is the shared demo fixture for components a–f; the SSE event-sequence fixture documents the progress contract.
- **Ship gates:** M1 — end-to-end demo on the stub passes in CI. M6 — full suite green re-run against *real* `ScoredResult` fixtures recorded from M5 output; snapshots stable.

## Definition of done
**M1:** repo layout + `core/schema.py` (all §4.3 types) + rubric loader land; all endpoints above exist (stubs allowed) and the M1 integration suite passes against the stub engine; dropzone + ID input + SSE progress demoable end-to-end; `ETHICS.md` + `PRIVACY.md` drafts committed.
**M6:**
- [ ] The report view + meta-research JSON render from `ScoredResult` with snapshot coverage; `report.json`/`.md` exports; JSON round-trips exactly; full payload persisted independent of the UI.
- [ ] D2 ordering rule implemented and tested; D3 uncited-praise lint in place; score-impact ranking and evidence-span PDF highlighting render.
- [ ] A5: append-only override table + per-step Disagree control with the honest "not yet learned from" label; JSONL export; outflow rules documented in code (blind re-rating gate, gold-set few-shot exclusion).
- [ ] F3: first-run modal, persistent mode indicator, local-mode inventory page, purge verified by test.
- [ ] C6: footer cost ledger, budget-confirm flow, calibration cost aggregate.
- [ ] `/calibration` renders the protocol-§4 content from a fixture report with per-metric honesty states + domain-validity line.

## Out of scope (deferred)
- **Active learning from overrides** — the A5 v1 half: overrides are recorded and exported only; nothing changes judgments (improvements §A5, §G.3).
- **Re-check / diff mode** on re-uploaded revisions (improvements §D4).
- **Multi-view layering (student mode, separate author/reviewer modes)** — v1, pure presentation over the persisted payload (PR-#1 decision).
- **Public dashboards / opt-in certification** — Phase 3 (improvements §E2).
