"""Phase 3b EoD iron condor simulation tests."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.strategies.zdte_ic_eod import (
    credit_spread_entry_credit,
    credit_spread_exit_cost,
    iron_condor_pnl,
    passes_regime_filter,
    resolve_ic_strikes,
    simulate_ic_trade,
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


def test_credit_spread_entry_and_exit() -> None:
    short_row = pd.Series({"bid": 2.0, "ask": 2.0, "last_price": 2.0})
    long_row = pd.Series({"bid": 0.5, "ask": 0.5, "last_price": 0.5})
    credit = credit_spread_entry_credit(short_row, long_row)
    assert credit == pytest.approx(1.5)
    cost = credit_spread_exit_cost(100.0, 102.0, 104.0, "C")
    assert cost == pytest.approx(0.0)
    cost_itm = credit_spread_exit_cost(105.0, 102.0, 104.0, "C")
    assert cost_itm == pytest.approx(2.0)


def test_iron_condor_pnl_max_profit() -> None:
    exit_cost, pnl = iron_condor_pnl(
        spot_exit=100.0,
        short_call=104.0,
        long_call=106.0,
        short_put=96.0,
        long_put=94.0,
        entry_credit=2.0,
        commission_per_contract=0.0,
    )
    assert exit_cost == pytest.approx(0.0)
    assert pnl == pytest.approx(200.0)


def test_regime_filter_long_gamma() -> None:
    assert passes_regime_filter(1.0, regime_filter="long_gamma_only") is True
    assert passes_regime_filter(-1.0, regime_filter="long_gamma_only") is False


def test_resolve_ic_strikes_expected_move_fallback() -> None:
    chain = _sample_chain()
    resolved = resolve_ic_strikes(
        chain,
        spot=100.0,
        call_wall_strike=99.0,
        put_wall_strike=101.0,
        wing_width=2.0,
        dte=1,
    )
    assert resolved is not None
    short_call, long_call, short_put, long_put, source = resolved
    assert source == "expected_move"
    assert short_call > 100.0
    assert short_put < 100.0
    assert long_call == short_call + 2.0
    assert long_put == short_put - 2.0


def test_simulate_ic_trade_profit_in_range() -> None:
    chain = _sample_chain()
    trade = simulate_ic_trade(
        chain,
        signal_date="2024-01-02",
        trade_date="2024-01-03",
        spot_signal=100.0,
        spot_exit=100.0,
        net_gex_bs=1e10,
        regime_filter="long_gamma_only",
        wing_width=2.0,
        commission_per_contract=0.0,
    )
    assert trade is not None
    assert trade.pnl_per_contract > 0


def test_simulate_skips_short_gamma_when_filtered() -> None:
    chain = _sample_chain()
    trade = simulate_ic_trade(
        chain,
        signal_date="2024-01-02",
        trade_date="2024-01-03",
        spot_signal=100.0,
        spot_exit=100.0,
        net_gex_bs=-1e10,
        regime_filter="long_gamma_only",
        wing_width=2.0,
        commission_per_contract=0.0,
    )
    assert trade is None
