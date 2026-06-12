# c. Deterministic detectors — VeriBayes v0 component

**Milestone:** M3
**v0 items covered:** C1 (library of deterministic detectors)
**Contract:** consumes `ParsedDoc` → produces `Evidence[]`   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** [`b-parse`](b-parse.md) in the live chain; built and tested **only against
recorded `ParsedDoc` fixtures** committed by b. Downstream [`d-screen-classify`](d-screen-classify.md)
and [`e-assess`](e-assess.md) are not needed — this component *records* their `Evidence[]` fixtures.

## Purpose
The grounding half of the hybrid engine: a versioned catalog of high-precision deterministic
detectors turning a `ParsedDoc` into structured `Evidence[]`, each hit with the exact span where it
was found. These hits keep the LLM honest in e-assess (it must reconcile with and cite them), and
each detector is independently testable, unlike prompt behavior. Completing a+b+c makes the **F3
local-only mode shippable** (spine §3.4): the evidence inventory needs no LLM and no scores.

## Design
**Catalog (improvements C1, plus the method-mention family the relevance gate floors on):**
- **Software/tooling:** Stan, brms, rstanarm, PyMC, NumPyro, TFP, JAGS, BUGS, HDDM, Turing.jl.
- **Bayesian-method & inference mentions** *(what [`d-screen-classify`](d-screen-classify.md)'s
  detector floor keys on — keeps a purely analytic/conjugate Bayesian paper, which triggers no
  software or sampler diagnostics, from yielding zero hits)*: plain prior/posterior mentions
  ("prior distribution", "posterior", "credible interval", "Bayes factor"), and inference-method
  mentions (MCMC/NUTS/HMC/Gibbs, variational inference/ADVI, conjugate/analytic posterior).
- **Diagnostics:** R-hat values, ESS (bulk/tail), divergent transitions, max-treedepth, BFMI/E-FMI,
  Pareto-k, WAIC/LOO/elpd, MCSE, trace/rank-plot mentions.
- **Workflow signals:** "prior predictive", "posterior predictive", "sensitivity analysis",
  "SBC"/"simulation-based calibration", number of chains/iterations/warmup, seed reporting.
- **Open-science:** data/code availability statements, OSF/GitHub/Zenodo links.

**Pure functions, deterministic output.** `run_detectors(parsed: ParsedDoc) -> list[Evidence]` —
no I/O, no LLM, no config-dependent behavior. Output ordering is canonical (section order, then
character offset), so identical input yields byte-identical output: the stage-3 sub-cache (spine
§3.5) is a pure replay. Each hit carries `detector_id` + `detector_version`; bumping any
`detector_version` invalidates the stage-3 sub-cache without re-parsing.

**Numeric-value extraction.** Rubric thresholds key on numbers, not mentions — so detectors parse
values into `Evidence.value` wherever the text states them: R-hat values and comparators
("all R̂ < 1.01", "Rhat = 1.002"; normalize R̂/\hat{R}/Rhat/r-hat), ESS numbers (incl. bulk/tail and
n_eff aliases), divergence counts ("12 divergent transitions", "no divergences" → 0),
chains/iterations/warmup counts, Pareto-k thresholds. `value` is a small structured payload
(`{metric, op?, number}` for diagnostics; counts for sampler config; URL for links); mentions
without numbers emit a mention-kind hit with `value` unset.

