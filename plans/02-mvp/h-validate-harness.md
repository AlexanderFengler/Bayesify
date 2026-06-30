# h. Validation harness — Bayesify v0 component

**Milestone:** M7
**v0 items covered:** A1 (the *engineering* of validation — the procedure itself is
[`../../validation/protocol.md`](../../validation/protocol.md); this subplan builds what executes it)
**Contract:** consumes `validation/goldset/*.json` (labels + pinned sha256) + engine `ScoredResult`s → produces `validation/reports/<engine_version>.json`, auto-generated `VALIDATION.md`, and the `/api/calibration` payload   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** the full a–f chain for *live* runs; all metric computation is developed and unit-tested against **hand-authored `ScoredResult` + goldset-label fixtures** (no engine, no LLM, no network). [`g-report-api-ui`](g-report-api-ui.md) consumes the report via `GET /api/calibration` (fixture-fed pre-M7).

## Status & v0 revisions (2026-06-16) — built fake-harness-first

The M6 capstone built this component **fake-harness-first**: everything except the live run was implemented and shipped against fabricated data, so the finished product can be critiqued before any rater exists. **Built (slices V0–V6):** the human-report contract (`core/validation/human_report.py`), the pure metric engine (`core/validation/metrics.py`), the report builder + three-artifact emitter (`core/validation/report.py`), the harness + honesty firewall (`core/validation/harness.py`), the blind rating producer (`web/src/Rate.tsx` + `/api/rate/*`), and the calibration view (`web/src/Calibration.tsx` + `/api/calibration`). `pixi run validate` runs the demo dry-run over a committed **fake** goldset (`validation/_fake_goldset/`, `origin=fake_llm`) behind the firewall.

Two revisions to the design below:

1. **Location.** The harness/metrics/report live in `bayesify/core/validation/` (not `tests/eval/`) for clean imports + reuse by `/api/calibration`; the CLI is `pixi run validate` (`python -m bayesify.core.validation.harness`).

2. **Consensus is AUTOMATED — no human adjudication UI (v0).** Instead of a side-by-side adjudication screen, a pure `consensus_from_ratings()` derives the consensus mechanically: a per-step status is the consensus iff a **strict majority** of raters chose it; otherwise the cell is **"no consensus" — excluded from the engine-vs-consensus metrics, but counted**. A thin assembly step (`pixi run assemble-goldset`) groups the captured ratings by paper and writes the `HumanReport` (`ratings=[the originals]`, `consensus=auto`). This is *more* defensible than a human adjudicator, not less: a mechanical consensus **cannot be engine-anchored**, so the "consensus-before-engine-inspection" leak guard and the "prompt-author-can't-adjudicate-own-disagreement" rule become moot. Original ratings are retained, so inter-rater agreement is unaffected. (Human adjudication is a possible v1 upgrade.)

**What remains for M7** (engineering; rater recruitment is the separate, months-long critical path):
- `consensus_from_ratings()` + the `assemble-goldset` CLI (the automated replacement for adjudication).
- Real-run pairing: run the **live** engine per goldset paper (fetched by sha256) + the sha256 hard-fail (`GoldsetVersionMismatch`) — the demo pairs by `work_id` from fixtures.
- test-retest κ (run the engine twice on Tier A) + the evidence-span audit (needs a human auditor; likely v1).
- `validate --check` regression gate (needs a baseline → post-first-run hardening).
- Durable rating persistence (ratings are in-memory today; required before the first real rater).
- Selection provenance: a committed candidate-frame manifest + seeded draw (mostly process; the `selection_seed` field + publish-time check exist).
- Tier-C case-reporting (Tiers A+B can ship first).
- **Moot in v0:** the few-shot exemplar-leakage guard — the v0 prompts are zero-shot (no paper exemplars to leak).

## Purpose
Build `bayesify validate`: the CLI + library that runs the engine over the gold set, computes every
metric in protocol §3, and emits the three surfacing artifacts (versioned report JSON, public
`VALIDATION.md`, calibration payload). The protocol defines *what* is measured and *why*; this
component makes it executable, repeatable, and impossible to fudge silently — it is the release
gate's mechanical half.

## Design
**CLI.** `bayesify validate [--tier A|B|C|all] [--engine-version-check] [--seed N]` — lives in
`tests/eval/` per spine §3.3, imports `bayesify-core` only (web-free seam, same rule as a).

**Run pipeline per Tier-A paper:** resolve goldset entry → fetch via a's `fetcher`/blob store →
**hash check against the pinned sha256 — hard-fail on mismatch** (protocol §1 version pinning;
the run aborts with a version-mismatch report, never computes metrics on a different document) →
run the engine **twice** (test-retest, protocol §3) → store both `ScoredResult`s content-addressed.
Tier B runs only through stage 4 (relevance); Tier C runs full but reports case results, not rates.

**Metric computation (pure functions over labels + results, fully unit-testable):**
- Two-stage agreement: stage-1 applicability (binary κ + sens/spec over all step×paper cells);
  stage-2 status (weighted κ, 3-level ordinal, both-applicable cells only) — human-vs-human pairwise
  and engine-vs-consensus; % agreement + Gwet's AC1/AC2 alongside every κ.
