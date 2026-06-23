# f. Score — Bayesify v0 component

**Milestone:** M5
**v0 items covered:** B1 (applicability gating) · B3 (profile-first scoring; no premature collapse — and, per the 2026-06-12 PR-#1 decision, **no categorical badge at all**)
**Contract:** consumes `StepAssessment[]` + `Relevance` + `PaperClass` + rubric spec → produces `ScoredResult`   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** rubric loader (`core/rubric/`, M1) for weights/severity tiers/gates from `rubric/steps.yaml`; `schema.py` (M1). Tested entirely against **recorded `StepAssessment[]` fixtures** (hand-authored, later augmented by [`e-assess`](e-assess.md) recordings) — never the live LLM chain. Replaces the M1 stub engine's fixed `ScoredResult`.

> **Design decision (2026-06-12, from collaborator review on PR #1):** the Verified/Shaky/Failed
> badge is **dropped**. The primary output is the **per-step profile**; the headline numbers are
> **coverage** (share of applicable steps present) and **quality** (weighted mean step sub-score —
> the "differentiated" layer the per-step statuses already provide). Rationale: a categorical
> verdict bakes in threshold judgments the instrument cannot yet defend, and per-step scores are
> what authors, reviewers, and the Phase-3 meta-research actually consume.

## Purpose
Turn per-step judgments into the **profile** (primary object) plus two transparent summary scores —
by a **pure, deterministic function** with no LLM calls and no IO. This is where the scoring rule
becomes code and where B1's applicability gating is enforced in the arithmetic (N/A never
penalizes).

## Design
**One pure function** in `core/score.py`:

```
score(relevance: Relevance, paper_class: PaperClass, step_assessments: list[StepAssessment],
      rubric: RubricSpec, meta: ScoreMeta) -> ScoredResult
```
`ScoreMeta` carries `engine_version`, `cost_ledger`, `validation_ref` (stub `"unvalidated"` before
M7); `rubric.rubric_version` and `rubric_profile` (see spine §2.3) are stamped onto the result. No
randomness, no clock, no network: identical inputs yield **byte-identical** serialized output
(canonical ordering: steps in rubric order).

**Scoring rule:**
- Each **applicable** step's status maps to a numeric sub-score; **N/A steps are excluded from the
  denominator** — no penalty for legitimately-inapplicable steps. The status→sub-score map
  (e.g., `done_well=1.0, partial=0.5, missing=0.0`) lives in the **scoring block of
  `rubric/steps.yaml`** (B2: spec, not code), as do all weights and tiers below.
- **Coverage** (the headline simple number, per the PR-#1 decision): `present / applicable`, where
  *present* = status ∈ {`done_well`, `partial`}. **Uncertainty-honest range:** absences with
  confidence below the rubric's low-confidence threshold count as *uncertain*, and coverage is
  reported as a range — `coverage_strict` (uncertain absences counted absent) to `coverage_lenient`
  (counted present), rendered e.g. "6–7 / 9". A low-confidence absence alone never silently lowers
  the headline number (this carries forward the old low-confidence-guard principle).
- **Quality** = weighted mean of sub-scores over applicable steps (the differentiated layer;
  weights from the rubric's per-class tables via `paper_class.primary`; mixed papers: v0 default
  *weight = max(primary, secondary)* — declared in `steps.yaml`, not hardcoded). Documented v0
  placeholder — deliberate proper-scoring aggregation is the B3 v1 half.
- **Severity tiers replace "essential":** the rubric's per-class `essential` flag no longer feeds a
  verdict; it now sets **expectation tier** — a missing tier-1 ("expected") step yields an
  *error*-severity suggestion and is flagged prominently in the profile; tier-2 ("recommended")
  yields *warning/info*. Same rubric data, no Failed semantics. Evidence-conditioned expectations
  (gate G6: BF claim ⇒ S6/S8 expected) plug in here as tier escalations.
- The **profile is the primary object**: `profile = {steps[{step_id, applicable, status, sub_score,
  weight, tier}], n_applicable, n_na, n_uncertain}`.

**Score-impact ranking (replaces the badge-era what-if explainer):** for each applicable step not
at `done_well`, compute the coverage/quality delta of upgrading it (re-run `score()` on the
hypothetical — impacts are *reachable by construction*, never speculative). The deltas feed D2's
suggestion ordering in [`g-report-api-ui`](g-report-api-ui.md): severity, then score impact, then
ease.

**B1 enforcement + defense in depth:** steps with `applicable=false` contribute nothing — no
sub-score, no denominator share; their `applicability_reason` passes through to the profile. f
re-derives the rubric's applicability gates from `paper_class` + the `gate_facts` object (gate G6)
and **raises `ContractError` on mismatch** with upstream's `applicable` flags rather than silently
trusting either side.

**Edge semantics:** `relevance.label == "no"` short-circuits upstream, so f is never invoked for
irrelevant papers; if called anyway it raises. `partial` relevance scores normally (the report
contextualizes it). **Zero applicable steps** with `relevance != no` → `coverage`/`quality` are
null with an explicit `not_gradable` marker — never 0/0. Unknown `step_id`, status outside the
enum, or an empty `step_assessments[]` with `relevance != no` → hard `ContractError`.

## Interface contract
- **In:** `StepAssessment[]` — f reads `step_id, applicable, applicability_reason, status,
  confidence, suggestions[].severity`; all other fields (`evidence`, `standards`, `did_well`,
  `adversarial_verdict`, …) pass through untouched into `ScoredResult.step_assessments[]`. Plus
  `Relevance`, `PaperClass` (echoed verbatim), `gate_facts`, the loaded rubric spec, and `ScoreMeta`.
- **Out:** `ScoredResult {relevance, paper_class, step_assessments[], profile, coverage{present,
  applicable, strict, lenient}, quality_score, score_impacts[], engine_version, rubric_version,
  rubric_profile, cost_ledger, validation_ref}` — field names per spine §4.3; shapes added to
  `schema.py`.
- **Errors:** `ContractError` (malformed input, gate mismatch, called on irrelevant paper) — never
  a partial result; `RubricSpecError` if the scoring block lacks a required table for the given
  paper class. Both carry the offending `step_id`/field.

## Test plan
All component-local; **no live upstream chain** — inputs are recorded fixtures of the
`StepAssessment[]` contract.
- **Golden tables** (hand-computed `ScoredResult`s, deep-equality asserts): empirical paper, all
  steps `done_well` → coverage n/n, quality 1.0 · one expected step `missing` at high confidence →
  coverage drops, error-severity flag · same absence below the confidence threshold → coverage
  range widens instead ("uncertain") · analytic-posterior paper with S4 N/A → denominator excludes
  it, scores unchanged vs. the same paper without S4 · mixed-class weight resolution · BF-claimed
  empirical paper with S8 missing → S8 expected (tier escalation) + error severity (gate G6 golden
  test) · zero-applicable → `not_gradable`, no division.
- **Property tests** (Hypothesis, over generated assessment sets):
  - **N/A never penalizes** — adding an N/A step never lowers coverage or quality;
  - **monotonicity** — upgrading any one step along `missing < partial < done_well` never lowers
    either score;
  - **uncertainty honesty** — `coverage_strict ≤ coverage_lenient` always; if every absence is
    high-confidence, strict == lenient;
  - **score-impact reachability** — applying each `score_impacts[]` entry and re-scoring yields
    exactly the promised deltas, 100% of entries;
  - **round-trip determinism** — score twice, serialize: byte-identical JSON; **totality** — no
    division by zero on any valid input.
- **Contract-error tests:** unknown step_id, bad enum, gate mismatch, irrelevant-paper invocation
  each raise with the offending field named.
- **Fixtures recorded for downstream:** canonical `ScoredResult` JSON per scenario (high-coverage,
  low-coverage, uncertain-range, not-gradable, local-only) under `tests/fixtures/scored_result/` —
  the input fixtures [`g-report-api-ui`](g-report-api-ui.md) builds against.
- **Ship gates:** all golden + property tests green; 100% branch coverage of the scoring rules;
  score-impact reachability at 100%.

## Definition of done
- [ ] `core/score.py` is pure (no LLM/IO imports; enforced by an import-linter rule) and replaces
      the M1 stub.
- [ ] All sub-score maps, weights, tiers, mixing rule, and the low-confidence threshold read from
      `rubric/steps.yaml`; none hardcoded.
- [ ] N/A exclusion, paper-type-conditioned weights/tiers, profile-primary, coverage range, and
      quality summary implemented exactly as above.
- [ ] `score_impacts[]` carries only re-scoring-verified deltas.
- [ ] `rubric_version`, `rubric_profile`, `engine_version`, `cost_ledger`, `validation_ref` stamped
      on every result.
- [ ] Golden, property, and contract-error suites pass; `ScoredResult` fixtures published for
      component g.

## Out of scope (deferred)
- **Deliberate proper-scoring aggregation design** — the v1 half of B3; v0's weighted mean is an
  explicitly documented placeholder (`04-improvements-and-extensions.md` §B3).
- **Re-introducing any categorical verdict/certification** — only with validated thresholds and
  community governance (cf. §E2 opt-in certification, v2); v0 ships scores, not verdicts.
- **Subfield-calibrated thresholds** — corpus-dependent (§B4).
- **Rigor-vs-reporting as separate axes** — §B5 (v1); f passes statuses through unchanged so the
  future split needs no rework here.
