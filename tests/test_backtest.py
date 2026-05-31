"""Backtest engine tests."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.backtest.engine import run_backtest
from quant_lab.strategies.baseline_zscore import zscore_mean_reversion_signals


def test_constant_long_matches_compounded_return() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    prices = pd.Series([100.0, 110.0, 121.0], index=idx)
    signals = pd.Series([1.0, 1.0, 1.0], index=idx)
    result = run_backtest(prices, signals, slippage_bps=0.0, commission_bps=0.0)
    assert result.stats.total_return == pytest.approx(0.21)
    assert result.stats.turnover == pytest.approx(1.0)


def test_zero_signal_flat_equity() -> None:
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    prices = pd.Series([100.0, 105.0, 103.0, 108.0, 110.0], index=idx)
    signals = pd.Series([0.0] * 5, index=idx)
    result = run_backtest(prices, signals, slippage_bps=0.0)
    assert result.stats.total_return == pytest.approx(0.0)


def test_slippage_reduces_return() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    prices = pd.Series([100.0, 110.0, 121.0], index=idx)
    signals = pd.Series([0.0, 1.0, 1.0], index=idx)
    no_cost = run_backtest(prices, signals, slippage_bps=0.0).stats.total_return
    with_cost = run_backtest(prices, signals, slippage_bps=10.0).stats.total_return
    assert with_cost < no_cost


def test_zscore_signal_is_bounded() -> None:
    idx = pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC")
    close = pd.Series(range(100, 120), index=idx, dtype="float64")
    sig = zscore_mean_reversion_signals(close, window=5)
    assert sig.min() >= -1.0
    assert sig.max() <= 1.0
