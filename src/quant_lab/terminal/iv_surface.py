"""Local IV surface helpers for MM structure (Pin Center P1)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_lab.terminal.mm_structure import round_strike


def iv_floor_strike_from_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    dte_max: int = 1,
    spot_band_pct: float = 0.03,
) -> float | None:
    """Quadratic IV smile fit — strike at synthetic IV floor near spot.

    Uses median IV per strike on the 0DTE cohort. Returns ``None`` when the
    fit is not a convex bowl or the floor lies outside the near-ATM band.
    """
    if chain.empty or not np.isfinite(spot) or spot <= 0:
        return None
    if "implied_volatility" not in chain.columns or "strike" not in chain.columns:
        return None

    work = chain.copy()
    if "dte" in work.columns:
        work["dte"] = pd.to_numeric(work["dte"], errors="coerce")
        work = work[work["dte"] <= dte_max]
    work["strike"] = pd.to_numeric(work["strike"], errors="coerce")
    work["implied_volatility"] = pd.to_numeric(work["implied_volatility"], errors="coerce")
    work = work[
        np.isfinite(work["strike"])
        & np.isfinite(work["implied_volatility"])
        & (work["implied_volatility"] > 0.01)
        & (work["implied_volatility"] < 3.0)
    ]
    if work.empty:
        return None

    by_strike = work.groupby("strike", as_index=False)["implied_volatility"].median()
    lo, hi = spot * (1.0 - spot_band_pct), spot * (1.0 + spot_band_pct)
    band = by_strike[(by_strike["strike"] >= lo) & (by_strike["strike"] <= hi)]
    curve = band if len(band) >= 5 else by_strike
    if len(curve) < 5:
        return None

    strikes = curve["strike"].to_numpy(dtype="float64")
    ivs = curve["implied_volatility"].to_numpy(dtype="float64")
    try:
        a, b, _c = np.polyfit(strikes, ivs, 2)
    except (np.linalg.LinAlgError, ValueError):
        return None
    if not np.isfinite(a) or a <= 1e-12:
        return None

    floor_k = float(-b / (2.0 * a))
    if not np.isfinite(floor_k) or abs(floor_k - spot) / spot > spot_band_pct:
        return None
    return round_strike(floor_k)
