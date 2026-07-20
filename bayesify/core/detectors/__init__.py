"""Deterministic detectors (component c): ``ParsedDoc -> Evidence[]``, pure and LLM-free.

``run_detectors`` is a pure function — no I/O, no config-dependent behavior — so identical input
yields byte-identical output and the stage-3 sub-cache is a pure replay. ``evidence_inventory``
turns those hits into the **F3 local-only report** (found / not-detected / where-looked), the thing
that makes a+b+c shippable with zero LLM calls and nothing leaving the machine.
"""

from __future__ import annotations

import json
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from bayesify.core.quotes import sentence_span
from bayesify.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    ParsedDoc,
    Section,
    SectionKind,
)

from .catalog import (
    CATALOG,
    CATALOG_VERSION,
    DETECTOR_FAMILY,
    FAMILIES,
    Detector,
    catalog_fingerprint,
    detector_ids,
)

__all__ = [
    "run_detectors",
    "evidence_inventory",
    "EvidenceInventory",
    "InventoryFamily",
    "InventoryHit",
    "ScannedSection",
    "CATALOG",
    "CATALOG_VERSION",
    "DETECTOR_FAMILY",
    "FAMILIES",
    "Detector",
    "catalog_fingerprint",
    "detector_ids",
]

# --- detection ------------------------------------------------------------------------------------


def run_detectors(parsed: ParsedDoc) -> list[Evidence]:
    """Run every catalog detector over the parsed document, returning canonical ``Evidence[]``.

    Detectors scan ``body|abstract|caption|supplement`` sections and **skip ``references``**
    (citation lists name Stan / R-hat without the paper using them, a precision trap). Output is
    ordered by section then character offset; duplicate matches of one detector with the same value
    in a section collapse to a single hit. Zero hits is a valid result (a real signal for d's gate).
    """
    collected: list[tuple[int, int, Evidence]] = []
    seen: set[tuple] = set()

    for idx, section in enumerate(parsed.sections):
        if section.kind is SectionKind.references:
            continue
        text = section.text or ""
        if not text:
            continue
        page = _section_page(section)
        for det in CATALOG:
            for m in det.pattern.finditer(text):
                value = det.extract(m) if det.extract else None
                kind = _emitted_kind(det, value)
                key = (det.id, section.id, m.group(0).lower(), _value_key(value))
                if key in seen:
                    continue
                seen.add(key)
                ev = Evidence(
                    detector_id=det.id,
                    detector_version=det.version,
                    kind=kind,
                    value=value,
                    span=EvidenceSpan(
                        section_id=section.id, page=page, quote=_quote(text, m.start(), m.end())
                    ),
                )
                collected.append((idx, m.start(), ev))

    collected.sort(key=lambda t: (t[0], t[1]))
    return [ev for _, _, ev in collected]


def _emitted_kind(det: Detector, value: dict | None) -> EvidenceKind:
    """A numeric detector that found no number degrades to its ``mention_kind``."""
    if det.extract is not None and value is None and det.mention_kind is not None:
        return det.mention_kind
    return det.kind


def _value_key(value: dict | None) -> tuple:
    return () if value is None else tuple(sorted((k, str(v)) for k, v in value.items()))


def _section_page(section: Section) -> int | None:
    return section.page_spans[0].page_start if section.page_spans else None


def _quote(text: str, start: int, end: int) -> str:
    """A readable, **verbatim substring** of ``text`` around the match (hard guarantee — e-assess
    grounding and UI highlighting slice on it). Sentence-aligned via ``sentence_span`` so the
    report's "In the paper" spans read as complete sentences, not the old ±30-char shards; the
    match always stays inside, so the result is contiguous within ``text``."""
    return sentence_span(text, start, end)


# --- inventory (the F3 local-only view) -----------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InventoryHit(_Base):
    detector_id: str
    family: str
    kind: EvidenceKind
    value: dict[str, object] | None = None
    section_id: str
    section_title: str
    page: int | None = None
    quote: str


class InventoryFamily(_Base):
    family: str
    found: list[InventoryHit] = Field(default_factory=list)
    not_detected: list[str] = Field(default_factory=list)  # catalog ids with zero hits


class ScannedSection(_Base):
    section_id: str
    kind: SectionKind
    title: str
    page: int | None = None


class EvidenceInventory(_Base):
    """The local-only report payload: **what was found**, **what was not** (stated as "not
    detected", never "not done"), and **where the engine looked** (the A3 enumeration rule)."""

    families: list[InventoryFamily] = Field(default_factory=list)
    where_looked: list[ScannedSection] = Field(default_factory=list)
    # references are listed here (not scanned) for honesty about coverage:
    skipped: list[ScannedSection] = Field(default_factory=list)
    n_hits: int = 0


def evidence_inventory(parsed: ParsedDoc, evidence: list[Evidence]) -> EvidenceInventory:
    """Group detector hits into the local-only report. Pure; pairs with ``run_detectors`` output."""
    titles = {s.id: s.title for s in parsed.sections}
    by_family: dict[str, list[InventoryHit]] = defaultdict(list)
    found_ids: set[str] = set()

    for e in evidence:
        family = DETECTOR_FAMILY.get(e.detector_id, "other")
        found_ids.add(e.detector_id)
        by_family[family].append(
            InventoryHit(
                detector_id=e.detector_id,
                family=family,
                kind=e.kind,
                value=e.value,
                section_id=e.span.section_id,
                section_title=titles.get(e.span.section_id, ""),
                page=e.span.page,
                quote=e.span.quote,
            )
        )

    families = [
        InventoryFamily(
            family=family,
            found=by_family.get(family, []),
            not_detected=[d for d in detector_ids(family) if d not in found_ids],
        )
        for family in FAMILIES
    ]
    where_looked = [
        ScannedSection(section_id=s.id, kind=s.kind, title=s.title, page=_section_page(s))
        for s in parsed.sections
        if s.kind is not SectionKind.references
    ]
    skipped = [
        ScannedSection(section_id=s.id, kind=s.kind, title=s.title, page=_section_page(s))
        for s in parsed.sections
        if s.kind is SectionKind.references
    ]
    return EvidenceInventory(
        families=families, where_looked=where_looked, skipped=skipped, n_hits=len(evidence)
    )


def evidence_json(evidence: list[Evidence]) -> str:
    """Canonical JSON for the determinism test and the stage-3 fixture dumps (sorted, stable)."""
    return json.dumps([e.model_dump(mode="json") for e in evidence], sort_keys=True, indent=2)
