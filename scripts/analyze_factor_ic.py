"""Full factor IC report: GEX + positioning, by year, exported to processed/ic/.

Examples:

    python scripts/analyze_factor_ic.py --symbol SPY
    python scripts/analyze_factor_ic.py --symbol SPY --export
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
from quant_lab.factors.ic import (
    align_gex_with_underlying,
    attach_forward_returns,
    compute_ic_table,
    ic_by_regime,
    ic_by_year,
)

log = logging.getLogger(__name__)

GEX_SIGNALS = ["net_gex_bn", "spot_vs_flip_pct", "net_gex_bs"]
POSITIONING_SIGNALS = [
    "pcr_oi",
    "pcr_vol",
    "spot_vs_max_pain_pct",
    "oi_concentration_all",
    "oi_concentration_dte1",
]
TARGETS = ["fwd_return", "fwd_abs_return", "fwd_realized_vol"]


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "").replace("/", "_")


def _ic_dir() -> Path:
    return settings.paths.processed / "ic"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _load_gex(symbol: str, start: date | None, end: date | None) -> pd.DataFrame:
    path = settings.paths.processed / "gex_history" / f"{_safe_symbol(symbol)}.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    gex = pd.read_parquet(path)
    gex["date"] = pd.to_datetime(gex["date"])
    if start is not None:
        gex = gex[gex["date"].dt.date >= start]
    if end is not None:
        gex = gex[gex["date"].dt.date <= end]
    return gex


def _load_positioning(symbol: str, start: date | None, end: date | None) -> pd.DataFrame:
    path = settings.paths.processed / "positioning_history" / f"{_safe_symbol(symbol)}.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    pos = pd.read_parquet(path)
    pos["date"] = pd.to_datetime(pos["date"])
    if start is not None:
        pos = pos[pos["date"].dt.date >= start]
    if end is not None:
        pos = pos[pos["date"].dt.date <= end]
    return pos


def _print_ic_block(title: str, table: pd.DataFrame) -> None:
    print(f"=== {title} ===")
    for _, row in table.iterrows():
        print(
            f"  {row['signal']:>24} → {row['target']:<18}  "
            f"IC={row['ic']:+.4f}  n={int(row['n'])}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument(
        "--export",
        action="store_true",
        help="write parquet tables to data/processed/ic/",
    )
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    try:
        gex_raw = _load_gex(args.symbol, args.start, args.end)
    except FileNotFoundError as exc:
        print(f"GEX history missing: {exc}", file=sys.stderr)
        return 1

    try:
        pos_raw = _load_positioning(args.symbol, args.start, args.end)
    except FileNotFoundError as exc:
        print(f"positioning history missing: {exc}", file=sys.stderr)
        print("run: python scripts/build_positioning_history.py", file=sys.stderr)
        return 1

    try:
        underlying = load_underlying(args.symbol, interval="1d")
    except FileNotFoundError as exc:
        print(f"underlying missing: {exc}", file=sys.stderr)
        return 2

    gex_df = align_gex_with_underlying(gex_raw, underlying).dropna(subset=["fwd_return"])
    pos_df = attach_forward_returns(pos_raw, underlying).dropna(subset=["fwd_return"])

    print(f"sample: GEX {len(gex_df)} days, positioning {len(pos_df)} days")
    print(f"range: {gex_df['date'].min().date()} → {gex_df['date'].max().date()}")
    print()

    gex_ic = compute_ic_table(gex_df, GEX_SIGNALS, TARGETS)
    pos_ic = compute_ic_table(pos_df, POSITIONING_SIGNALS, TARGETS)
    _print_ic_block("GEX Spearman IC (t → t+1)", gex_ic)
    _print_ic_block("Positioning Spearman IC (t → t+1)", pos_ic)

    gex_vol_by_year = pd.concat(
        [ic_by_year(gex_df, sig, "fwd_abs_return") for sig in GEX_SIGNALS],
        ignore_index=True,
    )
    pos_vol_by_year = pd.concat(
        [ic_by_year(pos_df, sig, "fwd_abs_return") for sig in POSITIONING_SIGNALS],
        ignore_index=True,
    )

    print("=== GEX net_gex_bn → fwd_abs_return by year ===")
    yr = gex_vol_by_year[gex_vol_by_year["signal"] == "net_gex_bn"].sort_values("year")
    for _, row in yr.iterrows():
        print(f"  {int(row['year'])}  IC={row['ic']:+.4f}  n={int(row['n'])}")
    print()

    print("=== Positioning pcr_oi → fwd_abs_return by year (top |IC|) ===")
    pcr_yr = pos_vol_by_year[pos_vol_by_year["signal"] == "pcr_oi"].sort_values("year")
    for _, row in pcr_yr.iterrows():
        print(f"  {int(row['year'])}  IC={row['ic']:+.4f}  n={int(row['n'])}")
    print()

    print("=== GEX regime split (net_gex_bn → fwd_abs_return) ===")
    for _, row in ic_by_regime(gex_df, "net_gex_bn", "fwd_abs_return").iterrows():
        label = "long_gamma" if row["regime"] else "short_gamma"
        print(f"  {label:>12}  IC={row['ic']:+.4f}  n={int(row['n'])}")
    print()

    if args.export:
        out = _ic_dir()
        out.mkdir(parents=True, exist_ok=True)
        safe = _safe_symbol(args.symbol)
        gex_ic.to_parquet(out / f"{safe}_gex_ic.parquet", index=False)
        pos_ic.to_parquet(out / f"{safe}_positioning_ic.parquet", index=False)
        gex_vol_by_year.to_parquet(out / f"{safe}_gex_ic_by_year.parquet", index=False)
        pos_vol_by_year.to_parquet(out / f"{safe}_positioning_ic_by_year.parquet", index=False)
        summary = pd.concat(
            [
                gex_ic.assign(factor_group="gex"),
                pos_ic.assign(factor_group="positioning"),
            ],
            ignore_index=True,
        )
        summary.to_parquet(out / f"{safe}_ic_summary.parquet", index=False)
        print(f"exported IC tables to {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
