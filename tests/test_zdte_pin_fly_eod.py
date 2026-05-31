"""Phase 3f EoD iron butterfly @ King tests."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.strategies.zdte_pin_fly_eod import (
    iron_butterfly_pnl_hand,
    resolve_fly_center,
    resolve_fly_strikes,
    simulate_pin_fly_trade,
    wing_width_from_expected_move,
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
                    "open_interest": 1000 + int(otm * 100),
                    "implied_volatility": 0.20,
                }
            )
    return pd.DataFrame(rows)


def test_wing_width_from_expected_move_spy() -> None:
    assert wing_width_from_expected_move(2.3) == pytest.approx(2.0)
    assert wing_width_from_expected_move(0.5) == pytest.approx(1.5)
    assert wing_width_from_expected_move(5.0) == pytest.approx(3.0)


def test_iron_butterfly_pnl_hand_max_profit_at_center() -> None:
    exit_cost, pnl = iron_butterfly_pnl_hand(
        spot_exit=100.0,
        center=100.0,
        wing_width=2.0,
        entry_credit=1.5,
        commission_per_contract=0.0,
    )
    assert exit_cost == pytest.approx(0.0)
    assert pnl == pytest.approx(150.0)


def test_iron_butterfly_pnl_hand_beyond_wing() -> None:
    exit_cost, pnl = iron_butterfly_pnl_hand(
        spot_exit=103.0,
        center=100.0,
        wing_width=2.0,
        entry_credit=1.0,
        commission_per_contract=0.0,
    )
    assert exit_cost == pytest.approx(2.0)
    assert pnl == pytest.approx(-100.0)


def test_resolve_fly_center_king() -> None:
    chain = _sample_chain()
    resolved = resolve_fly_center(
        chain,
        spot=100.0,
        center_mode="king",
        king_dte1=100.0,
        max_pain_dte1=float("nan"),
    )
    assert resolved == (100.0, "king")


def test_simulate_pin_fly_trade_king_mode() -> None:
    chain = _sample_chain()
    trade = simulate_pin_fly_trade(
        chain,
        signal_date="2024-01-02",
        trade_date="2024-01-03",
        spot_signal=100.0,
        spot_exit=100.0,
        net_gex_bs=1e10,
        center_mode="king",
        king_dte1=100.0,
        max_pain_dte1=float("nan"),
        expected_move_1sd=2.0,
        regime_filter="long_gamma_only",
        commission_per_contract=0.0,
    )
    assert trade is not None
    assert trade.center_strike == 100.0
    assert trade.center_source == "king"
    assert trade.pnl_per_contract > 0
