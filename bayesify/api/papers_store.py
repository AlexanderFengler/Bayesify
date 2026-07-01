"""Durable archive of processed papers — the backing store for the Archive page.

Like ``RatingStore``/``OverrideStore``, this is an on-disk store under the data dir (local-first; no
MongoDB required). One JSON file per paper, keyed by the **durable** identity ``<sha>__<profile>``
(the same ``bucket_key`` the rating store uses), so a paper processed twice (rerun, or AI then a
human rating) updates one archive entry rather than duplicating.

Each entry carries the paper's metadata plus its tags, grouped as:
- ``paper_type`` / ``discipline`` / ``methods`` — auto, derived from the engine's PaperClass and the
  detector inventory.
- ``manual_tags`` — freeform, added by a human (in the rate flow) or edited from the Archive.

Auto tags are refreshed on every upsert; manual tags are preserved across upserts (only the tag-edit
endpoint replaces them). The Archive is populated by real analysis runs and human ratings — never by
the labelled stub (a fake result is not archived), matching the analysis-event persistence policy.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bayesify.core.atomic import atomic_write_text
from bayesify.core.detectors import EvidenceInventory
from bayesify.core.schema import PaperClass
from bayesify.core.validation.rating_store import _safe, bucket_key

_log = logging.getLogger("bayesify.papers_store")


# Detector-id → friendly method/software tag. Only the families a reader thinks of as "methods and
# software" are surfaced (software, method, workflow, and the headline diagnostics); sampler config
# and open-science signals are left out of the facet. Unknown ids fall back to a prettified suffix.
_METHOD_LABELS: dict[str, str] = {
    "software.stan": "Stan",
    "software.brms": "brms",
    "software.rstanarm": "rstanarm",
    "software.pymc": "PyMC",
    "software.numpyro": "NumPyro",
    "software.tfp": "TensorFlow Probability",
    "software.jags": "JAGS",
    "software.bugs": "BUGS",
    "software.hddm": "HDDM",
    "software.turing": "Turing.jl",
    "method.prior": "Priors",
    "method.posterior": "Posterior",
    "method.credible_interval": "Credible intervals",
    "method.bayes_factor": "Bayes factor",
    "method.mcmc": "MCMC",
    "method.variational": "Variational inference",
    "method.analytic": "Analytic posterior",
    "diag.rhat": "R-hat",
    "diag.ess": "ESS",
    "diag.divergences": "Divergences",
    "diag.loo_waic": "LOO/WAIC",
    "workflow.prior_predictive": "Prior predictive check",
    "workflow.posterior_predictive": "Posterior predictive check",
    "workflow.sensitivity": "Sensitivity analysis",
    "workflow.sbc": "SBC",
    "workflow.recovery": "Parameter recovery",
}
_METHOD_FAMILIES = {"software", "method", "workflow", "diagnostic"}


def _prettify(detector_id: str) -> str:
    """Fallback label for a detector id with no curated name: drop the family prefix, spacify."""
    return detector_id.split(".", 1)[-1].replace("_", " ")


def methods_from_inventory(inventory: EvidenceInventory | None) -> list[str]:
    """Friendly method/software tags from the detector inventory's found hits (order-preserving,
    de-duplicated). Empty when there is no inventory (e.g. the placeholder stub path)."""
    if inventory is None:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for fam in inventory.families:
        if fam.family not in _METHOD_FAMILIES:
            continue
        for hit in fam.found:
            label = _METHOD_LABELS.get(hit.detector_id) or _prettify(hit.detector_id)
            if label not in seen:
                seen.add(label)
                out.append(label)
    return out


def _clean_tags(tags: list[str]) -> list[str]:
    """Trim, drop blanks, de-duplicate (case-insensitively, first spelling wins). Preserves the
    user's casing and order — freeform manual tags."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


class ArchivedPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = ""  # bucket_key: the durable archive id (also the tag-edit path segment)
    paper_id: str = ""  # the most recent (ephemeral) job id, for a "reopen report" link
    source_sha256: str = ""
    rubric_profile: str = "synthesis"
    version_label: str = ""
    source_label: str = ""
    paper_title: str | None = None
    paper_authors: list[str] = Field(default_factory=list)
    paper_year: int | None = None
    mode: str = "full"  # "full" (AI) | "local"/"rate" (Human)
    backend: str | None = None
    relevance_label: str = ""
    quality_score: float | None = None
    coverage_present: int | None = None
    coverage_applicable: int | None = None
    # auto tags (refreshed on every upsert)
    paper_type: list[str] = Field(default_factory=list)
    discipline: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    # freeform manual tags (preserved across upserts; replaced only by the tag-edit endpoint)
    manual_tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def all_tags(self) -> list[str]:
        return [*self.paper_type, *self.discipline, *self.methods, *self.manual_tags]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PapersStore:
    """One JSON file per processed paper, keyed by ``<sha>__<profile>``. Survives restart; a rerun
    or a later human rating of the same paper updates the one entry."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / f"{_safe(key)}.json"

    def get(self, key: str) -> ArchivedPaper | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            return ArchivedPaper.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _log.warning("skipping unreadable archive file %s: %s", path, exc)
            return None

    def upsert(self, paper: ArchivedPaper) -> ArchivedPaper:
        """Insert or update. Auto tags + metadata are taken from ``paper``; manual tags and the
        original ``created_at`` are preserved from any existing entry (auto tags that ``paper``
        leaves empty also fall back to the existing ones, so a human rating without an inventory
        does not wipe the AI-derived methods)."""
        key = paper.key or bucket_key(paper.source_sha256, paper.rubric_profile, paper.paper_id)
        paper.key = key
        existing = self.get(key)
        now = _now()
        if existing is not None:
            paper.created_at = existing.created_at or now
            paper.manual_tags = _clean_tags([*existing.manual_tags, *paper.manual_tags])
            paper.paper_type = paper.paper_type or existing.paper_type
            paper.discipline = paper.discipline or existing.discipline
            paper.methods = paper.methods or existing.methods
        else:
            paper.created_at = now
            paper.manual_tags = _clean_tags(paper.manual_tags)
        paper.updated_at = now
        atomic_write_text(self._path(key), paper.model_dump_json(indent=2))
        return paper

    def set_tags(self, key: str, tags: list[str]) -> ArchivedPaper | None:
        """Replace an entry's manual tags (the Archive tag editor). Returns None if unknown."""
        paper = self.get(key)
        if paper is None:
            return None
        paper.manual_tags = _clean_tags(tags)
        paper.updated_at = _now()
        atomic_write_text(self._path(key), paper.model_dump_json(indent=2))
        return paper

    def list(self) -> list[ArchivedPaper]:
        """All archived papers, newest-updated first. Empty when nothing has been processed."""
        if not self.root.is_dir():
            return []
        out: list[ArchivedPaper] = []
        for f in self.root.glob("*.json"):
            try:
                out.append(ArchivedPaper.model_validate_json(f.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                _log.warning("skipping unreadable archive file %s: %s", f, exc)
        out.sort(key=lambda p: p.updated_at, reverse=True)
        return out


def paper_type_tags(paper_class: PaperClass | None) -> list[str]:
    """Auto paper-type tags from a PaperClass (raw enum values; the UI prettifies)."""
    return [label.value for label in paper_class.labels] if paper_class else []


def discipline_tags(paper_class: PaperClass | None) -> list[str]:
    """Auto discipline tags from a PaperClass (already normalised soft-vocabulary strings)."""
    return list(paper_class.disciplines) if paper_class else []
