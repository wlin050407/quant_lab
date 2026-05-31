"""Information-coefficient utilities for factor → forward-outcome research.

IC here means the **Spearman rank correlation** between a positioning signal
observed at EoD (t) and a forward outcome over (t, t+1]. We use rank IC because
GEX and flip-distance are heavy-tailed and often non-linear — Pearson would
be dominated by a handful of crisis days.

Typical forward targets for 0DTE / EoD positioning research:

- ``fwd_return``: next-session close-to-close return (directional edge?)
- ``fwd_abs_return``: |next return| (volatility amplification under short gamma?)
- ``fwd_realized_vol``: sqrt(252) × |return| as a crude daily vol proxy
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ICResult:
    signal: str
    target: str
    ic: float
    n: int
    p_value: float | None = None


def align_gex_with_underlying(
    gex: pd.DataFrame,
    underlying: pd.DataFrame,
    *,
    price_col: str = "close",
) -> pd.DataFrame:
    """Join GEX history to underlying bars and compute forward outcomes.

    Expects ``gex`` with columns ``date``, ``spot``, ``net_gex_bs``,
    ``flip_level_bs``. Adds:

        ret_1d           same-day close return (for reference)
        fwd_return       next trading day return
        fwd_abs_return   |fwd_return|
        fwd_realized_vol sqrt(252) * |fwd_return|
        spot_vs_flip_pct (spot - flip) / spot * 100
        net_gex_bn       net_gex_bs / 1e9
        long_gamma       net_gex_bs > 0
    """
    if gex.empty:
        raise ValueError("gex history is empty")

    g = gex.copy()
    g["date"] = pd.to_datetime(g["date"]).dt.normalize()

    u = underlying.copy()
    if not isinstance(u.index, pd.DatetimeIndex):
        raise ValueError("underlying must have a DatetimeIndex")
    u = u.sort_index()
    u["date"] = u.index.tz_convert(None).normalize() if u.index.tz is not None else u.index.normalize()
    u = u.drop_duplicates(subset=["date"], keep="last")
    u["ret_1d"] = u[price_col].pct_change()
    u["fwd_return"] = u[price_col].pct_change().shift(-1)
    u["fwd_abs_return"] = u["fwd_return"].abs()
    u["fwd_realized_vol"] = u["fwd_abs_return"] * np.sqrt(252)

    merged = g.merge(
        u[["date", "ret_1d", "fwd_return", "fwd_abs_return", "fwd_realized_vol"]],
        on="date",
        how="inner",
    )
    merged["spot_vs_flip_pct"] = (merged["spot"] - merged["flip_level_bs"]) / merged["spot"] * 100
    merged["net_gex_bn"] = merged["net_gex_bs"] / 1e9
    merged["long_gamma"] = merged["net_gex_bs"] > 0
    return merged.sort_values("date").reset_index(drop=True)


def spearman_ic(signal: pd.Series, target: pd.Series) -> tuple[float, int]:
    """Spearman rank IC between two aligned series (drop NaN pairs).

    Returns:
        (ic, n_observations)
    """
    frame = pd.DataFrame({"signal": signal, "target": target}).dropna()
    n = len(frame)
    if n < 2:
        return float("nan"), n
    ic = float(frame["signal"].corr(frame["target"], method="spearman"))
    return ic, n


def compute_ic_table(
    df: pd.DataFrame,
    signals: list[str],
    targets: list[str],
) -> pd.DataFrame:
    """Compute IC for every signal × target pair.

    Returns a DataFrame with columns ``signal``, ``target``, ``ic``, ``n``.
    """
    rows: list[dict] = []
    for sig in signals:
        if sig not in df.columns:
            continue
        for tgt in targets:
            if tgt not in df.columns:
                continue
            ic, n = spearman_ic(df[sig], df[tgt])
            rows.append({"signal": sig, "target": tgt, "ic": ic, "n": n})
    return pd.DataFrame(rows)


def ic_by_regime(
    df: pd.DataFrame,
    signal: str,
    target: str,
    *,
    regime_col: str = "long_gamma",
) -> pd.DataFrame:
    """Split IC by a boolean regime column (e.g. long vs short gamma)."""
    rows: list[dict] = []
    for regime_val, group in df.groupby(regime_col, dropna=False):
        ic, n = spearman_ic(group[signal], group[target])
        rows.append(
            {
                "regime": regime_val,
                "signal": signal,
                "target": target,
                "ic": ic,
                "n": n,
            }
        )
    return pd.DataFrame(rows)


def attach_forward_returns(
    factors: pd.DataFrame,
    underlying: pd.DataFrame,
    *,
    date_col: str = "date",
    price_col: str = "close",
) -> pd.DataFrame:
    """Join any daily factor history to underlying bars with forward outcomes."""
    if factors.empty:
        raise ValueError("factors history is empty")

    f = factors.copy()
    f[date_col] = pd.to_datetime(f[date_col]).dt.normalize()

    u = underlying.copy()
    if not isinstance(u.index, pd.DatetimeIndex):
        raise ValueError("underlying must have a DatetimeIndex")
    u = u.sort_index()
    u["date"] = (
        u.index.tz_convert(None).normalize()
        if u.index.tz is not None
        else u.index.normalize()
    )
    u = u.drop_duplicates(subset=["date"], keep="last")
    u["ret_1d"] = u[price_col].pct_change()
    u["fwd_return"] = u[price_col].pct_change().shift(-1)
    u["fwd_abs_return"] = u["fwd_return"].abs()
    u["fwd_realized_vol"] = u["fwd_abs_return"] * np.sqrt(252)

    merged = f.merge(
        u[["date", "ret_1d", "fwd_return", "fwd_abs_return", "fwd_realized_vol"]],
        on="date",
        how="inner",
    )
    return merged.sort_values(date_col).reset_index(drop=True)


def ic_by_year(
    df: pd.DataFrame,
    signal: str,
    target: str,
    *,
    date_col: str = "date",
) -> pd.DataFrame:
    """Split Spearman IC by calendar year."""
    work = df.copy()
    work["year"] = pd.to_datetime(work[date_col]).dt.year
    rows: list[dict] = []
    for year, group in work.groupby("year", sort=True):
        ic, n = spearman_ic(group[signal], group[target])
        rows.append(
            {
                "year": int(year),
                "signal": signal,
                "target": target,
                "ic": ic,
                "n": n,
            }
        )
    return pd.DataFrame(rows)
