"""Intraday bar coverage metrics for equity L2 disclosure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import SESSION_CLOSE, SESSION_OPEN

BarSource = Literal["thetadata", "yfinance"]
EXPECTED_5M_BARS = 78  # 6.5h × 12 five-minute bars per hour


@dataclass(frozen=True)
class IntradaySessionQuality:
    regular_session_only: bool
    bar_interval: str
    expected_bars: int
    actual_bars: int
    missing_bar_pct: float
    premarket_excluded: bool
    intraday_source: BarSource


def intraday_session_quality(
    intraday: pd.DataFrame,
    session_date: date,
    *,
    intraday_source: BarSource,
    bar_interval: str = "5m",
) -> IntradaySessionQuality:
    """Summarize session bar depth for one trading day."""
    if intraday.empty:
        return IntradaySessionQuality(
            regular_session_only=True,
            bar_interval=bar_interval,
            expected_bars=EXPECTED_5M_BARS,
            actual_bars=0,
            missing_bar_pct=100.0,
            premarket_excluded=True,
            intraday_source=intraday_source,
        )

    idx_et = intraday.index.tz_convert(MARKET_TZ)
    dates = pd.Series([ts.date() for ts in idx_et], index=intraday.index)
    session = intraday.loc[dates == session_date]
    if session.empty:
        return IntradaySessionQuality(
            regular_session_only=True,
            bar_interval=bar_interval,
            expected_bars=EXPECTED_5M_BARS,
            actual_bars=0,
            missing_bar_pct=100.0,
            premarket_excluded=True,
            intraday_source=intraday_source,
        )

    times = [ts.time() for ts in session.index.tz_convert(MARKET_TZ)]
    in_rth = sum(1 for t in times if SESSION_OPEN <= t < SESSION_CLOSE)
    actual = int(in_rth)
    missing_pct = float(max(0.0, (1.0 - actual / EXPECTED_5M_BARS) * 100.0))
    return IntradaySessionQuality(
        regular_session_only=True,
        bar_interval=bar_interval,
        expected_bars=EXPECTED_5M_BARS,
        actual_bars=actual,
        missing_bar_pct=round(missing_pct, 1),
        premarket_excluded=True,
        intraday_source=intraday_source,
    )
