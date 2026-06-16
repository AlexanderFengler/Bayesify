"""Durable storage for A5 overrides (per-step "Disagree?" corrections + relevance reruns).

These corrections are the seed for a future v1 learning loop, so — like blind ratings — they cannot
live only in the in-memory job store (a restart would lose them). The log is a single append-only
NDJSON file under the data dir (``~/.veribayes/overrides.ndjson``), one JSON object per correction.
It is a flat audit log (corrections are many-per-paper), not yet used to change any judgment.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Override(_Base):
    """One recorded correction. ``kind='step_status'`` carries the disagreed step + corrected
    status; ``kind='relevance_rerun'`` carries the forced relevance ``value`` from the escape
    hatch."""

    paper_id: str
    kind: str  # "step_status" | "relevance_rerun"
    step_id: str | None = None
    corrected_status: str | None = None
    rationale: str = ""
    author: str = ""
    value: str | None = None


class OverrideStore:
    """Append-only durable override log (survives restart; the in-memory job dict does not)."""

    def __init__(self, root: Path) -> None:
        self.path = Path(root) / "overrides.ndjson"

    def add(self, override: Override) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(override.model_dump_json() + "\n")

    def all(self) -> list[Override]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        return [Override.model_validate_json(line) for line in lines if line.strip()]
