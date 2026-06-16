"""Durable storage for blind ratings (M7 slice 2).

A real blind rating takes a domain expert 30–60 minutes; it cannot live only in the in-memory job
store (a restart would lose it). Each submission is one JSON file at
``<root>/<paper_id>/<rater_id>.json`` — append-only, grouped by paper so ``assemble-goldset`` can
collect a paper's 2–3 ratings and derive the consensus. ``root`` defaults under the data dir
(``~/.veribayes/ratings``, like the blob store), never the repo.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from veribayes.core.validation.human_report import Rating


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubmittedRating(_Base):
    """One rater's submission as persisted: the Rating plus the paper provenance captured at submit
    time, so assembly can group by paper and pin the gold record's sha256 (protocol §1)."""

    paper_id: str
    source_sha256: str = ""
    version_label: str = ""
    rubric_version: str = ""
    rating: Rating


def _safe(name: str) -> str:
    """Sanitize an id for use as a path segment (app-controlled ids are simple, but be defensive
    against path traversal from a rater id)."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name) or "_"


class RatingStore:
    """Append-only, one file per (paper, rater). Survives restart; the job dict does not."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def add(self, sub: SubmittedRating) -> Path:
        paper_dir = self.root / _safe(sub.paper_id)
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / f"{_safe(sub.rating.rater_id)}.json"
        path.write_text(sub.model_dump_json(indent=2))
        return path

    def count_for(self, paper_id: str) -> int:
        paper_dir = self.root / _safe(paper_id)
        return len(list(paper_dir.glob("*.json"))) if paper_dir.is_dir() else 0

    def by_paper(self) -> dict[str, list[SubmittedRating]]:
        """All ratings grouped by paper_id, for assembly. Empty when nothing has been captured."""
        out: dict[str, list[SubmittedRating]] = {}
        if not self.root.is_dir():
            return out
        for paper_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            subs = [
                SubmittedRating.model_validate_json(f.read_text())
                for f in sorted(paper_dir.glob("*.json"))
            ]
            if subs:
                out[paper_dir.name] = subs
        return out
