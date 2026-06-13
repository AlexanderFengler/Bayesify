# a. Ingest & fetch — VeriBayes v0 component

**Milestone:** M2
**v0 items covered:** C5 (multi-format ingest) · C6 (caching + cost discipline — the cache *entry point*; ledger/budget guard live with the LLM stages)
**Contract:** consumes upload bytes (primary + optional supplement PDFs) or pasted ID/URL → produces a primary `SourceDoc` + optional supplement `SourceDoc`s   (types: ../02-mvp-tool-plan.md §4.3)
**Depends on / stubs:** only M1 skeleton (`schema.py`, `cache.py` shell). No upstream pipeline stage exists before it. Tested with recorded-HTTP transports; downstream components (b–g) are absent — this component *records* the `SourceDoc` + blob fixtures they consume.

## Purpose
Turn whatever the user gives us — a dropped PDF or a pasted arXiv ID / DOI / OpenAlex ID / URL — into one canonical `SourceDoc` plus a content-addressed byte blob, and perform the stage-0 cache check so repeat assessments cost nothing. This is `core/ingest.py` + `core/fetcher.py`: the ID → OA-PDF resolution module (arXiv API → OpenAlex/Unpaywall OA location → Crossref metadata) that Phase 3's acquisition step (`03-ingestion-corpus-plan.md`, M3) imports **verbatim** — built once, here, web-framework-free.

## Design
*(Carries over old plan §3.3 `fetcher.py`, §3.4 stages 0–1, and the §3.6 cache-key formula.)*

**Accepted inputs (C5).** (1) **PDF bytes** from the dropzone — which accepts **multiple files**:
one primary paper plus optional supplement PDFs (each hashed and blob-stored identically, emitted as
supplement `SourceDoc`s; [`b-parse`](b-parse.md) merges them into the one `ParsedDoc`); (2) **arXiv ID** — new style `2107.09023` with optional `v\d+`, old style `math.ST/0605234`, `arXiv:` prefix, abs/pdf URLs; (3) **DOI** — bare, `doi:`-prefixed, or `https://doi.org/...`; (4) **OpenAlex ID** — `W...` or full URL; (5) **URL** — direct PDF link, or a landing URL recognized as an arXiv/DOI form and re-dispatched to the matching resolver. A single `parse_input(str) -> NormalizedId | RawUrl` dispatcher decides; unparseable input raises `UnrecognizedInputError` (never a silent guess).

**ID normalization.** DOIs are **lowercased and de-versioned** (resolver prefixes stripped; trailing `.v\d+` registrant version suffixes split off and kept as a version hint) — DOIs are case-insensitive and we must not cache the same paper under two spellings. arXiv version suffixes are likewise split out, not discarded. The normalized forms populate `SourceDoc.ids{doi?, arxiv_id?, openalex_id?}`, including IDs *learned* during resolution (a DOI lookup that surfaces an arXiv ID records both — Phase 3 dedup depends on this).

**Resolution chain (old plan §3.4 stage 1, verbatim policy).** `fetcher.py` resolves IDs to an OA PDF:
1. **arXiv API** — for arXiv IDs (and DOIs that map to arXiv): authoritative metadata + PDF, version explicit. Politeness: ≤ 1 request / 3 s, single connection; use `export.arxiv.org`; **link back to arXiv for downloads** (its default license does not grant redistribution).
2. **OpenAlex / Unpaywall** — for DOIs/OpenAlex IDs: best OA location (`version` tells us VoR vs accepted manuscript), plus the **per-location `license`** field (cc-by / cc0 / publisher-specific / null).
3. **Crossref** — metadata of last resort; if it yields no fetchable OA PDF either, raise `NoOpenAccessError` carrying the title/venue found, so the UI can say *which* paper we found and invite a manual PDF upload.

