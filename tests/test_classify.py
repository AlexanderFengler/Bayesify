"""Paper-type classifier (M4 slice 3), driven by the fake LLM client (no network)."""

from __future__ import annotations

from datetime import datetime

import pytest

from bayesify.core import classify as C
from bayesify.core.schema import (
    Evidence,
    EvidenceKind,
    EvidenceSpan,
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


def _method_ev(detector_id: str, quote: str = "m") -> Evidence:
    return Evidence(
        detector_id=detector_id,
        detector_version="0.1.0",
        kind=EvidenceKind.method_mention,
        span=EvidenceSpan(section_id="s01", page=1, quote=quote),
    )


def _software_ev(detector_id: str, quote: str = "software") -> Evidence:
    return Evidence(
        detector_id=detector_id,
        detector_version="0.1.0",
        kind=EvidenceKind.software_mention,
        span=EvidenceSpan(section_id="s01", page=1, quote=quote),
    )


def test_classify_returns_paperclass_and_meters_cost() -> None:
    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.85,
        rationale="fits real data",
        evidence_refs=[0],
    )
    client = FakeLLMClient(canned)
    cls, entry = C.classify(_parsed("We fit a model to real RT data."), [_ev()], client=client)

    assert cls.labels == [PaperClassLabel.data_analysis]
    assert entry.stage == "classify" and entry.model == llm_config.classify_model()
    assert client.calls[0]["schema"] == "PaperClass"
    assert "DETECTOR HITS" in client.calls[0]["user"]


def test_classify_supports_multi_label_paper_types() -> None:
    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.data_analysis],
        confidence=0.7,
        rationale="new prior + a real-data application section",
        evidence_refs=[0],
    )
    cls, _ = C.classify(
        _parsed("We propose a new prior and apply it."), [_ev()], client=FakeLLMClient(canned)
    )
    assert cls.labels == [PaperClassLabel.method_development, PaperClassLabel.data_analysis]


def test_classify_fails_closed() -> None:
    client = FakeLLMClient(LLMTransientError("a"), LLMTransientError("b"), LLMTransientError("c"))
    with pytest.raises(LLMError):
        C.classify(_parsed("text"), [_ev()], client=client)


def test_classify_rejects_out_of_range_evidence_ref() -> None:
    # Only one detector hit (index 0) was shown; a ref to index 3 is a hallucinated citation.
    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.85,
        rationale="fits real data",
        evidence_refs=[3],
    )
    with pytest.raises(ValueError, match="evidence_refs"):
        C.classify(_parsed("We fit a model."), [_ev()], client=FakeLLMClient(canned))


def test_classify_keeps_methods_grounded_by_a_detector_hit() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits real data",
        evidence_refs=[0],
        methods_used=[InferenceMethod.hmc_nuts, InferenceMethod.sbi, InferenceMethod.smc],
    )
    # hmc_nuts grounds on method.mcmc, sbi on method.sbi, smc on method.smc — all present, so all
    # three survive.
    evidence = [
        _ev(),
        _method_ev("method.mcmc"),
        _method_ev("method.sbi"),
        _method_ev("method.smc"),
    ]
    cls, _ = C.classify(
        _parsed("We fit with NUTS, SBI, SMC."), evidence, client=FakeLLMClient(canned)
    )
    assert cls.methods_used == [InferenceMethod.hmc_nuts, InferenceMethod.sbi, InferenceMethod.smc]


def test_classify_drops_methods_with_no_detector_hit(caplog) -> None:
    import logging

    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="r",
        evidence_refs=[0],
        methods_used=[InferenceMethod.mcmc, InferenceMethod.smc],
    )
    # Only method.mcmc fired; the hallucinated smc has no corroborating detector hit -> dropped.
    evidence = [_ev(), _method_ev("method.mcmc")]
    with caplog.at_level(logging.WARNING, logger="bayesify.core.classify"):
        cls, _ = C.classify(
            _parsed("Inference used MCMC only."), evidence, client=FakeLLMClient(canned)
        )
    assert cls.methods_used == [InferenceMethod.mcmc]
    assert any("smc" in r.getMessage() for r in caplog.records)


