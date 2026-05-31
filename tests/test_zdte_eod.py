"""Phase 3 EoD 0DTE simulation tests."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.backtest.bs76 import bs_call_price, intrinsic_value
from quant_lab.strategies.zdte_directional_eod import (
    compute_direction,
    passes_regime_filter,
    select_atm_contract,
    simulate_one_trade,
    trades_to_daily_returns,
)


def test_intrinsic_call_itm() -> None:
    assert intrinsic_value(110.0, 100.0, "C") == pytest.approx(10.0)


def test_compute_direction_flip() -> None:
    assert compute_direction(spot=510.0, flip_level=500.0, max_pain=500.0, signal="spot_vs_flip") == 1
    assert compute_direction(spot=490.0, flip_level=500.0, max_pain=500.0, signal="spot_vs_flip") == -1


def test_regime_filter_short_gamma() -> None:
    assert passes_regime_filter(-1.0, regime_filter="short_gamma_only") is True
    assert passes_regime_filter(1.0, regime_filter="short_gamma_only") is False


def test_select_atm_contract() -> None:
    chain = pd.DataFrame(
        {
            "strike": [99.0, 100.0, 101.0],
            "right": ["C", "C", "C"],
            "dte": [1, 1, 1],
            "bid": [1.0, 2.0, 0.5],
            "ask": [1.2, 2.2, 0.7],
            "last_price": [1.1, 2.1, 0.6],
            "implied_volatility": [0.2, 0.2, 0.2],
        }
    )
    row = select_atm_contract(chain, spot=100.4, right="C", dte=1)
    assert row is not None
    assert float(row["strike"]) == pytest.approx(100.0)


def test_simulate_one_trade_call_profit() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0],
            "right": ["C"],
            "dte": [1],
            "bid": [2.0],
            "ask": [2.0],
            "last_price": [2.0],
            "implied_volatility": [0.25],
        }
    )
    trade = simulate_one_trade(
        chain,
        signal_date="2024-01-02",
        trade_date="2024-01-03",
        spot_signal=100.0,
        spot_exit=105.0,
        net_gex_bs=-1e10,
        flip_level=99.0,
        max_pain=100.0,
        direction_signal="spot_vs_flip",
        regime_filter="short_gamma_only",
        exit_mode="intrinsic",
        commission_per_contract=0.0,
        r=0.05,
        q=0.013,
    )
    assert trade is not None
    assert trade.pnl_per_contract == pytest.approx(300.0)


def test_simulate_skips_long_gamma_when_filtered() -> None:
    chain = pd.DataFrame(
        {
            "strike": [100.0],
            "right": ["C"],
            "dte": [1],
            "bid": [2.0],
            "ask": [2.0],
            "last_price": [2.0],
            "implied_volatility": [0.25],
        }
    )
    trade = simulate_one_trade(
        chain,
        signal_date="2024-01-02",
        trade_date="2024-01-03",
        spot_signal=100.0,
        spot_exit=105.0,
        net_gex_bs=1e10,
        flip_level=99.0,
        max_pain=100.0,
        direction_signal="spot_vs_flip",
        regime_filter="short_gamma_only",
        exit_mode="intrinsic",
        commission_per_contract=0.0,
        r=0.05,
        q=0.013,
    )
    assert trade is None


def test_trades_to_daily_returns() -> None:
    trades = pd.DataFrame(
        {
            "trade_date": ["2024-01-03", "2024-01-04"],
            "pnl_per_contract": [100.0, -50.0],
        }
    )
    ret = trades_to_daily_returns(trades, initial_cash=10_000.0, contracts=1)
    assert len(ret) == 2
    assert ret.iloc[0] == pytest.approx(0.01)


def test_bs_call_price_positive() -> None:
    px = bs_call_price(100.0, 100.0, 30 / 365, 0.2)
    assert px > 0
