# Bayesify Validation Protocol (A1)

**Status:** Protocol v0 (extracted from `plans/02-mvp-tool-plan.md` §7; content unchanged)
**Executed at:** Phase-2 milestone M7 — *v0 is not "done" until this protocol has run*
**Versioning:** frozen per `rubric_version`; see §2.4
**Artifacts:** `validation/rating-guide.md` · `validation/goldset/` · `validation/reports/` · auto-generated `VALIDATION.md`

> The engine is a measurement instrument; this document is its calibration procedure. It ships
> *with* v0 — a tool that grades Bayesian rigor without knowing its own error rate fails its own
> rubric.

## 1. Gold-standard set (tiered — expensive labels only where they're needed)
- **Tier A — fully step-rated: 30 papers** (10 per paper class: empirical / numerical-experiment /
  methodological), comp-neuro + comp-cog-sci; grow toward 100+ by v1 (then drawn via the Phase-3
  sampler so the set inherits sampling rigor).
- **Tier B — relevance-only probes: 20–30 papers** (non-Bayesian decoys + borderline cases). These
  need only a cheap yes/no/partial relevance label (minutes each, no step rating) — that's what
  gives relevance-gate sensitivity/specificity a usable CI; 3 decoys cannot.
- **Tier C — qualitative smoke tests:** ≥2 analytic/conjugate-posterior papers (N/A gating) and ≥2
  papers whose diagnostics live only in figures/supplements. Until these strata grow they are
  *probes, not measurements* — reported as case results, never as rates.
- **Selection rule (fixed before any engine run):** a **seeded random draw from a stated candidate
  frame** per class; the list is frozen with date + criteria recorded *prior to the first engine run
  on it*, and any exclusion is logged. No hand-picking after seeing engine output.
- **Version pinning:** each `validation/goldset/<work_id>.json` stores paper identifiers, labels,
  **and the `sha256` of the exact rated document bytes** (+ version, e.g. arXiv v2). `bayesify
  validate` verifies the hash of what it fetches and **hard-fails on mismatch** — metrics are never
  silently computed against a different version than the raters saw. PDFs themselves are never
  committed.

## 2. Expert rating protocol
1. **Raters:** 2 independent domain experts per paper (a 3rd on escalation), **blind to engine
   output**; **at least one rater per paper has no role in engine/prompt development**, and
   rater–project relationships are recorded in the validation report.
2. **Instrument:** `validation/rating-guide.md`, compiled from `rubric/steps.yaml` — same statuses
   (`adequate | partial | missing | not_applicable`), same applicability-gating rules the engine
   uses. Raters record, per step: applicability, status, an evidence pointer, and their own
   confidence; plus relevance and paper-class labels. For `missing`, raters optionally sub-tag
   **not-done vs not-reported(-suspected)** — v0 metrics collapse these, but the sub-label is stored
   so the v1 rigor-vs-reporting split (improvements B5) won't require relabeling everything.
3. **Consensus (v0: automated, 2026-06-16 amendment):** the consensus label is derived
   **mechanically** from the raters — a per-step status is the consensus iff a **strict majority**
   chose it; otherwise the cell is **"no consensus"**, excluded from the engine-vs-consensus metrics
   but **counted**. No human adjudication step. Both original ratings are retained (never
   overwritten), so inter-rater agreement is unaffected. Rationale: a mechanical consensus cannot be
   engine-anchored, which removes the "form consensus before inspecting engine output" leak risk and
   the "prompt author must not adjudicate their own disagreements" rule entirely. (A human
   *recorded-discussion* adjudication remains the v1 upgrade if a reviewer requires it.)
4. **Versioning & leakage rules:** the protocol and guide are frozen per `rubric_version`;
   relabeling is triggered only by rubric changes that alter step semantics. Gold-set papers are
   **ineligible as few-shot exemplars** in any prompt (no leakage from the measuring stick into the
   instrument). Override-nominated papers (plan `02-mvp/g-report-api-ui.md`) enter only after full
   blind re-rating under §2 — override labels themselves are engine-anchored and never imported.

## 3. Metrics (computed by `bayesify validate`, written to `validation/reports/<engine_version>.json`)
**Two-stage agreement** — `not_applicable` is a different *kind* of judgment, not a fourth ordinal
level, so agreement is decomposed to mirror the engine's own architecture:
- **Stage 1 — applicability agreement:** binary applicable-vs-N/A over *all* step×paper cells:
  unweighted κ plus sensitivity/specificity. (Engine-"missing" vs human-"N/A" is an applicability
  error and lands here, not in the FPR.)
