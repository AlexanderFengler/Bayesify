"""Paper-type classifier — component d, stage 5 (runs only after a non-``no`` relevance gate).

Assigns every evidence-supported paper-class label. The label set drives rubric-step applicability
downstream (B1): data-analysis papers, method/model/software
development papers, numerical/theoretical analyses, and reviews can have different expectations.
This component only *produces* the class; the applicability rules live in
``rubric/steps.yaml`` and are applied by e-assess / f-score.

Like the relevance gate it runs on the cheap model (C6), fails closed on LLM error, and meters its
single call into the cost ledger (stage tag ``classify``). Its context is wider than the screen
gate's, so a secondary or late-section real-data analysis is not truncated away before the model
sees it.
"""

from __future__ import annotations

import logging
import re

from bayesify.core.context import build_user, excerpt_context, validate_evidence_refs
from bayesify.core.prompts import CLASSIFY_SYSTEM
from bayesify.core.schema import (
    CostLedgerEntry,
    Evidence,
    InferenceMethod,
    PaperClass,
    PaperClassLabel,
    ParsedDoc,
)
from bayesify.llm import LLMClient, call_with_policy, ledger_entry
from bayesify.llm import config as llm_config

_log = logging.getLogger("bayesify.core.classify")

# Wider than the screen gate's DEFAULT_MAX_CHARS (12k): the paper type / disciplines can depend on
# content in a later section (e.g. a secondary real-data analysis) that a 12k prefix cut would drop.
CLASSIFY_MAX_CHARS = 30_000

# Literal detector IDs are only one corroboration path. The classifier can correctly infer modern
# method families from surrounding prose (e.g. simulations train neural networks => SBI), while a
# detector hit can be a background/comparison mention. Grounding therefore uses detector support
# plus own-use context from the excerpts.
_METHOD_DETECTOR: dict[InferenceMethod, str] = {
    InferenceMethod.mcmc: "method.mcmc",
    InferenceMethod.hmc_nuts: "method.mcmc",  # NUTS/HMC live in the method.mcmc pattern
    InferenceMethod.variational: "method.variational",
    InferenceMethod.sbi: "method.sbi",
    InferenceMethod.smc: "method.smc",
    InferenceMethod.abc: "method.abc",
    InferenceMethod.laplace_inla: "method.laplace_inla",
    InferenceMethod.exact_analytic: "method.analytic",
}

_SOFTWARE_METHODS: dict[str, tuple[InferenceMethod, ...]] = {
    "software.sbi": (InferenceMethod.sbi,),
    "software.bayesflow": (InferenceMethod.sbi,),
    "software.neuralestimators": (InferenceMethod.sbi,),
    "software.pyabc": (InferenceMethod.abc,),
    "software.stan": (InferenceMethod.mcmc,),
    "software.pymc": (InferenceMethod.mcmc,),
}
_MCMC_FAMILY = frozenset({InferenceMethod.mcmc, InferenceMethod.hmc_nuts})

_METHOD_ALIASES: dict[InferenceMethod, re.Pattern[str]] = {
    InferenceMethod.mcmc: re.compile(
        r"\b(?:mcmc|markov[- ]chain monte carlo|metropolis(?:[- ]hastings)?|"
        r"gibbs sampl\w*|nuts|hmc|hamiltonian monte carlo)\b",
        re.IGNORECASE,
    ),
    InferenceMethod.hmc_nuts: re.compile(
        r"\b(?:nuts|hmc|hamiltonian monte carlo)\b", re.IGNORECASE
    ),
    InferenceMethod.variational: re.compile(
        r"\b(?:variational inference|variational bayes|advi|elbo)\b",
        re.IGNORECASE,
    ),
    InferenceMethod.sbi: re.compile(
        r"\b(?:sbi|simulation[- ]based inference|amorti[sz]ed bayesian inference|"
        r"neural (?:posterior|likelihood|ratio) estimation|amortized inference)\b",
        re.IGNORECASE,
    ),
    InferenceMethod.smc: re.compile(
        r"\b(?:smc|sequential monte carlo|particle filter(?:s|ing)?)\b",
        re.IGNORECASE,
    ),
    InferenceMethod.abc: re.compile(
        r"\b(?:abc(?:[- ]smc)?|approximate bayesian computation)\b",
        re.IGNORECASE,
    ),
    InferenceMethod.laplace_inla: re.compile(
        r"\b(?:inla|integrated nested laplace|laplace approximation)\b",
        re.IGNORECASE,
    ),
    InferenceMethod.exact_analytic: re.compile(
        r"\b(?:conjugate prior|analytic(?:al)? posterior|closed[- ]form posterior)\b",
        re.IGNORECASE,
    ),
}

