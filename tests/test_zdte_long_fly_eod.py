"""EoD long call butterfly @ King tests."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.strategies.zdte_long_fly_eod import (
    long_call_butterfly_expiry_value,
    long_call_butterfly_pnl_hand,
    simulate_long_fly_trade,
)


def _sample_chain() -> pd.DataFrame:
    rows = []
    spot = 100.0
    for strike in range(95, 106):
        for right in ("C", "P"):
            if right == "C":
                otm = max(strike - spot, 0.0)
            else:
                otm = max(spot - strike, 0.0)
            mid = max(0.15, 2.5 - 0.35 * otm)
            rows.append(
                {
                    "strike": float(strike),
                    "right": right,
                    "dte": 1,
                    "bid": mid - 0.05,
                    "ask": mid + 0.05,
                    "last_price": mid,
                    "open_interest": 1000,
                    "implied_volatility": 0.20,
                }
            )
    return pd.DataFrame(rows)


def test_long_call_butterfly_expiry_value_at_center() -> None:
    """At spot=K, long call fly value equals wing width."""
    value = long_call_butterfly_expiry_value(
        100.0,
        lower_call=98.0,
        center=100.0,
        upper_call=102.0,
    )
    assert value == pytest.approx(2.0)


def test_long_call_butterfly_pnl_hand_profit_at_pin() -> None:
    exit_value, pnl = long_call_butterfly_pnl_hand(
        spot_exit=100.0,
        center=100.0,
        wing_width=2.0,
        entry_debit=0.25,
        commission_per_contract=0.0,
    )
    assert exit_value == pytest.approx(2.0)
    assert pnl == pytest.approx(175.0)


def test_long_call_butterfly_pnl_hand_max_loss_beyond_wing() -> None:
    exit_value, pnl = long_call_butterfly_pnl_hand(
        spot_exit=105.0,
        center=100.0,
        wing_width=2.0,
        entry_debit=0.25,
        commission_per_contract=0.0,
    )
    assert exit_value == pytest.approx(0.0)
    assert pnl == pytest.approx(-25.0)


def test_simulate_long_fly_king_mode() -> None:
    rows = []
    for strike, mid in ((98.0, 1.80), (100.0, 1.00), (102.0, 1.80)):
        for right in ("C", "P"):
            rows.append(
                {
                    "strike": strike,
                    "right": right,
                    "dte": 1,
                    "bid": mid - 0.02,
                    "ask": mid + 0.02,
                    "last_price": mid,
                    "open_interest": 1000,
                    "implied_volatility": 0.20,
                }
            )
    chain = pd.DataFrame(rows)
    trade = simulate_long_fly_trade(
        chain,
        signal_date="2024-01-02",
        trade_date="2024-01-03",
        spot_signal=99.0,
        spot_exit=100.0,
        net_gex_bs=1e10,
        center_mode="king",
        king_dte1=100.0,
        max_pain_dte1=float("nan"),
        expected_move_1sd=2.0,
        wing_width=2.0,
        regime_filter="none",
        commission_per_contract=0.0,
    )
    assert trade is not None
    assert trade.center_strike == 100.0
    assert trade.entry_debit > 0
    assert trade.pnl_per_contract > 0
