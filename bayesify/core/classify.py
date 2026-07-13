"""Paper-type classifier - component d, stage 5.

The model now answers a fixed checklist of factual yes/no questions. This module maps those
answers into the stable ``PaperClass`` contract used by scoring and the UI.
"""

from __future__ import annotations

import logging
import re

from bayesify.core import config
from bayesify.core.context import assessment_context, validate_evidence_refs
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

_LABEL_FACTS: tuple[tuple[str, PaperClassLabel], ...] = (
    ("develops_new_bayesian_model", PaperClassLabel.model_development),
    ("develops_new_bayesian_method", PaperClassLabel.method_development),
    ("develops_new_bayesian_software", PaperClassLabel.software_development),
    (
        "uses_bayesian_model_on_real_data",
        PaperClassLabel.data_analysis,
    ),
    ("runs_numerical_or_simulation_study", PaperClassLabel.numerical_analysis),
    ("investigates_theoretical_behavior", PaperClassLabel.theoretical_analysis),
    ("is_review_tutorial_or_commentary", PaperClassLabel.review),
)

_PRIMARY_LABEL_PRIORITY: tuple[PaperClassLabel, ...] = (
    PaperClassLabel.method_development,
    PaperClassLabel.model_development,
    PaperClassLabel.software_development,
    PaperClassLabel.data_analysis,
    PaperClassLabel.numerical_analysis,
    PaperClassLabel.theoretical_analysis,
    PaperClassLabel.review,
)

_MAX_PAPER_TYPE_LABELS = 4

_SECONDARY_LABEL_PRIORITY: dict[PaperClassLabel, tuple[PaperClassLabel, ...]] = {
    PaperClassLabel.method_development: (
        PaperClassLabel.model_development,
        PaperClassLabel.software_development,
        PaperClassLabel.numerical_analysis,
        PaperClassLabel.theoretical_analysis,
        PaperClassLabel.data_analysis,
    ),
    PaperClassLabel.model_development: (
        PaperClassLabel.data_analysis,
        PaperClassLabel.numerical_analysis,
        PaperClassLabel.theoretical_analysis,
        PaperClassLabel.method_development,
        PaperClassLabel.software_development,
    ),
    PaperClassLabel.software_development: (
        PaperClassLabel.method_development,
        PaperClassLabel.numerical_analysis,
        PaperClassLabel.data_analysis,
        PaperClassLabel.model_development,
        PaperClassLabel.theoretical_analysis,
    ),
    PaperClassLabel.data_analysis: (
        PaperClassLabel.model_development,
        PaperClassLabel.method_development,
        PaperClassLabel.theoretical_analysis,
        PaperClassLabel.numerical_analysis,
        PaperClassLabel.software_development,
    ),
    PaperClassLabel.numerical_analysis: (
        PaperClassLabel.method_development,
        PaperClassLabel.model_development,
        PaperClassLabel.software_development,
        PaperClassLabel.theoretical_analysis,
        PaperClassLabel.data_analysis,
    ),
    PaperClassLabel.theoretical_analysis: (
        PaperClassLabel.method_development,
        PaperClassLabel.model_development,
        PaperClassLabel.numerical_analysis,
        PaperClassLabel.software_development,
        PaperClassLabel.data_analysis,
    ),
    PaperClassLabel.review: (),
}

_METHOD_FACTS: tuple[tuple[str, InferenceMethod], ...] = (
    ("uses_mcmc", InferenceMethod.mcmc),
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
    "blackjax": "BlackJAX",
    "pyro": "Pyro",
    "pyroppl": "Pyro",
    "mcp": "mcp",
    "scikitlearn": "scikit-learn",
    "sklearn": "scikit-learn",
    "stan": "Stan",
    "pystan": "PyStan",
    "cmdstan": "CmdStan",
    "cmdstanr": "CmdStanR",
    "cmdstanpy": "CmdStanPy",
    "pymc": "PyMC",
    "pymc3": "PyMC",
    "pymc4": "PyMC",
    "bambi": "Bambi",
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
    "custompython": "Custom (Python)",
    "customr": "Custom (R)",
    "customjulia": "Custom (Julia)",
    "custommatlab": "Custom (MATLAB)",
}

