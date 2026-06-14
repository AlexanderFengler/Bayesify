"""Relevance gate — component d, stage 4 (the C6 cheap-before-expensive gate).

Decides whether a paper uses Bayesian methodology worth grading at all. Returns a ``Relevance``
(``yes`` / ``partial`` / ``no``) and the cost-ledger entry for the single cheap-model call. A ``no``
short-circuits the pipeline downstream (classify/assess skipped) rather than forcing a misleading
score.

Two deterministic guards wrap the LLM (d-screen-classify.md):
- **Context discipline (A3):** only abstract + body + captions are shown; the reference list is
  excluded (a frequentist paper citing "Bayes" is not evidence), and the detector ``Evidence[]`` is
  summarised with stable indices the model must cite via ``evidence_refs``.
- **Detector floor (anti-noise, anti-gaming-by-omission):** if ≥2 *independent* Bayesian evidence
  families were detected, the LLM is not allowed to say ``no`` — it is corrected to ``partial`` so a
  genuinely Bayesian paper is never discarded on LLM run-to-run noise.
"""

from __future__ import annotations

from veribayes.core import config
from veribayes.core.llm import LLMClient, call_with_policy, ledger_entry
from veribayes.core.prompts import SCREEN_SYSTEM
from veribayes.core.schema import (
    CostLedgerEntry,
    Evidence,
    EvidenceKind,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
    SectionKind,
)

# Evidence kinds that count as *Bayesian-substantive* for the floor. open_science is excluded — a
# GitHub link or data-availability statement is not evidence of Bayesian methodology. The two
# diagnostic kinds collapse to one family (they are not independent signals).
_FAMILY_OF_KIND: dict[EvidenceKind, str] = {
    EvidenceKind.software_mention: "software",
    EvidenceKind.method_mention: "method",
    EvidenceKind.diagnostic_value: "diagnostic",
    EvidenceKind.diagnostic_mention: "diagnostic",
    EvidenceKind.workflow_signal: "workflow",
    EvidenceKind.sampler_config: "sampler",
}
_CONTEXT_KINDS = (SectionKind.abstract, SectionKind.body, SectionKind.caption)
_CONTEXT_MAX_CHARS = 12_000
_FLOOR_MIN_FAMILIES = 2


def screen(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str = config.SCREEN_MODEL,
) -> tuple[Relevance, CostLedgerEntry]:
    """Run the relevance gate. Returns the (floor-corrected) ``Relevance`` and its cost entry.

    Raises ``LLMError`` (fail closed) if the cheap-model call cannot complete — never a defaulted
    label.
    """
    user = _build_user(parsed, evidence)
    response = call_with_policy(
        client, model=model, system=SCREEN_SYSTEM, user=user, schema=Relevance, max_tokens=600
    )
    return _apply_floor(response.parsed, evidence), ledger_entry("screen", response)


# --- context + evidence digest --------------------------------------------------------------------


def _build_user(parsed: ParsedDoc, evidence: list[Evidence]) -> str:
    return (
        "PAPER EXCERPTS (reference list excluded):\n"
        f"{_context(parsed)}\n\n"
        "DETECTOR HITS (deterministic; cite these indices in evidence_refs):\n"
        f"{_evidence_digest(evidence)}"
    )


def _context(parsed: ParsedDoc, *, max_chars: int = _CONTEXT_MAX_CHARS) -> str:
    """Abstract first, then body in reading order, then captions — references and supplements
    excluded. Truncated to a char budget (a cheap token proxy for the screen call)."""
    by_kind = {kind: [s for s in parsed.sections if s.kind is kind] for kind in _CONTEXT_KINDS}
    ordered = (
        by_kind[SectionKind.abstract] + by_kind[SectionKind.body] + by_kind[SectionKind.caption]
    )

    blocks: list[str] = []
    used = 0
    for section in ordered:
        if not section.text:
            continue
        block = f"## {section.title or section.kind.value}\n{section.text}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 0:
                blocks.append(block[:remaining])
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks) or "(no extractable text)"


def _evidence_digest(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(no deterministic detector hits)"
    lines = []
    for i, e in enumerate(evidence):
        value = f" {e.value}" if e.value else ""
        lines.append(f'[{i}] {e.detector_id} · {e.kind.value}{value}: "{e.span.quote}"')
    return "\n".join(lines)


# --- detector floor -------------------------------------------------------------------------------


def _bayes_families(evidence: list[Evidence]) -> set[str]:
    return {_FAMILY_OF_KIND[e.kind] for e in evidence if e.kind in _FAMILY_OF_KIND}


def _apply_floor(relevance: Relevance, evidence: list[Evidence]) -> Relevance:
    """If the LLM said ``no`` despite ≥2 independent Bayesian evidence families, correct to
    ``partial`` (and ensure it cites those families). Other labels pass through unchanged."""
    families = _bayes_families(evidence)
    if relevance.label is not RelevanceLabel.no or len(families) < _FLOOR_MIN_FAMILIES:
        return relevance
    refs = relevance.evidence_refs or [
        i for i, e in enumerate(evidence) if e.kind in _FAMILY_OF_KIND
    ][:3]
    note = (
        f" [Detector floor: raised to 'partial' — {len(families)} independent Bayesian evidence "
        f"families detected ({', '.join(sorted(families))}), so 'no' is not supported.]"
    )
    return relevance.model_copy(
        update={
            "label": RelevanceLabel.partial,
            "evidence_refs": refs,
            "rationale": relevance.rationale + note,
        }
    )
