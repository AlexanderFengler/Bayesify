"""The deterministic detector catalog (component c, gate C1).

Each detector is a high-precision regex emitting structured ``Evidence``. **Precision-first**
(c-detectors.md): a missed mention is recoverable — the LLM in e-assess reads the full sections and
can still find it — but a *false* hit poisons grounding, because e-assess trusts detector evidence
and the report cites it as fact. So acronyms that collide with English words (``Stan`` vs standard,
``ESS`` vs assess, ``NUTS`` vs nuts, ``BUGS`` vs debugs) are matched **case-sensitively**, while the
spelled-out phrases beside them stay case-insensitive via inline ``(?i:...)`` groups. Word boundaries
guard everything (``\\bR-hat\\b`` must not fire inside "rhattan").

Numeric diagnostics carry an ``extract`` that parses the value into ``Evidence.value`` and, when the
text mentions the metric with no number, falls back to ``mention_kind`` (a ``diagnostic_mention``
rather than a misleading ``count: 0``). Bumping any ``version`` here changes ``catalog_fingerprint``,
which feeds ``engine_version`` (gate G1) and the detect sub-cache key (gate G2). No detector ships
without a ``CATALOG.md`` entry.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from bayesify.core.schema import EvidenceKind

_V = "0.1.0"  # catalog version stamp for all detectors at this revision

# Family render/identity order (used by the inventory and the fingerprint).
FAMILIES: tuple[str, ...] = ("software", "method", "diagnostic", "workflow", "sampler", "open_science")


@dataclass(frozen=True)
class Detector:
    id: str
    kind: EvidenceKind
    family: str
    pattern: re.Pattern
    # Numeric diagnostics: parse the value; return None when the metric is mentioned without a number.
    extract: Callable[[re.Match], dict | None] | None = None
    # Kind to emit when `extract` returns None (e.g. diagnostic_value -> diagnostic_mention).
    mention_kind: EvidenceKind | None = None
    version: str = _V


# --- value extractors -----------------------------------------------------------------------------


def _num(s: str) -> float:
    return float(s.replace(",", ""))


_NUM = r"\d+(?:\.\d+)?"
_INT = r"[\d,]+"


def _val(numre: str) -> str:
    """An optional value suffix shared by the numeric diagnostics. The number must be introduced by a
    comparator (``< > = ≤ ≥``), a connector word (``was``/``of``/``is`` …), or a colon — optionally a
    connector *then* a comparator ("values were < 0.7"). A bare adjacent number is never extracted, so
    "ESS for 4 parameters" stays a mention (precision-first); "R-hat < 1.01" and "ESS was 1,500" do."""
    conn = r"(?i:was|were|of|is|are|about|approximately)"
    intro = r"(?:" + conn + r"\s+)?(?P<op>[<>=≤≥]{1,2})|" + conn + r"|:"
    return r"(?:\s*(?:" + intro + r")\s*(?P<num>" + numre + r"))?"


def _threshold(metric: str) -> Callable[[re.Match], dict | None]:
    """Diagnostics stated as ``metric <op> number`` (R-hat, ESS, Pareto-k). None → mention only."""

    def f(m: re.Match) -> dict | None:
        if m.groupdict().get("num"):
            return {"metric": metric, "op": (m.group("op") or "=").strip(), "value": _num(m.group("num"))}
        return None

    return f


def _divergences(m: re.Match) -> dict | None:
    raw = (m.group("count") or "").lower()
    if not raw:  # "we monitored divergences" — a mention, not a reported count of zero
        return None
    count = 0 if raw in ("no", "zero") else int(raw.replace(",", ""))
    return {"metric": "divergences", "count": count}


def _count(metric: str) -> Callable[[re.Match], dict]:
    def f(m: re.Match) -> dict:
        return {"metric": metric, "count": int(_num(m.group("num")))}

    return f


def _c(pattern: str, *, ci: bool = True) -> re.Pattern:
    """Compile a pattern. ``ci`` toggles the *default* case-sensitivity; patterns mixing an acronym
    with a phrase set ``ci=False`` and wrap the phrase in an inline ``(?i:...)`` group."""
    return re.compile(pattern, re.IGNORECASE if ci else 0)


# --- the catalog ----------------------------------------------------------------------------------

SW = EvidenceKind.software_mention
ME = EvidenceKind.method_mention
DV = EvidenceKind.diagnostic_value
DM = EvidenceKind.diagnostic_mention
WF = EvidenceKind.workflow_signal
SC = EvidenceKind.sampler_config
OS = EvidenceKind.open_science

CATALOG: list[Detector] = [
    # --- software / tooling (case-sensitive where the token is an English word) ---
    Detector("software.stan", SW, "software", _c(r"\bStan\b", ci=False)),
    Detector("software.brms", SW, "software", _c(r"\bbrms\b")),
    Detector("software.rstanarm", SW, "software", _c(r"\brstanarm\b")),
    Detector("software.pymc", SW, "software", _c(r"\bPyMC\d*\b")),
    Detector("software.numpyro", SW, "software", _c(r"\bNumPyro\b")),
    Detector("software.tfp", SW, "software", _c(r"(?i:tensorflow probability)|\bTFP\b", ci=False)),
    Detector("software.jags", SW, "software", _c(r"\bJAGS\b", ci=False)),
    Detector("software.bugs", SW, "software", _c(r"\b(?:Win|Open)?BUGS\b", ci=False)),
    Detector("software.hddm", SW, "software", _c(r"\bHDDM\b")),
    Detector("software.hssm", SW, "software", _c(r"\bHSSM\b")),
    Detector("software.turing", SW, "software", _c(r"\bTuring\.jl\b")),
    Detector("software.bayesflow", SW, "software", _c(r"\bBayesFlow\b")),
    # --- Bayesian method / inference mentions (the d-screen relevance floor keys on these) ---
    Detector("method.prior", ME, "method",
             _c(r"\bprior(?:s)?\s+(?:distribution|on|over|for)\b"
                r"|\b(?:weakly[- ]|non[- ]|un)?informative prior")),
    Detector("method.posterior", ME, "method",
             _c(r"\bposterior\s+(?:distribution|mean|median|sample|draw|predictive|probabilit\w+"
                r"|densit\w+|inference|estimate)|\bthe posterior\b")),
    Detector("method.credible_interval", ME, "method",
             _c(r"(?i:credible intervals?)|(?i:highest[- ](?:posterior )?density)"
                r"|\bHPDI?\b|\bHDIs?\b", ci=False)),
    Detector("method.bayes_factor", ME, "method", _c(r"\bBayes factors?\b")),
    Detector("method.mcmc", ME, "method",
             _c(r"\bMCMC\b|(?i:markov chain monte carlo)|\bNUTS\b"
                r"|(?i:hamiltonian monte carlo)|\bHMC\b|(?i:gibbs sampl)", ci=False)),
    Detector("method.variational", ME, "method",
             _c(r"(?i:variational (?:inference|bayes))|\bADVI\b|\bELBO\b", ci=False)),
    Detector("method.sbi", ME, "method",
             _c(r"(?i:simulation[- ]based inference)|\bSBI\b", ci=False)),
    Detector("method.analytic", ME, "method",
             _c(r"(?i:conjugate prior|analytic(?:al)? posterior|closed[- ]form posterior)", ci=False)),
    # --- diagnostics with numeric extraction (value -> diagnostic_value, else diagnostic_mention) ---
    Detector("diag.rhat", DV, "diagnostic",
             _c(r"(?:\bR[-\s]?hat\b|R̂|\bRhat\b)" + _val(_NUM)),
             extract=_threshold("rhat"), mention_kind=DM),
    Detector("diag.ess", DV, "diagnostic",
             _c(r"(?:(?i:effective sample sizes?)|(?i:bulk[- ]ess|tail[- ]ess)|\bESS\b|\bn_?eff\b)"
                + _val(_INT), ci=False),
             extract=_threshold("ess"), mention_kind=DM),
    Detector("diag.divergences", DV, "diagnostic",
             _c(r"(?:(?P<count>no|zero|\d[\d,]*)\s+)?diverg(?:ent transitions?|ences?)"),
             extract=_divergences, mention_kind=DM),
    Detector("diag.pareto_k", DV, "diagnostic",
             _c(r"Pareto[- ]?k(?:[- ]?(?:hat|values?))?" + _val(_NUM)),
             extract=_threshold("pareto_k"), mention_kind=DM),
    # --- diagnostics (mention only) ---
    Detector("diag.treedepth", DM, "diagnostic", _c(r"\b(?:max(?:imum)?[- ]?)?tree[- ]?depth\b")),
    Detector("diag.bfmi", DM, "diagnostic",
             _c(r"\bE?-?BFMI\b|\bE-?FMI\b|(?i:energy fraction of missing information)", ci=False)),
    Detector("diag.loo_waic", DM, "diagnostic",
             _c(r"\bPSIS[- ]?LOO\b|\bLOO[- ]?CV\b|\bLOO\b|\bWAIC\b|\belpd\b"
                r"|(?i:leave[- ]one[- ]out)", ci=False)),
    Detector("diag.mcse", DM, "diagnostic",
             _c(r"\bMCSE\b|(?i:monte carlo standard error)", ci=False)),
    Detector("diag.trace_plot", DM, "diagnostic", _c(r"\btrace[- ]?plots?\b")),
    Detector("diag.rank_plot", DM, "diagnostic", _c(r"\brank[- ]?plots?\b|\brank histograms?\b")),
    # --- workflow signals ---
    Detector("workflow.prior_predictive", WF, "workflow", _c(r"\bprior predictive\b")),
    Detector("workflow.posterior_predictive", WF, "workflow",
             _c(r"(?i:posterior predictive)|\bPPCs?\b", ci=False)),
    Detector("workflow.sensitivity", WF, "workflow",
             _c(r"\bsensitivity analys[ie]s\b|\bprior sensitivity\b"
                r"|\brobustness (?:check|analys[ie]s)\b")),
    Detector("workflow.sbc", WF, "workflow",
             _c(r"(?i:simulation[- ]based calibration)|\bSBC\b", ci=False)),
    Detector("workflow.recovery", WF, "workflow", _c(r"\bparameter recovery\b")),
    # --- sampler configuration (counts; the number is mandatory in the pattern) ---
    Detector("sampler.chains", SC, "sampler", _c(r"(?P<num>\d+)\s+chains?\b"), extract=_count("chains")),
    Detector("sampler.iterations", SC, "sampler",
             _c(r"(?P<num>[\d,]{2,})\s+(?:iterations?|samples?|draws?)\b"), extract=_count("iterations")),
    Detector("sampler.warmup", SC, "sampler",
             _c(r"(?P<num>[\d,]{2,})\s+(?:warm-?up|burn-?in)\b"), extract=_count("warmup")),
    Detector("sampler.seed", SC, "sampler", _c(r"\b(?:random )?seeds?\b")),
    # --- open science ---
    Detector("open.data", OS, "open_science",
             _c(r"\bdata (?:are|is)\s+availab\w+|\bdata availability\b")),
    Detector("open.code", OS, "open_science",
             _c(r"\bcode (?:is|are)\s+availab\w+|\bcode availability\b|\banalysis (?:code|scripts)\b")),
    Detector("open.osf", OS, "open_science",
             _c(r"(?i:osf\.io)|\bOSF\b|(?i:open science framework)", ci=False)),
    Detector("open.github", OS, "open_science", _c(r"\bgithub\.com\b")),
    Detector("open.zenodo", OS, "open_science", _c(r"\bzenodo\b")),
]

DETECTOR_FAMILY: dict[str, str] = {d.id: d.family for d in CATALOG}
CATALOG_VERSION = _V


def detector_ids(family: str) -> list[str]:
    """All detector ids in a family, in catalog order (used for the 'not detected' inventory)."""
    return [d.id for d in CATALOG if d.family == family]


def catalog_fingerprint() -> str:
    """A deterministic string identifying the whole catalog — id, version, pattern, and flags per
    detector. Pass to ``versioning.compute_engine_version(detector_catalog=...)`` (gate G1): any
    pattern, version, or flag change flows into ``engine_version`` and invalidates the result cache.
    """
    return "\n".join(
        f"{d.id}|{d.version}|{d.pattern.pattern}|{d.pattern.flags}" for d in CATALOG
    )
