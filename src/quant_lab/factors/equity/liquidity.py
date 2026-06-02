"""Liquidity proxies from daily bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_lab.factors.equity.prices import price_series_for_returns, uses_adjusted_close

# Back-compat alias
price_series_for_liquidity = price_series_for_returns


def average_dollar_volume(daily: pd.DataFrame, *, window: int = 20) -> float:
    if daily.empty or len(daily) < 2:
        return float("nan")
    close = price_series_for_returns(daily)
    volume = pd.to_numeric(daily["volume"], errors="coerce")
    dv = (close * volume).tail(window)
    return float(dv.mean())


def amihud_illiquidity(daily: pd.DataFrame, *, window: int = 20) -> float:
    """Mean |return| / dollar volume (Amihud 2002 style, scaled 1e6)."""
    if daily.empty or len(daily) < 3:
        return float("nan")
    close = price_series_for_returns(daily)
    volume = pd.to_numeric(daily["volume"], errors="coerce")
    ret = close.pct_change().abs()
    dollar_vol = (close * volume).replace(0, np.nan)
    illiq = (ret / dollar_vol).tail(window)
    scaled = illiq * 1e6
    return float(scaled.mean())


def amihud_percentile_threshold(
    daily: pd.DataFrame,
    *,
    window: int = 20,
    lookback: int = 252,
    percentile: float = 75.0,
) -> float:
    """Historical percentile of rolling Amihud for this ticker (elevated vs own baseline)."""
    if daily.empty or len(daily) < window + 2:
        return float("nan")
    close = price_series_for_returns(daily)
    volume = pd.to_numeric(daily["volume"], errors="coerce")
    ret = close.pct_change().abs()
    dollar_vol = (close * volume).replace(0, np.nan)
    illiq = (ret / dollar_vol) * 1e6
    rolling = illiq.rolling(window, min_periods=window).mean()
    hist = rolling.dropna().tail(lookback)
    if hist.empty:
        return float("nan")
    return float(np.percentile(hist, percentile))


def liquidity_quality_flags(daily: pd.DataFrame, *, window: int = 20) -> dict[str, bool | int]:
    """Provenance flags for equity L0 disclosure."""
    if daily.empty:
        return {
            "adjusted_price_used": False,
            "zero_volume_days": 0,
        }
    volume = pd.to_numeric(daily["volume"], errors="coerce").tail(window)
    zero_vol = int((volume.fillna(0) <= 0).sum())
    return {
        "adjusted_price_used": uses_adjusted_close(daily),
        "zero_volume_days": zero_vol,
    }
