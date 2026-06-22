# e. Assess (grounded + adversarial) — Bayesify v0 component

**Milestone:** M5
**v0 items covered:** A3 (dual grounding — paper evidence *and* methodological sources), A4 (adversarial self-verification)
**Contract:** consumes `ParsedDoc` + `Evidence[]` + `Relevance` + `PaperClass` → produces `StepAssessment[]`   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** `schema.py` + rubric loader (M1). Tested alone against recorded `ParsedDoc`/`Evidence[]` fixtures (from b/c) and `Relevance`/`PaperClass` fixtures (from d), plus a Claude-API replay shim — never the live upstream chain. f and g stub this component with the `StepAssessment[]` fixtures it records.

## Purpose
Stage 6: for each applicable rubric step, an LLM judge — conditioned on detector evidence and the
relevant parsed sections, never asked in a vacuum — produces a grounded `StepAssessment`; an
adversarial refutation pass then attacks every negative finding before anything is reported. This is
where A3's dual grounding and A4's anti-false-absence guarantee are implemented.

## Design

**Applicability gate.** The applicable-step set comes deterministically from the rubric's gating
rules (B1 — scoring side: [`f-score`](f-score.md)) over `PaperClass` + detector
`Evidence`; non-applicable steps get `applicable=false`/`not_applicable`, the triggering gate rule
as `applicability_reason`, and **no LLM call**.

**First pass — grounded judge (A3), one call per applicable step.** Prompt assembly is
deterministic and unit-testable: (1) the **rubric step spec** compiled from `rubric/steps.yaml` —
criteria, signals of good/poor, thresholds, and the step's `standards[]` candidates with their
verified/unverified provenance status; (2) the **detector hits** mapped to the step (declared
step→detector map) — if none, the prompt says so explicitly: never "did they report R-hat?" in a
vacuum (§3.5); (3) **relevant sections** — abstract + methods-kind sections + every section with a
detector hit for the step, under a per-step token budget; the assembler logs which `section_id`s
were included (raw material for where-looked); (4) few-shot anchors for `ease` — gold-set papers
ineligible as exemplars (protocol §2.4). The judge returns `status` (`done_well|partial|missing`),
`confidence`, cited spans, applied `standards[]` (selected from the enumerated candidates —
free-written citations rejected), `did_well[]`, `suggestions[]`. Detectors give precision on hard
signals; the LLM judges soft ones (was the prior *justified*? was the PPC *informative*?). A
practice named but never shown/quantified is "asserted but not evidenced" → caps at `partial` (F1).

**D2/D3 raw material.** `did_well[]` (D3): `{text, evidence[]}` entries, specific and evidence-cited
— generic praise is a bug and fails the eval. `suggestions[]` (D2): `severity` (error/warning/info)
is **derived deterministically** from the step's weight/essential flag × status, never LLM-chosen;
`ease` (low/med/high) is LLM-assigned, anchored by prompt examples. Ranking/ordering happens in g.

