"""Intraday 0DTE time / IV / EM helpers for pin score v2."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.factors.positioning import (
    PIN_SCORE_MODEL_VERSION,
    atm_iv_from_chain,
    expected_move_1sd,
    pin_score_from_chain,
    resolve_cohort_time_years,
)


def _0dte_row(strike: float = 5900.0, iv: float = 0.18, oi: int = 500) -> dict:
    return {
        "symbol": "SPXW",
        "expiry": pd.Timestamp("2026-05-29").date(),
        "strike": strike,
        "right": "C",
        "dte": 0,
        "bid": 10.0,
        "ask": 10.2,
        "last_price": 10.1,
        "implied_volatility": iv,
        "volume": 100,
        "open_interest": oi,
        "in_the_money": True,
        "time_to_expiry_years": 3.0 / (365.0 * 6.5),
    }


def test_resolve_cohort_time_from_intraday_column() -> None:
    chain = pd.DataFrame([_0dte_row(), {**_0dte_row(strike=5910.0), "right": "P"}])
    t = resolve_cohort_time_years(chain, dte_max=1)
    assert t == pytest.approx(3.0 / (365.0 * 6.5), rel=1e-6)


def test_resolve_cohort_time_from_hours_to_close() -> None:
    chain = pd.DataFrame([{**_0dte_row(), "time_to_expiry_years": None}])
    chain["time_to_expiry_years"] = float("nan")
    t = resolve_cohort_time_years(chain, dte_max=1, hours_to_close=3.0)
    assert t == pytest.approx(3.0 / (365.0 * 6.5), rel=1e-6)


def test_atm_iv_dte_zero_bucket() -> None:
    chain = pd.DataFrame(
        [
            _0dte_row(strike=5900.0, iv=0.20),
            {**_0dte_row(strike=5910.0, iv=0.22), "right": "P"},
        ]
    )
    iv = atm_iv_from_chain(chain, spot=5900.0, dte_max=1)
    assert iv == pytest.approx(0.20)


def test_expected_move_uses_time_years_not_integer_dte() -> None:
    t = 3.0 / (365.0 * 6.5)
    em = expected_move_1sd(5900.0, 0.20, time_years=t)
    assert em == pytest.approx(5900.0 * 0.20 * (t**0.5), rel=1e-6)


def test_pin_score_from_chain_0dte_finite() -> None:
    rows = [_0dte_row(strike=5900.0), {**_0dte_row(strike=5910.0), "right": "P"}]
    for k in (5850.0, 5950.0):
        rows.append({**_0dte_row(strike=k, oi=50), "right": "P"})
        rows.append({**_0dte_row(strike=k, oi=50), "right": "C"})
    chain = pd.DataFrame(rows)
    result = pin_score_from_chain(chain, 5900.0, dte_max=1, hours_to_close=3.0)
    assert PIN_SCORE_MODEL_VERSION == "v2"
    assert result.score >= 0.0
    assert result.score <= 100.0
    assert result.components["magnet_proximity"] >= 0.0


def test_atm_iv_legacy_dte_one_still_works() -> None:
    chain = pd.DataFrame(
        [
            {**_0dte_row(iv=0.20), "dte": 1},
            {**_0dte_row(strike=5910.0, iv=0.25), "dte": 1, "right": "P"},
        ]
    )
    iv = atm_iv_from_chain(chain, spot=5900.0, dte=1)
    assert iv == pytest.approx(0.20)
