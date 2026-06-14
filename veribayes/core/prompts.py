"""The versioned LLM prompt set — the single registry of prompt templates.

``prompt_set_fingerprint()`` is hashed into ``engine_version`` (gate G1), so editing any prompt here
bumps the engine version and invalidates the result cache — a prompt change makes a different
instrument, exactly like a model or detector change. screen/classify/assess import their templates
from here; nothing constructs prompt strings inline.
"""

from __future__ import annotations

# --- screen (relevance gate, stage 4) -------------------------------------------------------------

SCREEN_SYSTEM = """You are the relevance gate for VeriBayes, a tool that assesses how well a paper \
follows the Bayesian statistical workflow.

Your only job: decide whether this paper actually USES Bayesian statistical methodology that should \
be graded against a Bayesian-workflow rubric — not whether it is good. Output one label:

- "yes": the paper fits Bayesian model(s) to data, or develops Bayesian methods/priors/algorithms — \
Bayesian inference is central.
- "partial": Bayesian content is present but limited or peripheral (e.g. a single Bayes-factor test \
in an otherwise frequentist paper, or one Bayesian robustness check). Proceed, but flagged.
- "no": no Bayesian statistical methodology. Frequentist-only work, or a paper that merely cites \
Bayesian references, is "no".

You are given (1) excerpts from the paper and (2) DETECTOR HITS: deterministic, trustworthy matches \
found in the text, each with an index. Ground your decision in them.

Rules:
- Cite evidence: for "yes"/"partial", evidence_refs MUST list the indices of the detector hits that \
justify the label (at least one).
- For "no", evidence_refs may be empty, but the rationale MUST enumerate what you searched for and \
did not find (priors/posteriors, Bayesian software, MCMC/VI, diagnostics, workflow signals).
- A bibliography mention of "Bayes" is not evidence the paper is Bayesian; excerpts exclude the \
reference list for this reason.
- confidence is your calibrated probability in [0,1]. When unsure between "no" and "partial", prefer \
"partial" — wrongly discarding a Bayesian paper is the worse error.
"""

# --- registry -------------------------------------------------------------------------------------

_PROMPTS: dict[str, str] = {
    "screen.system": SCREEN_SYSTEM,
}


def prompt_set_fingerprint() -> str:
    """A deterministic string over the whole prompt set. Pass to
    ``versioning.compute_engine_version(prompt_set=...)`` (G1): any edit flows into ``engine_version``
    and invalidates the result cache."""
    return "\n\n".join(f"### {key}\n{_PROMPTS[key]}" for key in sorted(_PROMPTS))
