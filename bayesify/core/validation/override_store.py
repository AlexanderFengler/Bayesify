"""Durable storage for A5 overrides (per-step "Disagree?" corrections + relevance reruns).

These corrections are the seed for a future v1 learning loop, so — like blind ratings — they cannot
live only in the in-memory job store (a restart would lose them). The log is a single append-only
NDJSON file under the data dir (``~/.bayesify/overrides.ndjson``), one JSON object per correction.
It is a flat audit log (corrections are many-per-paper), not yet used to change any judgment.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_log = logging.getLogger("bayesify.override_store")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Override(_Base):
    """One recorded correction, with what it overrode and full provenance.

    ``kind='step_status'`` carries the disagreed step, the ``corrected_status`` the expert wants,
    and ``original_status`` — the engine verdict being corrected (so the log records *both* sides,
    not just the correction). ``kind='relevance_rerun'`` carries the forced relevance/force-grade in
    ``value`` and the short-circuit it overrode (e.g. ``"not_bayesian"``) in ``original_status``.

    ``rubric_profile`` + ``source_sha256`` pin which rubric and which paper the correction is about,
    so corrections never get conflated across rubrics and survive the loss of the in-memory job id
    (``paper_id`` is the ephemeral session id; ``source_sha256`` is the durable paper identity)."""

    paper_id: str
    kind: str  # "step_status" | "relevance_rerun"
    step_id: str | None = None
    corrected_status: str | None = None
    original_status: str | None = None  # what was overridden (engine status / short-circuit reason)
    rubric_profile: str = "synthesis"  # which rubric the correction is against (registry id)
    source_sha256: str = ""  # durable paper identity (paper_id is the ephemeral job/session id)
    version_label: str = ""  # which doc version was being corrected
    rationale: str = ""
    author: str = ""
    trusted: bool = False  # true only with a valid BAYESIFY_TRUSTED_TOKENS token
    # Rich encoding (kind="step_status"): each override is a self-contained correction *example* the
    # override-review pass judges for relevance against a new paper's step.
    paper_title: str = ""  # the source paper — shown in the provenance link
    paper_class_labels: list[str] = Field(default_factory=list)
    engine_rationale: str = ""  # engine reasoning for the step at override time (did-well + fixes)
    evidence_quotes: list[str] = Field(default_factory=list)  # the engine's cited quotes
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
        out: list[Override] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            # A crash mid-append can leave a torn final line; skip it rather than abort the whole
            # log (every prior correction is intact and must still load).
            try:
                out.append(Override.model_validate_json(line))
            except ValueError as exc:
                _log.warning("skipping unparseable override line: %s", exc)
        return out
