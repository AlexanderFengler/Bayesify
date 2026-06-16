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
from pathlib import Path

from veribayes.core.rubric.loader import load_rubric
from veribayes.core.schema import ScoredResult
from veribayes.core.validation.human_report import GoldOrigin, HumanReport
from veribayes.core.validation.report import (
    ValidationReport,
    build_report,
    to_markdown,
)

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


def load_goldset(goldset_dir: str | Path) -> list[HumanReport]:
    """Load every ``*.json`` HumanReport in the directory (non-recursive, so an ``_engine/`` sibling
    of engine results is not picked up)."""
    return [
        HumanReport.model_validate_json(p.read_text())
        for p in sorted(Path(goldset_dir).glob("*.json"))
    ]


def load_engine(engine_dir: str | Path) -> dict[str, ScoredResult]:
    """Load engine ScoredResults keyed by work_id (the file stem)."""
    return {
        p.stem: ScoredResult.model_validate_json(p.read_text())
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
    treat_as_real: bool | None = None,
    seed: int = 0,
    n_floor: int = 15,
    profile: str = "synthesis",
    n_resamples: int = 1000,
) -> ValidationReport:
    """Load → firewall → build the ValidationReport (READ-ONLY; no artifacts written). Used by the
    API to serve /api/calibration. ``treat_as_real`` defaults to 'is this the real goldset dir?'."""
    if treat_as_real is None:
        treat_as_real = Path(goldset_dir).resolve() == Path(REAL_GOLDSET_DIR).resolve()
    rubric = load_rubric(profile=profile)
    humans = load_goldset(goldset_dir)
    engines = load_engine(engine_dir)
    is_demo, status = decide_status(humans, treat_as_real=treat_as_real)
    pairs = [(h, engines[h.work_id]) for h in humans if h.work_id in engines]
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
    )


def run(
    *,
    goldset_dir: str | Path = FAKE_GOLDSET_DIR,
    engine_dir: str | Path = FAKE_ENGINE_DIR,
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
        treat_as_real=treat_as_real,
        seed=seed,
        n_floor=n_floor,
        profile=profile,
    )
    engine_version = report.engine_version
    default_dir = FAKE_REPORTS_DIR if report.is_demo else REAL_REPORTS_DIR
    out = Path(out_dir) if out_dir else Path(default_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{engine_version}.json").write_text(report.model_dump_json(indent=2))
    if report.is_demo:
        (out / DEMO_MD).write_text(to_markdown(report))
    else:
        guard_public_emit(report)  # belt-and-braces: cannot reach here with demo data
        Path(PUBLIC_MD).write_text(to_markdown(report))
    return report


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    ap = argparse.ArgumentParser(description="VeriBayes validation harness")
    ap.add_argument("--goldset-dir", default=FAKE_GOLDSET_DIR)
    ap.add_argument("--engine-dir", default=FAKE_ENGINE_DIR)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--real", action="store_true", help="treat the goldset as the real, blind set")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-floor", type=int, default=15)
    ap.add_argument("--profile", default="synthesis")
    args = ap.parse_args(argv)
    report = run(
        goldset_dir=args.goldset_dir,
        engine_dir=args.engine_dir,
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