- Absence errors both directions: strict/broad absence-FPR with raw counts; absence-miss-rate; the
  full `missing` row+column confusion matrix.
- Coverage/quality score agreement (difference distribution + ICC; replaces badge confusion per the
  2026-06-12 decision); Tier-B relevance sens/spec; paper-class accuracy; test-retest engine-self κ.
- Evidence-span audit sample: seeded random ~30 spans/run exported as an audit worksheet; the
  auditor's pass/fail comes back in as input to the report (pass-rate + CI).
- Wilson CIs on every rate; **κ ships as point + n in v0** (cluster-bootstrap κ CIs deferred to a v1
  re-enable at G9 — see protocol §3 amendment 2026-06-16); per-step **"insufficient data"** below the
  n-floor; regression comparison vs the previous report with noise-relative tolerances (protocol §3).

**Outputs.**
1. `validation/reports/<engine_version>.json` — every metric with n, CI, raw counts; goldset
   composition per tier; rater-relationship disclosures; the regression verdict vs prior report.
2. `VALIDATION.md` — auto-generated, public, citable; all numbers labeled **"development-set
   agreement"** until the sealed holdout exists (protocol §4); domain-validity statement included.
3. The `/api/calibration` payload g renders — same JSON, no reformatting logic in the API layer.

**Release gating.** `validate --check` exits non-zero on regression-rule violation; CI wires this so
a prompt/rubric/engine change that degrades absence-FPR, absence-miss-rate, or mean step-κ beyond
noise tolerance cannot merge to a release branch. (The per-PR golden-paper mini-set is improvements
§H4, v1 — explicitly disjoint from the gold set.)

## Interface contract
- **In:** `validation/goldset/<work_id>.json` — `{ids, sha256, version_label, rubric_version,
  raters[{id, relationship}], ratings[{step_id, applicable, status, missing_subtag?, evidence_ptr,
  confidence}] × 2..3, consensus[...], relevance_label, paper_class_label, tier}`. Plus engine
  `ScoredResult`s (live or fixture).
- **Out:** report JSON (schema versioned, additive-only changes), `VALIDATION.md`, calibration
  payload. All three derive from one computation — no number exists in two places independently.
- **Errors:** sha256 mismatch → `GoldsetVersionMismatch` (hard fail, names the paper and both
  hashes); missing consensus labels → that paper excluded *and counted* in the report's exclusion
  log (silent drops forbidden); engine failure on a goldset paper is itself a reported metric
  (completion rate), not a skip.

## Test plan
- **Metric unit tests against hand-computed cases:** small synthetic label/result tables where κ,
  AC1, FPR, miss-rate, and CIs are verifiable by hand (incl. the κ-paradox case: 95% agreement,
  skewed marginals — AC1 must stay high while κ collapses); two-stage decomposition cases where
  raters disagree on applicability (must land in stage 1, never stage 2 or FPR).
- **Determinism:** same seed + same inputs → byte-identical report JSON.
- **Hard-fail tests:** tampered sha256 → `GoldsetVersionMismatch`; missing consensus → exclusion
  logged; no silent paths (asserted by exhaustive enum on exit reasons).
- **Surfacing tests:** report JSON → `VALIDATION.md` generator snapshot; wide-CI metric renders the
  "preliminary" state; below-floor step renders "insufficient data" (consumed by g's footer tests).
- **End-to-end dry run (pre-M7 gate):** the full CLI over a **synthetic mini-goldset** (3 fixture
  papers with fabricated consensus labels + stub-engine results) exercises every code path without
  any expert labels — so M7's live run is the protocol's first execution, not the harness's.

## Definition of done
- [ ] `bayesify validate` runs Tiers A/B/C end-to-end on the synthetic mini-goldset in CI (no LLM).
- [ ] Every protocol-§3 metric implemented as a pure function with hand-verified unit tests; Wilson
      CIs on rates (κ as point + n in v0, cluster bootstrap deferred to G9); insufficient-data floors
      honored.
- [ ] sha256 pinning hard-fail + exclusion logging proven by tests.
- [ ] Report JSON, `VALIDATION.md`, and calibration payload generated from one computation; g's
      `/api/calibration` serves it unmodified.
- [ ] `validate --check` regression gate wired into CI for release branches.
- [ ] M7 exit: live run over the real Tier-A/B/C gold set completes; first `VALIDATION.md`
      published; calibration page live — **this closes v0**.

## Out of scope (deferred)
- **Human adjudication UI** — v0 derives consensus mechanically (see the revisions above); a
  side-by-side human-adjudication screen, if a reviewer ever demands one, is a v1 upgrade.
- **Sealed-holdout management** — arrives with the v1 gold-set growth (protocol §4); the report
  schema already reserves a `holdout` block so its addition is additive.
- **Confidence-calibration audit** (reliability diagrams, Brier scores) — improvements **H1** (v1);
  the report schema reserves the slot.
- **Golden-paper per-PR regression CI** — improvements **H4** (v1), disjoint mini-set.
- **Inter-model agreement runs** — improvements **H3b** (v1); test-retest (H3a) is in scope here.