**Second pass — adversarial refutation (A4, not optional).** Every negative finding (`status ∈
{missing, partial}`) is independently challenged: a fresh-context refuter gets the claim, the step
spec, and a **wider** slice — supplements, figure/table captions, plus a lexical sweep for
alternative wording (per-step synonym lists from the rubric) — and argues "find evidence this step
*was* done," never seeing the judge's rationale (no anchoring). `adversarial_verdict{challenged,
refuted, notes}` records the outcome: **refuted** → finding dropped or downgraded (status upgraded
per the found evidence, rescuing span appended to `evidence[]`, dependent suggestions removed);
**survived** → stands with high confidence. Positive findings carry `challenged: false`.

**Absence semantics — engine-constructed, schema-enforced (A3).** Where-looked enumerations are
built by the engine from the actual prompt-assembly and refuter context logs, never written by the
LLM: when `status=missing`, schema validation requires an `Evidence` item with
`detector_id="assess.where_looked"`, `kind="absence_search"`, `value` = section ids/kinds searched
by both passes, `span` = nearest-miss passage (fallback: top searched section) — else invalid.

**Reliability & cost plumbing.** All calls use schema-constrained structured output validated by
pydantic; every cited quote is normalized-substring-matched against its section's text. Validation
failure → one repair retry with errors echoed back; persistent failure raises `AssessError` — fail
loud, never emit an ungrounded judgment. Every call is metered into the **cost ledger**
`{stage:"assess", step_id, pass: judge|refute, model, tokens, $}` (C6); the budget guard checks an
estimate (doc length × applicable-step count) before the stage starts; per-step memoization lets a
failed run resume without re-paying; stage output cached per §3.5; `mode=local` never reaches here.

## Interface contract
- **In:** `ParsedDoc` (sections incl. `kind=supplement|caption` — required by the refuter),
  `Evidence[]`, `Relevance` (only `yes|partial` reach this stage; `no` short-circuits upstream),
  `PaperClass` (drives gating).
- **Out:** `StepAssessment[]`, exactly one per rubric step: `status ∈ done_well|partial|missing|
  not_applicable`; `confidence` ∈ [0,1] (uncalibrated); `evidence[]` = detector-`Evidence` refs +
  judge/refuter spans (quote-verified) + the mandatory `absence_search` item when `missing`;
  `standards[]` ⊆ compiled rubric refs with provenance status; `adversarial_verdict` always present.
- **Errors/edges:** retries exhausted → `AssessError` (loud; per-step memo kept). Empty applicable
  set → all-`not_applicable` list; f decides scoring semantics (not_gradable).

## Test plan
- **Unit (no LLM):** prompt assembler (deterministic; token budget; section selection; vacuum-prompt
  assertion); severity-derivation map; standards resolver (unknown refs rejected); schema invariants
  (`missing` ⇒ `absence_search`; `refuted` ⇒ upgrade-or-drop; quote match); per-call ledger entries.
- **Replay (no live API):** golden transcripts in `tests/fixtures/assess/`; the replay-shim run
  reproduces byte-stable `StepAssessment[]` — the **recorded fixtures consumed by f and g**.
- **Eval (live model — merge gate):** 3–5 mini fixture papers (synthetic/edited, spanning the three
  classes, gold-set-disjoint), run from `ParsedDoc`+`Evidence[]` fixtures: per-step status matches
  expected labels; **planted-evidence test** — a PPC described only in a supplement under
  non-standard wording is first-pass-flagged `missing` and MUST be rescued by the adversarial pass
  (`refuted=true`, status upgraded, rescuing span inside the supplement); **decoy negative** — a
  genuinely absent step survives refutation (`refuted=false` — no yes-machine); every `missing`
  carries where-looked; `did_well[]` cites evidence; `standards[]` resolve to real rubric sources.
- **Ship gates:** unit + replay green in CI; the live eval is a **merge gate** for any change to
  prompts, assembly, or the refuter (the continuous per-PR version is tracked as H4).

## Definition of done
- [ ] `core/assess.py` (no web deps) consumes the four input types, emits schema-valid
      `StepAssessment[]` one per rubric step; non-applicable steps cost zero LLM calls; no vacuum
      prompts (detector context or explicit none-found + selected sections, section list logged).
- [ ] Adversarial pass on every negative finding, verdicts recorded; planted-evidence and
      decoy-negative evals pass; absence claims carry engine-built where-looked enumerations.
- [ ] `standards[]` only from the compiled rubric with provenance status; `did_well[]` specific +
      evidence-cited; `suggestions[]` carry derived severity + LLM-assigned ease.
- [ ] Cost-ledger metering on every call; budget guard wired; structured-output validation with
      bounded retry and loud failure.
- [ ] Replay transcripts + `StepAssessment[]` fixtures for f/g committed; eval merge gate in CI.

## Out of scope (deferred)
- **Confidence calibration** — confidences are emitted but not audited/calibrated in v0
  (reliability diagrams, Brier scores vs gold-set correctness): improvements **A2 + H1**.
- **Prompt-injection red-teaming & mitigations** — disclosed as open surface in `ETHICS.md`; the
  parser's invisible-text suspect flags arrive in v1 and will be consumed here: improvements **H7**.
- **Figure/table understanding** — v0 reads text + captions only; figure-borne diagnostics surface
  as Tier-C probe failures by design (protocol §1): improvements **C2**.
- **Hardened asserted-but-not-evidenced detectors** — v0 applies the cap-at-`partial` policy in
  the judge prompt only: improvements **H6**.