**Provider terms & config (verified 2026-06-13 — see the OA-providers research).** Both providers are
fit for this on-demand single-paper use, with conditions, so the fetcher takes config and records
provenance accordingly:
- **OpenAlex** moved to a metered API (Feb 2026): a **free API key is now required** for real use
  (`OPENALEX_API_KEY`, env/config); single-entity DOI lookups remain free, but list/search/bulk are
  billed past a ~$1/day credit. For *this* component (one lookup per paper) the free tier suffices;
  the corpus path (Phase 3) uses the CC0 snapshot instead (`03` §2.1). 100 req/s hard cap.
- **Unpaywall** is free but requires a contact **`email` query parameter** (`UNPAYWALL_EMAIL`,
  config), ≤ 100,000 calls/day; its live-API ToS forbids redistributing *its index* and access is
  "freely revocable" — fine for on-demand lookups, not as a redistributable corpus source.
- **The PDF bytes are never the index's to license.** Capture the per-location `license` on the
  `SourceDoc` (or alongside it) so any later caching/redistribution decision (and the G3 fixture
  rule) can honor the *host/publisher* license. Downloading an OA copy for our own analysis is fine;
  **redistributing the bytes requires that paper's own license** (cc-by/cc0 ok; null/publisher
  likely not). This confirms the repo's existing "don't commit non-CC PDFs" stance (gate G3).
Fetched bytes are sniffed (`%PDF` magic + content type); an HTML paywall page raises `NotAPdfError` instead of poisoning the cache.

**sha256 + version_label (feeds validation).** Every ingest computes `sha256` over the **exact bytes** and captures a human-readable `version_label` — e.g. `"arXiv v2"`, `"publisher VoR (Unpaywall)"`, `"uploaded PDF"`. These two fields are exactly what `validation/protocol.md` §1 pins: each goldset entry stores the sha256 + version of the rated document, and `veribayes validate` hard-fails on mismatch. This component is the *only* place those values are minted — get them right here and version pinning is free everywhere else.

**Stage-0 cache behavior (C6).** Bytes land in a content-addressed blob store (`cache/blobs/<sha256>.pdf`); `SourceDoc.sha256` is the handle (the schema deliberately carries no bytes). `cache.py` owns the key formula `sha256(bytes) × engine_version × rubric_version × mode`:
- **Upload path:** hash immediately → full-result cache lookup *before any other work*; hit → stored `ScoredResult` returned instantly, byte-identical (reproducible by construction).
- **ID path:** an `(canonical_id, version_label) → sha256` alias table skips the PDF download on repeat lookups. Exact-versioned aliases (e.g. `arXiv:2107.09023` + `v2`) never expire; unversioned IDs re-resolve metadata (cheap) to learn the current version before trusting the alias — a new arXiv version must never silently replay a stale result.
- Stage-level sub-caches (parse, detect) are keyed under the same sha256 so engine upgrades re-judge without re-fetching or re-parsing (storage owned here; written by components b/c).

**The web-free seam.** `ingest.py`/`fetcher.py`/`cache.py` import only stdlib + `httpx` + `pydantic` — **no FastAPI, no SSE, no job-queue types**. The HTTP client is injected (constructor argument), which is both what keeps Phase 3's batch importer happy and what makes recorded-transport testing trivial. CI asserts the import boundary (a test imports `core.ingest` with `fastapi` absent from the environment).

## Interface contract
**Input:** `bytes` (primary upload) + optional `list[bytes]` (supplement uploads) **or** `str`
(ID/URL as typed by the user, pre-normalization). ID paths yield a single primary `SourceDoc` in v0.
**Output:** primary `SourceDoc` + `list[SourceDoc]` supplements (often empty), each
`SourceDoc {sha256, ids{doi?, arxiv_id?, openalex_id?}, version_label, source, fetched_at}` —
- `sha256`: hex digest of the exact stored bytes; key into the blob store and all caches.
- `ids`: normalized (lowercase de-versioned DOI; de-versioned arXiv ID; bare `W...`); all IDs discovered en route, not just the one supplied.
- `version_label`: human-readable provenance of *this byte stream* (`"arXiv v2"`, `"publisher VoR (Unpaywall)"`, `"uploaded PDF"`); never empty.
- `source`: how we got it — `upload | arxiv | openalex | unpaywall | crossref | url` plus the resolved URL when fetched.
- `fetched_at`: UTC ISO-8601.

