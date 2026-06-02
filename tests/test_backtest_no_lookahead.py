"""Backtest engine must not use same-bar signal for same-bar return."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.backtest.engine import run_backtest


def test_lagged_signal_no_same_day_pnl() -> None:
    """Signal at t applies to return t→t+1 only (via shift(1))."""
    idx = pd.date_range("2024-01-02", periods=4, freq="B")
    prices = pd.Series([100.0, 110.0, 121.0, 133.1], index=idx)
    signals = pd.Series([0.0, 1.0, 1.0, 1.0], index=idx)

    result = run_backtest(prices, signals, slippage_bps=0.0, commission_bps=0.0)
    rets = result.daily_returns.dropna()

    # First day: position 0 → no exposure to 10% jump on day 2
    assert rets.iloc[0] == 0.0
    # Second day: position from signal on day 1 (lagged) earns 10%
    assert rets.iloc[1] == pytest.approx(0.10, rel=1e-6)