_CUSTOM_LANGUAGE_KEYS: dict[str, str] = {
    "python": "Python",
    "r": "R",
    "rlanguage": "R",
    "julia": "Julia",
    "matlab": "MATLAB",
    "cpp": "C++",
    "cplusplus": "C++",
    "c": "C",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
}

_NON_INFERENCE_SOFTWARE_KEYS = {
    "r",
    "rproject",
    "rlanguage",
    "rstudio",
    "python",
    "julia",
    "matlab",
    "octave",
    "c",
    "cpp",
    "cplusplus",
    "csharp",
    "java",
    "javascript",
    "typescript",
    "bash",
    "shell",
    "unix",
    "linux",
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
    "bambi",
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
    "blackjax",
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
        r"metropolis|stan|pymc|bambi|brms|rstanarm|jags|bugs|turing|numpyro|blackjax|"
        r"hddm|hssm)\b",
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
    InferenceMethod.em: re.compile(
        r"\b(expectation[- ]maximization|em algorithm|em-style)\b",
        re.I,
    ),
    InferenceMethod.exact_analytic: re.compile(
        r"\b(conjugate|closed[- ]form|analytic posterior|exact posterior|analytic updating)\b",
        re.I,
    ),
}

_INN_CONTEXT_RE = re.compile(r"\b(invertible neural networks?|inns?)\b", re.I)
_POSTERIOR_CONTEXT_RE = re.compile(
    r"\bposterior (?:parameter )?distribution\b|\bparameter distribution\b|"
    r"\bdistribution over parameter space\b|\bfull distribution over parameter space\b",
    re.I,
)
_INVERSE_CONTEXT_RE = re.compile(r"\binverse problems?\b|\binverse pass\b", re.I)
_SIMULATOR_TRAINING_RE = re.compile(
    r"\b(train(?:ed|ing)?|learn(?:ed|ing)?)\b.{0,160}"
    r"\b(simulat\w*|synthetic|forward model|forward process|simulator)\b|"
    r"\b(simulat\w*|synthetic|forward model|forward process|simulator)\b.{0,160}"
    r"\b(train(?:ed|ing)?|learn(?:ed|ing)?)\b",
    re.I | re.S,
)
_NEURAL_INFERENCE_CONTEXT_RE = re.compile(
    r"\b(neural posterior|neural likelihood|neural ratio|neural score|normalizing flow|"
    r"amortized bayesian|likelihood-free inference)\b",
    re.I,
)

_LABEL_QUOTE_PATTERNS: dict[PaperClassLabel, re.Pattern[str]] = {
    PaperClassLabel.model_development: re.compile(
        r"\b(new|novel|propos|introduc|develop|extend).{0,80}\b(model|prior|likelihood|latent)\b"
        r"|\b(model|prior|likelihood|latent).{0,80}\b(new|novel|propos|introduc|develop|extend)\b",
        re.I,
    ),
    PaperClassLabel.method_development: re.compile(
        r"\b(new|novel|propos|introduc|develop|extend).{0,80}\b(method|algorithm|"
        r"procedure|workflow|diagnostic|framework|inference)\b"
        r"|\b(method|algorithm|procedure|workflow|diagnostic|framework|inference).{0,80}"
        r"\b(new|novel|propos|introduc|develop|extend)\b",
        re.I,
    ),
    PaperClassLabel.software_development: re.compile(
        r"\b(software|package|library|toolbox|tool|implementation|bayesflow)\b", re.I
    ),
    PaperClassLabel.data_analysis: re.compile(
        r"\b(real|empirical|observed|experimental|field|survey|clinical)\b.{0,80}"
        r"\b(data|dataset|application|case study)\b"
        r"|\b(data|dataset).{0,80}\b(real|empirical|observed|experimental|field|clinical)\b",
        re.I,
    ),
    PaperClassLabel.numerical_analysis: re.compile(
        r"\b(simulat\w*|simulation study|simulated data|synthetic|benchmark|numerical "
        r"experiment|toy example|toy model)\b",
        re.I,
    ),
    PaperClassLabel.theoretical_analysis: re.compile(
        r"\b(theorem|proposition|lemma|corollary|proof)\b", re.I
    ),
    PaperClassLabel.review: re.compile(
        r"\b(review|survey|tutorial|perspective|commentary)\b",
        re.I,
    ),
}

