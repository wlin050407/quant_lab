"""Realized volatility regime from daily returns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.factors.equity.prices import price_series_for_returns

VolRegime = Literal["low", "normal", "elevated"]


@dataclass(frozen=True)
class VolRegimeResult:
    regime: VolRegime
    rv_20d_ann: float
    percentile_vs_1y: float


def realized_vol_regime(daily: pd.DataFrame) -> VolRegimeResult:
    close = price_series_for_returns(daily).dropna()
    if len(close) < 25:
        return VolRegimeResult("normal", float("nan"), float("nan"))

    ret = close.pct_change().dropna()
    rv_20 = float(ret.tail(20).std() * np.sqrt(252))
    hist = ret.rolling(20).std().dropna() * np.sqrt(252)
    if hist.empty:
        pct = float("nan")
    else:
        pct = float((hist <= rv_20).mean() * 100.0)

    if not np.isfinite(pct):
        regime: VolRegime = "normal"
    elif pct >= 75:
        regime = "elevated"
    elif pct <= 25:
        regime = "low"
    else:
        regime = "normal"

    return VolRegimeResult(regime=regime, rv_20d_ann=rv_20, percentile_vs_1y=pct)
