# Responsible use of Bayesify

*Describes the tool as built — the hosted instance at [bayesify.org](https://bayesify.org) and
self-hosted copies. It ships with the tool and will be tightened as the validation evidence
matures. Last revised 2026-09.*

Bayesify reads an academic paper and reports how well it *documents* a principled Bayesian
workflow, step by step, against one of three rubrics distilled from the methodological literature
(`synthesis`, `gelman`, `schad`). This document states what that report does and does not mean,
how it is produced, and how it can be misused.

## Formative, not a verdict

- **There is no pass/fail badge.** A report is a **per-step profile** — `adequate`, `partial`,
  `missing` or not applicable per rubric step, each with the evidence it rests on — plus two
  transparent summary scores: **coverage** (share of applicable steps present) and **quality** (a
  weighted mean of step scores; the README documents the weights).
- The scores attest to **workflow practice as detectable in the document**: whether the paper
  *reports* and *justifies* the steps. They do **not** attest to the correctness of its results,
  the validity of its claims, or the competence of its authors.
- **There is no single standard workflow.** The three rubrics embody different philosophies and
  can grade the same paper differently; a score is always relative to the rubric named on the
  report.
- A low score can reflect *under-reporting* as much as *under-doing*: a diagnostic done but not
  described, or shown only in a figure, looks the same to a text-based engine as one never done.
  Every `missing` finding names where the engine looked, and low-confidence absences are flagged
  as such — do not read them as proof of bad work.

## How a grade is produced

The engine is a real multi-stage pipeline. (The original fixed-example stub survives only as a
labelled fallback for self-hosted runs with no model configured; stub results are never stored.)

1. **Parse** — text, sections, captions and supplements are extracted from the PDF.
2. **Detect** — deterministic pattern detectors inventory Bayesian vocabulary, diagnostics and
   software. The inventory is evidence, not a grade.
3. **Screen** — a cheap model call decides whether the paper uses Bayesian methodology at all. A
   `no` stops the pipeline: a non-Bayesian paper gets no score. If two or more independent
   Bayesian evidence families were detected, the model is not allowed to say `no`.
4. **Classify** — the model answers a fixed checklist of factual questions (paper type, inference
   methods, software) that decides which steps apply and how they are weighted. Mentioning a
   method or package is not the same as using it: only reported use counts.
5. **Assess** — for each applicable step a model judge, shown the mapped evidence and excerpts,
   grades the step and must cite **verbatim evidence spans**, which are checked against the text.
   An **adversarial refuter** then attacks every negative finding over a wider slice of the paper
   (supplements, captions, alternative wordings) before it is reported.
6. **Score** — a pure, deterministic function turns the step judgments into coverage and quality.
7. **Override review** (display time only) — if trusted reviewers have corrected similar steps on
   other papers, a model judges whether any such correction applies here and may adjust the step
   by at most one level, citing the correction. The validation harness measures the raw engine
   without this pass.

Each report records its engine version, rubric version, grading strategy, backend and per-call
model IDs and token counts, so any number can be traced to what produced it. Model outputs are not
deterministic: rerunning a paper can move a step. To keep results stable and cheap, identical
content graded against the same rubric is **not re-analysed** — the stored report is replayed until
the engine or rubric changes; a rerun can be forced from the report.

## The instrument must meet its own bar

Bayesify is itself a measurement instrument. **It has not yet been validated against expert
ratings.** The calibration page currently shows either a demo built from a labelled *fake* gold set
or "not yet validated"; the blind Human Expert flow exists to collect the real ratings
(`validation/protocol.md`). Until that validation is published, treat every report as a structured
prompt for reflection, not as evidence, and quote it with its engine and rubric versions.
Corpus-level claims (Phase 3) will carry the measured accuracy as their error term.

## Public archive and third-party scoring

The hosted instance keeps every relevant graded report and lists it in a **public Archive** — title,
authors, year, score, coverage, tags and the full evidence-linked report — regardless of who
submitted the paper. Analyzing a paper therefore publishes a preliminary, rubric-relative score of
it under its authors' names. Consider that before submitting someone else's work. The Archive says
which rubric and engine produced each score, the scores are formative and unvalidated in the sense
above, and authors can have a record removed by contacting the maintainers (see
[`PRIVACY.md`](PRIVACY.md)). Aggregate, corpus-level dashboards (Phase 3) will carry their own,
stricter note before they launch.

## Human corrections

Anyone can disagree with a step on a report. A plain correction is recorded as an **advisory note**
under the author label given and changes no grade. A correction made with a **trusted-reviewer
token** (issued by the maintainers and mapped to a named person) enters a global correction bank and
can adjust the same step on *similar* papers through the override-review pass above —
conservatively, by at most one level, and always linked back to the correction and its source
paper. Trusted reviewers are therefore part of the instrument: their names are recorded on their
corrections, and the complete correction ledger is exportable.

## Gaming surface (documented, not hidden)

- **Writing the magic words without doing the work.** Naming a check is not credited as doing it:
  every positive finding needs a cited evidence span, the classifier distinguishes methods that are
  *used* from methods that are merely *discussed*, and a step that is asserted or named but not
  shown or quantified scores `partial` at best.
- **Prompt injection (open attack surface, disclosed).** The engine is a model reading
  author-controlled text. Hidden or white-font instructions, PDF-comment payloads or "system:"-style
  strings could try to coerce a favourable judgment. The engine does **not** yet defend against this;
  red-teaming and mitigations (instruction/data separation, flagging invisible-text spans) remain
  planned. Treat any individual report accordingly.
- **Iterating against the grader.** The tool is free to re-run and tells you which change would
  raise a score. Editing prose against the grader can lift a score without improving the science;
  robustness to this is unmeasured.

## Misuse guidance

- **For authors:** a self-check before submission. Suggestions are starting points, not
  requirements; some legitimately do not apply to your paper (the report marks those not
  applicable).
- **For reviewers and editors:** a structured aid for organising a methodological critique — **not
  an auto-reject machine**. Do not paste a Bayesify score into a review as unattributed authority;
  carry the rubric, the engine version and the unvalidated status with it.
- **For meta-researchers:** per-paper scores in the Archive are not a validated measurement. Wait
  for the calibration results, and report scores only with the measured error.

## Known biases and limitations (disclosed)

- **Language and ecosystem.** The rubrics, detectors and prompts are English-language and lean on
  Stan-ecosystem vocabulary (R-hat, ESS, divergences, LOO). Papers using other tools or languages
  may be under-detected.
- **Text-first.** The engine reads text, captions and supplements; the only image it looks at is a
  rendering of page 1, used to read the title and byline. Diagnostics that live only in figures
  (trace or rank plots, PPC overlays) can produce false `missing` flags; the refuter and the
  low-confidence marking reduce but do not remove this.
- **Classification noise.** Paper type can be misjudged when a paper states its intent loosely, and
  inference methods or software can be misclassified or over-extracted (the landing page's "Known
  limitations"). Because applicability and weights follow the classification, such errors propagate
  to the scores.
- **Fetching.** Identifier fetching covers arXiv and the open-access providers listed in
  `PRIVACY.md`; many publisher sites are not supported — upload the PDF instead.
