"""Sanity-check our BS gamma against the Philipp Dubach dataset's `gamma` column.

The dataset ships pre-computed Greeks (delta/gamma/theta/vega/rho) generated
with someone else's BS implementation, presumably with their own assumptions
about r, q, and the dte→T mapping. If our BS76 (well, generalized BS with
continuous dividend yield) implementation is correct, our gamma should agree
with theirs to within a few percent **on liquid, near-ATM contracts where the
inputs are well-defined**.

Where we expect disagreement:

- Deep ITM / deep OTM rows: their gamma is tiny and absolute differences look
  big in relative terms but small in absolute terms. We filter these out by
  delta band.
- 0DTE rows (dte == 0): T → 0 is a numerical singularity. The dataset likely
  uses some intraday-fraction-of-day. We return NaN, they return a finite
  value. We skip dte=0 in the comparison.
- IV outliers (IV > 300% on dte ≤ 1, the OPT_IV_UNRELIABLE_AT_EXPIRY rule
  flagged 87 rows on 2025-12-12): both implementations produce garbage on
  garbage IV. We filter these too.

If after those filters our median |Δ| / dataset_gamma is > 5%, something is
wrong with our formula. Per AGENTS.md, this cross-check is **not optional** —
it's the strongest evidence we have that the single-contract gamma is right
before we aggregate to GEX.

Example:

    python scripts/cross_check_gamma.py
    python scripts/cross_check_gamma.py --options-date 2025-11-15 --delta-min 0.10 --delta-max 0.90
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.data.storage import (
    list_option_snapshots,
    load_option_chain,
)
from quant_lab.factors.gex import (
    DEFAULT_DIVIDEND_YIELD,
    DEFAULT_RISK_FREE_RATE,
    add_bs_gamma_column,
)


log = logging.getLogger(__name__)


def cross_check(
    chain: pd.DataFrame,
    spot: float,
    *,
    r: float,
    q: float,
    delta_min: float,
    delta_max: float,
    iv_max: float,
) -> pd.DataFrame:
    """Run the comparison and return the filtered/labeled diff frame."""
    needed = {"strike", "dte", "implied_volatility", "gamma", "delta"}
    missing = needed - set(chain.columns)
    if missing:
        raise ValueError(f"chain missing columns required for cross-check: {sorted(missing)}")

    work = add_bs_gamma_column(chain, spot=spot, r=r, q=q)
    work["dataset_gamma"] = pd.to_numeric(work["gamma"], errors="coerce").astype("float64")
    work["abs_delta"] = pd.to_numeric(work["delta"], errors="coerce").abs()

    diff = work[["strike", "right", "dte", "implied_volatility", "abs_delta",
                 "bs_gamma", "dataset_gamma"]].copy()
    diff["abs_diff"] = (diff["bs_gamma"] - diff["dataset_gamma"]).abs()
    # noise floor: 1e-6 sits well below liquid contract gamma (typically 1e-4
    # to 1e-2) and well above the dataset's tiny-positive float32 dust that
    # otherwise blows rel_diff to inf and pollutes mean/p95 stats.
    gamma_floor = 1e-6
    diff["rel_diff"] = np.where(
        diff["dataset_gamma"].abs() > gamma_floor,
        diff["abs_diff"] / diff["dataset_gamma"].abs(),
        np.nan,
    )

    filt = (
        (diff["dte"] > 0)
        & diff["bs_gamma"].notna()
        & diff["dataset_gamma"].notna()
        & (diff["dataset_gamma"] > gamma_floor)
        & (diff["implied_volatility"].between(0.05, iv_max))
        & (diff["abs_delta"].between(delta_min, delta_max))
        & diff["rel_diff"].notna()
    )
    return diff[filt].copy()


def summarize(diff: pd.DataFrame) -> None:
    if diff.empty:
        print("no rows survived the filters — check your delta/iv bands")
        return

    print(f"rows compared: {len(diff)}")
    print()
    print("=== relative diff |bs - dataset| / dataset ===")
    print(diff["rel_diff"].describe(percentiles=[0.5, 0.75, 0.9, 0.95, 0.99]))
    print()
    print("=== by dte bucket (median rel diff) ===")
    diff["dte_bucket"] = pd.cut(
        diff["dte"],
        bins=[0, 1, 7, 30, 90, 365, 10_000],
        labels=["1d", "≤1w", "≤1m", "≤3m", "≤1y", ">1y"],
    )
    by_bucket = diff.groupby("dte_bucket", observed=True)["rel_diff"].agg(
        ["count", "median", "mean", lambda s: s.quantile(0.95)]
    )
    by_bucket.columns = ["n", "median", "mean", "p95"]
    print(by_bucket)

    median_rel = float(diff["rel_diff"].median())
    p95_rel = float(diff["rel_diff"].quantile(0.95))
    print()
    if median_rel < 0.05:
        print(f"OK: median rel diff = {median_rel:.2%} (target < 5%)")
    else:
        print(f"FAIL: median rel diff = {median_rel:.2%} (target < 5%)")
    print(f"     p95   rel diff = {p95_rel:.2%}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument(
        "--options-date",
        default=None,
        help="YYYY-MM-DD; defaults to the latest snapshot from the Philipp Dubach import "
        "(2025-12-12 if you ran the import as documented).",
    )
    parser.add_argument("--r", type=float, default=DEFAULT_RISK_FREE_RATE)
    parser.add_argument("--q", type=float, default=DEFAULT_DIVIDEND_YIELD)
    parser.add_argument("--delta-min", type=float, default=0.15)
    parser.add_argument("--delta-max", type=float, default=0.85)
    parser.add_argument(
        "--iv-max",
        type=float,
        default=1.0,
        help="filter out rows with IV above this (default 100%, kills deep ITM/OTM junk IVs)",
    )
    parser.add_argument(
        "--save-diff",
        type=Path,
        default=None,
        help="optional parquet path to save the row-by-row diff for further analysis",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    snapshots = list_option_snapshots(args.symbol)
    if not snapshots:
        print(f"no snapshots for {args.symbol}", file=sys.stderr)
        return 1

    options_date = args.options_date
    if options_date is None:
        for d in reversed(snapshots):
            chain, _ = load_option_chain(args.symbol, d)
            if "gamma" in chain.columns:
                options_date = d
                break
        if options_date is None:
            print("no snapshot has a 'gamma' column — import Philipp Dubach data first",
                  file=sys.stderr)
            return 2

    chain, meta = load_option_chain(args.symbol, options_date)
    if "gamma" not in chain.columns:
        print(
            f"{args.symbol} snapshot {options_date} has no 'gamma' column "
            f"(not a Philipp Dubach import)", file=sys.stderr,
        )
        return 2

    spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
    if not np.isfinite(spot) or spot <= 0:
        print(f"snapshot {options_date} has invalid spot={spot}", file=sys.stderr)
        return 2

    print(f"cross-checking {args.symbol} {options_date} (spot={spot:.2f}, rows={len(chain)})")
    print(f"BS inputs: r={args.r}, q={args.q}")
    print(f"filters:   delta in [{args.delta_min}, {args.delta_max}], iv ≤ {args.iv_max}")
    print()

    diff = cross_check(
        chain,
        spot=spot,
        r=args.r,
        q=args.q,
        delta_min=args.delta_min,
        delta_max=args.delta_max,
        iv_max=args.iv_max,
    )
    summarize(diff)

    if args.save_diff is not None:
        args.save_diff.parent.mkdir(parents=True, exist_ok=True)
        diff.to_parquet(args.save_diff, engine="pyarrow")
        print(f"\nsaved row-by-row diff to {args.save_diff}")

    median_rel = float(diff["rel_diff"].median()) if not diff.empty else float("inf")
    return 0 if median_rel < 0.05 else 3


if __name__ == "__main__":
    raise SystemExit(main())
