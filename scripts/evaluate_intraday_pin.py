"""Intraday pin evaluation — compare 10:00 / 13:00 / 15:30 vs session close.

Validates Phase 1 hypotheses with local SPXW ThetaData snapshots:
- Which clock time has the best pin→close IC?
- King (|GEX| peak) vs max pain vs top-OI — which magnet is closest to close?

Examples::

    python scripts/evaluate_intraday_pin.py
    python scripts/evaluate_intraday_pin.py --time 13:00:00 --export
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from quant_lab.config import settings
from quant_lab.factors.pin_intraday_eval import (
    best_magnet_per_row,
    build_intraday_pin_frame,
    summarize_by_time_slot,
    summarize_magnet_accuracy,
)

log = logging.getLogger(__name__)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument(
        "--time",
        default=None,
        help="filter to one clock (e.g. 13:00:00); default = all PIN_PLAY times",
    )
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("=== Intraday pin: settled vs flow-adjusted OI ===")
    print()

    for mode_label, mode in (("settled OI", "settled"), ("flow-adjusted OI", "effective")):
        sub = build_intraday_pin_frame(
            start=args.start,
            end=args.end,
            oi_mode=mode,
        )
        if args.time is not None:
            sub = sub.loc[sub["time_of_day"] == args.time].reset_index(drop=True)
        if sub.empty:
            print(f"=== {mode_label}: no rows ===")
            if mode == "effective":
                print("  (run: python scripts/enrich_intraday_chains_flow.py)")
            print()
            continue

        print(f"=== {mode_label} (n={len(sub)}) ===")
        print("Pin IC by session clock (outcome = cash close):")
        for slot in summarize_by_time_slot(sub):
            print(
                f"  {slot.time_of_day[:5]} ET  n={slot.n:>4}  "
                f"IC={slot.spearman_ic:+.3f}  "
                f"high-pin median |dist|={slot.high_pin_median_dist_pct:.3f}%  "
                f"low-pin={slot.low_pin_median_dist_pct:.3f}%  "
                f"p={slot.comparison.p_value:.4g}"
            )
        print()

    frame = build_intraday_pin_frame(start=args.start, end=args.end, oi_mode="effective")
    if frame.empty:
        frame = build_intraday_pin_frame(start=args.start, end=args.end, oi_mode="settled")
    if args.time is not None:
        frame = frame.loc[frame["time_of_day"] == args.time].reset_index(drop=True)
    if frame.empty:
        log.error("no intraday rows — run backfill + enrich_intraday_chains_flow.py")
        return 1

    print(f"=== Magnet accuracy n={len(frame)} ===")
    for tod, grp in frame.groupby("time_of_day", sort=True):
        print(f"  --- {tod[:5]} ET ---")
        acc = summarize_magnet_accuracy(grp)
        for _, row in acc.iterrows():
            print(
                f"    {row['magnet']:<9} median={row['median_abs_dist_pct']:.3f}%  "
                f"within_EM={row['within_em_rate'] * 100:.1f}%"
            )
        winners = best_magnet_per_row(grp).value_counts(normalize=True) * 100.0
        print(f"    closest-to-close winner: {dict(winners.round(1))}")
    print()

    agree = frame["king_eq_max_pain"].mean() * 100.0 if len(frame) else float("nan")
    agree_top = frame["king_eq_top_oi"].mean() * 100.0 if len(frame) else float("nan")
    print(f"=== Magnet agreement ===")
    print(f"  King == max pain: {agree:.1f}% of rows")
    print(f"  King == top OI:   {agree_top:.1f}% of rows")
    print()

    if args.export:
        out_dir = settings.paths.processed / "pin_play"
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = args.time.replace(":", "")[:4] if args.time else "all"
        path = out_dir / f"intraday_pin_eval_{tag}.csv"
        frame.to_csv(path, index=False)
        log.info("wrote %s", path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
