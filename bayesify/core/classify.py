"""Paper-type classifier - component d, stage 5.

The model now answers a fixed checklist of factual yes/no questions. This module maps those
answers into the stable ``PaperClass`` contract used by scoring and the UI.
"""

from __future__ import annotations

import logging
import re
from typing import TypeVar

from bayesify.core.context import excerpt_context, validate_evidence_refs
from bayesify.core.prompts import CLASSIFY_FACTS_SYSTEM
from bayesify.core.schema import (
    ClassifierFact,
    ClassifierFacts,
    CostLedgerEntry,
    Evidence,
    FactAnswer,
    FactConfidence,
    InferenceMethod,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
)
from bayesify.llm import LLMClient, call_with_policy, ledger_entry
from bayesify.llm import config as llm_config

_log = logging.getLogger("bayesify.core.classify")
_T = TypeVar("_T")

# Wider than the screen gate's DEFAULT_MAX_CHARS (12k): the paper type / disciplines can depend on
# content in a later section (e.g. a secondary real-data analysis) that a 12k prefix cut would drop.
CLASSIFY_MAX_CHARS = 30_000

_LABEL_FACTS: tuple[tuple[str, PaperClassLabel], ...] = (
    ("develops_new_bayesian_model", PaperClassLabel.model_development),
    ("develops_new_bayesian_method", PaperClassLabel.method_development),
    ("develops_new_bayesian_software", PaperClassLabel.software_development),
    (
        "uses_bayesian_model_on_real_data_for_domain_conclusions",
        PaperClassLabel.data_analysis,
    ),
    ("runs_numerical_or_simulation_study", PaperClassLabel.numerical_analysis),
    ("investigates_theoretical_behavior", PaperClassLabel.theoretical_analysis),
    ("is_review_tutorial_or_commentary", PaperClassLabel.review),
)

_METHOD_FACTS: tuple[tuple[str, InferenceMethod], ...] = (
    ("uses_mcmc", InferenceMethod.mcmc),
    ("uses_hmc_or_nuts", InferenceMethod.mcmc),
    ("uses_variational_inference", InferenceMethod.variational),
    ("uses_sbi", InferenceMethod.sbi),
    ("uses_abc", InferenceMethod.abc),
    ("uses_smc_or_particle_filter", InferenceMethod.smc),
    ("uses_laplace_or_inla", InferenceMethod.laplace_inla),
    ("uses_em", InferenceMethod.em),
    ("uses_exact_or_analytic_posterior", InferenceMethod.exact_analytic),
)

_SOFTWARE_CANONICAL: dict[str, str] = {
    "bayesflow": "BayesFlow",
    "sbi": "sbi",
    "neuralestimators": "NeuralEstimators.jl",
    "neuralestimatorsjl": "NeuralEstimators.jl",
    "pyabc": "pyABC",
    "stan": "Stan",
    "pystan": "PyStan",
    "cmdstan": "CmdStan",
    "cmdstanr": "CmdStanR",
    "cmdstanpy": "CmdStanPy",
    "pymc": "PyMC",
    "pymc3": "PyMC",
    "pymc4": "PyMC",
    "brms": "brms",
    "rstanarm": "rstanarm",
    "jags": "JAGS",
    "bugs": "BUGS",
    "openbugs": "OpenBUGS",
    "winbugs": "WinBUGS",
    "turing": "Turing.jl",
    "turingjl": "Turing.jl",
    "numpyro": "NumPyro",
    "tensorflowprobability": "TensorFlow Probability",
    "tfp": "TensorFlow Probability",
    "hddm": "HDDM",
    "hssm": "HSSM",
    "custom": "Custom",
    "customcode": "Custom",
    "customimplementation": "Custom",
}

_SBI_SOFTWARE = {"bayesflow", "sbi", "neuralestimators", "neuralestimatorsjl"}
_ABC_SOFTWARE = {"pyabc"}
_MCMC_SOFTWARE = {
    "stan",
    "pystan",
    "cmdstan",
    "cmdstanr",
    "cmdstanpy",
    "pymc",
    "pymc3",
    "pymc4",
    "brms",
    "rstanarm",
    "jags",
    "bugs",
    "openbugs",
    "winbugs",
    "turing",
    "turingjl",
    "numpyro",
    "tensorflowprobability",
    "tfp",
    "hddm",
    "hssm",
}

_METHOD_DETECTOR_IDS: dict[InferenceMethod, frozenset[str]] = {
    InferenceMethod.mcmc: frozenset({"method.mcmc"}),
    InferenceMethod.variational: frozenset({"method.variational"}),
    InferenceMethod.sbi: frozenset({"method.sbi"}),
    InferenceMethod.abc: frozenset({"method.abc"}),
    InferenceMethod.smc: frozenset({"method.smc"}),
    InferenceMethod.laplace_inla: frozenset({"method.laplace_inla"}),
    InferenceMethod.em: frozenset({"method.em"}),
    InferenceMethod.exact_analytic: frozenset({"method.analytic"}),
}

