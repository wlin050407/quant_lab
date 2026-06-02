"""Relative strength vs benchmark across horizons."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_lab.factors.equity.prices import price_series_for_returns


@dataclass(frozen=True)
class RelativeStrength:
    rs_1d: float
    rs_5d: float
    rs_20d: float
    rs_60d: float
    rs_120d: float


def _period_return(close: pd.Series, n: int) -> float:
    if len(close) <= n:
        return float("nan")
    end = float(close.iloc[-1])
    start = float(close.iloc[-1 - n])
    if not np.isfinite(start) or start == 0:
        return float("nan")
    return float(end / start - 1.0)


def relative_strength_vs_benchmark(
    ticker_daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
) -> RelativeStrength:
    """Arithmetic RS spread: stock return minus benchmark return over N days (% points)."""
    t_close = price_series_for_returns(ticker_daily)
    b_close = price_series_for_returns(benchmark_daily)
    aligned = pd.concat([t_close.rename("ticker"), b_close.rename("benchmark")], axis=1).dropna()
    if aligned.empty:
        nan = float("nan")
        return RelativeStrength(nan, nan, nan, nan, nan)

    ticker = aligned["ticker"]
    benchmark = aligned["benchmark"]

    def rs(n: int) -> float:
        tr = _period_return(ticker, n)
        br = _period_return(benchmark, n)
        if not np.isfinite(tr) or not np.isfinite(br):
            return float("nan")
        return float((tr - br) * 100.0)

    return RelativeStrength(
        rs_1d=rs(1),
        rs_5d=rs(5),
        rs_20d=rs(20),
        rs_60d=rs(60),
        rs_120d=rs(120),
    )
