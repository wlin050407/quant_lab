"""Analyze whether GEX / flip-distance signals predict next-day outcomes.

Joins ``data/processed/gex_history/<symbol>.parquet`` with underlying
close-to-close returns and reports Spearman rank ICs.

Example:

    python scripts/analyze_gex_ic.py --symbol SPY
    python scripts/analyze_gex_ic.py --symbol SPY --start 2023-01-01
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from quant_lab.config import settings
from quant_lab.data.storage import load_underlying
from quant_lab.factors.ic import align_gex_with_underlying, compute_ic_table, ic_by_regime

log = logging.getLogger(__name__)

SIGNALS = ["net_gex_bn", "spot_vs_flip_pct", "net_gex_bs"]
TARGETS = ["fwd_return", "fwd_abs_return", "fwd_realized_vol"]


def _history_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "gex_history" / f"{safe}.parquet"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    hist_path = _history_path(args.symbol)
    if not hist_path.exists():
        print(f"GEX history not found: {hist_path}", file=sys.stderr)
        print("run: python scripts/build_gex_history.py --symbol SPY", file=sys.stderr)
        return 1

    gex = pd.read_parquet(hist_path)
    gex["date"] = pd.to_datetime(gex["date"])
    if args.start is not None:
        gex = gex[gex["date"].dt.date >= args.start]
    if args.end is not None:
        gex = gex[gex["date"].dt.date <= args.end]

    try:
        underlying = load_underlying(args.symbol, interval="1d")
    except FileNotFoundError as exc:
        print(f"underlying missing: {exc}", file=sys.stderr)
        return 2

    df = align_gex_with_underlying(gex, underlying)
    df = df.dropna(subset=["fwd_return"])
    print(f"sample: {len(df)} days ({df['date'].min().date()} → {df['date'].max().date()})")
    print()

    ic_table = compute_ic_table(df, SIGNALS, TARGETS)
    print("=== Spearman IC (signal at t → outcome t+1) ===")
    for _, row in ic_table.iterrows():
        print(f"  {row['signal']:>20} → {row['target']:<18}  IC={row['ic']:+.4f}  n={int(row['n'])}")
    print()

    print("=== IC split by gamma regime (net_gex > 0 = long gamma) ===")
    for target in TARGETS:
        regime_ic = ic_by_regime(df, "net_gex_bn", target)
        print(f"  target={target}:")
        for _, row in regime_ic.iterrows():
            label = "long_gamma" if row["regime"] else "short_gamma"
            print(f"    {label:>12}  IC={row['ic']:+.4f}  n={int(row['n'])}")
    print()

    print("=== IC split by gamma regime (flip distance → vol) ===")
    regime_flip = ic_by_regime(df, "spot_vs_flip_pct", "fwd_abs_return")
    for _, row in regime_flip.iterrows():
        label = "long_gamma" if row["regime"] else "short_gamma"
        print(f"  {label:>12}  spot_vs_flip → fwd_abs_return  IC={row['ic']:+.4f}  n={int(row['n'])}")
    print()

    print("=== bucket sanity: mean |next-day return| by net_gex sign ===")
    bucket = df.groupby("long_gamma").agg(
        n=("fwd_abs_return", "count"),
        mean_abs_ret=("fwd_abs_return", "mean"),
        median_abs_ret=("fwd_abs_return", "median"),
    )
    print(bucket.to_string(float_format=lambda x: f"{x:.5f}"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