**Errors (typed, in `core/errors.py`; each carries a `user_message` the API/UI renders as-is):** `UnrecognizedInputError` (input matches no accepted form) · `IdNotFoundError` (resolver 404 — the ID does not exist) · `NoOpenAccessError` (paper exists, no OA copy; message names the paper and suggests uploading the PDF) · `FetchFailedError` (network/5xx after bounded retries) · `NotAPdfError` (fetched payload is not a PDF). Errors never write to the blob store or alias table.

## Test plan
All CI tests run with the network **blocked** (socket guard); HTTP is replayed from recorded cassettes via the injected transport.
- **Unit — normalization:** table-driven over DOI spellings (case, prefixes, `.v2` suffix), arXiv old/new style ± version ± URL forms, OpenAlex ID/URL, URL dispatch, garbage → `UnrecognizedInputError`.
- **Fixture — one recorded cassette per ID type and per fallback edge:** arXiv hit; DOI → OpenAlex OA hit; DOI → Unpaywall fallback; DOI with metadata but no OA → `NoOpenAccessError` (assert the user-facing message names the paper); unknown ID → `IdNotFoundError`; HTML-instead-of-PDF → `NotAPdfError`.
- **Hash stability:** committed test PDFs have their sha256 pinned as constants; re-ingest across runs/OSes yields identical digests and identical `SourceDoc` JSON (modulo `fetched_at`).
- **Cache:** second ingest of the same upload performs **zero** transport calls and returns a byte-identical blob; versioned ID alias hit skips the PDF download; a cassette where the arXiv version advanced shows the unversioned alias re-resolving rather than replaying stale bytes.
- **Seam:** import-boundary test (no `fastapi` in `core.*` import graph).
- **Fixtures recorded for downstream:** 5–6 small OA papers (one per paper class, a supplement-heavy one, and one **main + separate-supplement pair**) checked in as `tests/fixtures/sourcedocs/*.json` + blobs under `tests/fixtures/pdfs/` — the canonical fixture set `b-parse` builds against (b may construct `SourceDoc` literals, but they point at *these* committed artifacts), per the spine's stubs-first additivity rule (§3.5).
- **Ship gate:** all of the above green in network-blocked CI; a manual (non-CI) live smoke script exercises each resolver once before the M2 demo.

## Definition of done
- [ ] All five input forms produce a valid `SourceDoc` from recorded fixtures; field semantics as specified above.
- [ ] ID normalization tests pass, including lowercase de-versioned DOI and learned-ID enrichment.
- [ ] `version_label` + `sha256` captured on every path; goldset pinning fields confirmed against `validation/protocol.md` §1 expectations.
- [ ] Stage-0 cache: upload re-ingest is a zero-network byte-identical replay; ID alias semantics (versioned permanent, unversioned re-resolved) covered by tests.
- [ ] All five typed errors raised with user-facing messages; no error path pollutes blob store or aliases.
- [ ] Import-boundary test proves `core/ingest.py`/`fetcher.py`/`cache.py` are web-free; Phase 3 M3 can `import` them unchanged.
- [ ] Multi-file upload emits primary + supplement `SourceDoc`s; supplements hashed/stored
      identically to primaries.
- [ ] `SourceDoc` + blob fixtures published for component b (incl. the main+supplement pair).

## Out of scope (deferred)
- **LaTeX-source ingest for arXiv papers** — source-tarball fetch alongside the PDF (improvements **H5**, v1).
- **Repo/artifact fetching** — GitHub/OSF/Zenodo linked-artifact retrieval (improvements **C4**, v2).
- **Batch acquisition** — rate-limit/polite-pool handling, bulk sampling, corpus-scale orchestration (Phase 3, `03-ingestion-corpus-plan.md` M3 — which imports this module rather than extending it here).