def test_classify_keeps_semantic_sbi_without_literal_detector_hit() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="new amortized neural inference method with simulations",
        evidence_refs=[0],
        methods_used=[InferenceMethod.sbi],
    )
    evidence = [_method_ev("method.posterior")]
    text = (
        "We propose a globally amortized Bayesian inference procedure based on invertible neural "
        "networks. The procedure uses simulation to learn a posterior estimator from observations "
        "to model parameters."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_adds_sbi_for_invertible_network_inverse_problem_wording() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="invertible neural inverse method",
        evidence_refs=[0],
        methods_used=[],
    )
    evidence = [_method_ev("method.posterior")]
    text = (
        "Many ambiguous inverse problems map hidden system parameters to measurements through a "
        "known forward process, and the aim is to recover the posterior parameter distribution. "
        "We argue that invertible neural networks are well suited to this task. "
        "The network learns the forward process jointly with an inverse pass, using latent "
        "variables to represent information loss. "
        "Given a measurement and sampled latent variables, the inverse pass produces a full "
        "distribution over parameter space."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_keeps_sbi_for_line_wrapped_inn_abstract() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="invertible neural inverse method",
        evidence_refs=[0],
        methods_used=[
            InferenceMethod.sbi,
            InferenceMethod.abc,
            InferenceMethod.mcmc,
            InferenceMethod.variational,
        ],
    )
    evidence = [_method_ev("method.posterior")]
    text = (
        "Often, the forward process from parameter- to measurement-space is a well-defined\n"
        "function, whereas the inverse problem is ambiguous: one measurement may map to\n"
        "multiple different sets of parameters. In this setting, the posterior parameter\n"
        "distribution, conditioned on an input measurement, has to be determined. We argue\n"
        "that a particular class of neural networks is well suited for this task -- so-called\n"
        "Invertible Neural Networks (INNs). Although INNs are not new, they have, so far,\n"
        "received little attention in literature. While classical neural networks attempt\n"
        "to solve the ambiguous inverse problem directly, INNs are able to learn it jointly\n"
        "with the well-defined forward process, using additional latent output variables\n"
        "to capture the information otherwise lost. Given a specific measurement and\n"
        "sampled latent variables, the inverse pass of the INN provides a full distribution\n"
        "over parameter space."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_drops_comparison_only_method_hits_but_keeps_sbi() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="new amortized neural inference method with simulation experiments",
        evidence_refs=[0],
        methods_used=[InferenceMethod.sbi, InferenceMethod.mcmc, InferenceMethod.abc],
    )
    evidence = [
        _method_ev("method.mcmc"),
        _method_ev("method.abc"),
        _method_ev("method.posterior"),
    ]
    text = (
        "Approximate Bayesian computation methods simulate data and retain draws when the "
        "distance to observed data is below a threshold. More efficient methods include "
        "ABC-SMC and Markov chain Monte Carlo variants. In this paper, we propose a globally "
        "amortized Bayesian inference method based on invertible neural networks and train the "
        "networks with simulations from the forward model."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_adds_semantic_sbi_when_model_only_names_baselines() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="new amortized neural inference method with baseline comparisons",
        evidence_refs=[0],
        methods_used=[InferenceMethod.mcmc, InferenceMethod.abc],
    )
    evidence = [
        _method_ev("method.mcmc"),
        _method_ev("method.abc"),
        _method_ev("method.posterior"),
    ]
    text = (
        "The standard solution is approximate Bayesian computation. "
        "More efficient methods include ABC-SMC and Markov chain Monte Carlo variants. "
        "Our main aim is the introduction of a general approach to amortized Bayesian inference. "
        "For each model, we train an invertible neural network jointly with a summary network "
        "using simulated data from the forward model. "
        "During inference, the network generates posterior samples for observed datasets."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_drops_bayesflow_related_work_mcmc_from_detector_quote() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="BayesFlow-like amortized inference method",
        evidence_refs=[0],
        methods_used=[
            InferenceMethod.sbi,
            InferenceMethod.abc,
            InferenceMethod.mcmc,
            InferenceMethod.variational,
        ],
    )
    evidence = [
        _method_ev("method.posterior", "posterior estimation"),
        _method_ev("method.abc", "ABC-SMC"),
        _method_ev("method.mcmc", "MCMC sampling"),
        _method_ev("method.variational", "variational inference"),
    ]
    text = (
        "With this work, we propose a novel method for globally amortized Bayesian inference "
        "based on invertible neural networks. The method uses simulation to learn a global "
        "estimator for the probabilistic mapping from observed data to underlying model "
        "parameters. For each model, we train an invertible network jointly with a summary "
        "network using simulated data from the forward model. "
        "Related Work. More efficient methods for approximate inference, such as ABC-SMC, "
        "Markov-Chain Monte Carlo variants, or neural density estimation methods, optimize "
        "sampling from a proposal distribution. In the context of Bayesian inference, "
        "transport maps have been applied to accelerate MCMC sampling."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_drops_mcmc_when_all_mentions_are_background() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="new amortized neural inference method",
        evidence_refs=[0],
        methods_used=[InferenceMethod.sbi, InferenceMethod.mcmc],
    )
    evidence = [_method_ev("method.mcmc"), _method_ev("method.posterior")]
    text = (
        "Existing MCMC methods can be slow for likelihood-free problems. "
        "Related work uses transport maps to accelerate MCMC sampling. "
        "More efficient methods include Markov chain Monte Carlo variants. "
        "In this paper, we propose a globally amortized Bayesian inference procedure based on "
        "invertible neural networks and train the networks with simulations from the forward model."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_keeps_mcmc_when_one_mention_is_own_use() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits the model with MCMC",
        evidence_refs=[0],
        methods_used=[InferenceMethod.mcmc],
    )
    evidence = [_method_ev("method.mcmc")]
    text = (
        "Related work used MCMC for a similar model. "
        "We ran MCMC with four chains for the posterior analysis."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.mcmc]


