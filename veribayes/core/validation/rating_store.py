"""Durable storage for blind ratings (M7 slice 2).

A real blind rating takes a domain expert 30–60 minutes; it cannot live only in the in-memory job
store (a restart would lose it). Each submission is one JSON file at
``<root>/<source_sha256>__<rubric_profile>/<rater_id>.json``. The bucket is keyed by the **durable**
paper identity (content sha) and the rubric — not the ephemeral in-memory job id — so a paper rated
in two sessions (or after a restart) still groups into one consensus, the same rater re-rating
overwrites (no double-count), and ratings under different rubrics stay cleanly separated (one gold
record per rubric). ``assemble-goldset`` collects each bucket's 2–3 ratings and derives the
consensus. ``root`` defaults under the data dir (``~/.veribayes/ratings``, like the blob store).
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
    rubric_profile: str = "synthesis"  # which rubric the rater rated against (registry id)
    rating: Rating


def _safe(name: str) -> str:
    """Sanitize an id for use as a path segment (app-controlled ids are simple, but be defensive
    against path traversal from a rater id)."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name) or "_"


def bucket_key(source_sha256: str, rubric_profile: str, paper_id: str = "") -> str:
    """The durable bucket for a paper's ratings under one rubric: ``<sha>__<profile>``. Falls back
    to the (ephemeral) paper_id only if no content sha was captured. sha is hex and profile a
    registry id, so the ``__`` join is unambiguous and filesystem-safe."""
    return f"{_safe(source_sha256 or paper_id)}__{_safe(rubric_profile)}"


class RatingStore:
    """One file per (paper+rubric, rater), keyed by durable identity. Survives restart; same rater
    re-rating overwrites (no double-count); the in-memory job dict does not survive."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def add(self, sub: SubmittedRating) -> Path:
        paper_dir = self.root / bucket_key(sub.source_sha256, sub.rubric_profile, sub.paper_id)
        paper_dir.mkdir(parents=True, exist_ok=True)
        path = paper_dir / f"{_safe(sub.rating.rater_id)}.json"
        path.write_text(sub.model_dump_json(indent=2))
        return path

    def count_for(
        self, source_sha256: str, rubric_profile: str = "synthesis", paper_id: str = ""
    ) -> int:
        paper_dir = self.root / bucket_key(source_sha256, rubric_profile, paper_id)
        return len(list(paper_dir.glob("*.json"))) if paper_dir.is_dir() else 0

    def by_paper(self) -> dict[str, list[SubmittedRating]]:
        """All ratings grouped by ``<sha>__<profile>`` bucket, for assembly. Each bucket is a single
        paper under a single rubric. Empty when nothing has been captured."""
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