_THEORY_STATEMENT_RE = re.compile(r"\b(theorem|proposition|lemma|corollary)\b", re.I)
_THEORY_PROOF_RE = re.compile(r"\bproof\b", re.I)


def classify(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str | None = None,
) -> tuple[PaperClass, CostLedgerEntry]:
    """Classify the paper type from checklist facts."""
    model = model or llm_config.classify_model()
    context = assessment_context(parsed, max_chars=config.classify_context_chars())
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
    return f"PAPER CONTEXT (references excluded; supplements included when parsed):\n{context}"


def _paper_class_from_facts(
    facts: ClassifierFacts, context: str, evidence: list[Evidence]
) -> PaperClass:
    labels = _labels_from_facts(facts, context)
    # Review-only / theoretical-only papers run no analysis, so an empty software list is honest
    # there; every computational label keeps the never-empty rule (no Bayesian analysis without
    # software).
    non_computational = set(labels) <= {
        PaperClassLabel.review,
        PaperClassLabel.theoretical_analysis,
    }
    software = _canonical_software(facts.software, allow_empty=non_computational)
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


def _labels_from_facts(facts: ClassifierFacts, context: str) -> list[PaperClassLabel]:
    candidates: list[PaperClassLabel] = []
    for attr, label in _LABEL_FACTS:
        fact = getattr(facts.paper_type, attr)
        if _label_fact_survives(label, fact, context):
            candidates.append(label)
    labels = _prioritize_labels(candidates)
    if not labels:
        _log.warning(
            "classifier checklist returned no high-confidence paper-type facts; using data_analysis"
        )
        labels.append(PaperClassLabel.data_analysis)
    return labels


def _label_fact_survives(
    label: PaperClassLabel, fact: ClassifierFact, context: str
) -> bool:
    if not _yes(fact):
        return False
    if fact.confidence is not FactConfidence.high:
        _log.warning("low-confidence classifier paper-type fact dropped: %s", label.value)
        return False
    if not _quote_in_text(fact.evidence, context) and not _label_quote_hit(label, fact.evidence):
        _log.warning(
            "classifier paper-type evidence lacked excerpt match or label cue (dropped): %s",
            label.value,
        )
        return False
    if label is PaperClassLabel.theoretical_analysis and not _has_proof_structure(
        context, fact.evidence
    ):
        _log.warning(
            "theoretical_analysis without theorem/proposition plus proof structure (dropped)"
        )
        return False
    return True


def _prioritize_labels(candidates: list[PaperClassLabel]) -> list[PaperClassLabel]:
    candidates = _dedupe_ordered(candidates)
    substantive = [label for label in candidates if label is not PaperClassLabel.review]
    if substantive:
        candidates = substantive
    elif PaperClassLabel.review in candidates:
        return [PaperClassLabel.review]

    primary = _first_by_priority(candidates, _PRIMARY_LABEL_PRIORITY)
    if primary is None:
        return []
    labels = [primary]
    remaining = [label for label in candidates if label is not primary]
    for label in _SECONDARY_LABEL_PRIORITY[primary]:
        if label in remaining:
            labels.append(label)
            if len(labels) >= _MAX_PAPER_TYPE_LABELS:
                break
    dropped = [label.value for label in candidates if label not in labels]
    if dropped:
        _log.warning("extra classifier paper-type labels dropped by priority: %s", dropped)
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
    context_methods = _context_implied_methods(context)
    for attr, method in _METHOD_FACTS:
        fact = getattr(facts.methods, attr, None)
        if fact is not None and _method_fact_survives(
            method, fact, context, evidence, ontology_method_set
        ):
            _append_unique(methods, method)
    for method in ontology_methods:
        _append_unique(methods, method)
    for method in context_methods:
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
    if method in ontology_methods:
        return True
    if _fact_detector_refs(fact, evidence, method=method):
        return True
    if _method_quote_hit(method, fact.evidence):
        return True
    if fact.confidence is FactConfidence.high:
        _log.warning(
            "high-confidence classifier method fact without method cue (dropped): %s",
            method.value,
        )
        return False
    _log.warning(
        "low-confidence classifier method fact without deterministic support (dropped): %s",
        method.value,
    )
    return False


