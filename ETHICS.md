# Responsible use of Bayesify

*Draft (milestone M1). This is a shipped artifact, not an aspiration — it ships with the tool and the
report links it. It will be tightened as the engine and the validation evidence mature.*

Bayesify reads an academic paper and reports how well it followed established Bayesian-workflow
practices, step by step. This document states what that report does and does not mean, and how it can
be misused.

## Formative, not a verdict

- **There is no pass/fail badge.** The earlier Verified/Shaky/Failed badge was deliberately dropped.
  Bayesify reports a **per-step profile** plus two transparent summary scores (coverage and quality).
- The scores attest to **workflow practice as detectable in the document(s)** — whether the paper
  *reports* and *justifies* the steps of a principled Bayesian workflow. They do **not** attest to the
  correctness of the paper's results, the validity of its scientific claims, or the competence of its
  authors.
- A low coverage score can reflect *under-reporting* as much as *under-doing*: a diagnostic done but
  not described, or done in an unparsed figure or supplement, looks the same to a text-only engine as
  one never done. The report flags low-confidence absences as such; do not read them as proof of bad
  work.

## The instrument must meet its own bar

Bayesify is itself a measurement instrument. Until it has been validated against expert ratings
(milestone M7, see `validation/protocol.md`), **every report is labelled "preliminary"** and should
be read as a structured prompt for reflection, not as evidence. Corpus-level claims (Phase 3) are
only as good as the engine's measured accuracy and will quote it as measurement error.

## Gaming surface (documented, not hidden)

- **Writing the magic words without doing the work.** Naming a check ("we performed posterior
  predictive checks") without showing or quantifying it is not credited as done: every positive
  finding requires an **evidence span** from the paper, and an asserted-but-unevidenced practice is
  marked as such and scores `partial` at best. Hardening this into a dedicated detector class is
  planned future work.
- **Prompt injection (open attack surface, disclosed).** The engine is an LLM reading
  author-controlled text. Hidden or white-font instructions, PDF-comment payloads, or "system:"-style
  strings in a supplement could try to coerce a favourable judgment. v0 does **not** yet defend
  against this; red-teaming and mitigations (instruction/data separation, flagging invisible-text
  spans) are scheduled. Treat any individual report accordingly.
- **Iterating against the grader.** The tool is local and free to re-run, and it tells you which
  change would raise a score. Editing prose against the grader can lift a score without improving the
  science; robustness to this is unmeasured in v0.

## Misuse guidance

- **For authors:** a self-check before submission. The suggestions are starting points, not
  requirements; some legitimately do not apply to your paper (the report marks those "not
  applicable").
- **For reviewers and editors:** a structured aid for organising a methodological critique — **not an
  auto-reject machine.** Do not paste a Bayesify verdict into a review as unattributed authority;
  carry the engine/rubric versions and the "preliminary" status with it.
- **Third-party scoring.** Bayesify does not auto-publish scores about other people's papers. The
  Phase-3 corpus dashboards (named-paper badges over a sampled literature) will carry their own,
  stricter ethics note before they launch; the default for public outputs is aggregate-only.

## Known biases (disclosed)

- **Language / ecosystem.** The rubric and detectors are English-language and lean on the
  Stan-ecosystem vocabulary (R-hat, ESS, divergences, LOO). Papers using other tools or languages may
  be under-detected. A subfield/venue bias audit is planned once a validation set exists.
- **Text-only.** Many diagnostics live only in figures (trace/rank plots, PPC overlays) and table
  columns. The current engine reads text and captions; a vision pass is the top post-v0 priority.
  Until then, figure-borne practice can produce false "missing" flags.

## Scope of this milestone

At M1 the engine is a **stub**: it returns a fixed, hand-authored example report and performs no real
analysis. The report UI labels this clearly. The real ingest → parse → detect → screen → classify →
assess → score pipeline arrives across subsequent milestones.
