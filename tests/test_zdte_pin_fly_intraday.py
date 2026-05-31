"""Phase 4 intraday Pin Play iron fly tests."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_lab.strategies.zdte_pin_fly_eod import iron_butterfly_entry_credit, wing_width_from_expected_move
from quant_lab.strategies.zdte_pin_fly_intraday import (
    iron_butterfly_mark_to_close,
    simulate_pin_fly_intraday_session,
    spot_stop_triggered,
    unrealized_pnl_per_contract,
)


def _flat_chain(*, spot: float = 4800.0) -> pd.DataFrame:
    center = round(spot / 5) * 5
    rows = []
    for strike in range(int(center - 150), int(center + 151), 5):
        for right in ("C", "P"):
            dist = abs(strike - spot)
            mid = max(0.05, 8.0 - 0.02 * dist)
            oi = 5000 + (50000 if strike == center else 0)
            rows.append(
                {
                    "strike": float(strike),
                    "right": right,
                    "dte": 0,
                    "bid": mid - 0.10,
                    "ask": mid + 0.10,
                    "last_price": mid,
                    "open_interest": oi,
                    "implied_volatility": 0.15,
                }
            )
    return pd.DataFrame(rows)


def test_unrealized_pnl_50pct_profit() -> None:
    pnl = unrealized_pnl_per_contract(
        entry_credit=10.0,
        exit_mark=5.0,
        commission_per_contract=0.0,
    )
    assert pnl == pytest.approx(500.0)


def test_spot_stop_em_breach() -> None:
    assert spot_stop_triggered(
        spot=4850.0,
        spot_entry=4800.0,
        king=4800.0,
        flip=float("nan"),
        expected_move_1sd=30.0,
    )


def test_iron_butterfly_mark_matches_entry_on_same_chain() -> None:
    chain = _flat_chain()
    center = 4800.0
    wing = 25.0
    long_call = center + wing
    long_put = center - wing
    credit = iron_butterfly_entry_credit(
        chain,
        center=center,
        long_call=long_call,
        long_put=long_put,
        dte=0,
    )
    mark = iron_butterfly_mark_to_close(
        chain,
        center=center,
        long_call=long_call,
        long_put=long_put,
        dte=0,
    )
    assert credit == pytest.approx(mark)


def test_simulate_real_session_if_data() -> None:
    from pathlib import Path

    chain_path = Path("data/raw/options/SPXW/2023-07-11/intraday/chain_1300.parquet")
    if not chain_path.is_file():
        pytest.skip("ThetaData chain not available")
    from quant_lab.data.thetadata_chain import load_built_intraday_chain

    chain, meta = load_built_intraday_chain(date(2023, 7, 11), "13:00:00")
    chain_exit, _ = load_built_intraday_chain(date(2023, 7, 11), "15:30:00")
    spot = float(meta["spot"].iloc[0])
    trade = simulate_pin_fly_intraday_session(
        chain,
        session_date=date(2023, 7, 11),
        spot_entry=spot,
        chain_exit=chain_exit,
        require_long_gamma=False,
    )
    assert trade is not None
    assert trade.entry_credit > 0
