"""Render the GEX history time series.

Three-panel figure aligned on a shared time axis:

1. **Top: SPY close** with annotated known events (2022 bear market trough,
   2023-03 SVB, 2024-08-05 carry-trade unwind, etc.). Sanity-anchors the
   regime story below.
2. **Middle: net dealer gamma exposure** (BS computation) in billions of
   dollars per $1 spot move. Zero line drawn explicitly; background shaded
   red when negative (dealer short gamma → vol amplifier regime) and green
   when positive (dealer long gamma → vol dampener regime).
3. **Bottom: spot vs gamma flip level** plotted as percentage distance,
   `(spot - flip) / spot`. Positive = spot is above flip (long-gamma regime
   from another angle); negative = spot is below flip. NaN where no flip
   crossing was found in the ±10% search window.

The point of this script is **not** to be pretty publication graphics — it's
to be the first eyeball check that our positioning factors track real-world
regime changes. If 2022's bear market doesn't show up as a sustained negative
net-GEX period, something is wrong upstream.

Outputs `data/processed/plots/gex_history_<symbol>.png`.

Example:

    python scripts/build_gex_history.py --symbol SPY   # build the parquet
    python scripts/plot_gex_history.py --symbol SPY
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from quant_lab.config import settings

log = logging.getLogger(__name__)

NAMED_EVENTS: list[tuple[date, str]] = [
    (date(2022, 6, 13), "FOMC 75bp"),
    (date(2022, 10, 13), "CPI shock"),
    (date(2023, 3, 10), "SVB"),
    (date(2023, 10, 27), "MidEast risk-off"),
    (date(2024, 8, 5), "Carry unwind"),
    (date(2025, 4, 7), "Tariff shock"),
]


def _history_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "gex_history" / f"{safe}.parquet"


def _plot_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "plots" / f"gex_history_{safe}.png"


def _annotate_events(ax, df: pd.DataFrame) -> None:
    """Vertical lines + small text labels for events that fall in the data window."""
    if df.empty:
        return
    lo, hi = df["date"].min(), df["date"].max()
    y_lo, y_hi = ax.get_ylim()
    label_y = y_hi - 0.05 * (y_hi - y_lo)
    for ev_date, label in NAMED_EVENTS:
        ts = pd.Timestamp(ev_date)
        if not (lo <= ts <= hi):
            continue
        ax.axvline(ts, color="black", alpha=0.25, linewidth=0.8, linestyle="--")
        ax.text(
            ts, label_y, label,
            rotation=90, va="top", ha="right",
            fontsize=8, color="black", alpha=0.6,
        )


def render(df: pd.DataFrame, *, symbol: str, out_path: Path) -> None:
    if df.empty:
        raise ValueError("history dataframe is empty — run build_gex_history.py first")

    df = df.sort_values("date").reset_index(drop=True)
    df["net_gex_bs_bn"] = df["net_gex_bs"] / 1e9
    df["spot_vs_flip_pct"] = (df["spot"] - df["flip_level_bs"]) / df["spot"] * 100

    fig, axes = plt.subplots(
        3, 1, figsize=(14, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 2, 1.5], "hspace": 0.08},
    )
    ax_price, ax_gex, ax_flip = axes

    ax_price.plot(df["date"], df["spot"], color="black", linewidth=1.0)
    ax_price.set_ylabel(f"{symbol} close ($)")
    ax_price.set_title(
        f"{symbol} dealer positioning: price, net GEX, and gamma-flip distance\n"
        f"({df['date'].min().date()} → {df['date'].max().date()}, "
        f"{len(df)} EoD snapshots)",
        loc="left",
    )
    ax_price.grid(True, alpha=0.3)
    _annotate_events(ax_price, df)

    positive = df["net_gex_bs_bn"] >= 0
    ax_gex.fill_between(
        df["date"], 0, df["net_gex_bs_bn"],
        where=positive, color="tab:green", alpha=0.35, step="post", label="long-gamma regime",
    )
    ax_gex.fill_between(
        df["date"], 0, df["net_gex_bs_bn"],
        where=~positive, color="tab:red", alpha=0.35, step="post", label="short-gamma regime",
    )
    ax_gex.plot(df["date"], df["net_gex_bs_bn"], color="black", linewidth=0.7)
    ax_gex.axhline(0, color="black", linewidth=0.8)
    ax_gex.set_ylabel("net GEX ($B per $1 spot move)")
    ax_gex.grid(True, alpha=0.3)
    ax_gex.legend(loc="upper left", fontsize=9)

    valid_flip = df["spot_vs_flip_pct"].notna()
    if valid_flip.any():
        above = valid_flip & (df["spot_vs_flip_pct"] >= 0)
        below = valid_flip & (df["spot_vs_flip_pct"] < 0)
        ax_flip.scatter(
            df.loc[above, "date"], df.loc[above, "spot_vs_flip_pct"],
            s=4, color="tab:green", label="spot > flip",
        )
        ax_flip.scatter(
            df.loc[below, "date"], df.loc[below, "spot_vs_flip_pct"],
            s=4, color="tab:red", label="spot < flip",
        )
    ax_flip.axhline(0, color="black", linewidth=0.8)
    ax_flip.set_ylabel("(spot - flip) / spot (%)")
    ax_flip.set_xlabel("date")
    ax_flip.grid(True, alpha=0.3)
    ax_flip.legend(loc="upper left", fontsize=9)

    ax_flip.xaxis.set_major_locator(mdates.YearLocator())
    ax_flip.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax_flip.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def summarize_regimes(df: pd.DataFrame) -> None:
    if df.empty:
        return
    n = len(df)
    n_long = int((df["net_gex_bs"] > 0).sum())
    n_short = int((df["net_gex_bs"] < 0).sum())
    n_flip_found = int(df["flip_level_bs"].notna().sum())
    n_spot_above = int(((df["spot"] - df["flip_level_bs"]) > 0).sum())

    print("=== regime summary ===")
    print(f"days:                       {n}")
    print(f"net_gex > 0 (long gamma):   {n_long} ({n_long / n:.0%})")
    print(f"net_gex < 0 (short gamma):  {n_short} ({n_short / n:.0%})")
    print(f"flip level found:           {n_flip_found} ({n_flip_found / n:.0%})")
    if n_flip_found > 0:
        print(f"  spot > flip (positive distance): {n_spot_above} ({n_spot_above / n_flip_found:.0%})")
    print()
    by_year = df.assign(year=df["date"].dt.year).groupby("year").agg(
        n=("date", "count"),
        median_gex_bn=("net_gex_bs", lambda s: float(np.median(s)) / 1e9),
        pct_short_gamma=("net_gex_bs", lambda s: float((s < 0).mean())),
    )
    print("=== by year ===")
    print(by_year.to_string(float_format=lambda x: f"{x:>8.3f}"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    src = _history_path(args.symbol)
    if not src.exists():
        print(f"history file not found: {src}")
        print("run: python scripts/build_gex_history.py --symbol {args.symbol}")
        return 1

    df = pd.read_parquet(src)
    df["date"] = pd.to_datetime(df["date"])

    summarize_regimes(df)

    out = _plot_path(args.symbol)
    render(df, symbol=args.symbol, out_path=out)
    print(f"\nwrote plot to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