def test_classify_keeps_mcmc_from_own_use_detector_quote() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits the model with MCMC",
        evidence_refs=[0],
        methods_used=[InferenceMethod.mcmc],
    )
    evidence = [
        Evidence(
            detector_id="method.mcmc",
            detector_version="0.1.0",
            kind=EvidenceKind.method_mention,
            span=EvidenceSpan(section_id="s01", page=1, quote="We ran MCMC with four chains"),
        )
    ]
    cls, _ = C.classify(
        _parsed("The posterior analysis is described in the supplement."),
        evidence,
        client=FakeLLMClient(canned),
    )
    assert cls.methods_used == [InferenceMethod.mcmc]


def test_classify_software_ontology_adds_sbi_method() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits simulator with SBI software",
        evidence_refs=[0],
        methods_used=[],
    )
    evidence = [_software_ev("software.bayesflow", "BayesFlow")]
    cls, _ = C.classify(
        _parsed("We used BayesFlow to perform amortized posterior inference."),
        evidence,
        client=FakeLLMClient(canned),
    )
    assert cls.methods_used == [InferenceMethod.sbi]


def test_classify_software_ontology_adds_abc_method() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits simulator with ABC software",
        evidence_refs=[0],
        methods_used=[],
    )
    evidence = [_software_ev("software.pyabc", "pyABC")]
    cls, _ = C.classify(
        _parsed("We implemented the parameter inference in pyABC."),
        evidence,
        client=FakeLLMClient(canned),
    )
    assert cls.methods_used == [InferenceMethod.abc]
    assert cls.software_used == ["software.pyabc"]


def test_classify_keeps_reported_baseline_software_and_method() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="new amortized neural inference method with baseline results",
        evidence_refs=[0],
        methods_used=[InferenceMethod.sbi],
    )
    evidence = [
        _software_ev("software.pyabc", "pyABC"),
        _method_ev("method.abc"),
        _method_ev("method.posterior"),
    ]
    text = (
        "We propose a globally amortized Bayesian inference method based on invertible neural "
        "networks and train the networks with simulations from the forward model. "
        "We compared against an ABC-SMC baseline implemented in pyABC, and Table 2 reports "
        "the baseline results."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi, InferenceMethod.abc]
    assert cls.software_used == ["software.pyabc"]


