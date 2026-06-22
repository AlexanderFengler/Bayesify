# d. Screen & classify — Bayesify v0 component

**Milestone:** M4
**v0 items covered:** D5 (relevance gate up front) + the baseline paper-type classifier (spine §2.2)
**Contract:** consumes `ParsedDoc` + `Evidence[]` → produces `Relevance`, `PaperClass`   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** needs only `core/schema.py` (M1) and the rubric taxonomy names. Built and tested against **recorded fixtures** of `ParsedDoc` + `Evidence[]` (captured from [`b-parse`](b-parse.md) / [`c-detectors`](c-detectors.md) runs) — the live upstream chain is never required. The LLM client is faked with canned responses in unit tests; real cheap-model calls happen only in the eval harness. Downstream, [`e-assess`](e-assess.md) and [`f-score`](f-score.md) consume the `Relevance`/`PaperClass` fixtures this component records.

## Purpose
Stages 4–5 of the pipeline: decide *whether* the paper should be graded as Bayesian workflow at all (D5), and *as what kind* of paper. Both are first-class outputs rendered at the top of the report; a `no` short-circuits the pipeline gracefully instead of forcing a misleading score, and `PaperClass` is the input that drives rubric-step applicability (B1) downstream. Both run on a **cheap model before any expensive stage** — this is the C6 cost gate.

## Design

**Relevance gate (`core/screen.py`, stage 4).** A gated classifier returning `{label: yes/partial/no, confidence, rationale}`. A paper with no Bayesian statistical methodology is **flagged and short-circuited** with a clear explanation — never forced into a misleading score. Grounded by deterministic signals (`Evidence[]` hits: prior/posterior mentions, Bayesian software, MCMC/VI diagnostics, workflow signals) plus cheap-LLM judgment. Borderline cases (e.g., a single Bayes-factor t-test) are labeled **`partial` — "partially relevant — limited Bayesian content"** rather than a hard yes/no; `partial` papers proceed through the full pipeline under a prominent banner that contextualizes the scores.

**Detector floor (anti-noise, anti-gaming-by-omission).** A deterministic pre-pass over `Evidence[]` constrains the LLM: hits in ≥2 independent detector kinds (e.g., software *and* diagnostics) ⇒ `label` cannot be `no` (floored at `partial`); zero hits plus an LLM `no` ⇒ a confident short-circuit. The gate is thus robust to LLM run-to-run noise, and the rationale for `no` must enumerate *what was searched and not found* — the same absence discipline as A3.

**Paper-type classifier (`core/classify.py`, stage 5).** One of, with confidence + rationale + evidence:
- **`empirical`** — fits Bayesian models to real observed data to draw substantive conclusions;
- **`numerical_experiment`** — evaluates methods/models on simulated or benchmark data (the "truth" is known/controlled);
- **`methodological`** — proposes/analyzes a new model, prior, algorithm, or diagnostic.

**Mixed is allowed** (`primary` + `secondary`) — many papers are methodological *and* include an empirical application; `secondary` is emitted only when independently evidence-supported (e.g., a real-data application section). The class **drives rubric applicability** (SBC near-mandatory for methodological work, optional for routine empirical fits; predictive checks on real data central for empirical work) — but the gating *rules* live in `rubric/steps.yaml` (B1) and are *applied* by [`e-assess`](e-assess.md)/[`f-score`](f-score.md); this component only produces the class.

**Mechanics & cost (C6).** Two sequential cheap-model calls — screen first, so a `no` also saves the classify call. Each receives a bounded context: title + abstract + methods-like body sections + captions (token-capped selection from `ParsedDoc.sections`, supplements included in the scan inventory), plus a structured summary of `Evidence[]`. Both calls are metered into the cost ledger (stage tags `screen`, `classify`) and sub-cached under the spine cache key, so replays are byte-identical. Cheap-tier model id comes from config; the assess-tier model is never used here.

**Grounded rationales.** `Relevance.rationale` and `PaperClass.rationale` must cite `evidence_refs[]` — references into the consumed `Evidence[]` (see contract). Schema validation enforces: `yes`/`partial` and every `PaperClass` require ≥1 ref; `no` may have empty refs but its rationale must enumerate the searched-and-not-found detector kinds.

**Short-circuit page (content defined here, rendered by [`g-report-api-ui`](g-report-api-ui.md)).** On `no`, the engine stops after stage 4 (classify skipped) and persists a result with the `Relevance` object, an empty assessment list, and **null scores**. The page reads "**this doesn't appear to apply — here's why**": verdict + confidence, the evidence-cited rationale, the inventory of signals searched (which detectors ran, where they looked — body, captions, supplements), an explicit "not graded — no scores were computed," and an escape hatch: **"Run full assessment anyway"** (a recorded user override that re-enters the pipeline treating relevance as `partial`). Low-confidence `no` still short-circuits — never a misleading score — but the page says so prominently next to the escape hatch.

