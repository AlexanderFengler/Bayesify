"""Shared LLM context builders for the cheap-model stages (screen + classify).

Both stages show the model the same bounded view (d-screen-classify.md): abstract + body + captions
(references and supplements excluded — A3), plus a digest of the deterministic detector
``Evidence[]`` with stable indices the model must cite via ``evidence_refs``. Centralised here so
the two stages stay byte-identical in what they show and so the token budget lives in one place.
"""

from __future__ import annotations

from bayesify.core.schema import Evidence, ParsedDoc, SectionKind

_CONTEXT_KINDS = (SectionKind.abstract, SectionKind.body, SectionKind.caption)
DEFAULT_MAX_CHARS = 12_000


def excerpt_context(parsed: ParsedDoc, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Abstract first, then body in reading order, then captions — references and supplements
    excluded. Truncated to a char budget (a cheap token proxy for the cheap-model call)."""
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


def evidence_digest(evidence: list[Evidence]) -> str:
    """The detector hits as an indexed list the model cites via ``evidence_refs``."""
    if not evidence:
        return "(no deterministic detector hits)"
    lines = []
    for i, e in enumerate(evidence):
        value = f" {e.value}" if e.value else ""
        lines.append(f'[{i}] {e.detector_id} · {e.kind.value}{value}: "{e.span.quote}"')
    return "\n".join(lines)


def build_user(
    parsed: ParsedDoc, evidence: list[Evidence], *, max_chars: int = DEFAULT_MAX_CHARS
) -> str:
    """The shared user message: paper excerpts + the indexed detector-hit digest."""
    return (
        "PAPER EXCERPTS (reference list excluded):\n"
        f"{excerpt_context(parsed, max_chars=max_chars)}\n\n"
        "DETECTOR HITS (deterministic; cite these indices in evidence_refs):\n"
        f"{evidence_digest(evidence)}"
    )
