# b. Parse — VeriBayes v0 component

**Milestone:** M2
**v0 items covered:** C3 (structure-aware parsing incl. supplements)
**Contract:** consumes `SourceDoc` → produces `ParsedDoc`   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** none upstream at test time — tests construct `SourceDoc` literals pointing
at component a's canonical committed fixture set (`tests/fixtures/pdfs/` + `sourcedocs/`; a's *code*
is not required). GROBID is stubbed by recorded TEI responses; the live docker service is exercised
only in a marked integration test.

## Purpose
Turn the fetched document(s) into a structure-aware `ParsedDoc`: sections with kinds, captions, and
page spans — including supplements and appendices. Structure matters because **absence claims depend
on where the engine looked** (spine §3.5, A3): "no convergence diagnostics" is only assertable if
the supplement and the figure captions were actually parsed. This stage is deterministic and LLM-free,
so it also underpins the F3 local-only evidence inventory.

## Design
Carried over from the old plan §3.4 stage 2: **GROBID primary, PyMuPDF fallback** → structured
sections incl. **supplements/appendices**, **figure/table captions**, and **references**.

**`ParsedDoc` construction.** `core/parse.py` resolves document bytes from the local ingest store via
`SourceDoc.sha256`, then builds `ParsedDoc{source, sections[], parser, parser_version}`:
- `sections[].kind ∈ {body, abstract, caption, supplement, references}` — mapped from GROBID TEI
  (`abstract`, `<div>` body sections, `<figDesc>` → caption, `<div type="appendix">` → supplement,
  `listBibl` → references). Kind reflects the content's *role*; which file it came from lives in
  `page_spans`.
- `sections[].id` — deterministic (`s01, s02, …` in document order, supplements after body) so
  `Evidence.span.section_id` references and cached fixtures are stable across runs.
- `sections[].page_spans` — `[{doc_sha256, page_start, page_end}]`; `doc_sha256` defaults to the
  primary source and differs for separate supplement files. This is the anchor every downstream
  evidence span and the UI's PDF-highlighting need.
- `sections[].title` — heading text, or `"Figure 3"` / `"Table 2"` for captions.

**Captions are first-class.** Every figure/table caption becomes its own `kind: caption` section
(never inlined into body text). The C2 vision upgrade and the validation Tier-C figure-only probes
(protocol §1) both key on captions being captured *now* — captions are where "see trace plots,
Fig. S4" lives, and they are the seam C2 plugs into without a parser rewrite.

**Supplement/appendix discovery.**
- *Same-PDF appendices:* TEI `type="appendix"` divs, plus a heading heuristic for material after
  references matching `Appendix|Supplementary|Supporting Information|S\d+` → `kind: supplement`.
- *Separate supplement files:* when ingest provides additional documents alongside the primary
  (multi-file upload, [`a-ingest-fetch`](a-ingest-fetch.md); arXiv source-package supplements are
  deferred with H5), each is parsed and merged into the **one** `ParsedDoc`: their sections get `kind: supplement` (captions inside them stay
  `kind: caption`), with `page_spans.doc_sha256` identifying the file.

**GROBID as a docker dependency; recorded degraded fallback.** GROBID runs as a docker-compose
service (`grobid/grobid`, pinned tag), health-checked at engine startup. If unreachable or it errors
on a document, parse degrades to PyMuPDF + heuristics (font-size/heading regex sectioning;
`^(Figure|Table|Fig\.)\s+\w+` caption lines; references split on the References/Bibliography
heading). The mode used is **recorded in the contract**: `parser: "grobid" | "pymupdf"` with the
exact `parser_version` (e.g. `"grobid-0.8.1"` / `"pymupdf-1.24"`), so every downstream judgment,
cache entry, and report footer knows whether it ran on degraded structure. The parse sub-cache key is
`sha256(bytes) × parser × parser_version` (spine §3.5), so a GROBID upgrade re-parses but an
LLM-engine upgrade does not.

**Scanned / no-text PDFs.** If median extractable text falls below a floor (~200 chars/page), parse
raises a typed `UnparseableDocument(reason="no_text_layer")` instead of emitting garbage; the API
maps it to a clear user message ("scanned PDF — OCR not supported in v0"). Flag only; no OCR.

