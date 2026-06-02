"""Unit tests for pinning zone cluster detection."""

from __future__ import annotations

import pytest

from quant_lab.factors.pin_cluster import (
    CLUSTER_MAX_DIST_PCT,
    detect_pin_cluster,
    compute_zone_break,
    spot_zone_state,
    zone_buffer_pts,
)


def _rankings(
    pairs: list[tuple[float, float]],
) -> list[dict[str, float | list[str]]]:
    return [
        {
            "strike": strike,
            "weight_pct": weight,
            "net_gex_bn": 1.0,
            "oi_share": 0.1,
            "dist_pct": 0.1,
            "tags": [],
        }
        for strike, weight in pairs
    ]


def test_detect_cluster_7600_7615_at_spot_7600() -> None:
    rows = _rankings([(7600.0, 52.0), (7615.0, 49.4)])
    result = detect_pin_cluster(
        rows,
        spot=7600.0,
        symbol="SPX",
        regime="long_gamma",
        pin_reliability="high",
    )
    assert result.is_cluster is True
    assert result.lower == pytest.approx(7600.0)
    assert result.upper == pytest.approx(7615.0)
    assert result.width == pytest.approx(15.0)
    assert result.center == pytest.approx(7607.5)
    assert result.strength_ratio == pytest.approx(49.4 / 52.0, rel=1e-6)
    assert result.cluster_strength == "high"
    assert result.zone_break is not None
    assert result.zone_break.buffer_pts == pytest.approx(5.0)
    assert result.zone_break.up_break_level == pytest.approx(7620.0)
    assert result.zone_break.down_break_level == pytest.approx(7595.0)
    assert result.spot_zone_state == "inside_zone"


def test_no_cluster_when_strikes_too_far() -> None:
    rows = _rankings([(7600.0, 50.0), (7650.0, 48.0)])
    result = detect_pin_cluster(rows, spot=7600.0, symbol="SPX", regime="long_gamma")
    assert result.is_cluster is False
    assert result.merge_reason == "strikes_too_far_apart"


def test_no_cluster_when_secondary_too_weak() -> None:
    rows = _rankings([(7600.0, 80.0), (7615.0, 40.0)])
    result = detect_pin_cluster(rows, spot=7600.0, symbol="SPX", regime="long_gamma")
    assert result.is_cluster is False
    assert result.merge_reason == "secondary_too_weak"


def test_no_cluster_short_gamma() -> None:
    rows = _rankings([(7600.0, 52.0), (7615.0, 49.0)])
    result = detect_pin_cluster(rows, spot=7600.0, symbol="SPX", regime="short_gamma")
    assert result.is_cluster is False
    assert result.merge_reason == "short_gamma_regime"


def test_spot_zone_state_testing_upside() -> None:
    zb = compute_zone_break(7600.0, 7615.0, symbol="SPX", spot=7620.0)
    assert spot_zone_state(7618.0, zone_low=7600.0, zone_high=7615.0, zone_break=zb) == "testing_upside_exit"
    assert spot_zone_state(7625.0, zone_low=7600.0, zone_high=7615.0, zone_break=zb) == "above_break"


def test_spot_zone_state_testing_downside() -> None:
    zb = compute_zone_break(7600.0, 7615.0, symbol="SPX", spot=7590.0)
    assert spot_zone_state(7598.0, zone_low=7600.0, zone_high=7615.0, zone_break=zb) == "testing_downside_exit"
    assert spot_zone_state(7590.0, zone_low=7600.0, zone_high=7615.0, zone_break=zb) == "below_break"


def test_zone_buffer_respects_spy_tick_floor() -> None:
    buf = zone_buffer_pts(zone_width=2.0, symbol="SPY", spot=500.0)
    assert buf == pytest.approx(0.5)


def test_dist_threshold_hand_computed() -> None:
    spot = 7600.0
    max_dist = spot * CLUSTER_MAX_DIST_PCT
    assert max_dist == pytest.approx(22.8)
    assert abs(7600.0 - 7615.0) < max_dist
