"""Unit tests for factors/positioning.py — hand-computed where possible."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from quant_lab.factors.positioning import (
    max_pain,
    oi_by_strike,
    oi_concentration,
    pin_magnet_ranking,
    pin_score_components,
    put_call_ratio,
)


def _row(strike: float, right: str, oi: int, *, dte: int = 7, vol: int = 0) -> dict:
    return {
        "strike": strike,
        "right": right,
        "open_interest": oi,
        "volume": vol,
        "dte": dte,
    }


def test_put_call_ratio_oi() -> None:
    chain = pd.DataFrame(
        [
            _row(100, "C", 1000),
            _row(100, "P", 500),
            _row(105, "C", 200),
        ]
    )
    assert put_call_ratio(chain, kind="open_interest") == pytest.approx(500 / 1200)


def test_put_call_ratio_volume() -> None:
    chain = pd.DataFrame(
        [
            _row(100, "C", 0, vol=100),
            _row(100, "P", 0, vol=300),
        ]
    )
    assert put_call_ratio(chain, kind="volume") == pytest.approx(3.0)


def test_put_call_ratio_nan_when_no_calls() -> None:
    chain = pd.DataFrame([_row(100, "P", 100)])
    assert math.isnan(put_call_ratio(chain, kind="open_interest"))


def test_max_pain_hand_computed() -> None:
    """Two strikes, symmetric OI — max pain at the lower strike when puts dominate below.

    Calls at 100 (OI=100), puts at 100 (OI=100).
    At S=100: payout = 0.
    At S=105: call payout = 5*100*100 = 50k, put payout = 0 → 50k.
    At S=95:  put payout = 5*100*100 = 50k, call payout = 0 → 50k.
    Minimum at S=100.
    """
    chain = pd.DataFrame(
        [
            _row(100, "C", 100),
            _row(100, "P", 100),
        ]
    )
    assert max_pain(chain) == pytest.approx(100.0)


def test_max_pain_skews_toward_put_heavy_strike() -> None:
    """Heavy put OI at 95 vs light activity at 100 — pain minimum stays at 100."""
    chain = pd.DataFrame(
        [
            _row(100, "C", 10),
            _row(100, "P", 10),
            _row(95, "P", 1000),
        ]
    )
    assert max_pain(chain) == pytest.approx(100.0)


def test_max_pain_respects_dte_filter() -> None:
    chain = pd.DataFrame(
        [
            _row(100, "C", 100, dte=1),
            _row(100, "P", 100, dte=1),
            _row(90, "P", 5000, dte=30),
        ]
    )
    assert max_pain(chain, dte_max=1) == pytest.approx(100.0)


def test_oi_concentration_top_n() -> None:
    chain = pd.DataFrame(
        [
            _row(100, "C", 100),
            _row(100, "P", 100),
            _row(105, "C", 50),
            _row(105, "P", 50),
            _row(110, "C", 10),
        ]
    )
    # total OI = 310, top-1 strike (100) = 200 → 200/310
    assert oi_concentration(chain, top_n=1) == pytest.approx(200 / 310)
    # top-2 strikes (100+105) = 300 → 300/310
    assert oi_concentration(chain, top_n=2) == pytest.approx(300 / 310)


def test_oi_by_strike_splits_calls_puts() -> None:
    chain = pd.DataFrame(
        [
            _row(100, "C", 10),
            _row(100, "P", 20),
            _row(105, "C", 5),
        ]
    )
    out = oi_by_strike(chain)
    assert out.loc[100, "call_oi"] == 10
    assert out.loc[100, "put_oi"] == 20
    assert out.loc[100, "total_oi"] == 30
    assert out.loc[105, "total_oi"] == 5


def test_pin_magnet_ranking_weights_sum_to_100() -> None:
    rows = [
        {"strike": 7600.0, "net_gex": 2.0e9, "net_gex_bn": 2.0, "total_oi": 1000.0},
        {"strike": 7550.0, "net_gex": -1.0e9, "net_gex_bn": -1.0, "total_oi": 2000.0},
        {"strike": 7650.0, "net_gex": 0.5e9, "net_gex_bn": 0.5, "total_oi": 500.0},
    ]
    ranked = pin_magnet_ranking(rows, spot=7580.0, king=7600.0, max_pain=7550.0, top_n=3)
    assert len(ranked) == 3
    assert sum(float(r["weight_pct"]) for r in ranked) == pytest.approx(100.0, rel=1e-6)
    king_row = next(r for r in ranked if "king" in r["tags"])
    assert king_row["strike"] == pytest.approx(7600.0)


def test_pin_score_components_hand_computed() -> None:
    parts = pin_score_components(
        spot=100.0,
        magnet_strike=100.0,
        oi_concentration_top3=0.45,
        net_gex_bn_per_1pct=3.0,
        time_to_close_pct=100.0,
    )
    assert parts["oi_concentration"] == pytest.approx(100.0)
    assert parts["magnet_proximity"] == pytest.approx(100.0)
    assert parts["time_remaining"] == pytest.approx(100.0)
    assert parts["gamma_magnitude"] == pytest.approx(100.0)
