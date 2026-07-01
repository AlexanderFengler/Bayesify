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

from bayesify.core import config
from bayesify.core.context import build_user, validate_evidence_refs
from bayesify.core.prompts import SCREEN_SYSTEM
from bayesify.core.schema import (
    CostLedgerEntry,
    Evidence,
    EvidenceKind,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
)
from bayesify.llm import LLMClient, call_with_policy, ledger_entry

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
_FLOOR_MIN_FAMILIES = 2


def screen(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str | None = None,
) -> tuple[Relevance, CostLedgerEntry]:
    """Run the relevance gate. Returns the (floor-corrected) ``Relevance`` and its cost entry.

    Raises ``LLMError`` (fail closed) if the cheap-model call cannot complete — never a defaulted
    label.
    """
    model = model or config.screen_model()
    user = build_user(parsed, evidence)
    response = call_with_policy(
        client, model=model, system=SCREEN_SYSTEM, user=user, schema=Relevance, max_tokens=600
    )
    # `overridden` is a human-only provenance flag; the model never owns it. Force it off here so a
    # stray model value can't bypass the grounding discipline — only the API rerun path sets it.
    relevance = _apply_floor(response.parsed.model_copy(update={"overridden": False}), evidence)
    # A3: a cited index must resolve to a real detector hit (no dangling refs in the report).
    validate_evidence_refs(relevance.evidence_refs, evidence, where="relevance")
    return relevance, ledger_entry("screen", response)


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
