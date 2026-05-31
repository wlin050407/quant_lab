"""Build daily max pain / PCR / OI concentration time series.

Output: ``data/processed/positioning_history/<symbol>.parquet``

Example:

    python scripts/build_positioning_history.py --symbol SPY
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
from quant_lab.factors.positioning import max_pain, oi_concentration, put_call_ratio

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "date",
    "symbol",
    "spot",
    "max_pain_all",
    "max_pain_dte1",
    "pcr_oi",
    "pcr_vol",
    "oi_concentration_all",
    "oi_concentration_dte1",
    "spot_vs_max_pain_pct",
]


def _output_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "positioning_history" / f"{safe}.parquet"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def compute_one_snapshot(chain: pd.DataFrame, *, spot: float) -> dict:
    mp_all = max_pain(chain)
    mp_dte1 = max_pain(chain, dte_max=1) if "dte" in chain.columns else float("nan")
    pcr_oi = put_call_ratio(chain, kind="open_interest")
    pcr_vol = put_call_ratio(chain, kind="volume") if "volume" in chain.columns else float("nan")
    conc_all = oi_concentration(chain, top_n=5)
    conc_dte1 = (
        oi_concentration(chain, top_n=5, dte_max=1)
        if "dte" in chain.columns
        else float("nan")
    )
    spot_vs_mp = (
        (spot - mp_all) / spot * 100.0 if np.isfinite(mp_all) and spot > 0 else float("nan")
    )
    return {
        "spot": float(spot),
        "max_pain_all": float(mp_all),
        "max_pain_dte1": float(mp_dte1),
        "pcr_oi": float(pcr_oi),
        "pcr_vol": float(pcr_vol),
        "oi_concentration_all": float(conc_all),
        "oi_concentration_dte1": float(conc_dte1),
        "spot_vs_max_pain_pct": float(spot_vs_mp),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
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

    snapshots = list_option_snapshots(args.symbol)
    if not snapshots:
        print(f"no snapshots for {args.symbol}", file=sys.stderr)
        return 1

    candidates = [
        date.fromisoformat(s)
        for s in snapshots
        if (args.start is None or date.fromisoformat(s) >= args.start)
        and (args.end is None or date.fromisoformat(s) <= args.end)
    ]
    existing_dates = (
        set(pd.to_datetime(existing["date"]).dt.date) if not existing.empty else set()
    )
    todo = candidates if args.rebuild else [d for d in candidates if d not in existing_dates]
    log.info("symbol=%s todo=%d", args.symbol, len(todo))

    rows: list[dict] = []
    start_ts = time.monotonic()
    for i, d in enumerate(todo, start=1):
        chain, meta = load_option_chain(args.symbol, d.isoformat())
        spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
        if not np.isfinite(spot) or spot <= 0:
            continue
        row = compute_one_snapshot(chain, spot=spot)
        row["date"] = pd.Timestamp(d)
        row["symbol"] = args.symbol
        rows.append(row)
        if i % args.progress_every == 0 or i == len(todo):
            elapsed = time.monotonic() - start_ts
            log.info("[%d/%d] %s (%.0f snap/s)", i, len(todo), d, i / max(elapsed, 1e-9))

    if not rows:
        print("nothing new to compute")
        return 0

    new_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    combined = pd.concat([existing, new_df], ignore_index=True) if not args.rebuild else new_df
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    combined.to_parquet(out_path, engine="pyarrow")
    print(f"wrote {len(combined)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
