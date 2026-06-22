"""Automated consensus (M7) — derive a single consensus ``Rating`` from 2–3 blind ``Rating``s.

This replaces the human adjudication UI (2026-06-16 owner decision): consensus is mechanical, so it
**cannot be engine-anchored** — which removes the "form consensus before seeing engine output" leak
risk and the "prompt author must not adjudicate their own disagreements" rule entirely. The original
ratings are retained (the harness still computes inter-rater agreement from them).

The rule: a per-step status (and its applicability, and the paper-level relevance/class) is the
consensus iff a **strict majority** of raters chose it. Otherwise it is **"no consensus"** — a step
cell is dropped from the consensus (so the harness skips it in the engine-vs-consensus comparison)
and tallied; a paper with no relevance/class majority yields ``consensus=None`` (the paper is then
excluded-and-counted by the harness's admissibility check). Pure: no IO, deterministic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from bayesify.core.schema import EvidenceSpan, GateFacts, PaperIds, RelevanceLabel, StepStatus
from bayesify.core.validation.human_report import (
    GoldOrigin,
    GoldProvenance,
    GoldTier,
    HumanReport,
    RaterRelationship,
    Rating,
    StepRating,
)


@dataclass(frozen=True)
class ConsensusResult:
    consensus: Rating | None  # None when there is no paper-level (relevance/class) majority
    no_consensus_steps: list[str] = field(default_factory=list)  # steps dropped (no majority)
    note: str = ""


def _strict_majority[T](values: Sequence[T]) -> T | None:
    """The value chosen by *more than half* the voters, or None (no strict majority / tie)."""
    if not values:
        return None
    val, cnt = Counter(values).most_common(1)[0]
    return val if cnt * 2 > len(values) else None


def _consensus_gate(ratings: Sequence[Rating]) -> GateFacts:
    """Per-field strict-majority of the raters' gate answers (a v0 diagnostic, not a headline);
    falls back to the first rater's value when a field has no majority — deterministic."""
    facts = [r.gate_facts for r in ratings if r.gate_facts is not None]
    base = facts[0]

    def maj(get, fallback):
        m = _strict_majority([get(f) for f in facts])
        return m if m is not None else fallback

    return GateFacts(
        inference_method=maj(lambda f: f.inference_method, base.inference_method),
        n_models=maj(lambda f: f.n_models, base.n_models),
        bf_claimed=maj(lambda f: f.bf_claimed, base.bf_claimed),
        prior_informativeness=maj(lambda f: f.prior_informativeness, base.prior_informativeness),
    )


def _consensus_steps(ratings: Sequence[Rating]) -> tuple[list[StepRating], list[str]]:
    """Majority-vote each step. Returns (consensus steps, step_ids with no majority)."""
    by_step: dict[str, list[StepRating]] = {}
    for r in ratings:
        for sr in r.steps:
            by_step.setdefault(sr.step_id, []).append(sr)

    steps: list[StepRating] = []
    no_consensus: list[str] = []
    for sid in sorted(by_step, key=_step_key):
        votes = by_step[sid]
        applicable = _strict_majority([v.applicable for v in votes])
        if applicable is None:  # raters split on applicability → stage-1 no-consensus
            no_consensus.append(sid)
            continue
        if not applicable:
            na = [v for v in votes if not v.applicable]
            steps.append(
                StepRating(
                    step_id=sid,
                    applicable=False,
                    status=StepStatus.not_applicable,
                    confidence=_mean([v.confidence for v in na]),
                )
            )
            continue
        applicable_votes = [v for v in votes if v.applicable]
        status = _strict_majority([v.status for v in applicable_votes])
        if status is None:  # applicable, but no status majority → stage-2 no-consensus
            no_consensus.append(sid)
            continue
        agreeing = [v for v in applicable_votes if v.status is status]
        steps.append(
            StepRating(
                step_id=sid,
                applicable=True,
                status=status,
                confidence=_mean([v.confidence for v in agreeing]),
                evidence=_union_spans(agreeing),
                rationale=f"Consensus of {len(agreeing)} rater(s).",
            )
        )
    return steps, no_consensus


def _step_key(step_id: str) -> tuple[int, object]:
    """Natural sort so S2 precedes S10 (not lexicographic)."""
    body = step_id[1:]
    return (0, int(body)) if step_id[:1] == "S" and body.isdigit() else (1, step_id)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _union_spans(ratings: Sequence[StepRating]) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    for sr in ratings:
        for sp in sr.evidence:
            if sp not in spans:
                spans.append(sp)
    return spans


def consensus_from_ratings(ratings: Sequence[Rating]) -> ConsensusResult:
    """Build the consensus ``Rating`` from the blind ratings, or ``None`` if there is no paper-level
    majority (relevance, or — when relevant — paper class)."""
    if not ratings:
        return ConsensusResult(consensus=None, note="no ratings")

    relevance = _strict_majority([r.relevance_label for r in ratings])
    if relevance is None:
        return ConsensusResult(consensus=None, note="no relevance consensus")

    if relevance is RelevanceLabel.no:
        cons = Rating(
            rater_id="consensus",
            relationship=RaterRelationship.consensus,
            relevance_label=RelevanceLabel.no,
            relevance_rationale="Majority consensus: not a Bayesian-workflow paper.",
        )
        return ConsensusResult(consensus=cons, note="relevance=no (majority)")

    paper_class = _strict_majority(
        [r.paper_class_label for r in ratings if r.paper_class_label is not None]
    )
    if paper_class is None:
        return ConsensusResult(consensus=None, note="no paper-class consensus")

    steps, no_consensus = _consensus_steps(ratings)
    note = f"Majority consensus over {len(ratings)} raters."
    if no_consensus:
        note += f" No-consensus steps (excluded, counted): {', '.join(no_consensus)}."
    cons = Rating(
        rater_id="consensus",
        relationship=RaterRelationship.consensus,
        relevance_label=relevance,
        relevance_rationale=note,
        paper_class_label=paper_class,
        paper_class_rationale="Majority consensus.",
        gate_facts=_consensus_gate(ratings),
        steps=steps,
    )
    return ConsensusResult(consensus=cons, no_consensus_steps=no_consensus, note=note)


def assemble_human_report(
    *,
    work_id: str,
    source_sha256: str,
    version_label: str,
    rubric_version: str,
    tier: GoldTier,
    ratings: Sequence[Rating],
    origin: GoldOrigin,
    rubric_profile: str = "synthesis",
    ids: PaperIds | None = None,
) -> HumanReport | None:
    """Group one paper's blind ratings into a gold record with an auto-derived consensus. A gold
    record is single-rubric: ``rubric_profile`` is the rubric all these ratings used. Returns None
    when there is no paper-level consensus (the caller logs it as excluded-and-counted)."""
    result = consensus_from_ratings(ratings)
    if result.consensus is None:
        return None
    return HumanReport(
        work_id=work_id,
        ids=ids or PaperIds(),
        source_sha256=source_sha256,
        version_label=version_label,
        rubric_version=rubric_version,
        rubric_profile=rubric_profile,
        tier=tier,
        provenance=GoldProvenance(origin=origin),
        ratings=list(ratings),
        consensus=result.consensus,
        discussion_note=result.note,
    )
