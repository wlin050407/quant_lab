"""Intraday session microstructure beyond VWAP."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OpeningSegment:
    """First ~30 minutes (6×5m bars) return vs benchmark, in percentage points."""

    rs_open_30m: float
    ticker_ret_pct: float
    benchmark_ret_pct: float
    n_bars: int


def _session_open_return(intraday: pd.DataFrame, *, n_bars: int = 6) -> float:
    if intraday.empty or len(intraday) < 2:
        return float("nan")
    frame = intraday.sort_index().head(n_bars)
    open_px = float(pd.to_numeric(frame["open"], errors="coerce").iloc[0])
    close_px = float(pd.to_numeric(frame["close"], errors="coerce").iloc[-1])
    if not np.isfinite(open_px) or open_px == 0 or not np.isfinite(close_px):
        return float("nan")
    return float((close_px / open_px - 1.0) * 100.0)


def opening_30m_rs(
    ticker_intraday: pd.DataFrame,
    benchmark_intraday: pd.DataFrame,
    *,
    n_bars: int = 6,
) -> OpeningSegment:
    """Opening auction segment RS vs benchmark (free-data proxy for L2 flow)."""
    t_ret = _session_open_return(ticker_intraday, n_bars=n_bars)
    b_ret = _session_open_return(benchmark_intraday, n_bars=n_bars)
    used = min(n_bars, len(ticker_intraday), len(benchmark_intraday)) if not ticker_intraday.empty else 0
    if not np.isfinite(t_ret) or not np.isfinite(b_ret):
        return OpeningSegment(float("nan"), t_ret, b_ret, used)
    return OpeningSegment(float(t_ret - b_ret), t_ret, b_ret, used)
