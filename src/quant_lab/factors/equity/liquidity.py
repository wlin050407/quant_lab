"""Liquidity proxies from daily bars."""

from __future__ import annotations

import numpy as np
import pandas as pd


def average_dollar_volume(daily: pd.DataFrame, *, window: int = 20) -> float:
    if daily.empty or len(daily) < 2:
        return float("nan")
    close = pd.to_numeric(daily["close"], errors="coerce")
    volume = pd.to_numeric(daily["volume"], errors="coerce")
    dv = (close * volume).tail(window)
    return float(dv.mean())


def amihud_illiquidity(daily: pd.DataFrame, *, window: int = 20) -> float:
    """Mean |return| / dollar volume (Amihud 2002 style, scaled 1e6)."""
    if daily.empty or len(daily) < 3:
        return float("nan")
    close = pd.to_numeric(daily["close"], errors="coerce")
    volume = pd.to_numeric(daily["volume"], errors="coerce")
    ret = close.pct_change().abs()
    dollar_vol = (close * volume).replace(0, np.nan)
    illiq = (ret / dollar_vol).tail(window)
    scaled = illiq * 1e6
    return float(scaled.mean())
