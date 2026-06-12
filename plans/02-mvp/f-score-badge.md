# f. Score & badge — VeriBayes v0 component

**Milestone:** M5
**v0 items covered:** B1 (applicability gating) · B3-part (profile-first + transparent thresholds + what-if explainer)
**Contract:** consumes `StepAssessment[]` + `Relevance` + `PaperClass` + rubric spec → produces `ScoredResult`   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** rubric loader (`core/rubric/`, M1) for weights/essential flags/gates from `rubric/steps.yaml`; `schema.py` (M1). Tested entirely against **recorded `StepAssessment[]` fixtures** (hand-authored, later augmented by [`e-assess`](e-assess.md) recordings) — never the live LLM chain. Replaces the M1 stub engine's fixed `ScoredResult`.

## Purpose
Turn per-step judgments into the profile, scalar summary, and **Verified / Shaky / Failed** badge — by a **pure, deterministic function** with no LLM calls and no IO. This is where the Phase-1 scoring rule (`01-research-plan.md` §4) becomes code, where B1's applicability gating is enforced in the arithmetic (N/A never penalizes), and where the badge is made to *teach* via transparent thresholds and a what-if explainer (B3 v0 half).

## Design
**One pure function** in `core/score.py`:

```
score(relevance: Relevance, paper_class: PaperClass, step_assessments: list[StepAssessment],
      rubric: RubricSpec, meta: ScoreMeta) -> ScoredResult
```
`ScoreMeta` carries `engine_version`, `cost_ledger`, `validation_ref` (stub `"unvalidated"` before M7); `rubric.rubric_version` is stamped onto the result. No randomness, no clock, no network: identical inputs yield **byte-identical** serialized output (canonical ordering: steps in rubric order; `what_if[]` sorted by badge gain, then fewest changes, then rubric order).

**Scoring rule (carried from `01-research-plan.md` §4 — already reviewed; this implements, not re-designs):**
- Each **applicable** step's status maps to a numeric sub-score; **N/A steps are excluded from the denominator** — no penalty for legitimately-inapplicable steps. The status→sub-score map (e.g., `done_well=1.0, partial=0.5, missing=0.0`) lives in the **scoring block of `rubric/steps.yaml`** (B2: spec, not code), as do all thresholds below.
- **Weights and essential flags are conditioned on paper type** (B1): resolved from the rubric's per-class tables using `paper_class.primary`; for mixed papers the v0 default mixing rule is *weight = max(primary, secondary), essential = OR* — declared in `steps.yaml` and overridable there, not hardcoded.
- The **profile is the primary object**; the scalar is a summary: `profile = {steps[{step_id, applicable, status, sub_score, weight, essential}], badge_rule_fired, n_applicable, n_na}`; `overall_score` = weighted mean of sub-scores over applicable steps (documented v0 placeholder — deliberate proper-scoring aggregation is the B3 v1 half).

**Badge decision (old plan §4.3 semantics, verbatim intent), evaluated in fixed order:**
1. **Failed** — ≥1 essential applicable step `missing`/incorrect **with confidence ≥ the rubric's low-confidence threshold**.
2. **Low-confidence guard (A2/B3):** essential absences below that threshold — alone, in any number — cap the badge at **Shaky**, never Failed. (Adversarial verdicts are not re-litigated here: e-assess already dropped refuted findings; f reads only `status` + `confidence`.)
3. **Verified** — all essential applicable steps `done_well` and no applicable step carries an error-severity suggestion ("no critical gaps").
4. **Shaky** — everything else: essential steps present but with notable gaps, or important non-essential steps missing.
5. **Degenerate case** — if *zero* essential steps are applicable, the badge falls back to `aggregate_bands` (overall_score → badge) defined in the rubric scoring block; the fallback is recorded in `badge_rule_fired`.

**B1 enforcement + defense in depth:** steps with `applicable=false` contribute nothing — no sub-score, no denominator share, no badge influence; their `applicability_reason` passes through to the profile. f independently re-derives the rubric's applicability gates for `paper_class` and **raises `ContractError` on mismatch** with upstream's `applicable` flags rather than silently trusting either side.

**What-if explainer (B3):** compute the **minimal status changes that flip the badge upward**, with the threshold logic recorded into `what_if[]`:
- Enumerate single-step upgrades along `missing → partial → done_well` on applicable steps; **re-run `score()` on each hypothetical**; keep those that improve the badge. If no single change flips it, search change-sets up to size 3, essential steps first.
- Each entry: `{changes[{step_id, from_status, to_status}], badge_before, badge_after, rule_id, text}` — `rule_id` names the rubric threshold the hypothetical crosses (e.g., *"add a posterior predictive check → Shaky → Verified"*, rule `verified.all_essential_done_well`). A leading entry with empty `changes[]` records why the *current* badge holds (the fired rule + the blocking steps), so the report can render the full threshold trace from `what_if[]` alone.
- Suggestions are *reachable by construction* (each was verified by re-scoring) — never speculative text.