**Precision-first philosophy (the key engineering rule).** A missed mention is recoverable — the
LLM in e-assess reads the full sections and can still find it; a **false hit poisons grounding**,
because e-assess treats detector evidence as trustworthy and the report cites it as fact. So:
word-boundary and case-sensitive matching where ambiguity exists ("Stan" must not hit "standard
deviation", "Stanford", "instance"); context guards on short tokens (BUGS, TFP, ESS); detectors run
over `body|abstract|caption|supplement` sections but **skip `kind: references`** (citation lists
mention Stan/R-hat without the paper using them). Recall is reported, never gated; precision is
gated (test plan).

**Versioned catalog doc.** `core/detectors/CATALOG.md`: one entry per `detector_id` — version,
emitted `kind`(s), pattern family, value-extraction rule, known failure modes, changelog. The doc
is the review surface for adding detectors; no detector ships without an entry.

**Evidence inventory (what makes F3 shippable here).** A pure helper
`evidence_inventory(parsed, evidence)` groups hits by catalog family and renders three things:
**what was found** (per hit: quote + section + page), **what was not found** (every catalog entry
with zero hits, stated as "not detected", never "not done"), and **where the engine looked** (the
section kinds/titles scanned, incl. supplements — the A3 enumeration rule). With a (ingest) and
b (parse) in place, g renders this as the local-only report, labeled "detection only, not graded":
no LLM call, no scores, nothing leaves the machine.

## Interface contract
**Input — `ParsedDoc`** (§4.3): detectors read only `sections[].{id, kind, title, text,
page_spans}`. They must tolerate empty `text`, missing `page_spans` (then `span.page = null`), and
any section ordering. They never raise on malformed text; worst case is zero hits.

**Output — `Evidence[]`** (§4.3), possibly empty (zero hits is a valid result and a real signal
for the d relevance gate). Field semantics:
- `detector_id` — stable catalog id (e.g. `software.stan`, `diag.rhat_value`); `detector_version`
  — per-detector semver, bumped on any pattern/extraction change.
- `kind` — the **detector-emitted subset** of the §4.3 enum: `software_mention | method_mention |
  diagnostic_value | diagnostic_mention | workflow_signal | sampler_config | open_science`.
  (e-assess additionally mints `absence_search` Evidence items for its where-looked enumeration —
  that value belongs to the shared enum in `schema.py`, never to detector output.)
- `value?` — structured payload as above; absent for pure mentions.
- `span` — `{section_id, page, quote}`; **`quote` is a verbatim substring of that section's
  `text`** (hard guarantee — e-assess grounding and UI highlighting depend on it).
- Dedup: overlapping matches of the same detector in one section collapse to one `Evidence`
  (widest match wins); distinct detectors may overlap freely.

## Test plan
- **Table-driven snippet tests:** per detector, a parameterized table of (snippet → expected
  `Evidence[]` incl. `kind`, `value`, exact `quote`). Covers alias/notation variants (R̂ vs Rhat,
  n_eff vs ESS, "no divergent transitions" → count 0).
- **False-positive corpus:** snippets that must yield **zero** hits — "standard deviation",
  "Stanford", "rhattan", "Manhattan", "debugs", reference-list entries citing Stan/loo. Every FP
  found later in real use is added here as a permanent regression case.
- **Per-detector precision audit:** run on ~10 real-paper `ParsedDoc`s from the dev set (never
  gold-set papers); hand-label all hits. **Ship gate: precision ≥ 0.95 per catalog family**;
  recall recorded in CATALOG.md but not gated (precision-first).
- **Determinism test:** same fixture twice → byte-identical JSON output.
- **Record fixtures for downstream:** run over b's committed `ParsedDoc` fixtures; commit the
  `Evidence[]` JSON under `tests/fixtures/evidence/` — what d and e build against (spine additivity).
- **Inventory test:** fixture with known gaps → inventory lists found / not-found / where-looked
  correctly, including supplement sections.

## Definition of done
- [ ] `run_detectors` pure function implemented; full catalog covered (all five families, incl.
      method-mentions for the d relevance floor).
- [ ] Every hit carries `detector_id`, `detector_version`, and a span whose `quote` is verbatim.
- [ ] Numeric values extracted for R-hat, ESS, divergences, chains/iterations/warmup, Pareto-k.
- [ ] `CATALOG.md` exists; `detector_version` participates in the stage-3 sub-cache key.
- [ ] Snippet tables + FP corpus green; precision ≥ 0.95 per family on the dev-paper audit.
- [ ] `Evidence[]` fixtures recorded and committed for d and e.
- [ ] `evidence_inventory` produces found / not-found / where-looked; with a+b landed, the F3
      local-only report runs end-to-end with zero LLM calls — **M3 exit: local-only shippable**.

## Out of scope (deferred)
- **Asserted-but-not-evidenced detector class** — flagging named-but-unshown practices is policy in
  `ETHICS.md` (F1) for v0; the dedicated detectors are improvements **H6** (v1–v2).
- **Vision-based detection** of figure/table-borne diagnostics (trace plots, R-hat columns) —
  improvements **C2** (v1); v0's text-only cost is made visible by Tier-C probes (protocol §1).
- **Soft judgments** (was the prior *justified*? was the PPC *informative*?) — never detector work;
  that is e-assess's job, grounded by these hits.
