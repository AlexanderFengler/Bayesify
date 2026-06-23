"""Record canonical ScoredResult fixtures (run: pixi run python tests/fixtures/build_scored_results.py).

The inputs component g (report UX) builds against, produced by the real f-score over a hand-authored
StepAssessment[] — a realistic empirical paper with a mix of statuses, suggestions, and cited praise.
"""

from __future__ import annotations

from pathlib import Path

from bayesify.core.rubric.applicability import step_applicability
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import (
    CostLedger,
    CostLedgerEntry,
    Ease,
    GateFacts,
    InferenceMethod,
    PaperClass,
    PaperClassLabel,
    PriorInformativeness,
    Relevance,
    RelevanceLabel,
    Severity,
    StepAssessment,
    StepStatus,
    Suggestion,
)
from bayesify.core.score import ScoreMeta, score

_RUBRIC = load_rubric()
_HERE = Path(__file__).parent

_STATUSES = {
    "S1": StepStatus.adequate, "S2": StepStatus.adequate, "S3": StepStatus.partial,
    "S4": StepStatus.adequate, "S5": StepStatus.missing, "S7": StepStatus.missing,
    "S8": StepStatus.adequate, "S9": StepStatus.partial, "S10": StepStatus.adequate,
}
_DID_WELL = {
    "S1": ["States a hierarchical drift-diffusion generative model (§s02)."],
    "S4": ['Reports "all R-hat < 1.01" and ESS for every parameter (§s02).'],
}
_SUGGESTIONS = {  # severity matches tier×status (as e-assess would derive)
    "S3": Suggestion(severity=Severity.info, text="Add a prior predictive check.",
                     how_to="Simulate from the prior and overlay on plausible ranges.", ease=Ease.medium),
    "S5": Suggestion(severity=Severity.error, text="Add posterior predictive checks.",
                     how_to="Overlay replicated datasets on the observed RT distribution.", ease=Ease.medium),
    "S7": Suggestion(severity=Severity.warning, text="Add a parameter-recovery study.",
                     how_to="Fit simulated data with known parameters and check recovery.", ease=Ease.high),
    "S9": Suggestion(severity=Severity.warning, text="State the software version and seed.",
                     how_to="Report Stan/cmdstanr versions and the RNG seed.", ease=Ease.low),
}


def _assessments(gate_facts: GateFacts):
    out = []
    for step in _RUBRIC.steps:
        ap = step_applicability(step, PaperClassLabel.empirical, gate_facts)
        status = _STATUSES.get(step.id, StepStatus.adequate) if ap.applicable else StepStatus.not_applicable
        sug = [_SUGGESTIONS[step.id]] if ap.applicable and step.id in _SUGGESTIONS else []
        out.append(
            StepAssessment(
                step_id=step.id,
                applicable=ap.applicable,
                applicability_reason=ap.reason,
                status=status,
                confidence=0.9,
                did_well=_DID_WELL.get(step.id, []),
                suggestions=sug,
            )
        )
    return out


def main() -> None:
    gate_facts = GateFacts(
        inference_method=InferenceMethod.hmc_nuts,
        n_models=1,
        bf_claimed=False,
        prior_informativeness=PriorInformativeness.weakly_informative,
    )
    paper_class = PaperClass(
        primary=PaperClassLabel.empirical, confidence=0.9, rationale="real RT data", evidence_refs=[0]
    )
    relevance = Relevance(label=RelevanceLabel.yes, confidence=0.95, rationale="Bayesian", evidence_refs=[0])
    ledger = CostLedger(
        entries=[
            CostLedgerEntry(stage="screen", model="claude-opus-4-8", input_tokens=4000,
                            output_tokens=200, cost_usd=0.025),
            CostLedgerEntry(stage="assess", model="claude-opus-4-8", input_tokens=40000,
                            output_tokens=5000, cost_usd=0.325),
        ],
        total_tokens=49200,
        total_cost_usd=0.35,
    )
    meta = ScoreMeta(engine_version="pkg=0.1.0;fixture", cost_ledger=ledger)
    result = score(relevance, paper_class, _assessments(gate_facts), gate_facts, _RUBRIC, meta)

    out = _HERE / "scored_result"
    out.mkdir(parents=True, exist_ok=True)
    (out / "empirical_mixed.json").write_text(result.model_dump_json(indent=2) + "\n")
    print(f"wrote empirical_mixed.json: coverage {result.coverage.present}/{result.coverage.applicable}")


if __name__ == "__main__":
    main()
