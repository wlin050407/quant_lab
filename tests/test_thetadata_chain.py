"""Tests for ThetaData intraday chain builder (no network)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_lab.data.intraday_time import hours_to_close, intraday_time_to_expiry_years
from quant_lab.data.iv_solver import implied_volatility_from_mid
from quant_lab.data.thetadata_chain import assemble_chain_from_quotes_oi
from quant_lab.factors.gex import add_bs_gamma_column, compute_dealer_gamma_exposure


def test_intraday_time_to_expiry_at_1300() -> None:
    d = date(2023, 7, 11)
    hrs = hours_to_close(d, "13:00:00")
    assert 2.9 < hrs < 3.1
    t = intraday_time_to_expiry_years(d, "13:00:00")
    assert t > 0


def test_iv_solver_recovers_known_vol() -> None:
    from quant_lab.backtest.bs76 import bs_call_price

    spot, strike, t, vol = 4500.0, 4500.0, 0.01, 0.18
    mid = bs_call_price(spot, strike, t, vol)
    solved = implied_volatility_from_mid(spot, strike, "C", mid, t)
    assert abs(solved - vol) < 0.01


def test_assemble_chain_produces_gex_heatmap_rows() -> None:
    quotes = pd.DataFrame(
        {
            "strike": [4500.0, 4500.0, 4510.0, 4510.0],
            "right": ["CALL", "PUT", "CALL", "PUT"],
            "bid": [10.0, 9.0, 5.0, 12.0],
            "ask": [10.4, 9.4, 5.4, 12.4],
        }
    )
    oi = pd.DataFrame(
        {
            "strike": [4500.0, 4500.0, 4510.0, 4510.0],
            "right": ["C", "P", "C", "P"],
            "open_interest": [1000, 2000, 500, 800],
        }
    )
    snap = assemble_chain_from_quotes_oi(
        quotes,
        oi,
        spot=4500.0,
        session_date=date(2023, 7, 11),
        time_of_day="13:00:00",
    )
    chain = snap.chain
    assert len(chain) == 4
    assert chain["open_interest"].sum() > 0
    assert "effective_open_interest" in chain.columns
    wg = add_bs_gamma_column(chain, snap.spot)
    gex = compute_dealer_gamma_exposure(wg, snap.spot)
    assert len(gex) >= 2