## Interface contract
- **In:** `SourceDoc {sha256, ids{doi?, arxiv_id?, openalex_id?}, version_label, source, fetched_at}`
  (primary) + optional supplement `SourceDoc`s from ingest; bytes resolved from the local store by
  `sha256` — parse never re-fetches.
- **Out:** `ParsedDoc {source, sections[{id, kind: body|abstract|caption|supplement|references,
  title, text, page_spans}], parser, parser_version}` — `source` is the *primary* `SourceDoc`;
  supplement provenance is in `page_spans.doc_sha256`. Section order = reading order, supplements
  last. Empty-text sections are dropped.
- **Errors:** `UnparseableDocument(reason)` (typed; reasons: `no_text_layer`, `corrupt_pdf`,
  `encrypted`) aborts the job with a user-facing explanation. GROBID unavailability is **not** an
  error: degraded result with `parser: "pymupdf"`. A document yielding no recognizable structure
  still returns a valid `ParsedDoc` (single `body` section) — downstream must tolerate that.

## Test plan
Fixture PDFs in `tests/fixtures/pdfs/` (small, redistributable or fetched-once-and-hashed):
1. **two-column** journal-style paper — section segmentation, reading order, captions across columns;
2. **appendix-in-same-PDF** — appendix sections come out `kind: supplement` with correct page_spans;
3. **main + separate supplement file** — merged `ParsedDoc`; supplement sections carry the
   supplement's `doc_sha256`; captions inside the supplement are `kind: caption`;
4. **scanned/no-text** — raises `UnparseableDocument(reason="no_text_layer")`, never garbage output.

Tests run **without docker**: GROBID TEI responses for fixtures 1–3 are recorded under
`tests/fixtures/grobid_tei/` and replayed; one `@integration` test hits the live container.
Assertions: every expected section kind present per fixture; every `Figure N`/`Table N` caption
captured as its own non-empty `caption` section; references isolated from body; section ids and
page_spans byte-stable across two runs (cache determinism). **Fallback parity smoke test:** parse
fixture 1 with both parsers; PyMuPDF must recover abstract + a body/references split + ≥80% of
GROBID's body text and ≥50% of its captions (smoke thresholds, not validation metrics).
**Recorded outputs:** serialized `ParsedDoc` JSON for fixtures 1–3 is committed to
`tests/fixtures/parsed/` — these are the input fixtures components **c** (detectors), **d**
(screen/classify), and **e** (assess) test against, never the live chain.
**Ship gates:** unit suite green offline; integration test green against the pinned GROBID image;
`ParsedDoc` fixtures regenerated and diff-reviewed whenever `parser_version` changes.

## Definition of done
- [ ] `core/parse.py` returns schema-valid `ParsedDoc` for fixtures 1–3 via GROBID, all section
      kinds and captions asserted; ids/page_spans deterministic.
- [ ] Same-PDF appendices and separate supplement files both land as `kind: supplement` with correct
      `doc_sha256` provenance.
- [ ] PyMuPDF fallback passes the parity smoke test; `parser`/`parser_version` correctly record the
      engine actually used, and feed the parse sub-cache key.
- [ ] GROBID runs from docker-compose with health check; engine degrades (not fails) when it's down.
- [ ] Scanned-PDF fixture raises the typed error; API surfaces the OCR-not-supported message.
- [ ] `ParsedDoc` fixtures committed under `tests/fixtures/parsed/` and consumed by component c's
      test suite.

## Out of scope (deferred)
- **Figure/table *content* parsing via vision models** — captions only in v0; vision is C2
  (`04-improvements-and-extensions.md` §C2, the top post-v0 priority).
- **OCR for scanned PDFs** — typed flag only; tracked alongside C2 in improvements §C.
- **Linked-artifact fetching** (repos/OSF) — C4.
- **Structured bibliography / citation matching** — references kept as a text section; resolution
  belongs to Phase 3 (`03-ingestion-corpus-plan.md`).
