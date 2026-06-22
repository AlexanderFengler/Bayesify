"""Parse component (b). Runs only where the parser deps exist — `pixi run -e parse test-parse`.

In the light default env this whole module is skipped (importorskip below), so `pixi run check`
stays fast. No PDF files are committed: fixtures are synthesized in-memory with PyMuPDF; the rich
Docling assertions use a real local paper if present and skip otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")  # PyMuPDF — skips the module in the light default env

from bayesify.core import parse as P  # noqa: E402
from bayesify.core.cache import BlobStore  # noqa: E402
from bayesify.core.errors import UnparseableDocument  # noqa: E402
from bayesify.core.ingest import ingest_upload  # noqa: E402

_BODY = [
    "Bayesian Workflow Methods",
    "Abstract",
    "We fit a hierarchical drift-diffusion model with MCMC and report R-hat and ESS.",
    "1 Introduction",
    "Reaction times are modelled per trial with weakly-informative priors.",
    "2 Methods",
    "We ran 4 chains of 2000 iterations; all R-hat < 1.01.",
    "Figure 1: Posterior predictive checks overlaid on the observed RT distribution.",
    "References",
    "Gelman et al. 2020. Bayesian Workflow.",
]


def _make_pdf(lines: list[str] | None = None) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines or []:
        page.insert_text((72, y), line, fontsize=11)
        y += 20
    return doc.tobytes()


def _source(blob: BlobStore, data: bytes):
    return ingest_upload(blob, data, filename="paper.pdf")


# --- PyMuPDF fallback (deterministic, no ML) ------------------------------------------------------


def test_pymupdf_fallback_extracts_kinds(tmp_path: Path) -> None:
    raws = P._parse_pymupdf("sha", _make_pdf(_BODY))
    kinds = {r.kind for r in raws if r.text}
    assert "caption" in kinds  # "Figure 1: ..." line pulled out
    assert "references" in kinds
    assert "abstract" in kinds
    # the caption is standalone — body text after it must NOT have been absorbed into the caption
    caption = next(r for r in raws if r.kind == "caption")
    assert "References" not in caption.text


def test_pymupdf_blank_pdf_is_no_text_layer(tmp_path: Path) -> None:
    with pytest.raises(UnparseableDocument) as exc:
        P._parse_pymupdf("sha", _make_pdf([]))
    assert exc.value.reason == "no_text_layer"


# --- Docling primary (needs the model stack) ------------------------------------------------------


def test_parse_uses_docling_and_returns_valid_parseddoc(tmp_path: Path) -> None:
    pytest.importorskip("docling")
    blob = BlobStore(tmp_path)
    doc = P.parse(_source(blob, _make_pdf(_BODY)), blob)
    assert doc.parser == "docling"
    assert doc.sections and all(s.text for s in doc.sections)
    assert [s.id for s in doc.sections] == [f"s{i:02d}" for i in range(1, len(doc.sections) + 1)]


def test_supplements_are_merged_and_labelled(tmp_path: Path) -> None:
    pytest.importorskip("docling")
    blob = BlobStore(tmp_path)
    primary = _source(blob, _make_pdf(_BODY))
    supp = _source(blob, _make_pdf(["Supplementary Methods", "Extra detail on the sampler."]))
    doc = P.parse(primary, blob, supplements=(supp,))
    supp_sections = [s for s in doc.sections if s.kind.value == "supplement"]
    assert supp_sections, "supplement content should be present and labelled"
    assert all(ps.doc_sha256 == supp.sha256 for s in supp_sections for ps in s.page_spans)


# --- Real-paper structural check (local only; skipped without the fixture) ---

_REAL = Path("research/sources/pdfs/vehtari2017-psis-loo-waic.pdf")


@pytest.mark.skipif(
    not _REAL.exists(), reason="local OA fixture not present (run fetch_sources.sh)"
)
def test_docling_on_a_real_paper_extracts_tables_and_captions(tmp_path: Path) -> None:
    pytest.importorskip("docling")
    blob = BlobStore(tmp_path)
    data = _REAL.read_bytes()
    doc = P.parse(_source(blob, data), blob)
    kinds = {s.kind.value for s in doc.sections}
    assert "caption" in kinds  # figure/table captions are first-class
    assert any(
        s.title == "Table" for s in doc.sections
    )  # structured tables captured (C2 head-start)
    assert "references" in kinds