_SOFTWARE_ALIASES: dict[str, re.Pattern[str]] = {
    "software.brms": re.compile(r"\bbrms\b", re.IGNORECASE),
    "software.rstanarm": re.compile(r"\brstanarm\b", re.IGNORECASE),
    "software.numpyro": re.compile(r"\bNumPyro\b", re.IGNORECASE),
    "software.tfp": re.compile(r"\b(?:tensorflow probability|TFP)\b", re.IGNORECASE),
    "software.jags": re.compile(r"\bJAGS\b"),
    "software.bugs": re.compile(r"\b(?:Win|Open)?BUGS\b"),
    "software.hddm": re.compile(r"\bHDDM\b", re.IGNORECASE),
    "software.hssm": re.compile(r"\bHSSM\b", re.IGNORECASE),
    "software.turing": re.compile(r"\bTuring\.jl\b", re.IGNORECASE),
    "software.sbi": re.compile(
        r"\b(?:sbi\s+(?:package|toolbox|library|software|toolkit)|"
        r"(?:package|toolbox|library|software|toolkit)\s+sbi|"
        r"from\s+sbi\s+import|import\s+sbi\b|sbi\.inference)\b",
        re.IGNORECASE,
    ),
    "software.bayesflow": re.compile(r"\bBayesFlow\b", re.IGNORECASE),
    "software.neuralestimators": re.compile(r"\bNeuralEstimators(?:\.jl)?\b", re.IGNORECASE),
    "software.pyabc": re.compile(r"\bpyABC\b", re.IGNORECASE),
    "software.stan": re.compile(r"\bStan\b"),
    "software.pymc": re.compile(r"\bPyMC\d*\b", re.IGNORECASE),
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_CLAUSE_SPLIT = re.compile(
    r"\s*(?:;|\b(?:but|whereas|although|though)\b|"
    r",\s+(?=(?:we|our|this|for comparison|the\s+(?:baseline|benchmark|comparison|"
    r"result|results)|table|figure)\b))\s*",
    re.IGNORECASE,
)
_BASELINE_OR_COMPARISON = re.compile(
    r"\b(?:baseline(?:s)?|competing|alternative|compared? (?:with|against|to)|"
    r"comparison(?:s)? (?:with|against|to)|for comparison|versus|vs\.?|"
    r"benchmark(?:ed|s|ing)?(?: against)?)\b",
    re.IGNORECASE,
)
_BACKGROUND = re.compile(
    r"\b(?:related work|prior work|previous(?:ly)?|existing|standard solution|review|"
    r"such as|including|methods described above|have been applied|closely related|"
    r"often|commonly|typically|generally|usually|widely)\b",
    re.IGNORECASE,
)
_EXPLICIT_OWN_USE = re.compile(
    r"\b(?:we|our|this (?:paper|work|study|method|approach)|in this paper)\b"
    r".{0,140}\b(?:use|uses|used|employ|employed|fit|fitted|estimate|estimated|"
    r"infer|inference|sample|sampling|train|trained|implement|implemented|run|ran|"
    r"apply|applied|propose|proposed|introduce|introduced|develop|developed|obtain|"
    r"obtained|compute|computed|compare|compared|benchmark|benchmarked|evaluate|evaluated|"
    r"test|tested|report|reported)\b",
    re.IGNORECASE,
)
_PASSIVE_OWN_USE = re.compile(
    r"\b(?:inference|posterior(?:s)?|parameters?|estimation|sampling|model|method)\b"
    r".{0,80}\b(?:used|uses|via|with|by|obtained|estimated|computed|sampled|trained|"
    r"implemented|run|fit|fitted|performed|using)\b",
    re.IGNORECASE,
)
_GENERAL_USE = re.compile(
    r"\b(?:used|uses|employed|fit|fitted|estimated|obtained|computed|sampled|trained|"
    r"implemented|ran|run|applied|performed|derive|derived|using)\b",
    re.IGNORECASE,
)
_PAPER_EVAL_ACTOR = re.compile(
    r"\b(?:we|our|this (?:paper|work|study|method|approach|experiment|experiments|"
    r"simulation study|benchmark|benchmarks|comparison|comparisons)|in this paper|"
    r"for comparison)\b",
    re.IGNORECASE,
)
_EVAL_ACTION = re.compile(
    r"\b(?:compare|compared|compares|comparing|benchmark|benchmarked|benchmarks|"
    r"benchmarking|evaluate|evaluated|evaluates|evaluating|test|tested|tests|testing|"
    r"report|reported|reports|reporting|use|used|uses|using|employ|employed|employs|"
    r"implement|implemented|implements|run|ran|runs|apply|applied|applies|obtain|"
    r"obtained|obtains|compute|computed|computes)\b",
    re.IGNORECASE,
)
_RESULT_CONTEXT = re.compile(
    r"\b(?:result|results|table|figure|benchmark|benchmarks|experiment|experiments|"
    r"simulation study|performance|accuracy|coverage)\b",
    re.IGNORECASE,
)
_HYPOTHETICAL_USE = re.compile(
    r"\b(?:can|could|may|might|would|should)\s+be\s+"
    r"(?:used|applied|employed|implemented|run|evaluated|compared)\b",
    re.IGNORECASE,
)
_MCMC_CONFIG_CONTEXT = re.compile(
    r"\b(?:chains|iterations?|draws?|samples?|warm[- ]?up|burn[- ]?in|"
    r"r[- ]?hat|ess|divergences?)\b",
    re.IGNORECASE,
)

_SBI_GLOBAL = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bamorti[sz]ed bayesian inference\b",
        r"\bneural (?:posterior|likelihood|ratio) estimation\b",
        r"\bnormalizing[- ]flow posterior\b",
        r"\binvertible neural network(?:s)?.{0,120}\bposterior(?:s)?\b",
    )
)
_SIMULATION = re.compile(r"\bsimulat(?:e|es|ed|ing|ion|ions|or|ors)?\b", re.IGNORECASE)
_NEURAL = re.compile(
    r"\b(?:neural network(?:s)?|network(?:s)?|normalizing flow(?:s)?|invertible|"
    r"density estimator(?:s)?|flow[- ]based)\b|\bINNs?\b",
    re.IGNORECASE,
)
_POSTERIOR_OR_INFERENCE = re.compile(
    r"\b(?:posterior(?:s)?|bayesian inference|likelihood[- ]free|inverse model)\b",
    re.IGNORECASE,
)
_TRAIN_OR_AMORTIZE = re.compile(
    r"\b(?:train(?:ed|ing)?|learn(?:ed|ing)?|amorti[sz]ed|pre[- ]trained)\b",
    re.IGNORECASE,
)
_OBSERVED_DATA = re.compile(r"\b(?:observed|real)\s+data(?:set)?s?\b", re.IGNORECASE)
_FORWARD_OR_INVERSE = re.compile(
    r"\b(?:forward (?:process|model|mapping|operator|simulator)|inverse problem(?:s)?|"
    r"inverse pass|parameter[- ]to[- ]measurement|measurement[- ]space|simulator|"
    r"generative model)\b",
    re.IGNORECASE,
)
_PARAMETER_DISTRIBUTION = re.compile(
    r"\b(?:posterior parameter distribution|posterior distribution over parameters?|"
    r"distribution over parameter space|full distribution over parameter space|"
    r"parameter distribution|posterior samples?)\b",
    re.IGNORECASE,
)
_LATENT_OR_STOCHASTIC_INVERSE = re.compile(
    r"\b(?:latent (?:output )?variables?|sampled latent variables?|samples? (?:from|of) "
    r"(?:the )?latent|multi[- ]modalit(?:y|ies)|parameter correlations?)\b",
    re.IGNORECASE,
)
_SBI_OWN_ACTION = re.compile(
    r"\b(?:we|our|this (?:paper|work|study|method|approach)|in this paper)\b.{0,180}"
    r"\b(?:propose|present|introduce|develop|argue|show|demonstrate|verify|study|"
    r"analy[sz]e|learn|train|use)\b",
    re.IGNORECASE,
)
_ABC_MATCHING = re.compile(
    r"\b(?:threshold|tolerance|distance|similar(?:ity)?|reject(?:ed|ion)?|"
    r"retain(?:ed)?|accept(?:ed|ance)?|weight(?:ed)?)\b",
    re.IGNORECASE,
)
_METHOD_DEV = re.compile(
    r"\b(?:we|our|this (?:paper|work|study))\b.{0,120}"
    r"\b(?:propose|introduce|develop|present|derive)\b.{0,120}"
    r"\b(?:method|approach|procedure|algorithm|framework|inference)\b",
    re.IGNORECASE,
)
_SOFTWARE_DEV = re.compile(
    r"\b(?:we|our|this (?:paper|work|study))\b.{0,160}"
    r"\b(?:release|introduce|develop|present|provide)\b.{0,160}"
    r"\b(?:software|package|library|toolbox|toolkit|implementation|codebase)\b",
    re.IGNORECASE,
)


