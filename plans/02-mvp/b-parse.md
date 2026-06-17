# b. Parse — VeriBayes v0 component

**Milestone:** M2
**v0 items covered:** C3 (structure-aware parsing incl. supplements)
**Contract:** consumes `SourceDoc` → produces `ParsedDoc`   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** none upstream at test time — tests construct `SourceDoc` literals pointing
at component a's canonical committed fixture set (`tests/fixtures/pdfs/` + `sourcedocs/`; a's *code*
is not required). **Docling** runs in-process (no external service), so there is nothing to stub: a
few `@slow` tests run it on small fixture PDFs and assert structural properties; everything else
builds against the committed recorded `ParsedDoc` fixtures.

## Purpose
Turn the fetched document(s) into a structure-aware `ParsedDoc`: sections with kinds, captions, and
page spans — including supplements and appendices. Structure matters because **absence claims depend
on where the engine looked** (spine §3.5, A3): "no convergence diagnostics" is only assertable if
the supplement and the figure captions were actually parsed. This stage is deterministic and LLM-free,
so it also underpins the F3 local-only evidence inventory.

## Parser choice — Docling primary (decided 2026-06-13)

**Primary parser: [Docling](https://github.com/docling-project/docling)** (PyMuPDF fast fallback;
GROBID dropped). Verified + prototyped before deciding:
- **Verified facts:** MIT-licensed, v2.102 (Jun 2026), actively maintained (61.5k★), an **LF AI & Data**
  project started at IBM Research. Pure-Python, **runs locally / air-gapped** (no Java service, no
  docker) → fits our local-first + pixi setup. Produces a structured `DoclingDocument` with layout,
  reading order, section structure, **table-structure recognition**, figures, captions, formulas,
  and OCR.
- **Prototyped on real papers** from `research/sources/pdfs/`: on Vehtari 2021 (26 pp) it recovered
  30 hierarchical section headers, 37 figure captions, and 26 formulas; on Vehtari 2017 and Gelman
  2020 it extracted **3 and 4 tables** respectively and parsed a results table into clean columns/rows.
  Warm inference ≈ 3 s/paper (first run / very long docs slower; models load once).
- **Why over GROBID:** GROBID's one clear edge is reference/citation parsing — our weakest need (we
  mostly *exclude* references from detectors; citation matching is a Phase-3 concern). Docling wins on
  the things we *do* need: **table structure** (R-hat/ESS columns become structured cells a detector
  can read — a direct head-start on C2), first-class captions, and zero-service deployment.
- **Cost / caveat:** Docling pulls a heavy dependency tree (torch + layout/table models, ~hundreds of
  MB–~1 GB downloaded on first use) and CPU inference is slower per-doc than GROBID. Acceptable for a
  local tool; the dependency lands when this component is built (it is **not** in the committed env
  yet). Pin the docling version; it moves fast.

## Design
**Docling primary, PyMuPDF fast fallback** → structured sections incl. **supplements/appendices**,
**figure/table captions**, and **references**.

**`ParsedDoc` construction.** `core/parse.py` resolves document bytes from the local ingest store via
`SourceDoc.sha256`, runs Docling once, and maps the `DoclingDocument` into
`ParsedDoc{source, sections[], parser, parser_version}`:
- `sections[].kind ∈ {body, abstract, caption, supplement, references}` — mapped from Docling
  `DocItemLabel`s: `section_header`/`text`/`list_item`/`formula` → `body` (grouped under their
  heading), the abstract header's group → `abstract`, `caption` → `caption`, the bibliography group →
  `references`, and post-reference appendix material → `supplement` (see discovery below). Page
  furniture (`page_header`/`page_footer`/`footnote`) is dropped. Kind reflects the content's *role*;
  which file it came from lives in `page_spans`.
- **Tables** are captured as their own `kind: body` (or a future dedicated kind) carrying the table's
  structured text (Docling `TableItem.export_to_markdown`), so a detector can read R-hat/ESS columns
  directly — this is the table-borne slice of C2, available now.
- `sections[].id` — deterministic (`s01, s02, …` in document order, supplements after body) so
  `Evidence.span.section_id` references and cached fixtures are stable across runs.
- `sections[].page_spans` — `[{doc_sha256, page_start, page_end}]`; `doc_sha256` defaults to the
  primary source and differs for separate supplement files. This is the anchor every downstream
  evidence span and the UI's PDF-highlighting need.
- `sections[].title` — heading text, or `"Figure 3"` / `"Table 2"` for captions.

**Captions are first-class.** Every figure/table caption becomes its own `kind: caption` section
(Docling already emits these as distinct `caption` items — confirmed in the prototype, 37 captions on
a 26-page paper). The remaining C2 vision work (reading the *plot pixels* — trace/rank/PPC plots) and
the validation Tier-C figure-only probes (protocol §1) both key on captions being captured *now* —
captions are where "see trace plots, Fig. S4" lives, and they are the seam the plot-vision upgrade
plugs into without a parser rewrite.

**Supplement/appendix discovery.**
- *Same-PDF appendices:* TEI `type="appendix"` divs, plus a heading heuristic for material after
  references matching `Appendix|Supplementary|Supporting Information|S\d+` → `kind: supplement`.
- *Separate supplement files:* when ingest provides additional documents alongside the primary
  (multi-file upload, [`a-ingest-fetch`](a-ingest-fetch.md); arXiv source-package supplements are
  deferred with H5), each is parsed and merged into the **one** `ParsedDoc`: their sections get `kind: supplement` (captions inside them stay
  `kind: caption`), with `page_spans.doc_sha256` identifying the file.

