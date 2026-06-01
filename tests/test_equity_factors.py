"""Tests for equity factor functions."""

from __future__ import annotations

import pandas as pd

from quant_lab.factors.equity.relative_strength import relative_strength_vs_benchmark
from quant_lab.factors.equity.vwap import session_vwap_metrics


def test_session_vwap_hand_example() -> None:
    df = pd.DataFrame(
        {
            "open": [100.0, 102.0],
            "high": [101.0, 103.0],
            "low": [99.0, 101.0],
            "close": [100.0, 104.0],
            "adj_close": [100.0, 104.0],
            "volume": [1000.0, 3000.0],
            "symbol": "X",
        },
        index=pd.date_range("2026-01-02 14:30", periods=2, freq="5min", tz="UTC"),
    )
    m = session_vwap_metrics(df)
    # VWAP = (100*1000 + 104*3000) / 4000 = 103
    assert m.vwap == 103.0
    assert m.last_close == 104.0
    assert abs(m.deviation_pct - (104 - 103) / 103 * 100) < 1e-6
    assert m.above_vwap is True


def test_relative_strength_spread() -> None:
    idx = pd.date_range("2025-01-01", periods=130, freq="B", tz="UTC")
    stock = pd.DataFrame({"close": [100 + i * 0.5 for i in range(130)]}, index=idx)
    bench = pd.DataFrame({"close": [100 + i * 0.1 for i in range(130)]}, index=idx)
    rs = relative_strength_vs_benchmark(stock, bench)
    assert rs.rs_5d > 0
    assert rs.rs_20d > 0