**Edge semantics:** `relevance.label == "no"` short-circuits upstream, so f is never invoked for irrelevant papers; if called anyway it raises. `partial` relevance scores normally (the report contextualizes it). Unknown `step_id`, status outside the enum, or an empty `step_assessments[]` with `relevance != no` → hard `ContractError`; no silent skipping.

## Interface contract
- **In:** `StepAssessment[]` — f reads `step_id, applicable, applicability_reason, status, confidence, suggestions[].severity`; all other fields (`evidence`, `standards`, `did_well`, `adversarial_verdict`, …) pass through untouched into `ScoredResult.step_assessments[]`. Plus `Relevance`, `PaperClass` (echoed verbatim into the result), the loaded rubric spec, and `ScoreMeta`.
- **Out:** `ScoredResult {relevance, paper_class, step_assessments[], profile, overall_score, badge, what_if[], engine_version, rubric_version, cost_ledger, validation_ref}` — field names per spine §4.3; `profile` and `what_if[]` item shapes as defined above (added to `schema.py`).
- **Errors:** `ContractError` (malformed input, gate mismatch, called on irrelevant paper) — never a partial result; `RubricSpecError` if the scoring block lacks a required table for the given paper class. Both carry the offending `step_id`/field.

## Test plan
All component-local; **no live upstream chain** — inputs are recorded fixtures of the `StepAssessment[]` contract.
- **Golden tables** (hand-computed `ScoredResult`s, deep-equality asserts): empirical paper, all essentials `done_well` → Verified · one essential `missing` at high confidence → Failed · same absence below the confidence threshold → Shaky · analytic-posterior paper with S4 N/A → denominator excludes it, score unchanged vs. the same paper without S4 · mixed-class weight/essential resolution · zero-essential degenerate case → `aggregate_bands` fallback · error-severity suggestion blocking Verified.
- **Property tests** (Hypothesis, over generated assessment sets):
  - **N/A never penalizes** — adding an N/A step never lowers `overall_score` or worsens the badge;
  - **monotonicity** — upgrading any one step along `missing < partial < done_well` never worsens badge or `overall_score`;
  - **low-confidence guard** — if every `missing` has confidence below threshold, badge ≠ Failed;
  - **what-if reachability** — applying each `what_if` entry's `changes[]` and re-scoring yields exactly `badge_after`, 100% of entries;
  - **round-trip determinism** — score twice, serialize: byte-identical JSON.
- **Contract-error tests:** unknown step_id, bad enum, gate mismatch, irrelevant-paper invocation each raise with the offending field named.
- **Fixtures recorded for downstream:** canonical `ScoredResult` JSON per badge (and one local-only/degenerate case) under `tests/fixtures/scored_result/` — the input fixtures [`g-report-api-ui`](g-report-api-ui.md) builds against.
- **Ship gates:** all golden + property tests green; 100% branch coverage of the badge decision order; what-if reachability at 100%.

## Definition of done
- [ ] `core/score.py` is pure (no LLM/IO imports; enforced by an import-linter rule) and replaces the M1 stub.
- [ ] All thresholds, sub-score maps, weights, essential flags, mixing rule, and `aggregate_bands` read from `rubric/steps.yaml`; none hardcoded.
- [ ] N/A exclusion, paper-type-conditioned weights/essentials, profile-primary + scalar-summary, and the low-confidence-absence guard match `01-research-plan.md` §4 exactly.
- [ ] `what_if[]` carries the current-badge rule trace plus only re-scoring-verified upgrade paths.
- [ ] `rubric_version`, `engine_version`, `cost_ledger`, `validation_ref` stamped on every result.
- [ ] Golden, property, and contract-error suites pass; `ScoredResult` fixtures published for component g.

## Out of scope (deferred)
- **Deliberate proper-scoring aggregation design** — the v1 half of B3; v0's weighted mean is an explicitly documented placeholder (`04-improvements-and-extensions.md` §B3).
- **Subfield-calibrated thresholds** — corpus-dependent; judged-against-peers scoring waits for Phase 3 (§B4).
- **Rigor-vs-reporting as separate axes** — §B5 (v1); f passes statuses through unchanged so the future split needs no rework here.
