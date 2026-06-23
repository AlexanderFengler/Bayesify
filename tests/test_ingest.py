"""Ingest classification, normalization, and upload (network-free core)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bayesify.core.cache import BlobStore
from bayesify.core.errors import NotAPdfError, UnrecognizedInputError
from bayesify.core.ingest import ingest_upload, parse_input, to_paper_ids


@pytest.mark.parametrize(
    "raw,kind,value,version",
    [
        ("2011.01808", "arxiv", "2011.01808", None),
        ("arXiv:2107.09023v2", "arxiv", "2107.09023", "v2"),
        ("https://arxiv.org/abs/1904.12765", "arxiv", "1904.12765", None),
        ("https://arxiv.org/pdf/1904.12765v3", "arxiv", "1904.12765", "v3"),
        ("math.ST/0605234", "arxiv", "math.st/0605234", None),
        ("10.1038/s41562-021-01177-7", "doi", "10.1038/s41562-021-01177-7", None),
        ("doi:10.1111/RSSA.12378", "doi", "10.1111/rssa.12378", None),  # lowercased
        ("https://doi.org/10.1214/20-BA1221", "doi", "10.1214/20-ba1221", None),
        ("W2099012345", "openalex", "W2099012345", None),
        ("https://openalex.org/w2099012345", "openalex", "W2099012345", None),  # uppercased
        ("https://example.com/paper.pdf", "url", "https://example.com/paper.pdf", None),
    ],
)
def test_parse_input_classifies_and_normalizes(raw, kind, value, version) -> None:
    p = parse_input(raw)
    assert (p.kind, p.value, p.version_hint) == (kind, value, version)


@pytest.mark.parametrize("raw", ["", "   ", "not an id", "hello world", "42"])
def test_parse_input_rejects_garbage(raw) -> None:
    with pytest.raises(UnrecognizedInputError):
        parse_input(raw)


def test_to_paper_ids_maps_each_kind() -> None:
    assert to_paper_ids(parse_input("2011.01808")).arxiv_id == "2011.01808"
    assert to_paper_ids(parse_input("10.1038/x")).doi == "10.1038/x"
    assert to_paper_ids(parse_input("W123")).openalex_id == "W123"
    # a bare URL carries no canonical id yet
    ids = to_paper_ids(parse_input("https://example.com/x.pdf"))
    assert ids.arxiv_id is None and ids.doi is None and ids.openalex_id is None


def test_ingest_upload_stores_pdf_and_builds_sourcedoc(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"%PDF-1.5\n... bytes ..."
    doc = ingest_upload(store, data, filename="paper.pdf")
    assert store.exists(doc.sha256)
    assert doc.source == "upload"
    assert "paper.pdf" in doc.version_label


def test_ingest_upload_rejects_non_pdf(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    with pytest.raises(NotAPdfError):
        ingest_upload(store, b"<html>paywall</html>")