def test_classify_keeps_used_abc_baseline_without_leaking_competing_mcmc() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="new amortized neural inference method with baseline results",
        evidence_refs=[0],
        methods_used=[InferenceMethod.sbi, InferenceMethod.mcmc, InferenceMethod.abc],
    )
    evidence = [
        _method_ev("method.mcmc"),
        _method_ev("method.abc"),
        _software_ev("software.pyabc", "pyABC"),
        _method_ev("method.posterior"),
    ]
    text = (
        "We propose a globally amortized Bayesian inference method based on invertible neural "
        "networks and train the networks with simulations from the forward model. "
        "MCMC is a competing method, but in our experiments we compare against an ABC-SMC "
        "baseline implemented in pyABC and report the results."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi, InferenceMethod.abc]
    assert cls.software_used == ["software.pyabc"]


def test_classify_drops_software_that_is_only_mentioned() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.method_development, PaperClassLabel.numerical_analysis],
        confidence=0.86,
        rationale="new amortized neural inference method",
        evidence_refs=[0],
        methods_used=[],
    )
    evidence = [_software_ev("software.pyabc", "pyABC"), _method_ev("method.posterior")]
    text = (
        "The pyABC package implements ABC-SMC. "
        "In this paper, we propose an amortized Bayesian inference method based on neural "
        "networks trained with simulations from the forward model."
    )
    cls, _ = C.classify(_parsed(text), evidence, client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.sbi]
    assert cls.software_used == []


def test_classify_software_ontology_adds_mcmc_method() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits model in Stan",
        evidence_refs=[0],
        methods_used=[],
    )
    evidence = [_software_ev("software.stan", "Stan")]
    cls, _ = C.classify(
        _parsed("We fit the hierarchical model in Stan."),
        evidence,
        client=FakeLLMClient(canned),
    )
    assert cls.methods_used == [InferenceMethod.mcmc]


def test_classify_software_ontology_keeps_hmc_nuts_as_mcmc_family() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits model in Stan with NUTS",
        evidence_refs=[0],
        methods_used=[InferenceMethod.hmc_nuts],
    )
    evidence = [_software_ev("software.stan", "Stan")]
    cls, _ = C.classify(
        _parsed("We fit the hierarchical model in Stan with NUTS."),
        evidence,
        client=FakeLLMClient(canned),
    )
    assert cls.methods_used == [InferenceMethod.hmc_nuts]


def test_classify_software_ontology_ignores_background_mentions() -> None:
    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="fits model with an unstated method",
        evidence_refs=[0],
        methods_used=[],
    )
    evidence = [_software_ev("software.stan", "Stan")]
    cls, _ = C.classify(
        _parsed("Related work used Stan. We fit our model with a custom analytic calculation."),
        evidence,
        client=FakeLLMClient(canned),
    )
    assert cls.methods_used == []
    assert cls.software_used == []


def test_classify_skips_method_grounding_without_evidence() -> None:
    from bayesify.core.schema import InferenceMethod

    canned = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="r",
        evidence_refs=[0],
        methods_used=[InferenceMethod.smc],
    )
    # The forced-rerun escape hatch grades without grounding (evidence == []): methods pass through.
    cls, _ = C.classify(_parsed("x"), [], client=FakeLLMClient(canned))
    assert cls.methods_used == [InferenceMethod.smc]


def test_paperclass_methods_used_drops_unknown_unstated_and_dupes() -> None:
    # A stray/hallucinated method token is filtered (mode="before"), not a hard failure; "unstated"
    # and duplicates are dropped by the after-validator, so one bad word never fails the whole call.
    from bayesify.core.schema import InferenceMethod

    pc = PaperClass(
        labels=[PaperClassLabel.data_analysis],
        confidence=0.8,
        rationale="r",
        evidence_refs=[0],
        methods_used=["mcmc", "nuts", "mcmc", "unstated"],  # "nuts" not in vocab; dup + unstated
    )
    assert pc.methods_used == [InferenceMethod.mcmc]


def test_paperclass_methods_used_logs_dropped(caplog) -> None:
    # Out-of-vocab tokens are dropped (not fatal) AND logged, so an untracked method surfaces.
    import logging

    from bayesify.core.schema import InferenceMethod

    with caplog.at_level(logging.WARNING, logger="bayesify.core.schema"):
        pc = PaperClass(
            labels=[PaperClassLabel.data_analysis],
            confidence=0.8,
            rationale="r",
            evidence_refs=[0],
            methods_used=["mcmc", "particle_filter"],
        )
    assert pc.methods_used == [InferenceMethod.mcmc]
    assert any("particle_filter" in r.getMessage() for r in caplog.records)
