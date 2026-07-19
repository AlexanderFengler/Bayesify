"""Paper-type classifier — the checklist contract: the fake LLM returns ``ClassifierFacts`` and the
deterministic mapper (labels / methods / software ontology) owns the final ``PaperClass``."""

from __future__ import annotations

from datetime import datetime

import pytest

from bayesify.core import classify as C
from bayesify.core.schema import (
    ClassifierFacts,
    ClassifierMethodFacts,
    ClassifierPaperTypeFacts,
    Evidence,
    EvidenceKind,
    EvidenceSpan,
    InferenceMethod,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
    Section,
    SectionKind,
    SourceDoc,
)
from bayesify.llm import FakeLLMClient, LLMError, LLMTransientError
from bayesify.llm import config as llm_config

_WHEN = datetime(2026, 1, 1)


def _parsed(text: str) -> ParsedDoc:
    src = SourceDoc(sha256="a" * 64, version_label="t", source="upload", fetched_at=_WHEN)
    secs = [Section(id="s01", kind=SectionKind.body, title="Body", text=text)]
    return ParsedDoc(source=src, sections=secs, parser="test", parser_version="0")


def _ev() -> Evidence:
    return Evidence(
        detector_id="software.stan",
        detector_version="0.1.0",
        kind=EvidenceKind.software_mention,
        span=EvidenceSpan(section_id="s01", page=1, quote="in Stan"),
    )


_NO = {"answer": "no", "confidence": "low", "evidence": ""}


def _facts(
    paper_type: dict[str, dict] | None = None,
    methods: dict[str, dict] | None = None,
    software: list[dict] | None = None,
    disciplines: list[str] | None = None,
) -> ClassifierFacts:
    """An all-'no' checklist with targeted overrides — the wire format classify now expects."""
    pt = {name: dict(_NO) for name in ClassifierPaperTypeFacts.model_fields}
    pt.update(paper_type or {})
    me = {name: dict(_NO) for name in ClassifierMethodFacts.model_fields}
    me.update(methods or {})
    return ClassifierFacts(
        paper_type=pt, methods=me, software=software or [], disciplines=disciplines or []
    )


def _yes(evidence: str, confidence: str = "high") -> dict:
    return {"answer": "yes", "confidence": confidence, "evidence": evidence}


def _sw(name: str, evidence: str = "", confidence: str = "high") -> dict:
    """A software claim in the checklist wire format (grounded like every other fact)."""
    return {"name": name, "confidence": confidence, "evidence": evidence}


# --- fact -> label mapping ------------------------------------------------------------------------


def test_classify_maps_checklist_facts_and_meters_cost() -> None:
    parsed = _parsed("We fit a Bayesian model to real reaction-time data in Stan.")
    facts = _facts(
        paper_type={
            "uses_bayesian_model_on_real_data": _yes(
                "fit a Bayesian model to real reaction-time data in Stan"
            )
        },
        software=[_sw("Stan", "real reaction-time data in Stan")],
        disciplines=["neuroscience"],
    )
    client = FakeLLMClient(facts)
    cls, entry = C.classify(parsed, [_ev()], client=client)

    assert cls.labels == [PaperClassLabel.data_analysis]
    assert cls.methods_used == [InferenceMethod.mcmc]  # Stan implies MCMC via the ontology
    assert cls.software_used == ["Stan"]
    assert cls.disciplines == ["neuroscience"]
    assert cls.evidence_refs == [0]  # the fact quote overlaps the detector span ("in Stan")
    assert entry.stage == "classify" and entry.model == llm_config.classify_model()
    assert client.calls[0]["schema"] == "ClassifierFacts"


def test_classify_supports_multi_label_papers() -> None:
    facts = _facts(
        paper_type={
            "develops_new_bayesian_model": _yes("we propose a new hierarchical model"),
            "uses_bayesian_model_on_real_data": _yes("applied to real census data"),
        }
    )
    cls, _ = C.classify(_parsed("irrelevant"), [_ev()], client=FakeLLMClient(facts))
    # both quotes carry their label cue; model_development is primary, data_analysis secondary
    assert cls.labels == [PaperClassLabel.model_development, PaperClassLabel.data_analysis]