_METHOD_QUOTE_PATTERNS: dict[InferenceMethod, re.Pattern[str]] = {
    InferenceMethod.mcmc: re.compile(
        r"\b(mcmc|markov chain monte carlo|nuts|hamiltonian monte carlo|hmc|gibbs|"
        r"metropolis|stan|pymc|brms|rstanarm|jags|bugs|turing|numpyro|hddm|hssm)\b",
        re.I,
    ),
    InferenceMethod.variational: re.compile(
        r"\b(variational inference|variational bayes|advi|elbo|mean[- ]field)\b",
        re.I,
    ),
    InferenceMethod.sbi: re.compile(
        r"\b(sbi|simulation[- ]based inference|amortized bayesian|likelihood[- ]free "
        r"inference|neural (posterior|likelihood|ratio|score)|normalizing flow|"
        r"invertible neural network|bayesflow)\b|trained .{0,80}\bsimulat",
        re.I,
    ),
    InferenceMethod.abc: re.compile(
        r"\b(abc|abc[- ]smc|approximate bayesian computation|rejection abc|distance|tolerance)\b",
        re.I,
    ),
    InferenceMethod.smc: re.compile(
        r"\b(sequential monte carlo|particle filter|particle filtering|particle mcmc|smc)\b",
        re.I,
    ),
    InferenceMethod.laplace_inla: re.compile(r"\b(laplace approximation|inla)\b", re.I),
    InferenceMethod.em: re.compile(r"\b(expectation[- ]maximization|em algorithm|em-style)\b", re.I),
    InferenceMethod.exact_analytic: re.compile(
        r"\b(conjugate|closed[- ]form|analytic posterior|exact posterior|analytic updating)\b",
        re.I,
    ),
}


def classify(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str | None = None,
) -> tuple[PaperClass, CostLedgerEntry]:
    """Classify the paper type from checklist facts."""
    model = model or llm_config.classify_model()
    context = excerpt_context(parsed, max_chars=CLASSIFY_MAX_CHARS)
    user = _classify_user(context)
    response = call_with_policy(
        client,
        model=model,
        system=CLASSIFY_FACTS_SYSTEM,
        user=user,
        schema=ClassifierFacts,
        max_tokens=1400,
    )
    paper_class = _paper_class_from_facts(response.parsed, context, evidence)

    # Detector refs are now best-effort traceability, not a veto. The checklist evidence lives in
    # binary fact quotes; methods are mapped from yes/no answers plus the software ontology.
    if evidence and paper_class.evidence_refs:
        validate_evidence_refs(paper_class.evidence_refs, evidence, where="paper_class")
    return paper_class, ledger_entry("classify", response)


def _classify_user(context: str) -> str:
    return f"PAPER EXCERPTS (reference list excluded):\n{context}"


def _paper_class_from_facts(
    facts: ClassifierFacts, context: str, evidence: list[Evidence]
) -> PaperClass:
    labels = _labels_from_facts(facts)
    software = _canonical_software(facts.software)
    methods = _methods_from_facts(facts, context, evidence, software)

    disciplines = _disciplines_from_facts(facts, labels, methods)
    return PaperClass(
        labels=labels,
        disciplines=disciplines,
        confidence=_confidence_from_facts(facts),
        rationale=_rationale(labels, methods, software),
        evidence_refs=_matching_evidence_refs(facts, evidence),
        methods_used=methods,
        software_used=software,
    )


def _labels_from_facts(facts: ClassifierFacts) -> list[PaperClassLabel]:
    labels: list[PaperClassLabel] = []
    for attr, label in _LABEL_FACTS:
        if _yes(getattr(facts.paper_type, attr)):
            labels.append(label)
    if not labels:
        _log.warning("classifier checklist returned no yes paper-type facts; using data_analysis")
        labels.append(PaperClassLabel.data_analysis)
    return labels


def _methods_from_facts(
    facts: ClassifierFacts,
    context: str,
    evidence: list[Evidence],
    software: list[str],
) -> list[InferenceMethod]:
    methods: list[InferenceMethod] = []
    ontology_methods = _software_implied_methods(software)
    ontology_method_set = set(ontology_methods)
    for attr, method in _METHOD_FACTS:
        fact = getattr(facts.methods, attr, None)
        if fact is not None and _method_fact_survives(
            method, fact, context, evidence, ontology_method_set
        ):
            _append_unique(methods, method)
    for method in ontology_methods:
        _append_unique(methods, method)
    return methods


