"""Compute a per-day GEX time series across every stored option-chain snapshot.

For each snapshot under `data/raw/options/<symbol>/<date>/chain.parquet`:

1. Load the chain + meta (`spot`).
2. Compute our own BS gamma (`add_bs_gamma_column`).
3. Aggregate to per-strike dealer GEX (`compute_dealer_gamma_exposure`) and
   sum to a single `net_gex_bs` headline.
4. Repeat with the dataset's pre-computed `gamma` column (`net_gex_dataset`)
   as a sanity reference — they should track closely; large divergence on a
   given day flags either a chain anomaly or a BS-input misspec.
5. Optionally compute the gamma flip level (slow: 41 BS recomputes per day),
   skip with `--skip-flip` if you only want net GEX.
6. Append one row to the per-symbol time-series parquet.

Output schema (`data/processed/gex_history/<symbol>.parquet`):

    date                date (sorted, unique)
    symbol              str
    spot                float64
    net_gex_bs          float64    dollars per $1 spot move
    net_gex_dataset     float64    same units, computed from dataset gamma
    flip_level_bs       float64    NaN if no zero crossing in ±10%
    n_contracts         int64      rows in the chain
    total_oi            int64
    call_oi             int64
    put_oi              int64
    n_zero_dte_rows     int64      already-expired-at-snapshot rows (dte == 0)
    n_one_day_rows      int64      "next-day 0DTE" cohort (dte == 1)

Designed to be idempotent: re-runs only process dates not already in the
output file unless `--rebuild` is passed.

Examples:

    python scripts/build_gex_history.py --symbol SPY
    python scripts/build_gex_history.py --symbol SPY --skip-flip
    python scripts/build_gex_history.py --symbol SPY --rebuild --start 2025-01-01
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.config import settings
from quant_lab.data.storage import list_option_snapshots, load_option_chain
from quant_lab.factors.gex import (
    DEFAULT_DIVIDEND_YIELD,
    DEFAULT_RISK_FREE_RATE,
    add_bs_gamma_column,
    compute_dealer_gamma_exposure,
    gamma_flip_level,
    total_net_gex,
)

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "date",
    "symbol",
    "spot",
    "net_gex_bs",
    "net_gex_dataset",
    "flip_level_bs",
    "n_contracts",
    "total_oi",
    "call_oi",
    "put_oi",
    "n_zero_dte_rows",
    "n_one_day_rows",
]


def _output_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "gex_history" / f"{safe}.parquet"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def compute_one_snapshot(
    chain: pd.DataFrame,
    *,
    spot: float,
    r: float,
    q: float,
    compute_flip: bool,
) -> dict:
    """Return one row of the output schema (excluding `date` and `symbol`)."""
    if chain.empty:
        return {
            "spot": spot,
            "net_gex_bs": 0.0,
            "net_gex_dataset": 0.0,
            "flip_level_bs": float("nan"),
            "n_contracts": 0,
            "total_oi": 0,
            "call_oi": 0,
            "put_oi": 0,
            "n_zero_dte_rows": 0,
            "n_one_day_rows": 0,
        }

    with_bs = add_bs_gamma_column(chain, spot=spot, r=r, q=q)
    per_strike_bs = compute_dealer_gamma_exposure(with_bs, spot=spot, gamma_col="bs_gamma")
    net_bs = total_net_gex(per_strike_bs)

    if "gamma" in chain.columns:
        per_strike_ds = compute_dealer_gamma_exposure(chain, spot=spot, gamma_col="gamma")
        net_ds = total_net_gex(per_strike_ds)
    else:
        net_ds = float("nan")

    flip = (
        gamma_flip_level(with_bs, spot=spot, r=r, q=q)
        if compute_flip
        else float("nan")
    )

    call_oi = int(chain.loc[chain["right"] == "C", "open_interest"].sum())
    put_oi = int(chain.loc[chain["right"] == "P", "open_interest"].sum())

    return {
        "spot": float(spot),
        "net_gex_bs": float(net_bs),
        "net_gex_dataset": float(net_ds),
        "flip_level_bs": float(flip),
        "n_contracts": int(len(chain)),
        "total_oi": call_oi + put_oi,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "n_zero_dte_rows": int((chain["dte"] == 0).sum()) if "dte" in chain.columns else 0,
        "n_one_day_rows": int((chain["dte"] == 1).sum()) if "dte" in chain.columns else 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--r", type=float, default=DEFAULT_RISK_FREE_RATE)
    parser.add_argument("--q", type=float, default=DEFAULT_DIVIDEND_YIELD)
    parser.add_argument(
        "--skip-flip",
        action="store_true",
        help="don't compute gamma_flip_level (much faster: ~3x speedup)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="overwrite the output file instead of incrementally appending",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="log a progress line every N snapshots",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    out_path = _output_path(args.symbol)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing = pd.DataFrame(columns=OUTPUT_COLUMNS)
    if out_path.exists() and not args.rebuild:
        existing = pd.read_parquet(out_path)
        log.info("loaded existing history: %d rows (%s → %s)",
                 len(existing),
                 existing["date"].min() if len(existing) else None,
                 existing["date"].max() if len(existing) else None)

    snapshots = list_option_snapshots(args.symbol)
    if not snapshots:
        print(f"no snapshots for {args.symbol}", file=sys.stderr)
        return 1

    candidates: list[date] = []
    for s in snapshots:
        d = date.fromisoformat(s)
        if args.start is not None and d < args.start:
            continue
        if args.end is not None and d > args.end:
            continue
        candidates.append(d)

    existing_dates = set(pd.to_datetime(existing["date"]).dt.date) if not existing.empty else set()
    todo = [d for d in candidates if d not in existing_dates] if not args.rebuild else candidates
    log.info("symbol=%s total=%d existing=%d todo=%d compute_flip=%s",
             args.symbol, len(candidates), len(existing_dates), len(todo), not args.skip_flip)

    new_rows: list[dict] = []
    start_ts = time.monotonic()
    for i, d in enumerate(todo, start=1):
        try:
            chain, meta = load_option_chain(args.symbol, d.isoformat())
        except FileNotFoundError as exc:
            log.warning("skip %s: %s", d, exc)
            continue

        spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
        if not np.isfinite(spot) or spot <= 0:
            log.warning("skip %s: invalid spot=%s", d, spot)
            continue

        row = compute_one_snapshot(
            chain,
            spot=spot,
            r=args.r,
            q=args.q,
            compute_flip=not args.skip_flip,
        )
        row["date"] = pd.Timestamp(d)
        row["symbol"] = args.symbol
        new_rows.append(row)

        if i % args.progress_every == 0 or i == len(todo):
            elapsed = time.monotonic() - start_ts
            rate = i / elapsed if elapsed > 0 else 0
            log.info(
                "[%d/%d] %s spot=%.2f net_gex_bs=%+.2e flip=%s (%.1f snap/s)",
                i, len(todo), d, spot, row["net_gex_bs"],
                f"{row['flip_level_bs']:.2f}" if np.isfinite(row['flip_level_bs']) else "NaN",
                rate,
            )

    if not new_rows:
        print("nothing new to compute")
        return 0

    new_df = pd.DataFrame(new_rows, columns=OUTPUT_COLUMNS)
    combined = pd.concat([existing, new_df], ignore_index=True) if not args.rebuild else new_df
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    combined = combined.reset_index(drop=True)
    combined.to_parquet(out_path, engine="pyarrow")

    print(f"\nwrote {len(combined)} total rows to {out_path}")
    print(f"new this run: {len(new_rows)}")
    print(f"date range:   {combined['date'].min().date()} → {combined['date'].max().date()}")
    print()
    print("=== net_gex_bs summary (dollars per $1 spot move) ===")
    print(combined["net_gex_bs"].describe())
    if not args.skip_flip:
        n_with_flip = int(combined["flip_level_bs"].notna().sum())
        print()
        print(f"=== flip levels found: {n_with_flip}/{len(combined)} days ===")
        if n_with_flip > 0:
            spot_vs_flip = (combined["spot"] - combined["flip_level_bs"]) / combined["spot"]
            print("(spot - flip) / spot:")
            print(spot_vs_flip.describe())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
