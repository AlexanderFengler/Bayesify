"""The override-review pass — the LLM-judged global correction layer. A relevant bank entry nudges
the step one level and re-scores with provenance; an irrelevant verdict leaves it unchanged; an
empty bank makes no LLM call. Driven by a scripted fake client — no network."""

from __future__ import annotations

import pathlib

from bayesify.core.override_review import BankOverride, ReviewVerdict, review_overrides
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import ScoredResult, StepStatus
from bayesify.llm import FakeLLMClient
from bayesify.llm import config as llm_config

_FIX = pathlib.Path(__file__).parent / "fixtures" / "scored_result" / "empirical_mixed.json"
_RUBRIC = load_rubric()


def _result() -> ScoredResult:
    return ScoredResult.model_validate_json(_FIX.read_text(encoding="utf-8"))


def _bank_for(step_id: str) -> dict[str, list[BankOverride]]:
    return {
        step_id: [
            BankOverride(
                step_id=step_id,
                original_status="missing",
                corrected_status="adequate",
                rationale="the supplement reports it",
                paper_title="Prior Paper",
                author="alice",
            )
        ]
    }


def test_relevant_override_nudges_one_level_and_rescores() -> None:
    result = _result()
    target = next(
        a for a in result.step_assessments if a.applicable and a.status is StepStatus.missing
    )
    # the LLM judges it relevant and asks for adequate — but the nudge is capped at one level
    fake = FakeLLMClient(
        ReviewVerdict(
            relevant=True, corrected_status="adequate", used_override=0, justification="m"
        )
    )
    corrected, applied, cost = review_overrides(
        result, _bank_for(target.step_id), _RUBRIC, client=fake, model=llm_config.judge_model()
    )

    new = next(a for a in corrected.step_assessments if a.step_id == target.step_id)
    assert new.status is StepStatus.partial  # missing -> partial (one level only, not adequate)
    assert len(applied) == 1 and len(fake.calls) == 1 and len(cost) == 1
    c = applied[0]
    assert c.from_status is StepStatus.missing and c.to_status is StepStatus.partial
    assert c.source_paper_title == "Prior Paper" and c.override_author == "alice"
    assert c.justification == "m" and c.quality_delta > 0


def test_irrelevant_verdict_leaves_the_grade_unchanged() -> None:
    result = _result()
    target = next(
        a for a in result.step_assessments if a.applicable and a.status is StepStatus.missing
    )
    fake = FakeLLMClient(ReviewVerdict(relevant=False))
    corrected, applied, cost = review_overrides(
        result, _bank_for(target.step_id), _RUBRIC, client=fake, model=llm_config.judge_model()
    )
    assert corrected is result and applied == [] and len(cost) == 1  # judged once, no change


def test_empty_bank_makes_no_llm_call() -> None:
    result = _result()
    fake = FakeLLMClient()  # no scripted responses → any call would raise
    corrected, applied, cost = review_overrides(
        result, {}, _RUBRIC, client=fake, model=llm_config.judge_model()
    )
    assert corrected is result and applied == [] and cost == [] and fake.calls == []