def _method_fact_survives(
    method: InferenceMethod,
    fact: ClassifierFact,
    context: str,
    evidence: list[Evidence],
    ontology_methods: set[InferenceMethod],
) -> bool:
    if not _yes(fact):
        return False
    if not _quote_in_text(fact.evidence, context):
        _log.warning(
            "classifier method evidence quote not found in excerpts (dropped): %s",
            method.value,
        )
        return False
    if fact.confidence is FactConfidence.high:
        return True
    if method in ontology_methods:
        return True
    if _fact_detector_refs(fact, evidence, method=method):
        return True
    if _method_quote_hit(method, fact.evidence):
        return True
    _log.warning(
        "low-confidence classifier method without deterministic support (dropped): %s",
        method.value,
    )
    return False


def _disciplines_from_facts(
    facts: ClassifierFacts,
    labels: list[PaperClassLabel],
    methods: list[InferenceMethod],
) -> list[str]:
    disciplines: list[str] = []
    for discipline in facts.disciplines:
        tag = discipline.strip().lower().replace("_", "-").replace(" ", "-")
        if tag:
            _append_unique(disciplines, tag)
    if disciplines:
        return disciplines[:3]
    if PaperClassLabel.method_development in labels:
        if InferenceMethod.sbi in methods:
            return ["statistics", "machine-learning"]
        return ["statistics"]
    return ["statistics"]


def _confidence_from_facts(facts: ClassifierFacts) -> float:
    selected = [fact for _, fact in _iter_yes_facts(facts)]
    if not selected:
        return 0.5
    score = sum(0.9 if fact.confidence is FactConfidence.high else 0.65 for fact in selected)
    return round(score / len(selected), 2)


def _rationale(
    labels: list[PaperClassLabel],
    methods: list[InferenceMethod],
    software: list[str],
) -> str:
    label_text = ", ".join(label.value for label in labels)
    method_text = ", ".join(method.value for method in methods) or "none"
    software_text = ", ".join(software) or "none"
    return (
        "Binary checklist mapped deterministically: "
        f"paper_type={label_text}; methods_used={method_text}; software_used={software_text}."
    )


def _matching_evidence_refs(facts: ClassifierFacts, evidence: list[Evidence]) -> list[int]:
    refs: list[int] = []
    for _, fact in _iter_yes_facts(facts):
        for idx in _fact_detector_refs(fact, evidence):
            _append_unique(refs, idx)
            break
    return refs


def _iter_yes_facts(facts: ClassifierFacts):
    for name, fact in _iter_facts(facts):
        if _yes(fact):
            yield name, fact


def _iter_facts(facts: ClassifierFacts):
    for group in (facts.paper_type, facts.methods):
        for name in type(group).model_fields:
            fact = getattr(group, name)
            if isinstance(fact, ClassifierFact):
                yield name, fact


def _yes(fact: ClassifierFact) -> bool:
    return fact.answer is FactAnswer.yes


def _canonical_software(raw: list[str]) -> list[str]:
    out: list[str] = []
    for item in raw:
        name = item.strip()
        if not name:
            continue
        canonical = _SOFTWARE_CANONICAL.get(_software_key(name), name)
        _append_unique_ci(out, canonical)
    return out


def _software_implied_methods(software: list[str]) -> list[InferenceMethod]:
    methods: list[InferenceMethod] = []
    keys = {_software_key(name) for name in software}
    if keys & _SBI_SOFTWARE:
        methods.append(InferenceMethod.sbi)
    if keys & _ABC_SOFTWARE:
        methods.append(InferenceMethod.abc)
    if keys & _MCMC_SOFTWARE:
        methods.append(InferenceMethod.mcmc)
    return methods


def _fact_detector_refs(
    fact: ClassifierFact,
    evidence: list[Evidence],
    *,
    method: InferenceMethod | None = None,
) -> list[int]:
    quote = _norm_space(fact.evidence)
    if not quote:
        return []
    allowed_ids = _METHOD_DETECTOR_IDS.get(method) if method is not None else None
    refs: list[int] = []
    for idx, item in enumerate(evidence):
        if allowed_ids is not None and item.detector_id not in allowed_ids:
            continue
        hit_quote = _norm_space(item.span.quote)
        if quote in hit_quote or hit_quote in quote:
            refs.append(idx)
    return refs


def _method_quote_hit(method: InferenceMethod, quote: str) -> bool:
    pattern = _METHOD_QUOTE_PATTERNS.get(method)
    return pattern.search(quote) is not None if pattern is not None else False


def _software_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _quote_in_text(quote: str, text: str) -> bool:
    norm_quote = _norm_space(quote)
    return bool(norm_quote and norm_quote in _norm_space(text))


def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _append_unique(items: list[_T], item: _T) -> None:
    if item not in items:
        items.append(item)


def _append_unique_ci(items: list[str], item: str) -> None:
    key = item.lower()
    if all(existing.lower() != key for existing in items):
        items.append(item)
