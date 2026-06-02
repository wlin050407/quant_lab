"""Download SOFR (FRED SOFR series) into positioning rate parquet.

One-off or occasional local run — no deploy hook. Writes
``data/processed/rates/sofr_daily.parquet`` (columns ``date``, ``rate`` decimal).

After run, set in ``config/settings.yaml``::

  positioning:
    risk_free_rate_series: data/processed/rates/sofr_daily.parquet

Or pass the same path via env if you add support later.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

from quant_lab.config import settings

# FRED public graph CSV — no API key required for this endpoint.
FRED_SOFR_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR"


def fetch_sofr_dataframe() -> pd.DataFrame:
    """Pull SOFR daily levels from FRED CSV."""
    resp = requests.get(FRED_SOFR_CSV, timeout=60)
    resp.raise_for_status()
    raw = pd.read_csv(pd.io.common.StringIO(resp.text))
    if raw.shape[1] < 2:
        raise RuntimeError(f"unexpected FRED CSV shape: {raw.columns.tolist()}")
    date_col = raw.columns[0]
    rate_col = raw.columns[1]
    work = raw.rename(columns={date_col: "date", rate_col: "rate"}).copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.date
    work["rate"] = pd.to_numeric(work["rate"], errors="coerce") / 100.0
    work = work.dropna(subset=["date", "rate"])
    work = work.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return work.reset_index(drop=True)


def default_output_path() -> Path:
    return settings.paths.processed / "rates" / "sofr_daily.parquet"


def main() -> None:
    parser = argparse.ArgumentParser(description="Update SOFR daily rate parquet for GEX r input.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output parquet path (default: data/processed/rates/sofr_daily.parquet)",
    )
    args = parser.parse_args()
    out = args.output or default_output_path()
    out.parent.mkdir(parents=True, exist_ok=True)

    df = fetch_sofr_dataframe()
    if df.empty:
        raise RuntimeError("SOFR download returned no rows")
    df.to_parquet(out, index=False)
    last = df.iloc[-1]
    print(f"Wrote {len(df)} rows to {out}")
    print(f"Latest: {last['date']} rate={float(last['rate']):.4f}")


if __name__ == "__main__":
    main()