def classify(
    parsed: ParsedDoc,
    evidence: list[Evidence],
    *,
    client: LLMClient,
    model: str | None = None,
) -> tuple[PaperClass, CostLedgerEntry]:
    """Classify the paper type. Returns the ``PaperClass`` and its cost entry; raises ``LLMError``
    (fail closed) if the cheap-model call cannot complete."""
    model = model or llm_config.classify_model()
    user = build_user(parsed, evidence, max_chars=CLASSIFY_MAX_CHARS)
    response = call_with_policy(
        client, model=model, system=CLASSIFY_SYSTEM, user=user, schema=PaperClass, max_tokens=800
    )
    paper_class = response.parsed
    # A3: reject a hallucinated citation before it becomes a dangling ref. Guarded on `evidence`
    # because the only zero-evidence caller is the forced rerun escape hatch (which grades without
    # grounding by design); the normal relevance gate only reaches classify when evidence exists.
    if evidence:
        validate_evidence_refs(paper_class.evidence_refs, evidence, where="paper_class")
        _ground_methods(paper_class, evidence, parsed)
        _ground_labels(paper_class, parsed)
    return paper_class, ledger_entry("classify", response)


def _ground_methods(paper_class: PaperClass, evidence: list[Evidence], parsed: ParsedDoc) -> None:
    """Keep method chips that are corroborated by own-use context.

    A detector hit is useful but context-free: "MCMC" in a related-work comparison is still a hit.
    Conversely, modern SBI papers often say "amortized Bayesian inference" or describe simulations
    training neural networks without the literal token "SBI". This verifier uses both sources.
    """
    fired = {e.detector_id for e in evidence}
    text = excerpt_context(parsed, max_chars=CLASSIFY_MAX_CHARS)
    software_used = _own_use_software_ids(fired, text, evidence, parsed)
    paper_class.software_used = software_used
    implied = _implied_methods(software_used, text)
    kept: list[InferenceMethod] = []
    dropped: list[InferenceMethod] = []
    for m in paper_class.methods_used:
        contexts = _method_contexts(m, text, evidence, parsed)
        if _method_is_corroborated(m, text, contexts) or _is_software_implied(m, implied):
            kept.append(m)
        else:
            dropped.append(m)
    if dropped:
        _log.warning(
            "classifier named methods without own-use corroboration (dropped): %s",
            [m.value for m in dropped],
        )
    paper_class.methods_used = _with_implied_methods(kept, implied)


