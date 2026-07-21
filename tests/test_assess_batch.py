"""Batched assess strategy: screen + classify + all-step judge + all-negative refuter."""

from __future__ import annotations

from datetime import datetime

from bayesify.core.assess import derive_gate_facts
from bayesify.core.assess_batch import BatchAssessJudgments, BatchRefuterVerdicts
from bayesify.core.engine import grade_parsed
from bayesify.core.rubric.applicability import step_applicability_for_labels
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    Relevance,
    RelevanceLabel,
    Section,
    SectionKind,
    SourceDoc,
)
from bayesify.llm import FakeLLMClient

_WHEN = datetime(2026, 1, 1)
_RUBRIC = load_rubric()


def _parsed() -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="uploaded PDF", source="upload",
                    fetched_at=_WHEN)
    return ParsedDoc(
        source=src,
        parser="test",
        parser_version="0",
        sections=[
            Section(
                id="s01",
                kind=SectionKind.body,
                title="Methods",
                text=(
                    "We fit a Bayesian hierarchical model with weakly informative priors. "
                    "NUTS was run in Stan. R-hat was below 1.01. Posterior predictive checks "
                    "were shown. Code and data are available."
                ),
            )
        ],
    )


def _ev(detector_id: str, kind: EvidenceKind, quote: str) -> Evidence:
    return Evidence(
        detector_id=detector_id,
        detector_version="test",
        kind=kind,
        span=EvidenceSpan(section_id="s01", page=1, quote=quote),
    )


def test_batch_strategy_grades_with_four_llm_calls(monkeypatch) -> None:
    monkeypatch.setenv("BAYESIFY_GRADING_STRATEGY", "batch")
    monkeypatch.setenv("BAYESIFY_SCREEN_MODEL", "gpt-5.4-nano")
    monkeypatch.setenv("BAYESIFY_CLASSIFY_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("BAYESIFY_JUDGE_MODEL", "gpt-5.4")
    monkeypatch.setenv("BAYESIFY_REFUTER_MODEL", "gpt-5.5")
    parsed = _parsed()
    evidence = [
        _ev("method.prior", EvidenceKind.method_mention, "weakly informative priors"),
        _ev("method.mcmc", EvidenceKind.method_mention, "NUTS was run in Stan"),
        _ev("diag.rhat", EvidenceKind.diagnostic_value, "R-hat was below 1.01"),
        _ev("workflow.posterior_predictive", EvidenceKind.workflow_signal,
            "Posterior predictive checks"),
        _ev("open.code", EvidenceKind.open_science, "Code and data are available"),
    ]
    relevance = Relevance(
        label=RelevanceLabel.yes,
        confidence=0.9,
        rationale="Bayesian model fitted with NUTS.",
        evidence_refs=[0, 1],
    )
    paper_class = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.9,
        rationale="The paper fits a model to real data.",
        evidence_refs=[0],
    )
    # The wire format the classify stage now receives: checklist facts that the deterministic
    # mapper turns into the same [data_analysis] PaperClass (Stan implies mcmc via the ontology).
    from bayesify.core.schema import (
        ClassifierFacts,
        ClassifierMethodFacts,
        ClassifierPaperTypeFacts,
    )

    no = {"answer": "no", "confidence": "low", "evidence": ""}
    pt = {name: dict(no) for name in ClassifierPaperTypeFacts.model_fields}
    pt["uses_bayesian_model_on_real_data"] = {
        "answer": "yes",
        "confidence": "high",
        "evidence": "we fit the model to real data",
    }
    classifier_facts = ClassifierFacts(
        paper_type=pt,
        methods={name: dict(no) for name in ClassifierMethodFacts.model_fields},
        software=[{"name": "Stan", "confidence": "high", "evidence": "NUTS was run in Stan"}],
        disciplines=[],
    )
    gate_facts = derive_gate_facts(evidence, paper_class)
    applicable_ids = [
        step.id
        for step in _RUBRIC.steps
        if step_applicability_for_labels(step, paper_class.labels, gate_facts).applicable
    ]
    first_applicable = applicable_ids[0]
    judgments = BatchAssessJudgments.model_validate(
        {
            "judgments": [
                {
                    "step_id": step_id,
                    "status": "missing" if step_id == first_applicable else "adequate",
                    "confidence": 0.8,
                    "rationale": "batch judgment",
                    "did_well": ["Evidence was reviewed."],
                }
                for step_id in applicable_ids
            ]
        }
    )
    refutations = BatchRefuterVerdicts.model_validate(
        {"verdicts": [{"step_id": first_applicable, "refuted": False, "notes": "Still absent."}]}
    )
    client = FakeLLMClient(relevance, classifier_facts, judgments, refutations)

    result = grade_parsed(
        parsed,
        evidence,
        client=client,
        rubric=_RUBRIC,
        engine_version="test-engine",
        rubric_version=_RUBRIC.rubric_version,
    )

    assert result.coverage is not None
    assert result.step_assessments
    assert [c["schema"] for c in client.calls] == [
        "Relevance",
        "ClassifierFacts",
        "BatchAssessJudgments",
        "BatchRefuterVerdicts",
    ]
    assert [e.pass_label for e in result.cost_ledger.entries if e.stage == "assess"] == [
        "batch_judge",
        "batch_refute",
    ]
    assert client.calls[0]["model"] == "gpt-5.4-nano"
    assert client.calls[1]["model"] == "gpt-5.4-mini"
    assert client.calls[2]["model"] == "gpt-5.4"
    assert client.calls[3]["model"] == "gpt-5.5"