## Interface contract

**Consumes** (recorded-fixture-testable, per spine §3.5 additivity):
- `ParsedDoc` — uses `sections[]` (`kind: body|abstract|caption|supplement|references`); reads abstract + methods-like body + captions under a token cap; missing abstract ⇒ fall back to first body section; `references`-kind sections are excluded from relevance signals (a frequentist paper citing "Bayes" in its bibliography is not evidence).
- `Evidence[]` — detector hits (kinds per [`c-detectors`](c-detectors.md): software, diagnostics, prior/posterior mentions, workflow signals, …); an empty list is valid input (typical decoy).

**Produces:**
- `Relevance {label: yes|partial|no, confidence, rationale, evidence_refs[]}` — `confidence` ∈ [0,1]; `evidence_refs[]` are indices into the consumed `Evidence[]` array (stable: that array is itself a cached stage output under the same content hash); ref/rationale discipline as in Design.
- `PaperClass {primary, secondary?, confidence, rationale, evidence_refs[]}` — `primary`/`secondary` ∈ {`empirical`, `numerical_experiment`, `methodological`}; `secondary` is `None` unless mixed; `confidence` applies to `primary`. **Not produced at all when the gate short-circuits** (`label: no` without the escape hatch).

**Error/edge semantics:** LLM failure/timeout ⇒ retry then a typed stage error — **never a defaulted `yes`/`no`** (fail closed to "error," not to a guess). Malformed LLM output ⇒ one repair re-prompt, then error. Detector floor violations (LLM says `no` despite ≥2 evidence kinds) are corrected to `partial` and logged. Budget guard applies before each call.

## Test plan
- **Unit (no LLM):** detector-floor rules; section selection/truncation incl. missing-abstract and references-exclusion edges; schema validation of the `evidence_refs` discipline; cache replay byte-identity; fail-closed error paths via the faked client.
- **Labeled fixture set** (`tests/fixtures/screen/`, recorded `ParsedDoc`+`Evidence[]` pairs with expected labels): ≥9 relevant (3 per paper class, one of them mixed primary+secondary), ≥3 partial/borderline (incl. a lone Bayes-factor t-test), ≥4 non-Bayesian decoys (incl. one frequentist paper mentioning "Bayes" only in references). Fixture papers are **disjoint from the validation gold set** (all tiers) — they are development data and must not contaminate the protocol's Tier B measurement.
- **Eval harness ship gates** (live cheap model over the fixture set, in `tests/eval/`): relevance **sensitivity ≥ 0.95** (short-circuiting a genuinely Bayesian paper is the worst error), **specificity ≥ 0.80** on decoys, **primary-class accuracy ≥ 0.80**. These fixture thresholds **gate development only — the real measurement is [`../../validation/protocol.md`](../../validation/protocol.md) §3 (Tier B relevance probes, paper-class accuracy, with CIs), which gates release at M7.** Fixture numbers are never quoted publicly.
- **Short-circuit snapshot:** golden-file test of the full short-circuited result object and the rendered not-applicable page content for a decoy fixture (verdict, rationale, searched-inventory, not-graded statement, escape hatch).
- **Fixtures recorded for downstream:** `Relevance`/`PaperClass` outputs for one paper per class + one mixed + one `partial` + one short-circuit, committed for [`e-assess`](e-assess.md), [`f-score`](f-score.md), and [`g-report-api-ui`](g-report-api-ui.md) to build against.

## Definition of done
- [ ] `core/screen.py` + `core/classify.py` in `bayesify-core` (no web deps), coded verbatim against `schema.py` `Relevance`/`PaperClass`.
- [ ] Detector floor implemented and unit-tested; `no`-rationales enumerate searched-and-not-found kinds.
- [ ] `evidence_refs` discipline enforced at schema level; refs resolve against fixture `Evidence[]`.
- [ ] Screen runs before classify and both before assess; `no` short-circuits with classify skipped; "Run full assessment anyway" path re-enters as `partial`.
- [ ] Both calls cheap-model only, metered (`screen`/`classify` ledger tags), sub-cached, budget-guarded.
- [ ] Eval gates met on the labeled fixture set; short-circuit snapshot green; downstream fixtures recorded.
- [ ] M4 stub replaced: the always-working app shows real relevance + paper type at the top of the (still-stubbed-assess) report.

## Out of scope (deferred)
- **Subfield ontology tagging** (comp-neuro vs comp-cog-sci sub-areas, method/software/model-family terms) — Phase 3, `03-ingestion-corpus-plan.md` §5; this component decides *relevant or not* and *paper class*, nothing finer.
- **Subfield-calibrated relevance/applicability norms** — improvements §B4 [v2].
- **Prompt-injection hardening of the gate** (author-controlled text coercing a `yes`) — disclosed in `ETHICS.md`; closed by improvements §H7.
- **Learning from "Run full assessment anyway" overrides** — recorded only; active loop is improvements §A5 [v1].
