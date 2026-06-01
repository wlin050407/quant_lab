"""Tests for equity factor functions."""

from __future__ import annotations

import pandas as pd
import numpy as np

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


def test_relative_strength_aligns_calendars() -> None:
    """Shared trading dates only — benchmark gaps must not shift lookback."""
    ticker_idx = pd.date_range("2025-01-01", periods=6, freq="B", tz="UTC")
    bench_idx = ticker_idx.delete(3)
    stock = pd.DataFrame({"close": [100.0, 100.0, 100.0, 101.0, 101.0, 101.0]}, index=ticker_idx)
    bench = pd.DataFrame({"close": [50.0, 50.0, 50.0, 50.0, 50.0]}, index=bench_idx)
    rs = relative_strength_vs_benchmark(stock, bench)
    assert rs.rs_1d == 0.0


def test_volume_profile_expands_contiguously_from_poc() -> None:
    from quant_lab.factors.equity.volume_profile import volume_profile

    prices = list(np.linspace(90.0, 100.0, 11))
    volumes = [800.0] + [10.0] * 9 + [50.0]
    df = pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": volumes,
        },
        index=pd.date_range("2026-01-02 14:30", periods=11, freq="5min", tz="UTC"),
    )
    profile = volume_profile(df, n_bins=11, value_area_pct=0.70)
    assert profile.vah == profile.val
    assert profile.vah < prices[-1]


def test_amihud_percentile_threshold() -> None:
    from quant_lab.factors.equity.liquidity import amihud_illiquidity, amihud_percentile_threshold

    idx = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")
    close = pd.Series(100 + np.sin(np.arange(300)) * 0.5, index=idx)
    volume = pd.Series(1_000_000.0, index=idx)
    daily = pd.DataFrame({"close": close, "volume": volume})
    current = amihud_illiquidity(daily)
    threshold = amihud_percentile_threshold(daily)
    assert np.isfinite(current)
    assert np.isfinite(threshold)
