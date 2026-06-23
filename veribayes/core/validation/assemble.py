"""`assemble-goldset` (M7 slice 2) — turn captured blind ratings into gold records.

Groups the persisted ratings by paper, derives the consensus mechanically (``consensus.py``), and
writes one ``HumanReport`` per paper to the goldset directory. A paper whose raters reach no
paper-level consensus is **skipped and reported** (never silently dropped). This is the bridge from
"raters submitted ratings" to "the harness has a gold set" — the automated replacement for the
adjudication step. Run with ``pixi run assemble-goldset``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from veribayes.core.validation.consensus import assemble_human_report
from veribayes.core.validation.human_report import GoldOrigin, GoldTier
from veribayes.core.validation.rating_store import RatingStore


def _default_ratings_dir() -> str:
    root = os.environ.get("VERIBAYES_DATA_DIR") or str(Path.home() / ".veribayes")
    return str(Path(root) / "ratings")


def assemble(
    *,
    ratings_dir: str | Path,
    out_dir: str | Path,
    tier: GoldTier = GoldTier.A,
    origin: GoldOrigin = GoldOrigin.blind_human,
) -> tuple[list[str], list[str]]:
    """Returns (written work_ids, skipped work_ids). ``origin`` defaults to ``blind_human`` — the
    captured ratings are real human submissions, which the owner running this vouches for (the
    firewall enforces blind_human at the harness's public-emit step)."""
    store = RatingStore(Path(ratings_dir))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    # Each bucket is one paper under one rubric (the store keys by <sha>__<profile>), so a gold
    # record is single-rubric by construction — one paper under two rubrics becomes two records.
    for bucket, subs in store.by_paper().items():
        first = subs[0]
        report = assemble_human_report(
            work_id=bucket,
            source_sha256=first.source_sha256,
            version_label=first.version_label,
            rubric_version=first.rubric_version,
            rubric_profile=first.rubric_profile,
            tier=tier,
            ratings=[s.rating for s in subs],
            origin=origin,
        )
        # Skip-and-report (never silently drop): no paper-level consensus, or not structurally
        # admissible (e.g. <2 raters, no independent rater) — the gold set takes only ready records.
        if report is None or report.validate_admissible():
            skipped.append(bucket)
            continue
        (out / f"{bucket}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        written.append(bucket)
    return written, skipped


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    ap = argparse.ArgumentParser(description="Assemble blind ratings into gold records")
    ap.add_argument("--ratings-dir", default=None, help="default: <data dir>/ratings")
    ap.add_argument("--out-dir", default="validation/goldset")
    ap.add_argument("--tier", default="A", choices=[t.value for t in GoldTier])
    ap.add_argument("--origin", default="blind_human", choices=[o.value for o in GoldOrigin])
    args = ap.parse_args(argv)
    written, skipped = assemble(
        ratings_dir=args.ratings_dir or _default_ratings_dir(),
        out_dir=args.out_dir,
        tier=GoldTier(args.tier),
        origin=GoldOrigin(args.origin),
    )
    print(
        f"assembled {len(written)} gold record(s) → {args.out_dir}; "
        f"skipped {len(skipped)} (no consensus): {skipped}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
