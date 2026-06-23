"""The validation harness (V5b) — the impure shell around the pure ``build_report``.

It loads (HumanReport, ScoredResult) pairs from disk, runs the builder, and writes the three
artifacts (report JSON, VALIDATION(.demo).md, and the /api/calibration payload = the JSON). Its job
is the **honesty firewall** — the structural guards that make it impossible for fabricated demo data
to be presented as a real validation result:

- ``FakeDataInRealGoldset``: a non-``blind_human`` record under the real ``validation/goldset/`` is
  a hard error (the real path demands real data).
- ``FakeDataInPublicReport``: the citable ``VALIDATION.md`` is emitted ONLY from a non-demo report;
  a demo/fake report routes to ``VALIDATION.demo.md`` instead, and the guard aborts before writing.
- Single source: ``is_demo``/``status`` come from the ONE ``ValidationReport`` object, so no
  artifact can disagree (set in ``build_report``; see ``report``).

Run the demo dry-run with ``pixi run validate`` (defaults to the fake goldset); regenerate the fake
data with ``pixi run demo-data``. The real run (``--real`` over ``validation/goldset/``) is M7.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from bayesify.core.cache import BlobStore, sha256_bytes
from bayesify.core.rubric.loader import load_rubric
from bayesify.core.schema import ScoredResult
from bayesify.core.validation.human_report import GoldOrigin, GoldTier, HumanReport
from bayesify.core.validation.report import (
    ValidationReport,
    build_report,
    to_markdown,
)

# An engine source produces the engine's ScoredResult for one gold-set paper. Two implementations:
# fixtures (the demo, paired by work_id) and live (fetch the rated bytes by sha256, run the engine).
EngineSource = Callable[[HumanReport], "ScoredResult | None"]

REAL_GOLDSET_DIR = "validation/goldset"
FAKE_GOLDSET_DIR = "validation/_fake_goldset"
FAKE_ENGINE_DIR = "validation/_fake_goldset/_engine"
FAKE_REPORTS_DIR = "validation/_fake_reports"
REAL_REPORTS_DIR = "validation/reports"
PUBLIC_MD = "VALIDATION.md"
DEMO_MD = "VALIDATION.demo.md"


class HarnessError(Exception):
    """Base for harness-level failures (named in the exit; never silent)."""


class FakeDataInRealGoldset(HarnessError):
    """A non-blind_human record was loaded from the real goldset directory."""


class FakeDataInPublicReport(HarnessError):
    """An attempt to emit the public VALIDATION.md from demo/fake data."""


class GoldsetVersionMismatch(HarnessError):
    """The engine cannot be run on the exact document the rater rated (protocol §1 byte-pin): the
    pinned sha256 is not in the blob store, or the stored bytes hash differently. A hard fail — the
    harness never grades a substitute document."""


# --- engine sources -------------------------------------------------------------------------------


class FixtureEngineSource:
    """Demo/dry-run: read pre-recorded engine ScoredResults from a directory, paired by work_id."""

    def __init__(self, engine_dir: str | Path) -> None:
        self._by_work_id = load_engine(engine_dir)

    def __call__(self, human: HumanReport) -> ScoredResult | None:
        return self._by_work_id.get(human.work_id)


class LiveEngineSource:
    """Real run: grade each gold-set paper with the live engine, on the exact bytes the rater rated.
    Fetches by the pinned sha256 from the blob store and hard-fails ``GoldsetVersionMismatch`` if
    the rated document isn't available — never grades a substitute. ``grade_fn`` (bytes ->
    ScoredResult) is injected so this is testable without the LLM; the CLI wires the real engine via
    ``core.engine.grade_document``."""

    def __init__(self, blobs: BlobStore, grade_fn: Callable[[bytes], ScoredResult]) -> None:
        self.blobs = blobs
        self.grade_fn = grade_fn

    def __call__(self, human: HumanReport) -> ScoredResult:
        sha = human.source_sha256
        if not sha or not self.blobs.exists(sha):
            raise GoldsetVersionMismatch(
                f"{human.work_id}: rated document {sha!r} is not in the blob store"
            )
        data = self.blobs.get(sha)
        actual = sha256_bytes(data)
        if actual != sha:  # defensive: a content-addressed store should never return other bytes
            raise GoldsetVersionMismatch(
                f"{human.work_id}: stored bytes hash {actual} != pinned {sha}"
            )
        return self.grade_fn(data)


def load_goldset(goldset_dir: str | Path) -> list[HumanReport]:
    """Load every ``*.json`` HumanReport in the directory (non-recursive, so an ``_engine/`` sibling
    of engine results is not picked up)."""
    return [
        HumanReport.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(Path(goldset_dir).glob("*.json"))
    ]


def load_engine(engine_dir: str | Path) -> dict[str, ScoredResult]:
    """Load engine ScoredResults keyed by work_id (the file stem)."""
    return {
        p.stem: ScoredResult.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(Path(engine_dir).glob("*.json"))
    }


def decide_status(humans: list[HumanReport], *, treat_as_real: bool) -> tuple[bool, str]:
    """Resolve (is_demo, status) and enforce the real-goldset guard. The real path demands every
    record be ``blind_human``; a fake one there is a hard ``FakeDataInRealGoldset``."""
    all_blind = bool(humans) and all(
        h.provenance.origin is GoldOrigin.blind_human for h in humans
    )
    if treat_as_real and not all_blind:
        offenders = sorted(
            {
                h.provenance.origin.value
                for h in humans
                if h.provenance.origin is not GoldOrigin.blind_human
            }
        )
        raise FakeDataInRealGoldset(
            f"{REAL_GOLDSET_DIR} must contain only blind_human records; found: {offenders}"
        )
    is_demo = not (treat_as_real and all_blind)
    return is_demo, ("development_set" if not is_demo else "demo_fake_data")


def guard_public_emit(report: ValidationReport) -> None:
    """The one-way door: VALIDATION.md can be produced only from a real, non-demo report."""
    if report.is_demo or report.status != "development_set":
        raise FakeDataInPublicReport(
            f"refusing to emit {PUBLIC_MD} from a non-real report (status={report.status!r})"
        )


def build(
    *,
    goldset_dir: str | Path = FAKE_GOLDSET_DIR,
    engine_dir: str | Path = FAKE_ENGINE_DIR,
    engine_source: EngineSource | None = None,
    engine_runs: int = 1,
    treat_as_real: bool | None = None,
    seed: int = 0,
    n_floor: int = 15,
    profile: str = "synthesis",
    n_resamples: int = 1000,
) -> ValidationReport:
    """Load → firewall → build the ValidationReport (READ-ONLY; no artifacts written). Used by the
    API to serve /api/calibration. ``engine_source`` produces each paper's engine result — defaults
    to the fixture source (demo); the real run passes a ``LiveEngineSource``. ``engine_runs >= 2``
    grades each Tier-A paper a second time for test-retest κ (only meaningful with a stochastic live
    engine — fixtures are deterministic). ``treat_as_real`` defaults to 'is this the real goldset
    dir?'."""
    if treat_as_real is None:
        treat_as_real = Path(goldset_dir).resolve() == Path(REAL_GOLDSET_DIR).resolve()
    if engine_source is None:
        engine_source = FixtureEngineSource(engine_dir)
    rubric = load_rubric(profile=profile)
    humans = load_goldset(goldset_dir)
    is_demo, status = decide_status(humans, treat_as_real=treat_as_real)
    pairs: list[tuple[HumanReport, ScoredResult]] = []
    retest_pairs: list[tuple[ScoredResult, ScoredResult]] = []
    for h in humans:
        sr = engine_source(h)  # may raise GoldsetVersionMismatch (hard fail; no substitute doc)
        if sr is None:
            continue
        pairs.append((h, sr))
        if engine_runs >= 2 and h.tier is GoldTier.A:
            sr2 = engine_source(h)  # a second independent run (stochastic on the live engine)
            if sr2 is not None:
                retest_pairs.append((sr, sr2))
    engine_version = next((s.engine_version for _, s in pairs), "unknown")
    return build_report(
        pairs,
        rubric,
        engine_version=engine_version,
        is_demo=is_demo,
        status=status,
        seed=seed,
        n_floor=n_floor,
        n_resamples=n_resamples,
        retest_pairs=retest_pairs,
    )


