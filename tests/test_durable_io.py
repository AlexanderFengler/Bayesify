"""Durable-store I/O hardening: atomic writes + skip-and-report reads.

A crash or concurrent writer must not leave a half-written file that a reader then trusts (blobs) or
that aborts a whole eager directory load (ratings, overrides, gold set).
"""

from __future__ import annotations

from pathlib import Path

from bayesify.core.atomic import atomic_write_bytes, atomic_write_text
from bayesify.core.validation.override_store import Override, OverrideStore


def test_atomic_write_text_creates_parent_and_overwrites(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "x.json"  # parent does not exist yet
    atomic_write_text(p, '{"a": 1}')
    assert p.read_text(encoding="utf-8") == '{"a": 1}'
    atomic_write_text(p, '{"a": 2}')  # overwrite the existing file
    assert p.read_text(encoding="utf-8") == '{"a": 2}'


def test_atomic_write_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    atomic_write_bytes(tmp_path / "blob.bin", b"\x00\x01\x02")
    # Only the final file remains; the temp sibling was renamed away by os.replace.
    assert [p.name for p in tmp_path.iterdir()] == ["blob.bin"]


def test_override_all_skips_a_torn_line(tmp_path: Path) -> None:
    store = OverrideStore(tmp_path)
    store.add(Override(paper_id="p1", kind="step_status", step_id="S4", corrected_status="partial"))
    # Simulate a crash mid-append: a truncated trailing line after a complete record.
    with store.path.open("a", encoding="utf-8") as f:
        f.write('{"paper_id": "p2", "kind": "step_st')
    saved = store.all()
    assert [o.paper_id for o in saved] == ["p1"]  # good record survives; torn line skipped
