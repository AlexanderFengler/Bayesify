# Privacy & data handling

*Describes the app as built — the hosted instance at [bayesify.org](https://bayesify.org) and any
self-hosted copy run from this repository. This document is the source of truth; the landing page's
"Privacy & data handling" section summarises it. Last revised 2026-09.*

Bayesify has **no accounts, no tracking and no analytics**. What it does keep is the **graded
report** of every relevant paper it analyses — durably, in a shared database, and visible to everyone
in the public **Archive**. Read this before submitting an unpublished or confidential manuscript.

## What you submit

- **A PDF** (50 MB limit by default), *or* an **identifier** — arXiv ID, DOI, OpenAlex ID or URL.
  For an identifier the server fetches the open-access PDF from the arXiv API, OpenAlex, Unpaywall,
  Crossref, OSF, or the URL you gave; that request necessarily reveals to the provider which paper
  you are looking up. The operator's contact address (`UNPAYWALL_EMAIL`) is sent as the polite-pool
  identifier — nothing about you is.
- A **rubric**, and who assesses: **AI Agent** (the engine) or **Human Expert** (the blind rating
  form).

## The manuscript itself

- The bytes are hashed (SHA-256) and written to a **temporary directory on the server** for the run;
  the engine reads them from there, and a **rerun** of the same job reuses them. The directory is
  created per server process and disappears with it. The bytes are **never written to the database**
  and never leave the server except as extracted text and, for title extraction, an image of page 1
  (next section).
- The **uploaded filename** is kept as the report's source label, and the extracted **title, author
  list and year** are stored with the report. Rename the file if its name is itself sensitive.

## What is sent to a model (AI Agent only)

To grade a paper, Bayesify sends **extracted text** to the configured LLM provider — **Anthropic**
(an API key, or a Claude subscription through the Claude Agent SDK) or **OpenAI** (Responses API).
Which provider and which models is decided by whoever operates the instance; every report records
the backend and the per-call model IDs and token counts in its cost ledger, and shows a backend badge
in its header.

| Stage | What is sent |
| --- | --- |
| Title/author extraction (uploads without provider metadata) | Page-1 text (≤ 4 000 characters) and, on multimodal backends, a rendered image of page 1 |
| Relevance screen | Abstract, body and captions — references excluded — plus a summary of detector hits |
| Paper-type classifier | Section excerpts, up to 200 000 characters by default |
| Step grading and adversarial refutation | Section excerpts plus the wider context (supplements, captions), up to 500 000 characters by default — in practice the whole paper |
| Override review (at display time) | The step's excerpts and past trusted corrections that may apply to it |

Nothing else leaves the server: not the PDF file, not your IP address, not who you are. The
provider's own API data-handling terms apply to that text. If a manuscript is confidential or
embargoed, treat AI Agent mode as "this text will be sent to a third-party API" and decide
accordingly.

With no LLM backend configured (a self-hosted run), AI Agent mode falls back to a **labelled stub**
that returns a fixed example report; a stub result is never stored.

**Human Expert** and **Local** runs send nothing to any model: they run the on-device parser and the
deterministic detectors only, and produce an evidence inventory (what was found, where) rather than
scores. Local mode is reachable through the API (`mode=local`) but is not exposed in the hosted UI.

## What is stored, and who can see it

Reports and ratings are persisted to **MongoDB** — MongoDB Atlas for the hosted instance, a local
`mongod` for self-hosting. Persistence is best-effort: if the database is unreachable the analysis
still runs and simply is not saved.

- **`reports`** — one record per *paper content + rubric*, keyed by the content hash, written when
  the relevance gate passes (`yes` or `partial`) and refreshed on reruns and human ratings. It holds
  the title, authors, year, submitted identifier, source filename, scores and tags, the **full graded
  result** (per-step judgments, rationale and **verbatim evidence quotes** from the manuscript), the
  detector inventory, the engine and rubric versions, and the latest complete human rating.
- **`events`** — a sparse audit log: job lifecycle, report-ready pointers, rating pointers (with the
  rater id) and correction records (author label, rationale, quoted evidence).
- **The server's disk**, under `BAYESIFY_DATA_DIR` (default `~/.bayesify`): blind ratings as one JSON
  file per paper and rater id, and the corrections ledger.

**Every stored report is public.** The Archive lists all of them — title, authors, year, score,
coverage and tags — and each entry opens the full report, quotes included. There is no login and no
private analysis on the hosted instance. Identical bytes graded against the same rubric are not
re-analysed: the stored report is replayed to whoever submits them next, and the report you see may
have been produced by someone else's earlier submission.

Reports are kept **indefinitely**; nothing expires automatically.

## Human ratings and corrections

- **Blind ratings** are stored with the rater id you type (default `rater-1`), your declared
  relationship to the engine (independent, engine developer or prompt author), and your per-step
  judgments, rationale and quotes. They are anonymous exactly as far as the rater id you choose is.
- **"Disagree?" corrections** on a report are stored with the author label you enter (default
  `anonymous`), your rationale, the paper title, and the engine's own rationale plus up to five
  evidence quotes for that step. The complete corrections ledger can be exported without
  authentication (`GET /api/overrides/export`).
- A **trusted-reviewer token** lives only in your browser's local storage and travels with your
  corrections; the operator maps it to your name, which is then recorded on them. What trusted
  corrections do to grading is described in [`ETHICS.md`](ETHICS.md).

## Contact form

The About page's form sends your name, email address and message through **Resend** (a third-party
email API) to the maintainers' inbox, with your address as the reply-to. It is enabled only when the
operator has configured both a Resend key and a recipient address; otherwise it reports itself
unavailable.

## In the browser

No analytics, no trackers, no cookies. Local storage holds your colour-mode preference and, if you
set one, the reviewer token. Front-end errors are written to the browser console only and are not
transmitted anywhere.

## Server logs

The API writes standard web-server access logs (client IP address, path, status, timestamp) and a
startup line naming the database it reached, with credentials redacted. It records nothing linking
a person to a paper. What the hosting platform retains of those logs is governed by that platform.

## Removal

There is **no self-service delete**. To have a report removed from the Archive and the database,
contact the maintainers through the About page or the repository; the record is deleted by its
content hash. Rerunning a paper replaces its stored report rather than adding a second one.

## Summary

| | AI Agent | Human Expert | Local (API only) |
| --- | --- | --- | --- |
| Extracted text → LLM provider | yes | no | no |
| PDF bytes stored durably | no | no | no |
| Stored in the database | the report, if the paper is relevant | your rating, if complete and relevant | nothing |
| Visible in the public Archive | yes | yes | no |
| Produces scores | yes | your own | no — evidence inventory |
| Accounts, telemetry | none | none | none |