def _ground_labels(paper_class: PaperClass, parsed: ParsedDoc) -> None:
    text = excerpt_context(parsed, max_chars=CLASSIFY_MAX_CHARS)
    labels = list(paper_class.labels)
    if PaperClassLabel.software_development in labels and not _software_development_supported(text):
        labels = [label for label in labels if label is not PaperClassLabel.software_development]
        if _method_development_supported(text) and PaperClassLabel.method_development not in labels:
            labels.insert(0, PaperClassLabel.method_development)
        elif not labels:
            labels = [PaperClassLabel.method_development]
        _log.warning(
            "classifier named software_development without software-contribution support "
            "(corrected)"
        )
    paper_class.labels = _dedupe_labels(labels)


def _dedupe_labels(labels: list[PaperClassLabel]) -> list[PaperClassLabel]:
    seen: set[PaperClassLabel] = set()
    out: list[PaperClassLabel] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def _method_development_supported(text: str) -> bool:
    return bool(_METHOD_DEV.search(text)) or _semantic_sbi(text)


def _software_development_supported(text: str) -> bool:
    return bool(_SOFTWARE_DEV.search(text))


def _implied_methods(software_used: list[str], text: str) -> list[InferenceMethod]:
    implied = _software_implied_methods(software_used)
    if _semantic_sbi(text):
        implied.append(InferenceMethod.sbi)
    if _semantic_abc(text):
        implied.append(InferenceMethod.abc)
    return implied