def run(
    *,
    goldset_dir: str | Path = FAKE_GOLDSET_DIR,
    engine_dir: str | Path = FAKE_ENGINE_DIR,
    engine_source: EngineSource | None = None,
    engine_runs: int = 1,
    out_dir: str | Path | None = None,
    treat_as_real: bool | None = None,
    seed: int = 0,
    n_floor: int = 15,
    profile: str = "synthesis",
) -> ValidationReport:
    """Build the report, then WRITE the three artifacts behind the firewall. Returns the report."""
    report = build(
        goldset_dir=goldset_dir,
        engine_dir=engine_dir,
        engine_source=engine_source,
        engine_runs=engine_runs,
        treat_as_real=treat_as_real,
        seed=seed,
        n_floor=n_floor,
        profile=profile,
    )
    engine_version = report.engine_version
    default_dir = FAKE_REPORTS_DIR if report.is_demo else REAL_REPORTS_DIR
    out = Path(out_dir) if out_dir else Path(default_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{engine_version}.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    if report.is_demo:
        (out / DEMO_MD).write_text(to_markdown(report), encoding="utf-8")
    else:
        guard_public_emit(report)  # belt-and-braces: cannot reach here with demo data
        Path(PUBLIC_MD).write_text(to_markdown(report), encoding="utf-8")
    return report


def _live_engine_source(*, profile: str) -> LiveEngineSource:  # pragma: no cover - real run, billed
    """Build the live engine source for ``--real``: the same engine the app ships, over the rated
    bytes in the blob store. Bills the LLM — only the deliberate M7 run reaches here."""
    import os

    from bayesify.core import engine
    from bayesify.core.stub import ENGINE_VERSION, RUBRIC_VERSION
    from bayesify.llm import make_llm_client

    root = os.environ.get("BAYESIFY_DATA_DIR") or str(Path.home() / ".bayesify")
    blobs = BlobStore(Path(root) / "blobs")
    client = make_llm_client()
    rubric = load_rubric(profile=profile)

    def grade_fn(data: bytes) -> ScoredResult:
        return engine.grade_document(
            data,
            blobs=blobs,
            client=client,
            rubric=rubric,
            engine_version=ENGINE_VERSION,
            rubric_version=RUBRIC_VERSION,
        )

    return LiveEngineSource(blobs, grade_fn)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    ap = argparse.ArgumentParser(description="Bayesify validation harness")
    ap.add_argument("--goldset-dir", default=FAKE_GOLDSET_DIR)
    ap.add_argument("--engine-dir", default=FAKE_ENGINE_DIR)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--real", action="store_true", help="real run: blind goldset + live engine")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-floor", type=int, default=15)
    ap.add_argument("--profile", default="synthesis")
    args = ap.parse_args(argv)
    # --real grades each paper with the LIVE engine over its pinned bytes (bills); the demo uses
    # the recorded fixture engine results.
    engine_source = _live_engine_source(profile=args.profile) if args.real else None
    report = run(
        goldset_dir=args.goldset_dir,
        engine_dir=args.engine_dir,
        engine_source=engine_source,
        engine_runs=2 if args.real else 1,  # the real run grades Tier A twice for test-retest κ
        out_dir=args.out_dir,
        treat_as_real=True if args.real else None,
        seed=args.seed,
        n_floor=args.n_floor,
        profile=args.profile,
    )
    tag = "DEMO (fake data)" if report.is_demo else "development-set"
    print(
        f"[{tag}] {report.n_papers} papers ({report.n_excluded} excluded) · "
        f"status={report.status} · status κ={report.status_kappa.value} · "
        f"absence-FPR(strict)={report.absence_fpr_strict.x}/{report.absence_fpr_strict.n}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
