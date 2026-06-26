"""Parse — turn fetched document bytes into a structure-aware ``ParsedDoc`` (component b).

**Docling primary, PyMuPDF fast fallback** (decided 2026-06-13; see ``plans/02-mvp/b-parse.md``).
Docling gives layout, reading order, section structure, **table structure**, captions, and formulas;
the PyMuPDF path is a degraded fallback when Docling is unavailable. Both produce the same
parser-agnostic ``ParsedDoc`` contract; the engine records which parser ran in ``parser`` /
``parser_version`` (feeds the gate-G2 parse sub-cache key).

Heavy deps (docling/torch, pymupdf) are **imported lazily** so this module imports cleanly in the
light default env; only calling a parser needs its dependency. Structure matters because absence
claims depend on where the engine looked (A3) — captions and supplements are first-class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.metadata import version

from bayesify.core import schema as s
from bayesify.core.cache import BlobStore
from bayesify.core.errors import UnparseableDocument

_CAPTION_RE = re.compile(
    r"^\s*(figure|fig\.?|table|supplementary figure)\s*\.?\s*\w+", re.IGNORECASE
)
_REFERENCES_RE = re.compile(r"^\s*(references|bibliography|literature cited)\s*$", re.IGNORECASE)
_ABSTRACT_RE = re.compile(r"^\s*abstract\s*$", re.IGNORECASE)
_APPENDIX_RE = re.compile(r"^\s*(appendix|supplementary|supporting information)\b", re.IGNORECASE)
_MIN_CHARS_PER_PAGE = 200  # below this median → treat as scanned / no text layer


def _header_kind(title: str, in_references: bool) -> tuple[str, bool]:
    """Classify a heading into a section kind and the new in-references state.

    Appendices break out of references (they may carry diagnostics — these must reach the detectors,
    not be excluded as 'references'). Once in references, plain headers stay references until an
    appendix."""
    if _REFERENCES_RE.match(title):
        return "references", True
    if _APPENDIX_RE.match(title):
        return "supplement", False
    if _ABSTRACT_RE.match(title):
        return "abstract", False
    return ("references", True) if in_references else ("body", False)


@dataclass
class _RawSection:
    kind: str  # body | abstract | caption | supplement | references
    title: str
    parts: list[str] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)
    doc_sha256: str = ""

    @property
    def text(self) -> str:
        return "\n".join(p for p in self.parts if p).strip()


# --- public entry ---------------------------------------------------------------------------------


def parse(
    source: s.SourceDoc,
    blob_store: BlobStore,
    *,
    supplements: tuple[s.SourceDoc, ...] = (),
) -> s.ParsedDoc:
    """Parse the primary document (+ optional supplements merged into one ``ParsedDoc``)."""
    data = blob_store.get(source.sha256)
    raws, parser, parser_version, title = _parse_doc(source.sha256, data)
    authors, year = _pdf_meta(data)  # embedded PDF metadata (best-effort; providers are cleaner)
    for supp in supplements:
        s_raws, _, _, _ = _parse_doc(
            supp.sha256, blob_store.get(supp.sha256), force_supplement=True
        )
        raws.extend(s_raws)

    sections = [
        s.Section(
            id=f"s{i:02d}",
            kind=s.SectionKind(r.kind),
            title=r.title,
            text=r.text,
            page_spans=(
                [
                    s.PageSpan(
                        doc_sha256=r.doc_sha256, page_start=min(r.pages), page_end=max(r.pages)
                    )
                ]
                if r.pages
                else []
            ),
        )
        for i, r in enumerate((r for r in raws if r.text), start=1)
    ]
    return s.ParsedDoc(
        source=source,
        sections=sections,
        parser=parser,
        parser_version=parser_version,
        title=title,
        authors=authors,
        year=year,
    )


def _parse_doc(
    sha256: str, data: bytes, *, force_supplement: bool = False
) -> tuple[list[_RawSection], str, str, str | None]:
    """Parse one document's bytes into raw sections (+ the page-1 title). Tries Docling, falls back
    to PyMuPDF."""
    try:
        raws, title = _parse_docling(sha256, data)
        parser, pv = "docling", f"docling-{_safe_version('docling')}"
    except _DoclingUnavailable:
        raws, title = _parse_pymupdf(sha256, data)
        parser, pv = "pymupdf", f"pymupdf-{_safe_version('pymupdf')}"
    if force_supplement:
        for r in raws:
            if r.kind != "caption":  # captions inside a supplement stay captions
                r.kind = "supplement"
    return raws, parser, pv, title


# --- Docling primary ------------------------------------------------------------------------------


class _DoclingUnavailable(Exception):
    """Docling is not installed or failed to load — fall back to PyMuPDF."""


_CONVERTER = None


def _docling_converter():
    """Lazily build and cache a Docling converter with **OCR off** (v0: cost/latency, and it avoids
    needing the OCR model bundle). Table-structure recognition stays on."""
    global _CONVERTER
    if _CONVERTER is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = False
        _CONVERTER = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
    return _CONVERTER


def _parse_docling(sha256: str, data: bytes) -> tuple[list[_RawSection], str | None]:
    try:
        import io

        from docling.datamodel.base_models import DocumentStream
    except ImportError as exc:  # docling not installed (light env) → fallback
        raise _DoclingUnavailable(str(exc)) from exc

    stream = DocumentStream(name="doc.pdf", stream=io.BytesIO(data))
    doc = _docling_converter().convert(stream).document

    current = _RawSection(kind="body", title="", doc_sha256=sha256)
    sections: list[_RawSection] = [current]
    in_references = False
    paper_title: str | None = None  # the first `title`-labelled item is the paper title

    for item, _level in doc.iterate_items():
        label = getattr(getattr(item, "label", None), "value", "")
        page = _page_of(item)

        if label in ("section_header", "title"):
            title = (getattr(item, "text", "") or "").strip()
            if label == "title" and paper_title is None and title:
                paper_title = re.sub(r"\s+", " ", title)
            kind, in_references = _header_kind(title, in_references)
            current = _RawSection(kind=kind, title=title, doc_sha256=sha256)
            _add_page(current, page)
            sections.append(current)
        elif label == "caption":  # standalone; does not change `current`
            cap = _RawSection(
                kind="caption",
                title=_short(getattr(item, "text", "")),
                parts=[getattr(item, "text", "")],
                doc_sha256=sha256,
            )
            _add_page(cap, page)
            sections.append(cap)
        elif label == "table":  # standalone, structured text; does not change `current`
            md = item.export_to_markdown(doc) if hasattr(item, "export_to_markdown") else ""
            tbl = _RawSection(
                kind=current.kind if in_references else "body",
                title="Table",
                parts=[md],
                doc_sha256=sha256,
            )
            _add_page(tbl, page)
            sections.append(tbl)
        elif label in ("text", "list_item", "formula"):
            current.parts.append(getattr(item, "text", ""))
            _add_page(current, page)
        # page_header / page_footer / footnote / picture → skipped

    return sections, paper_title


def _page_of(item: object) -> int | None:
    prov = getattr(item, "prov", None) or []
    return getattr(prov[0], "page_no", None) if prov else None


def _add_page(section: _RawSection, page: int | None) -> None:
    if page is not None:
        section.pages.add(page)


# --- PyMuPDF fallback -----------------------------------------------------------------------------


def _parse_pymupdf(sha256: str, data: bytes) -> tuple[list[_RawSection], str | None]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise UnparseableDocument(
            "corrupt_pdf",
            user_message="No PDF parser is available (neither Docling nor PyMuPDF).",
        ) from exc

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UnparseableDocument(
            "corrupt_pdf", user_message="This PDF could not be opened."
        ) from exc
    if doc.needs_pass:
        raise UnparseableDocument("encrypted", user_message="This PDF is encrypted.")

    page_texts = [page.get_text() for page in doc]
    total_chars = sum(len(t) for t in page_texts)
    if doc.page_count and total_chars / doc.page_count < _MIN_CHARS_PER_PAGE:
        raise UnparseableDocument(
            "no_text_layer",
            user_message="This looks like a scanned PDF; OCR is not supported in this version.",
        )

    title = _pdf_title(doc)

    # Degraded heuristic sectioning: split on heading-like lines, pull out captions + references.
    current = _RawSection(kind="body", title="", doc_sha256=sha256)
    sections: list[_RawSection] = [current]
    in_references = False
    for page_no, text in enumerate(page_texts, start=1):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _CAPTION_RE.match(stripped):  # standalone caption line; `current` unchanged
                cap = _RawSection(
                    kind="caption", title=_short(stripped), parts=[stripped], doc_sha256=sha256
                )
                cap.pages.add(page_no)
                sections.append(cap)
                continue
            if (
                _REFERENCES_RE.match(stripped)
                or _APPENDIX_RE.match(stripped)
                or _ABSTRACT_RE.match(stripped)
            ):
                kind, in_references = _header_kind(stripped, in_references)
                current = _RawSection(kind=kind, title=stripped, doc_sha256=sha256)
                current.pages.add(page_no)
                sections.append(current)
                continue
            current.parts.append(stripped)
            current.pages.add(page_no)
    return sections, title


# The paper title is, on essentially every academic PDF, the largest text near the top of page 1.
# We read per-span font sizes from page 1, take the lines at (or just under) the max size in the top
# half, and join them in reading order. Conservative: returns None if the result looks wrong, so the
# caller can fall back to the source label.
_NON_TITLE_RE = re.compile(
    r"^(abstract|introduction|arxiv:|doi:|https?://|figure|table|\d+$)", re.IGNORECASE
)


def _pdf_title_from_page1(doc) -> str | None:  # doc: fitz.Document
    if doc.page_count == 0:
        return None
    try:
        page = doc[0]
        info = page.get_text("dict")
        height = page.rect.height or 1
    except Exception:
        return None

    lines: list[tuple[float, float, str]] = []  # (font_size, y_top, text)
    for block in info.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = " ".join((sp.get("text") or "").strip() for sp in spans).strip()
            if not text:
                continue
            size = max((sp.get("size", 0.0) for sp in spans), default=0.0)
            y = line.get("bbox", (0, 0, 0, 0))[1]
            if y <= height * 0.5:  # title sits in the top half of the first page
                lines.append((round(size, 1), y, text))
    if not lines:
        return None

    max_size = max(size for size, _, _ in lines)
    # the title may span multiple lines at the same (largest) size; keep them in reading order
    parts = [text for size, _, text in sorted(lines, key=lambda t: t[1]) if size >= max_size - 0.5]
    title = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if 8 <= len(title) <= 250 and not _NON_TITLE_RE.match(title):
        return title
    return None


# Embedded /Title metadata is a useful fallback when the visual heuristic finds nothing, but PDF
# producers routinely dump junk there — the source filename, a Word/LaTeX artefact, or a generic
# placeholder — so we filter hard before trusting it.
_JUNK_TITLE_RE = re.compile(
    r"^(microsoft word\b|untitled\b|no title\b|main\b|paper\b|manuscript\b|article\b|template\b"
    r"|preprint\b|document\b|title\b|slide\b)",
    re.IGNORECASE,
)


def _pdf_title_from_metadata(doc) -> str | None:  # doc: fitz.Document
    """The embedded /Title, when it looks like a real paper title (not a filename/placeholder)."""
    try:
        raw = (doc.metadata or {}).get("title") or ""
    except Exception:
        return None
    title = re.sub(r"\s+", " ", raw).strip()
    if not (8 <= len(title) <= 250):
        return None
    if _NON_TITLE_RE.match(title) or _JUNK_TITLE_RE.match(title):
        return None
    # a filename masquerading as a title (no spaces, but underscores or a trailing extension)
    if " " not in title and re.search(r"_|\.\w{2,4}$", title):
        return None
    return title


def _pdf_title(doc) -> str | None:  # doc: fitz.Document
    """Best-effort paper title for an uploaded PDF, taken from the document itself: the visually
    largest text at the top of page 1 (what a reader reads as the title), falling back to the
    embedded /Title metadata. Conservative on both paths — returns None rather than a wrong/junk
    title, so the caller can fall back to the filename."""
    return _pdf_title_from_page1(doc) or _pdf_title_from_metadata(doc)


# --- embedded PDF metadata (authors + year) -------------------------------------------------------
# Best-effort, from the PDF's own /Author and /CreationDate. Often empty or stale (the creation date
# is the file's, which only approximates the publication year), so both may be absent — a fetched
# paper's provider metadata is preferred when available. We never invent: filtered, range-checked.
_AUTHOR_SPLIT_RE = re.compile(r"\s*(?:;|\band\b|&|\n|/)\s*", re.IGNORECASE)


def _split_authors(raw: str | None) -> list[str]:
    """Split the /Author metadata into names on unambiguous separators (``;`` / ``and`` / ``&`` /
    newline / ``/``). Commas are left intact — they ambiguously separate authors *or* a single
    ``Last, First`` — so the display joins on ``, `` and reads correctly either way."""
    if not raw:
        return []
    names = [re.sub(r"\s+", " ", p).strip() for p in _AUTHOR_SPLIT_RE.split(raw)]
    # Drop empties and obvious non-names (emails, or blobs too long to be a person's name).
    names = [n for n in names if n and "@" not in n and len(n) <= 80]
    return names[:25]


def _meta_year(raw: str | None) -> int | None:
    """The 4-digit year from a PDF date string (``D:20210315...``), range-checked. Best-effort."""
    if not raw:
        return None
    m = re.search(r"\d{4}", raw)
    if not m:
        return None
    year = int(m.group(0))
    return year if 1900 <= year <= 2100 else None


def _pdf_meta(data: bytes) -> tuple[list[str], int | None]:
    """Authors + year from the PDF's embedded metadata (PyMuPDF, always available). Returns
    ``([], None)`` on any error — metadata is a best-effort enrichment, never a hard failure."""
    try:
        import fitz  # PyMuPDF — a base dep

        with fitz.open(stream=data, filetype="pdf") as doc:
            meta = doc.metadata or {}
    except Exception:
        return [], None
    return _split_authors(meta.get("author")), _meta_year(meta.get("creationDate"))


# --- helpers --------------------------------------------------------------------------------------


def _short(text: str, n: int = 60) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:n]


def _safe_version(pkg: str) -> str:
    try:
        return version(pkg)
    except Exception:
        return "unknown"