def _context_implied_methods(context: str) -> list[InferenceMethod]:
    methods: list[InferenceMethod] = []
    if _sbi_context_hit(context):
        _log.warning("context ontology implied SBI")
        methods.append(InferenceMethod.sbi)
    return methods


def _sbi_context_hit(context: str) -> bool:
    inn_posterior_inverse = (
        _INN_CONTEXT_RE.search(context) is not None
        and _POSTERIOR_CONTEXT_RE.search(context) is not None
        and _INVERSE_CONTEXT_RE.search(context) is not None
    )
    neural_sim_training = (
        _NEURAL_INFERENCE_CONTEXT_RE.search(context) is not None
        and _SIMULATOR_TRAINING_RE.search(context) is not None
    )
    return inn_posterior_inverse or neural_sim_training


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


def _canonical_software(raw: list[str], *, allow_empty: bool = False) -> list[str]:
    out: list[str] = []
    custom_languages: list[str] = []
    for item in raw:
        name = item.strip()
        if not name:
            continue
        key = _software_key(name)
        if key in _CUSTOM_LANGUAGE_KEYS:
            _append_unique(custom_languages, _CUSTOM_LANGUAGE_KEYS[key])
            _log.warning("programming language kept only as Custom qualifier: %s", name)
            continue
        if key in _NON_INFERENCE_SOFTWARE_KEYS:
            _log.warning("programming language/general environment dropped from software: %s", name)
            continue
        canonical = _SOFTWARE_CANONICAL.get(key, name)
        _append_unique_ci(out, canonical)
    out = _qualify_custom_software(out, custom_languages)
    if not out and allow_empty:
        return []  # review/theoretical-only papers run no analysis; never fabricate "Custom"
    return out or ["Custom"]


def _qualify_custom_software(software: list[str], languages: list[str]) -> list[str]:
    if not languages:
        return software
    qualified = f"Custom ({languages[0]})"
    out: list[str] = []
    replaced = False
    for item in software:
        if _software_key(item) == "custom":
            _append_unique_ci(out, qualified)
            replaced = True
        else:
            _append_unique_ci(out, item)
    if replaced:
        return out
    return software


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


def _label_quote_hit(label: PaperClassLabel, quote: str) -> bool:
    pattern = _LABEL_QUOTE_PATTERNS.get(label)
    return pattern.search(quote) is not None if pattern is not None else False


def _has_proof_structure(context: str, quote: str) -> bool:
    search_text = f"{quote}\n{context}"
    return _THEORY_STATEMENT_RE.search(search_text) is not None and (
        _THEORY_PROOF_RE.search(search_text) is not None
    )


def _first_by_priority(
    candidates: list[PaperClassLabel],
    priority: tuple[PaperClassLabel, ...],
) -> PaperClassLabel | None:
    candidate_set = set(candidates)
    for label in priority:
        if label in candidate_set:
            return label
    return None


def _software_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _quote_in_text(quote: str, text: str) -> bool:
    norm_quote = _norm_match_text(quote)
    norm_text = _norm_match_text(text)
    if not norm_quote:
        return False
    if norm_quote in norm_text:
        return True
    words = _content_words(norm_quote)
    if len(words) < 6:
        return False
    present = sum(1 for word in set(words) if word in norm_text)
    return present / len(set(words)) >= 0.8


def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _norm_match_text(text: str) -> str:
    text = text.lower()
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return _norm_space(text)


def _content_words(text: str) -> list[str]:
    stop = {
        "that",
        "this",
        "with",
        "from",
        "into",
        "have",
        "been",
        "were",
        "using",
        "used",
        "paper",
        "study",
        "method",
        "model",
        "data",
    }
    return [word for word in text.split() if len(word) >= 4 and word not in stop]


def _append_unique[T](items: list[T], item: T) -> None:
    if item not in items:
        items.append(item)


def _dedupe_ordered[T](items: list[T]) -> list[T]:
    out: list[T] = []
    for item in items:
        _append_unique(out, item)
    return out


def _append_unique_ci(items: list[str], item: str) -> None:
    key = item.lower()
    if all(existing.lower() != key for existing in items):
        items.append(item)
