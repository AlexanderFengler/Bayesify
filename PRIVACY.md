# Privacy & data handling

*Draft (milestone M1). Authors upload **unpublished manuscripts** to a tool like this, so the data
path must be stated plainly. This document is the source of truth; the in-app privacy surface
(first-run disclosure, mode indicator, per-paper delete) is completed at milestone M6.*

VeriBayes is **local-first**: it runs on your machine, and all storage — the SQLite database, parsed
artifacts, cached results, and exported reports — stays on your machine. There is **no telemetry** and
no account.

## What leaves your machine

There are two analysis modes, chosen per paper:

### Full mode

To make per-step judgments, VeriBayes sends **extracted text from your document** (and, later, figure
captions) to the Anthropic API. Nothing else leaves the machine — not the PDF file itself, not your
identity, not the results. This is the only outbound data flow in full mode.

If your manuscript is confidential or embargoed, treat full mode as "this text will be sent to a
third-party API for processing" and decide accordingly — or use local-only mode.

### Local-only mode

**Nothing leaves your machine.** Local-only mode runs the structure-aware parser and the deterministic
detectors only — no LLM call, no text sent anywhere. It produces an **evidence inventory** ("what was
found, where; what was not found"), **not a graded report**: there are no coverage or quality scores
in this mode, because scoring requires the model's judgment.

> At M1 the detector catalog does not exist yet, so local-only mode is a labelled placeholder. It
> becomes genuinely useful at milestone M3, when the detectors land.

## Identifiers (arXiv / DOI / OpenAlex / URL)

When you submit an identifier instead of a file, VeriBayes contacts the corresponding open-access
provider (arXiv, OpenAlex, Unpaywall, Crossref) to fetch the paper. That request necessarily reveals
which paper you are looking up to that provider. (Identifier fetching arrives at milestone M2; at M1
the identifier is accepted but not yet resolved.)

## Right to forget

Deleting a paper purges everything derived from it. The complete purge — including the
content-addressed document bytes and any cache entries — is wired up at milestone M2 alongside the
local store; a delete endpoint exists today.

## Summary

| | Full mode | Local-only mode |
|---|---|---|
| Document text → Anthropic API | yes | **no** |
| Stored locally only | yes | yes |
| Produces scores | yes | no (evidence inventory) |
| Telemetry | none | none |
