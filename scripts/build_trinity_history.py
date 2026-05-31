"""Build cross-index Trinity alignment history (Ultimate Terminal M1).

Joins terminal factor rows for SPY and ^SPX on common dates and scores
structural King-node alignment (Skylit Trinity Mode).

Output: ``data/processed/trinity/history.parquet``

Example:

    python scripts/build_trinity_history.py
    python scripts/build_trinity_history.py --rebuild
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quant_lab.config import settings
from quant_lab.factors.trinity import trinity_from_kings

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "date",
    "trinity_score",
    "trinity_direction",
    "n_symbols",
    "spy_spot",
    "spy_king_dte1",
    "spx_spot",
    "spx_king_dte1",
    "spy_king_dist_pct",
    "spx_king_dist_pct",
]


def _terminal_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "terminal" / f"{safe}.parquet"


def _output_path() -> Path:
    return settings.paths.processed / "trinity" / "history.parquet"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spy-symbol", default="SPY")
    parser.add_argument("--spx-symbol", default="^SPX")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--tolerance-pct", type=float, default=0.008)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    spy_path = _terminal_path(args.spy_symbol)
    spx_path = _terminal_path(args.spx_symbol)
    if not spy_path.exists():
        print(f"missing {spy_path} — run build_terminal_history.py first", file=sys.stderr)
        return 1

    spy = pd.read_parquet(spy_path)
    spy["date"] = pd.to_datetime(spy["date"]).dt.normalize()
    spy = spy.rename(columns={c: f"spy_{c}" for c in spy.columns if c != "date"})

    if spx_path.exists():
        spx = pd.read_parquet(spx_path)
        spx["date"] = pd.to_datetime(spx["date"]).dt.normalize()
        spx = spx.rename(columns={c: f"spx_{c}" for c in spx.columns if c != "date"})
        merged = spy.merge(spx, on="date", how="left")
        has_spx = True
    else:
        log.warning("no SPX terminal at %s — Trinity will be SPY-only placeholder", spx_path)
        merged = spy.copy()
        has_spx = False

    rows: list[dict] = []
    for _, r in merged.iterrows():
        spy_tuple = None
        spx_tuple = None
        if np.isfinite(r.get("spy_spot", np.nan)) and np.isfinite(r.get("spy_king_dte1", np.nan)):
            spy_tuple = (float(r["spy_spot"]), float(r["spy_king_dte1"]))
        if has_spx and np.isfinite(r.get("spx_spot", np.nan)) and np.isfinite(
            r.get("spx_king_dte1", np.nan)
        ):
            spx_tuple = (float(r["spx_spot"]), float(r["spx_king_dte1"]))

        align = trinity_from_kings(spy=spy_tuple, spx=spx_tuple, tolerance_pct=args.tolerance_pct)
        row = {
            "date": r["date"],
            "trinity_score": align.score,
            "trinity_direction": align.direction,
            "n_symbols": align.n_symbols,
            "spy_spot": float(r["spy_spot"]) if "spy_spot" in r else float("nan"),
            "spy_king_dte1": float(r["spy_king_dte1"]) if "spy_king_dte1" in r else float("nan"),
            "spx_spot": float(r.get("spx_spot", np.nan)),
            "spx_king_dte1": float(r.get("spx_king_dte1", np.nan)),
            "spy_king_dist_pct": align.distance_pcts.get("SPY", float("nan")),
            "spx_king_dist_pct": align.distance_pcts.get("SPX", float("nan")),
        }
        rows.append(row)

    if not rows:
        print("no rows to write", file=sys.stderr)
        return 1

    out_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    out_path = _output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, engine="pyarrow")
    valid = out_df["trinity_score"].notna().sum()
    print(f"wrote {len(out_df)} rows to {out_path} ({valid} with trinity_score)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