- **Stage 2 — status agreement:** weighted κ on the genuinely ordinal 3-level scale
  (`adequate > partial > missing`), restricted to cells **both** judges deem applicable.
  Computed human-vs-human (pairwise, blind) and engine-vs-consensus.
- **Prevalence robustness:** κ is prevalence-sensitive and most steps have skewed marginals (κ can
  look terrible at 95% raw agreement). Report **% agreement and Gwet's AC1/AC2** alongside every κ;
  the caveat rule below keys on the *pair*, not κ alone.
- **Both directions of the absence error** (one-sided FPR would be gamed by the adversarial pass
  simply never saying "missing"):
  - **Absence-FPR** — of engine `missing` claims: *strict* (consensus `adequate`) and *broad*
    (consensus ∈ {`adequate`, `partial`}), reported with raw counts (x/n).
  - **Absence-miss-rate** — of consensus-`missing` steps, the share the engine failed to flag.
  - The full confusion matrix for the `missing` row *and* column goes on the calibration page so
    the trade-off is visible.
- **Engine accuracy, rest:** coverage/quality score agreement (engine-vs-consensus difference
  distribution + ICC; replaces the badge confusion matrix after the 2026-06-12 badge removal);
  relevance sensitivity/specificity (Tier B); paper-class accuracy.
- **Test-retest reliability (compute-only, free):** the harness runs the engine **twice** on Tier A
  and reports engine-self κ — the engine's own noise floor, below which no engine-vs-human number is
  interpretable.
- **Evidence-span validity:** a **seeded random sample of ~30 spans per validation run**, audited by
  someone other than the prompt author where feasible; pass-rate + CI in the report like every other
  metric — the dual-grounding promise (A3) is measured, not assumed.
- **Uncertainty on everything:** analytic Wilson CIs on every rate. **v0 amendment (2026-06-16):**
  κ ships as a point estimate + n (no CI) — at v0 n a cluster-bootstrap κ CI is noisy and
  contestable, and the uncertainties that matter most (rater coherence, engine noise) are reported
  separately as the inter-expert and test-retest κ. The κ cluster bootstrap is retained and tested
  for a v1 re-enable at G9 once the real run has enough papers. Per-step metrics show **"insufficient
  data" / "preliminary"** below an n-floor (e.g., 15 applicable papers) instead of an over-claimed CI.
- **Regression rule:** a change that worsens absence-FPR, absence-miss-rate, or mean step-κ beyond
  the **bootstrap variability** of the metric does not ship (tolerances defined relative to noise,
  not as raw point deltas).

## 4. Surfacing (how validation is shown)
> **Honesty caveat that governs all surfacing:** because the regression rule evaluates every change
> against this set, it functions as a **development set** — so all v0 numbers are labeled
> **"development-set agreement"**, not "accuracy." When the set grows at v1 (Phase-3 sampler), a
> **sealed holdout** is reserved — never used for release gating or prompt iteration — and becomes
> the source of the headline number. The same train/test hygiene we'd flag in a paper.
1. **A `/calibration` page in the app** — the instrument's spec sheet: per-step two-stage agreement
   table (engine-vs-consensus with **inter-expert agreement (pairwise, blind)** alongside — labeled
   exactly so, *not* "ceiling": consensus is built by those raters, so the engine can legitimately
   score above pairwise-human κ), absence-FPR + miss-rate with confusion matrix, coverage/quality
   score agreement, test-retest κ, gold-set size & composition per tier, last-validated date,
   engine/rubric versions (+ rubric profile — v0 validates the `synthesis` profile only),
   override count feeding the next round — **every number with its n** (and a CI where one ships:
   Wilson on rates; κ as point + n in v0, per the §3 amendment).
2. **A provenance footer on every report** (plan `02-mvp-tool-plan.md` §4.1): engine & rubric
   version, "development-set agreement: κ=… [CI], absence-FPR …/… , absence-miss …/…", validation
   date → `/calibration`. **Per-metric honesty:** any metric whose CI is wide or n below floor
   renders as "preliminary — interpret with care," rather than one global cliff. Plus one sentence
   of **domain validity**: *"validated on comp-neuro / comp-cog-sci samples; accuracy outside this
   domain is unmeasured."*
3. **Per-step reliability caveats:** steps where κ *and* raw agreement are both low (or n is below
   floor) carry an inline caveat marker in *every* report — low instrument reliability is disclosed
   at the point of use, not buried.
4. **`VALIDATION.md` in the repo,** auto-generated from the latest validation report — public and
   citable; Phase-3 corpus outputs quote it as their measurement-error statement.