def _software_implied_methods(software_used: list[str]) -> list[InferenceMethod]:
    implied: list[InferenceMethod] = []
    for software_id in software_used:
        implied.extend(_SOFTWARE_METHODS.get(software_id, ()))
    return implied


def _own_use_software_ids(
    fired: set[str], text: str, evidence: list[Evidence], parsed: ParsedDoc
) -> list[str]:
    out: list[str] = []
    for software_id in _SOFTWARE_ALIASES:
        if software_id in fired and _software_is_used(software_id, text, evidence, parsed):
            out.append(software_id)
    return out


def _software_is_used(
    software_id: str, text: str, evidence: list[Evidence], parsed: ParsedDoc
) -> bool:
    return any(
        _context_supports_software_use(c)
        for c in _software_contexts(software_id, text, evidence, parsed)
    )


def _software_contexts(
    software_id: str, text: str, evidence: list[Evidence], parsed: ParsedDoc
) -> list[str]:
    alias = _SOFTWARE_ALIASES.get(software_id)
    if alias is None:
        return []
    contexts = _alias_contexts(alias, text)
    contexts.extend(_evidence_alias_contexts(alias, software_id, evidence, parsed))
    return _dedupe(contexts)


def _context_supports_software_use(context: str) -> bool:
    return _context_supports_reported_use(context)


def _is_software_implied(method: InferenceMethod, implied: list[InferenceMethod]) -> bool:
    if method in implied:
        return True
    return method is InferenceMethod.hmc_nuts and InferenceMethod.mcmc in implied


def _with_implied_methods(
    methods: list[InferenceMethod], implied: list[InferenceMethod]
) -> list[InferenceMethod]:
    out = list(methods)
    for method in implied:
        if method is InferenceMethod.mcmc and any(m in _MCMC_FAMILY for m in out):
            continue
        if method not in out:
            out.append(method)
    return out


def _method_is_corroborated(
    method: InferenceMethod, text: str, contexts: list[str]
) -> bool:
    if method is InferenceMethod.sbi and _semantic_sbi(text):
        return True
    if method is InferenceMethod.abc and _semantic_abc(text):
        return True

    return any(_context_supports_method_use(method, c) for c in contexts)


def _method_contexts(
    method: InferenceMethod, text: str, evidence: list[Evidence], parsed: ParsedDoc
) -> list[str]:
    alias = _METHOD_ALIASES.get(method)
    if alias is None:
        return []
    contexts = _alias_contexts(alias, text)
    detector_id = _METHOD_DETECTOR.get(method)
    if detector_id is not None:
        contexts.extend(_evidence_alias_contexts(alias, detector_id, evidence, parsed))
    return _dedupe(contexts)


