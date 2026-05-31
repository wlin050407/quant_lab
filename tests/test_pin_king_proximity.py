"""Unit tests for Phase 3e pin → King proximity."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.factors.pin_king_proximity import (
    build_proximity_frame,
    compare_pin_strata,
    pin_tier,
    proximity_ic,
)


def test_pin_tier_buckets() -> None:
    assert pin_tier(75.0) == "high"
    assert pin_tier(70.0) == "high"
    assert pin_tier(55.0) == "mid"
    assert pin_tier(49.0) == "low"
    assert pin_tier(float("nan")) == "unknown"


def test_build_proximity_frame_same_day_hand_computed() -> None:
    """King=100, close=100.5 → abs_dist_pct ≈ 0.4975%."""
    terminal = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-03"]),
            "spot": [100.0],
            "king_dte1": [100.0],
            "pin_score": [80.0],
            "regime": ["long_gamma"],
            "n_contracts_dte1": [100.0],
            "expected_move_1sd": [2.0],
            "symbol": ["SPY"],
        }
    )
    idx = pd.to_datetime(["2024-06-03"]).tz_localize("UTC")
    underlying = pd.DataFrame({"close": [100.5]}, index=idx)

    frame = build_proximity_frame(terminal, underlying, mode="same_day", min_dte1_contracts=50)
    row = frame.iloc[0]
    assert bool(row["valid"]) is True
    assert row["abs_dist_pts"] == pytest.approx(0.5)
    assert row["abs_dist_pct"] == pytest.approx(0.5 / 100.5 * 100.0)
    assert bool(row["within_em"]) is True
    assert bool(row["within_half_em"]) is True


def test_build_proximity_frame_next_session_hand_computed() -> None:
    """Signal Mon king=400; Tue close=401 → dist 1 pt."""
    terminal = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-03", "2024-06-04"]),
            "spot": [399.0, 400.0],
            "king_dte1": [400.0, 400.0],
            "pin_score": [80.0, 30.0],
            "regime": ["long_gamma", "long_gamma"],
            "n_contracts_dte1": [100.0, 100.0],
            "expected_move_1sd": [5.0, 5.0],
            "symbol": ["SPY", "SPY"],
        }
    )
    idx = pd.to_datetime(["2024-06-03", "2024-06-04", "2024-06-05"]).tz_localize("UTC")
    underlying = pd.DataFrame({"close": [399.0, 401.0, 402.0]}, index=idx)

    frame = build_proximity_frame(terminal, underlying, mode="next_session", min_dte1_contracts=50)
    row0 = frame.loc[frame["date"] == pd.Timestamp("2024-06-03")].iloc[0]
    assert row0["outcome_close"] == pytest.approx(401.0)
    assert row0["abs_dist_pts"] == pytest.approx(1.0)
    assert row0["abs_dist_pct"] == pytest.approx(1.0 / 401.0 * 100.0)


def test_proximity_ic_higher_pin_closer() -> None:
    terminal = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "spot": [100.0, 100.0, 100.0, 100.0],
            "king_dte1": [100.0, 100.0, 100.0, 100.0],
            "pin_score": [90.0, 80.0, 40.0, 20.0],
            "regime": ["long_gamma"] * 4,
            "n_contracts_dte1": [100.0] * 4,
            "expected_move_1sd": [5.0] * 4,
            "symbol": ["SPY"] * 4,
        }
    )
    idx = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    ).tz_localize("UTC")
    underlying = pd.DataFrame({"close": [100.1, 100.2, 101.0, 102.0]}, index=idx)

    frame = build_proximity_frame(terminal, underlying, mode="same_day", min_dte1_contracts=50)
    ic, n = proximity_ic(frame)
    assert n == 4
    assert ic == pytest.approx(1.0)
