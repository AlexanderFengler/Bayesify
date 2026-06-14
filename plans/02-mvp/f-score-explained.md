# f-score, in plain terms (what `core/score.py` actually does)

A companion to [`f-score.md`](f-score.md) (the spec). This describes the code shipped in M5 slice 2.

## One sentence
`score()` is a **pure function** (no LLM, no network, no clock — enforced by an import-linter rule)
that turns the LLM's **per-step judgments** into the final numbers: a per-step **profile** plus two
headline summaries, **coverage** and **quality**.

## What goes in
- `step_assessments` — one judgment per rubric step (from e-assess), each with a `status`
  (`done_well` / `partial` / `missing` / `not_applicable`) and a `confidence` in [0,1].
- `relevance`, `paper_class` — echoed through; `paper_class` + `gate_facts` drive applicability.
- `gate_facts` — the evidence-derived facts (inference method, #models, BF claimed, prior
  informativeness) that decide which steps apply.
- `rubric` — carries the **scoring block** (`rubric/steps.yaml`): the status→number map, the
  low-confidence threshold, per-class weights. **Nothing is hardcoded in the code.**
- `meta` — engine version, cost ledger, validation ref (stamped onto the result).

## What it computes, step by step
1. **Guards.** Refuses to run on an irrelevant paper (`relevance == no` short-circuits upstream), on
   empty input, or with no scoring block — raises `ContractError` / `RubricSpecError` rather than
   inventing a number.
2. **Per rubric step (in rubric order):**
   - **Re-derives applicability** itself (via the shared `step_applicability` resolver) and
     **cross-checks** it against the flag e-assess set. If they disagree → `ContractError`. (It
     trusts neither side blindly — defense in depth.)
   - Looks up the step's **weight** (per paper class; mixed papers take `max(primary, secondary)`)
     and its **sub-score** from the status map (`done_well=1.0, partial=0.5, missing=0.0`;
     **N/A → no sub-score, excluded entirely**).
   - Emits a `StepProfile` row: status, sub-score, weight, and **expectation tier**
     (expected / recommended / none — e.g. a Bayes-factor claim escalates S8 to *expected*).
3. **Coverage** = `present / applicable`, where *present* = `done_well | partial` and **N/A steps are
   never in the denominator**. A *missing* step whose confidence is below the rubric threshold is
   "uncertain", so coverage is a **range**: `strict` counts it absent, `lenient` counts it present
   (rendered e.g. "6–7 / 9"). A low-confidence absence alone never silently drops the headline.
4. **Quality** = weighted mean of the sub-scores over applicable steps. (v0 weights are uniform — a
   documented placeholder; proper aggregation is the B3 v1 task.)
5. **Score-impacts** — for each applicable step not already `done_well`, the **exact** coverage and
   quality gain of upgrading it to `done_well`, computed by re-running the arithmetic. Every delta is
   reachable by construction (the report ranks suggestions by these).

## Worked example
Empirical paper, MCMC, one model, no Bayes factor → **S6 is N/A** (single model, no BF), so **9 of
10 steps apply**. Say 7 are `done_well`, S5 is `partial`, S3 is `missing`:

- present = 7 (`done_well`) + 1 (`partial`) = **8**; applicable = **9**
- **coverage** = 8/9 ≈ **0.89**. If S3's *missing* is high-confidence → `strict == lenient` (no
  range). If low-confidence → `lenient` = 9/9 = 1.0, i.e. **"8–9 / 9"**.
- **quality** = (7×1.0 + 1×0.5 + 1×0.0) / 9 = 7.5/9 ≈ **0.83**
- **score-impacts**: upgrading S5 (partial→done_well) → coverage Δ 0, quality Δ ≈ +0.056; upgrading
  S3 (missing→done_well) → coverage Δ = 1/9 ≈ +0.111, quality Δ ≈ +0.111.

## What it deliberately does *not* do
- No LLM and no judgment of its own — it only does arithmetic on e-assess's statuses.
- **No categorical badge** (the dropped Verified/Shaky/Failed). The tier only sets suggestion
  *severity*, never a verdict.
- Weights are uniform in v0; confidences are uncalibrated (calibration is later work).

## Why "pure" matters
Identical inputs → byte-identical output, so a run is reproducible and cacheable, and Phase-3's batch
pipeline can score thousands of papers with the same code. The tests pin this with golden tables,
contract-error cases, and Hypothesis property checks (N/A never penalizes; upgrading a step never
lowers a score; `strict ≤ lenient`; every score-impact is reachable).