@pytest.mark.parametrize(
    "quote",
    [
        "we introduce a new sampler",
        "we propose a fundamentally new generally applicable prior",
    ],
)
def test_method_development_accepts_sampler_and_general_prior_cues(quote: str) -> None:
    facts = _facts(paper_type={"develops_new_bayesian_method": _yes(quote)})
    cls, _ = C.classify(_parsed("x"), [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [PaperClassLabel.method_development]


def test_prior_method_conflict_drops_prior_only_model_overemit() -> None:
    text = (
        "We propose a prior on model fit, measured by a Bayesian coefficient of determination R2. "
        "We place a beta prior on R2 and derive the induced prior on the global variance parameter "
        "for generalized linear mixed models. Using PyMC we fit the resulting model to real census "
        "data."
    )
    facts = _facts(
        paper_type={
            "develops_new_bayesian_model": _yes("prior on model fit"),
            "develops_new_bayesian_method": _yes(
                "beta prior on R2 and derive the induced prior"
            ),
            "uses_bayesian_model_on_real_data": _yes("real census data"),
        },
        software=[_sw("PyMC", "Using PyMC we fit the resulting model")],
    )
    cls, _ = C.classify(_parsed(text), [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [PaperClassLabel.method_development, PaperClassLabel.data_analysis]


def test_prior_theory_conflict_drops_prior_only_model_overemit() -> None:
    text = (
        "We propose a new weakly-informative prior for hierarchical variance parameters. "
        "We derive properties of the resulting posterior distribution and study posterior "
        "contraction."
    )
    facts = _facts(
        paper_type={
            "develops_new_bayesian_model": _yes(
                "new weakly-informative prior for hierarchical variance parameters"
            ),
            "develops_new_bayesian_method": _yes(
                "new weakly-informative prior for hierarchical variance parameters"
            ),
            "investigates_theoretical_behavior": _yes(
                "derive properties of the resulting posterior distribution and study posterior "
                "contraction"
            ),
        }
    )
    cls, _ = C.classify(_parsed(text), [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [
        PaperClassLabel.method_development,
        PaperClassLabel.theoretical_analysis,
    ]


def test_prior_conflict_keeps_independent_model_contribution() -> None:
    facts = _facts(
        paper_type={
            "develops_new_bayesian_model": _yes("we propose a new hierarchical model"),
            "develops_new_bayesian_method": _yes("we introduce a new sampler"),
        }
    )
    cls, _ = C.classify(_parsed("x"), [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [PaperClassLabel.method_development, PaperClassLabel.model_development]


def test_low_confidence_paper_type_fact_is_dropped() -> None:
    facts = _facts(
        paper_type={
            "develops_new_bayesian_model": _yes("we propose a new hierarchical model"),
            "uses_bayesian_model_on_real_data": _yes("applied to real data", confidence="low"),
        }
    )
    cls, _ = C.classify(_parsed("x"), [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [PaperClassLabel.model_development]


def test_unverifiable_quote_without_label_cue_is_dropped() -> None:
    facts = _facts(
        paper_type={
            # neither in the excerpt nor carrying a model_development cue -> dropped
            "develops_new_bayesian_model": _yes("the weather was nice that day"),
            "uses_bayesian_model_on_real_data": _yes("we analyse real data"),
        }
    )
    cls, _ = C.classify(_parsed("something else entirely"), [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [PaperClassLabel.data_analysis]


def test_no_surviving_facts_falls_back_to_data_analysis() -> None:
    cls, _ = C.classify(_parsed("x"), [_ev()], client=FakeLLMClient(_facts()))
    assert cls.labels == [PaperClassLabel.data_analysis]


def test_theoretical_analysis_requires_formal_or_derivation_structure() -> None:
    # theoretical-sounding but informal property discussion -> dropped (falls back to data_analysis)
    no_structure = _facts(
        paper_type={"investigates_theoretical_behavior": _yes("informal discussion of consistency")}
    )
    parsed = _parsed("We give an informal discussion of consistency and intuition.")
    cls, _ = C.classify(parsed, [_ev()], client=FakeLLMClient(no_structure))
    assert PaperClassLabel.theoretical_analysis not in cls.labels

    # formal result marker is enough; some papers omit literal "Proof" in extracted context
    formal = _facts(
        paper_type={
            "investigates_theoretical_behavior": _yes("Proposition 1 establishes consistency")
        }
    )
    parsed = _parsed("Proposition 1 establishes consistency.")
    cls, _ = C.classify(parsed, [_ev()], client=FakeLLMClient(formal))
    assert cls.labels == [PaperClassLabel.theoretical_analysis]

    # derivation/asymptotic language also counts as theory, even without theorem/proof markers
    derivation = _facts(
        paper_type={
            "investigates_theoretical_behavior": _yes(
                "derive properties of the resulting posterior distribution and study posterior "
                "contraction"
            )
        }
    )
    parsed = _parsed(
        "We derive properties of the resulting posterior distribution and study posterior "
        "contraction."
    )
    cls, _ = C.classify(parsed, [_ev()], client=FakeLLMClient(derivation))
    assert cls.labels == [PaperClassLabel.theoretical_analysis]


# --- software rules -------------------------------------------------------------------------------


def test_review_only_paper_may_have_empty_software() -> None:
    facts = _facts(
        paper_type={"is_review_tutorial_or_commentary": _yes("a review of Bayesian workflow")}
    )
    cls, _ = C.classify(_parsed("x"), [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [PaperClassLabel.review]
    assert cls.software_used == []  # no fabricated "Custom" on a paper that runs nothing


def test_theoretical_only_paper_may_have_empty_software() -> None:
    facts = _facts(
        paper_type={"investigates_theoretical_behavior": _yes("Theorem 1 establishes consistency")}
    )
    parsed = _parsed("Theorem 1 establishes consistency. Proof. See the appendix.")
    cls, _ = C.classify(parsed, [_ev()], client=FakeLLMClient(facts))
    assert cls.labels == [PaperClassLabel.theoretical_analysis]
    assert cls.software_used == []


def test_computational_paper_without_named_software_gets_custom() -> None:
    facts = _facts(paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")})
    cls, _ = C.classify(_parsed("x"), [_ev()], client=FakeLLMClient(facts))
    assert cls.software_used == ["Custom"]  # computational labels keep the never-empty rule


def test_software_canonicalization_and_language_qualifier() -> None:
    text = "We analyse real data. We implemented the model in PyMC3 with custom code in Python."
    facts = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        software=[
            _sw("pymc3", "implemented the model in PyMC3"),
            _sw("python"),  # bare language: no quote needed, only ever a Custom qualifier
            _sw("custom", "custom code in Python"),
            _sw("R "),
        ],
    )
    cls, _ = C.classify(_parsed(text), [_ev()], client=FakeLLMClient(facts))
    # pymc3 canonicalizes; bare languages drop out of the list but qualify Custom
    assert cls.software_used == ["PyMC", "Custom (Python)"]


# --- fact -> method mapping -----------------------------------------------------------------------


def test_method_fact_requires_its_quote_in_the_excerpts() -> None:
    facts = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        methods={"uses_sbi": _yes("simulation-based inference approach")},
    )
    # quote absent from the paper -> dropped
    cls, _ = C.classify(_parsed("nothing of the sort here"), [_ev()], client=FakeLLMClient(facts))
    assert cls.methods_used == []

    # quote present in the paper (and carrying the SBI cue) -> kept
    facts2 = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        methods={"uses_sbi": _yes("simulation-based inference approach")},
    )
    parsed = _parsed("We take a simulation-based inference approach to estimation.")
    cls, _ = C.classify(parsed, [_ev()], client=FakeLLMClient(facts2))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_software_ontology_implies_methods() -> None:
    text = "We analyse real data. Amortized inference used BayesFlow throughout."
    facts = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        software=[_sw("BayesFlow", "Amortized inference used BayesFlow")],
    )
    cls, _ = C.classify(_parsed(text), [_ev()], client=FakeLLMClient(facts))
    assert InferenceMethod.sbi in cls.methods_used  # BayesFlow -> SBI, no method fact needed


def test_low_confidence_software_is_dropped_and_implies_no_method() -> None:
    # The model's own "perfunctory baseline / unclear it was executed" signal: listed but low.
    text = "We analyse real data. We compare briefly against results reported for Stan."
    facts = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        software=[_sw("Stan", "compare briefly against results reported for Stan", "low")],
    )
    cls, _ = C.classify(_parsed(text), [_ev()], client=FakeLLMClient(facts))
    assert cls.software_used == ["Custom"]  # computational fallback, not the baseline package
    assert cls.methods_used == []  # and no phantom mcmc via the software->method ontology


def test_software_with_unverifiable_quote_is_dropped() -> None:
    facts = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        software=[_sw("Stan", "we ran everything in Stan")],  # quote not in the excerpts
    )
    cls, _ = C.classify(_parsed("We analyse real data."), [_ev()], client=FakeLLMClient(facts))
    assert cls.software_used == ["Custom"]


def test_software_quote_must_name_the_package() -> None:
    text = "We analyse real data. We fit the model with MCMC sampling."
    facts = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        software=[_sw("Stan", "We fit the model with MCMC sampling.")],  # real quote, wrong name
    )
    cls, _ = C.classify(_parsed(text), [_ev()], client=FakeLLMClient(facts))
    assert cls.software_used == ["Custom"]


def test_general_purpose_tooling_is_dropped_even_when_grounded() -> None:
    text = "We analyse real data. Preprocessing used scikit-learn pipelines."
    facts = _facts(
        paper_type={"uses_bayesian_model_on_real_data": _yes("we analyse real data")},
        software=[_sw("scikit-learn", "Preprocessing used scikit-learn pipelines")],
    )
    cls, _ = C.classify(_parsed(text), [_ev()], client=FakeLLMClient(facts))
    assert cls.software_used == ["Custom"]  # out of scope: not the Bayesian analysis workflow


# --- transport + schema invariants (unchanged) ----------------------------------------------------


def test_classify_fails_closed() -> None:
    client = FakeLLMClient(LLMTransientError("a"), LLMTransientError("b"), LLMTransientError("c"))
    with pytest.raises(LLMError):
        C.classify(_parsed("text"), [_ev()], client=client)


def test_paperclass_methods_used_drops_unknown_unstated_and_dupes() -> None:
    # A stray/hallucinated method token is filtered (mode="before"), not a hard failure; "unstated"
    # and duplicates are dropped by the after-validator, so one bad word never fails the whole call.
    pc = PaperClass(
        labels=[PaperClassLabel.data_analysis], confidence=0.8, rationale="r", evidence_refs=[0],
        methods_used=["mcmc", "nuts", "mcmc", "unstated"],  # "nuts" not in vocab; dup + unstated
    )
    assert pc.methods_used == [InferenceMethod.mcmc]


def test_paperclass_methods_used_logs_dropped(caplog) -> None:
    # Out-of-vocab tokens are dropped (not fatal) AND logged, so an untracked method surfaces.
    import logging

    with caplog.at_level(logging.WARNING, logger="bayesify.core.schema"):
        pc = PaperClass(
            labels=[PaperClassLabel.data_analysis], confidence=0.8, rationale="r",
            evidence_refs=[0], methods_used=["mcmc", "particle_filter"],
        )
    assert pc.methods_used == [InferenceMethod.mcmc]
    assert any("particle_filter" in r.getMessage() for r in caplog.records)
