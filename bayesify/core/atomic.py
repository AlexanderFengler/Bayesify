"""Atomic file writes: write to a unique temp file in the same directory, then ``os.replace`` it
onto the target. ``os.replace`` is atomic on POSIX and Windows, so a reader never observes a
half-written file and a crash mid-write leaves the previous file intact instead of a truncated one.

The durable stores (ratings, blobs, the result cache) use this because their readers load a whole
directory eagerly — one partially-written file would otherwise abort the entire load.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically: a temp file in the same dir, then ``os.replace``.
    The parent directory is created if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)  # atomic: the target only ever appears fully written
    except BaseException:
        Path(tmp).unlink(missing_ok=True)  # never leave the partial temp behind
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Atomic text write — encodes ``text`` and delegates to :func:`atomic_write_bytes`."""
    atomic_write_bytes(path, text.encode(encoding))
