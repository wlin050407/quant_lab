"""Session VWAP and price deviation metrics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VwapMetrics:
    vwap: float
    last_close: float
    deviation_pct: float
    above_vwap: bool


def session_vwap_metrics(intraday: pd.DataFrame) -> VwapMetrics:
    """Compute session VWAP from intraday OHLCV bars."""
    if intraday.empty:
        return VwapMetrics(
            vwap=float("nan"),
            last_close=float("nan"),
            deviation_pct=float("nan"),
            above_vwap=False,
        )

    close = pd.to_numeric(intraday["close"], errors="coerce")
    volume = pd.to_numeric(intraday["volume"], errors="coerce").fillna(0.0)
    last_close = float(close.iloc[-1])
    total_vol = float(volume.sum())
    if total_vol <= 0:
        vwap = float(close.mean())
    else:
        vwap = float((close * volume).sum() / total_vol)

    if not np.isfinite(vwap) or vwap == 0:
        dev = float("nan")
    else:
        dev = float((last_close - vwap) / vwap * 100.0)

    return VwapMetrics(
        vwap=vwap,
        last_close=last_close,
        deviation_pct=dev,
        above_vwap=bool(np.isfinite(dev) and dev > 0),
    )
