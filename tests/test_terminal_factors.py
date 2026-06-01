"""Tests for Ultimate Terminal M1 factors."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from quant_lab.factors.gex import (
    compute_dealer_gamma_exposure,
    compute_gex_profile,
    king_node,
    strongest_ceiling,
    strongest_floor,
)
from quant_lab.factors.positioning import expected_move_1sd, pin_score
from quant_lab.factors.regime import pin_reliability, pin_score_regime_adjusted, regime_from_net_gex, should_trade_zdte
from quant_lab.factors.trinity import trinity_from_kings, trinity_score


def _per_strike() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "call_oi": [0, 0, 0],
            "put_oi": [0, 0, 0],
            "call_gex": [1e8, 3e8, 1e7],
            "put_gex": [-2e7, -1e8, -5e8],
            "net_gex": [8e7, 2e8, -4.9e8],
            "total_oi": [0, 0, 0],
        },
        index=[95.0, 100.0, 105.0],
    )


def test_king_node_is_max_abs_net_gex() -> None:
    ps = _per_strike()
    assert king_node(ps) == pytest.approx(105.0)


def test_floor_and_ceiling_relative_to_spot() -> None:
    ps = _per_strike()
    assert strongest_floor(ps, 102.0) == pytest.approx(100.0)
    assert strongest_ceiling(ps, 102.0) == pytest.approx(105.0)


def test_expected_move_1sd_hand() -> None:
    # spot=100, iv=0.20, dte=1 → 100 * 0.2 * sqrt(1/365)
    em = expected_move_1sd(100.0, 0.20, dte=1)
    assert em == pytest.approx(100.0 * 0.20 * (1 / 365) ** 0.5, rel=1e-6)


def test_pin_score_high_when_concentrated_and_near_magnet() -> None:
    score = pin_score(
        spot=100.0,
        magnet_strike=100.5,
        oi_concentration_top3=0.42,
        magnet_gex_bn_per_1pct=2.5,
        time_to_close_pct=100.0,
        expected_move_1sd=2.0,
    )
    assert score > 70.0


def test_regime_from_net_gex() -> None:
    assert regime_from_net_gex(1.0) == "long_gamma"
    assert regime_from_net_gex(-1.0) == "short_gamma"
    assert regime_from_net_gex(0.0) == "undetermined"


def test_pin_score_regime_adjusted_short_gamma() -> None:
    adjusted = pin_score_regime_adjusted(80.0, "short_gamma")
    assert adjusted == pytest.approx(56.0)


def test_pin_reliability_high_long_gamma() -> None:
    tier, _ = pin_reliability(75.0, "long_gamma")
    assert tier == "high"


def test_pin_reliability_caution_short_gamma() -> None:
    tier, detail = pin_reliability(75.0, "short_gamma")
    assert tier == "caution"
    assert "short" in detail.lower()


def test_should_trade_zdte_low_dte_share() -> None:
    ok, reason = should_trade_zdte(
        pct_gex_dte1=10.0,
        pin_score=50.0,
        regime="long_gamma",
    )
    assert ok is False
    assert reason == "low_dte_gex_share"


def test_trinity_score_aligned_support() -> None:
    # Both kings below spot → support alignment
    align = trinity_from_kings(
        spy=(500.0, 495.0),
        spx=(5000.0, 4950.0),
        tolerance_pct=0.02,
    )
    assert align.direction == "support"
    assert align.n_symbols == 2
    assert align.score > 80.0


def test_trinity_score_mixed_direction_low() -> None:
    align = trinity_score(
        [("SPY", 500.0, 510.0), ("SPX", 5000.0, 4900.0)],
        tolerance_pct=0.01,
    )
    assert align.direction == "mixed"
    assert align.score <= 50.0


def test_compute_gex_profile_empty_chain() -> None:
    profile = compute_gex_profile(pd.DataFrame(), spot=100.0, compute_flip=False)
    assert profile.n_contracts == 0
    assert math.isnan(profile.king_node)