**Fast fallback; recorded degraded mode.** If Docling fails or is unavailable (e.g. models not yet
downloaded in an offline first-run), parse degrades to **PyMuPDF + heuristics** (font-size/heading
regex sectioning; `^(Figure|Table|Fig\.)\s+\w+` caption lines; references split on the
References/Bibliography heading). The parser used is **recorded in the contract**: `parser: "docling"
| "pymupdf"` with the exact `parser_version` (e.g. `"docling-2.102.1"` / `"pymupdf-1.24"`), so every
downstream judgment, cache entry, and report footer knows whether it ran on degraded structure. The
parse sub-cache key is `sha256(bytes) × parser × parser_version` (spine §3.5, gate G2), so a Docling
or model upgrade re-parses but an LLM-engine upgrade does not.

**Scanned / no-text PDFs.** Docling ships OCR (RapidOCR), so scanned PDFs are parseable in principle;
for cost/latency control OCR is **off by default in v0** and a scanned PDF (median extractable text
below ~200 chars/page) raises a typed `UnparseableDocument(reason="no_text_layer")` mapped to a clear
user message. Enabling Docling OCR is a config flag, not a rewrite — a cheap future upgrade.

## Interface contract
- **In:** `SourceDoc {sha256, ids{doi?, arxiv_id?, openalex_id?}, version_label, source, fetched_at}`
  (primary) + optional supplement `SourceDoc`s from ingest; bytes resolved from the local store by
  `sha256` — parse never re-fetches.
- **Out:** `ParsedDoc {source, sections[{id, kind: body|abstract|caption|supplement|references,
  title, text, page_spans}], parser, parser_version}` — `source` is the *primary* `SourceDoc`;
  supplement provenance is in `page_spans.doc_sha256`. Section order = reading order, supplements
  last. Empty-text sections are dropped.
- **Errors:** `UnparseableDocument(reason)` (typed; reasons: `no_text_layer`, `corrupt_pdf`,
  `encrypted`) aborts the job with a user-facing explanation. Docling unavailability is **not** an
  error: degraded result with `parser: "pymupdf"`. A document yielding no recognizable structure
  still returns a valid `ParsedDoc` (single `body` section) — downstream must tolerate that.

## Test plan
Fixture PDFs in `tests/fixtures/pdfs/` (small, redistributable or fetched-once-and-hashed):
1. **two-column** journal-style paper — section segmentation, reading order, captions across columns;
2. **appendix-in-same-PDF** — appendix sections come out `kind: supplement` with correct page_spans;
3. **main + separate supplement file** — merged `ParsedDoc`; supplement sections carry the
   supplement's `doc_sha256`; captions inside the supplement are `kind: caption`;
4. **scanned/no-text** — raises `UnparseableDocument(reason="no_text_layer")`, never garbage output.

Docling runs **in-process** (no service); the heavy/slow runs are marked `@slow` and excluded from
the default fast suite. Most tests build against the **committed recorded `ParsedDoc` fixtures** (the
contract instances c/d/e consume), so the fast suite needs no models. The `@slow` tests run Docling
on fixtures 1–3 and assert **structural properties** (not byte-equality — ML output is not guaranteed
byte-stable across model versions): every expected section kind present; every `Figure N`/`Table N`
caption captured as its own non-empty `caption` section; references isolated from body; tables
present where expected. **Fallback parity smoke test:** parse fixture 1 with both parsers; PyMuPDF
must recover abstract + a body/references split + ≥80% of Docling's body text and ≥50% of its
captions (smoke thresholds, not validation metrics).
**Recorded outputs:** serialized `ParsedDoc` JSON for fixtures 1–3 is committed to
`tests/fixtures/parsed/`, stamped with the `docling`/model version that produced them, and
regenerated + diff-reviewed on a deliberate version bump (gate G2 / the fixture-cascade policy) —
these are the input fixtures components **c**, **d**, and **e** test against, never the live chain.
**Ship gates:** fast unit suite green offline (fixture-only); `@slow` Docling structural tests green
on the pinned docling version.

## Definition of done
- [ ] `core/parse.py` returns schema-valid `ParsedDoc` via Docling for fixtures 1–3, all section
      kinds and captions asserted; ids/page_spans deterministic; tables captured as structured text.
- [ ] Same-PDF appendices and separate supplement files both land as `kind: supplement` with correct
      `doc_sha256` provenance.
- [ ] PyMuPDF fallback passes the parity smoke test; `parser`/`parser_version` correctly record the
      engine actually used (`docling-<v>` / `pymupdf-<v>`), and feed the parse sub-cache key.
- [ ] Docling added to the env as a `parse` optional-dependency group/pixi feature (kept out of the
      default fast-test env so CI stays light); version pinned.
- [ ] Scanned-PDF fixture raises the typed error; API surfaces the OCR-not-supported message.
- [ ] `ParsedDoc` fixtures committed under `tests/fixtures/parsed/` (version-stamped) and consumed by
      component c's test suite.

## Out of scope (deferred)
- **Plot/figure-pixel understanding via vision models** — Docling gives us caption text and **table
  structure** now; reading the *plot pixels* (trace/rank/PPC overlays) is the remaining C2
  (`04-improvements-and-extensions.md` §C2, the top post-v0 priority).
- **OCR for scanned PDFs** — Docling supports it (RapidOCR); off by default in v0 for cost/latency,
  a config-flag upgrade rather than new work.
- **Linked-artifact fetching** (repos/OSF) — C4.
- **Structured bibliography / citation matching** — references kept as a text section; resolution
  belongs to Phase 3 (`03-ingestion-corpus-plan.md`).
