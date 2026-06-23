"""The pure metric engine (component h) — agreement/accuracy statistics over rater-vs-engine labels.

Validation's computational core: data in (aligned label pairs / paired scalars) → numbers out (κ,
Gwet's AC, absence-FPR, miss-rate, confusion, ICC, CIs). It is **pure** — no LLM, no network, no IO,
no global state, and deterministic (the bootstrap is seeded) — same discipline as ``score.py``
(enforced by an import-linter contract). It knows nothing about ``HumanReport`` or ``ScoredResult``;
the harness (V5) extracts the aligned pairs from those reports and feeds them here, so each function
is testable against tiny hand-authored tables.

Two-stage discipline (protocol §3): applicability (applicable-vs-N/A) is stage 1; status agreement
is stage 2, computed only over cells *both* judges deem applicable. An engine-"missing" vs
human-"N/A" disagreement is therefore an applicability error (stage 1), excluded from absence-FPR —
see ``absence_fpr``. Every κ is reported alongside %-agreement and Gwet's AC1 because κ is
paradoxically low under skewed marginals (high agreement, low κ); AC1 is prevalence-robust.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from random import Random
from statistics import NormalDist

from veribayes.core.schema import StepStatus

# The ordinal status scale for stage-2 (worst -> best); not_applicable is excluded from stage 2.
STATUS_ORDER: tuple[StepStatus, ...] = (
    StepStatus.missing,
    StepStatus.partial,
    StepStatus.adequate,
)

Pair = tuple[Hashable, Hashable]  # (rater_a_label, rater_b_label) — order-agnostic for agreement


@dataclass(frozen=True)
class Rate:
    """A count-backed proportion, e.g. absence-FPR = ``x``/``n``. ``value`` is None when n == 0."""

    x: int
    n: int

    @property
    def value(self) -> float | None:
        return self.x / self.n if self.n else None


@dataclass(frozen=True)
class Interval:
    lo: float
    hi: float


# --- agreement matrices -------------------------------------------------------------------------


def _categories(pairs: Sequence[Pair], order: Sequence[Hashable] | None) -> list[Hashable]:
    if order is not None:
        return list(order)
    seen: list[Hashable] = []
    for a, b in pairs:
        for x in (a, b):
            if x not in seen:
                seen.append(x)
    return seen


def _matrix(pairs: Sequence[Pair], cats: Sequence[Hashable]) -> list[list[int]]:
    idx = {c: i for i, c in enumerate(cats)}
    m = [[0] * len(cats) for _ in cats]
    for a, b in pairs:
        m[idx[a]][idx[b]] += 1
    return m


def percent_agreement(pairs: Sequence[Pair]) -> float | None:
    """Raw fraction of pairs that agree. Reported beside every κ (the κ-paradox guard)."""
    if not pairs:
        return None
    return sum(1 for a, b in pairs if a == b) / len(pairs)


# --- kappa family -------------------------------------------------------------------------------


def _weight_matrix(k: int, kind: str) -> list[list[float]]:
    """Agreement weights (1.0 on the diagonal). ``nominal`` = identity; ``linear``/``quadratic`` use
    the ordinal distance |i-j|/(k-1) so near-misses count as partial agreement."""
    if k <= 1:
        return [[1.0]]
    w = [[0.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(k):
            d = abs(i - j) / (k - 1)
            if kind == "nominal":
                w[i][j] = 1.0 if i == j else 0.0
            elif kind == "linear":
                w[i][j] = 1.0 - d
            elif kind == "quadratic":
                w[i][j] = 1.0 - d * d
            else:
                raise ValueError(f"unknown weight kind {kind!r}")
    return w


def _kappa(pairs: Sequence[Pair], order: Sequence[Hashable] | None, kind: str) -> float | None:
    """Cohen's κ (``kind='nominal'``) or weighted κ. None for no data; 1.0 for the degenerate
    single-category perfect-agreement case (chance agreement is 1, so κ is otherwise 0/0)."""
    if not pairs:
        return None
    cats = _categories(pairs, order)
    k = len(cats)
    m = _matrix(pairs, cats)
    n = len(pairs)
    w = _weight_matrix(k, kind)
    rows = [sum(m[i]) for i in range(k)]
    cols = [sum(m[i][j] for i in range(k)) for j in range(k)]
    po = sum(w[i][j] * m[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w[i][j] * rows[i] * cols[j] for i in range(k) for j in range(k)) / (n * n)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def cohen_kappa(pairs: Sequence[Pair], order: Sequence[Hashable] | None = None) -> float | None:
    """Unweighted (nominal) κ — for stage-1 applicability (applicable vs N/A) and nominal axes."""
    return _kappa(pairs, order, "nominal")


def weighted_kappa(
    pairs: Sequence[Pair], order: Sequence[Hashable], *, kind: str = "linear"
) -> float | None:
    """Weighted κ on an ordinal scale — for stage-2 status (missing < partial < adequate), so a
    adequate-vs-partial disagreement is penalised less than adequate-vs-missing."""
    return _kappa(pairs, order, kind)


def gwet_ac(pairs: Sequence[Pair], order: Sequence[Hashable] | None = None) -> float | None:
    """Gwet's AC1 — prevalence-robust agreement. Unlike κ it does not collapse under skewed
    marginals, so it is the honest companion to κ on the paradox. Chance agreement uses the mean
    marginal probabilities (identity weights)."""
    if not pairs:
        return None
    cats = _categories(pairs, order)
    k = len(cats)
    if k == 1:
        return 1.0  # everyone used one category and agreed
    m = _matrix(pairs, cats)
    n = len(pairs)
    rows = [sum(m[i]) for i in range(k)]
    cols = [sum(m[i][j] for i in range(k)) for j in range(k)]
    pi = [(rows[i] + cols[i]) / (2 * n) for i in range(k)]  # mean marginal per category
    pa = sum(m[i][i] for i in range(k)) / n
    pe = sum(p * (1 - p) for p in pi) / (k - 1)
    if pe == 1.0:
        return 1.0 if pa == 1.0 else 0.0
    return (pa - pe) / (1 - pe)


# --- absence error rates (the headline safety metrics) ------------------------------------------


def absence_fpr(pairs: Sequence[tuple[StepStatus, StepStatus]], *, mode: str = "strict") -> Rate:
    """Of the engine's ``missing`` calls, the share that were actually present per the human — the
    rate of *crying wolf*. ``strict`` counts only human==adequate as a false positive; ``broad``
    counts {adequate, partial}. Pairs are (human_status, engine_status). Cells where the human said
    N/A are EXCLUDED (that is a stage-1 applicability disagreement, not a false absence)."""
    present = (
        {StepStatus.adequate}
        if mode == "strict"
        else {StepStatus.adequate, StepStatus.partial}
        if mode == "broad"
        else None
    )
    if present is None:
        raise ValueError(f"unknown mode {mode!r} (expected 'strict' or 'broad')")
    flagged = [
        (h, e)
        for h, e in pairs
        if e is StepStatus.missing and h is not StepStatus.not_applicable
    ]
    return Rate(sum(1 for h, _ in flagged if h in present), len(flagged))


def absence_miss_rate(pairs: Sequence[tuple[StepStatus, StepStatus]]) -> Rate:
    """Of the steps the human (consensus) judged ``missing``, the share the engine FAILED to flag as
    missing — the opposite direction from FPR, so a never-says-missing engine can't game it. Cells
    where the engine said N/A are excluded (a stage-1 disagreement)."""
    consensus_missing = [
        (h, e)
        for h, e in pairs
        if h is StepStatus.missing and e is not StepStatus.not_applicable
    ]
    missed = sum(1 for _, e in consensus_missing if e is not StepStatus.missing)
    return Rate(missed, len(consensus_missing))


def confusion(
    pairs: Sequence[tuple[StepStatus, StepStatus]], order: Sequence[StepStatus] = STATUS_ORDER
) -> dict[str, dict[str, int]]:
    """Full human×engine status crosstab (rows = human/consensus, cols = engine), so the missing
    row+column trade-off is visible on the calibration page. N/A is included if present in pairs."""
    cats: list[StepStatus] = list(order)
    for h, e in pairs:
        for s in (h, e):
            if s not in cats:
                cats.append(s)
    table = {h.value: {e.value: 0 for e in cats} for h in cats}
    for h, e in pairs:
        table[h.value][e.value] += 1
    return table


# --- scalar agreement (relevance, paper-class, coverage/quality) --------------------------------


def accuracy(pairs: Sequence[Pair]) -> Rate:
    """Exact-match accuracy (e.g. paper-class) against the human as ground truth."""
    return Rate(sum(1 for a, b in pairs if a == b), len(pairs))


def binary_sens_spec(pairs: Sequence[tuple[bool, bool]]) -> tuple[Rate, Rate]:
    """Sensitivity + specificity with the human label as truth. Pairs are (human_positive,
    engine_positive) — for Tier-B relevance, positive = 'is a Bayesian-workflow paper'. Sensitivity
    (recall on positives) is the one that matters most: short-circuiting a real paper is the worst
    error."""
    tp = sum(1 for h, e in pairs if h and e)
    pos = sum(1 for h, _ in pairs if h)
    tn = sum(1 for h, e in pairs if not h and not e)
    neg = sum(1 for h, _ in pairs if not h)
    return Rate(tp, pos), Rate(tn, neg)


def icc_a1(values: Sequence[tuple[float, float]]) -> float | None:
    """Two-way absolute-agreement single-measure ICC(A,1) between human-derived and engine
    coverage/quality across papers — replaces the dropped badge crosstab. Captures whether the two
    track the *same value*, not merely correlate. None for <2 papers or zero total variance."""
    n = len(values)
    if n < 2:
        return None
    k = 2
    grand = sum(a + b for a, b in values) / (n * k)
    row_means = [(a + b) / 2 for a, b in values]
    col_means = (sum(a for a, _ in values) / n, sum(b for _, b in values) / n)
    ss_total = sum((v - grand) ** 2 for a, b in values for v in (a, b))
    if ss_total == 0:
        return None
    ss_rows = k * sum((rm - grand) ** 2 for rm in row_means)
    ss_cols = n * sum((cm - grand) ** 2 for cm in col_means)
    ss_err = ss_total - ss_rows - ss_cols
    msr = ss_rows / (n - 1)
    msc = ss_cols / (k - 1)
    mse = ss_err / ((n - 1) * (k - 1))
    denom = msr + (k - 1) * mse + k * (msc - mse) / n
    return None if denom == 0 else (msr - mse) / denom


# --- uncertainty --------------------------------------------------------------------------------


def _z(level: float) -> float:
    return NormalDist().inv_cdf((1 + level) / 2)


def wilson_ci(x: int, n: int, *, level: float = 0.95) -> Interval | None:
    """Wilson score interval for a binomial rate — robust at small n / extreme p."""
    if n == 0:
        return None
    z = _z(level)
    p = x / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return Interval(max(0.0, centre - half), min(1.0, centre + half))


def _quantile(xs: Sequence[float], q: float) -> float:
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= len(xs):
        return xs[-1]
    return xs[lo] * (1 - frac) + xs[lo + 1] * frac


def bootstrap_ci[T](
    units: Sequence[T],
    stat,
    *,
    seed: int,
    n_resamples: int = 2000,
    level: float = 0.95,
) -> Interval | None:
    """Percentile bootstrap CI for any statistic. ``units`` is the resampling unit — pass PAPERS
    (each carrying its cells) and a ``stat`` that flattens them, to get the protocol §3 / G9
    paper-level CLUSTER bootstrap (resample papers, not cells, so within-paper correlation is
    respected). Deterministic given ``seed``. A resample that can't be scored is skipped.

    v0 DECISION (owner, 2026-06-16): κ CIs are OFF for v0 — ``report._kappa_ci`` returns None, so
    this is NOT currently invoked by the report (only unit-tested here). At v0 n a cluster-bootstrap
    κ CI is noisy/contestable; κ ships as point + n. Retained for a possible v1 re-enable (flip the
    seam back) once the real run has enough papers; revisit at the G9 amendment (protocol §3)."""
    if not units:
        return None
    rng = Random(seed)
    n = len(units)
    samples: list[float] = []
    for _ in range(n_resamples):
        resample = [units[rng.randrange(n)] for _ in range(n)]
        try:
            v = stat(resample)
        except (ZeroDivisionError, ValueError):
            continue
        if v is not None:
            samples.append(v)
    if not samples:
        return None
    samples.sort()
    lo_q = (1 - level) / 2
    return Interval(_quantile(samples, lo_q), _quantile(samples, 1 - lo_q))


def is_sufficient(n: int, floor: int) -> bool:
    """Whether a cell/metric clears the protocol §3 minimum-n floor; below it the report renders
    'insufficient data' rather than a misleadingly precise number."""
    return n >= floor
