"""Moving-average structure for mid/long horizons."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MaStructure:
    ma20: float
    ma50: float
    ma200: float
    price: float
    above_ma20: bool
    above_ma50: bool
    above_ma200: bool
    ma20_above_ma50: bool


def ma_structure(daily: pd.DataFrame) -> MaStructure:
    close = pd.to_numeric(daily["close"], errors="coerce").dropna()
    if close.empty:
        nan = float("nan")
        return MaStructure(nan, nan, nan, nan, False, False, False, False)

    price = float(close.iloc[-1])

    def sma(n: int) -> float:
        if len(close) < n:
            return float("nan")
        return float(close.tail(n).mean())

    ma20 = sma(20)
    ma50 = sma(50)
    ma200 = sma(200)

    def above(ma: float) -> bool:
        return bool(np.isfinite(ma) and np.isfinite(price) and price > ma)

    return MaStructure(
        ma20=ma20,
        ma50=ma50,
        ma200=ma200,
        price=price,
        above_ma20=above(ma20),
        above_ma50=above(ma50),
        above_ma200=above(ma200),
        ma20_above_ma50=bool(np.isfinite(ma20) and np.isfinite(ma50) and ma20 > ma50),
    )