def _sentences(text: str) -> list[str]:
    return [" ".join(s.split()) for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _sentence_windows(sentences: list[str], *, size: int) -> list[str]:
    return [
        " ".join(sentences[i : i + size])
        for i in range(len(sentences))
        if sentences[i : i + size]
    ]


def _alias_contexts(alias: re.Pattern[str], text: str) -> list[str]:
    contexts: list[str] = []
    for sentence in _sentences(text):
        if not alias.search(sentence):
            continue
        clauses = [" ".join(c.strip(" ,").split()) for c in _CLAUSE_SPLIT.split(sentence)]
        clauses = [c for c in clauses if c]
        contexts.extend(c for c in clauses if alias.search(c))
    return contexts


def _evidence_alias_contexts(
    alias: re.Pattern[str], detector_id: str, evidence: list[Evidence], parsed: ParsedDoc
) -> list[str]:
    by_id = {section.id: section for section in parsed.sections}
    contexts: list[str] = []
    for e in evidence:
        if e.detector_id != detector_id or not alias.search(e.span.quote):
            continue
        section = by_id.get(e.span.section_id)
        source = e.span.quote
        if section is not None:
            source = _quote_neighborhood(section.text or "", e.span.quote)
            if section.title:
                source = f"{section.title}. {source}"
        contexts.extend(_alias_contexts(alias, source))
    return contexts


def _quote_neighborhood(text: str, quote: str, *, pad: int = 350) -> str:
    if not text or not quote:
        return quote
    start = text.find(quote)
    if start < 0:
        return quote
    end = start + len(quote)
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return text[lo:hi]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _context_supports_method_use(method: InferenceMethod, context: str) -> bool:
    if _context_supports_reported_use(context):
        return True
    if (
        method in _MCMC_FAMILY
        and _MCMC_CONFIG_CONTEXT.search(context)
        and not _background_only_context(context)
    ):
        return True
    return False


def _sentence_supports_own_use(sentence: str) -> bool:
    return _context_supports_reported_use(sentence)


def _context_supports_reported_use(context: str) -> bool:
    if _hypothetical_or_background_only(context):
        return False
    if _EXPLICIT_OWN_USE.search(context) or _PASSIVE_OWN_USE.search(context):
        return True
    if _baseline_was_evaluated(context):
        return True
    return bool(_GENERAL_USE.search(context) and not _background_only_context(context))


def _hypothetical_or_background_only(context: str) -> bool:
    if _HYPOTHETICAL_USE.search(context) and not _PAPER_EVAL_ACTOR.search(context):
        return True
    return _background_only_context(context)


def _background_only_context(context: str) -> bool:
    return bool(_BACKGROUND.search(context) and not _paper_evaluation_context(context))


def _paper_evaluation_context(context: str) -> bool:
    return bool(
        _PAPER_EVAL_ACTOR.search(context)
        and _EVAL_ACTION.search(context)
        and (_BASELINE_OR_COMPARISON.search(context) or _RESULT_CONTEXT.search(context))
    )


def _baseline_was_evaluated(context: str) -> bool:
    return bool(
        _BASELINE_OR_COMPARISON.search(context)
        and _EVAL_ACTION.search(context)
        and (_PAPER_EVAL_ACTOR.search(context) or _RESULT_CONTEXT.search(context))
    )


def _semantic_sbi(text: str) -> bool:
    if any(p.search(text) for p in _SBI_GLOBAL):
        return True
    usable_sentences = [s for s in _sentences(text) if not _BASELINE_OR_COMPARISON.search(s)]
    for sentence in usable_sentences:
        if _BASELINE_OR_COMPARISON.search(sentence):
            continue
        if (
            _SIMULATION.search(sentence)
            and _NEURAL.search(sentence)
            and _POSTERIOR_OR_INFERENCE.search(sentence)
            and _TRAIN_OR_AMORTIZE.search(sentence)
        ):
            return True
    for context in _sentence_windows(usable_sentences, size=3):
        if _background_only_context(context) and not _SBI_OWN_ACTION.search(context):
            continue
        if (
            _NEURAL.search(context)
            and _FORWARD_OR_INVERSE.search(context)
            and _PARAMETER_DISTRIBUTION.search(context)
            and (
                _TRAIN_OR_AMORTIZE.search(context)
                or _LATENT_OR_STOCHASTIC_INVERSE.search(context)
                or _SBI_OWN_ACTION.search(context)
            )
        ):
            return True
    return False


def _semantic_abc(text: str) -> bool:
    for sentence in _sentences(text):
        if not _sentence_supports_own_use(sentence):
            continue
        if (
            _SIMULATION.search(sentence)
            and _OBSERVED_DATA.search(sentence)
            and _ABC_MATCHING.search(sentence)
        ):
            return True
    return False
