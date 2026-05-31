"""Tests for SPY → SPX GEX proxy / calibration."""

from __future__ import annotations

import pytest

from quant_lab.factors.calibration import GEXSnapshot
from quant_lab.factors.spx_spy_calibration import (
    SPXCalibrationParams,
    aggregate_paired_calibration,
    calibrate_paired_day,
    default_params,
    list_paired_snapshot_dates,
    spx_chain_quality,
    spy_to_spx_proxy,
    theoretical_gex_scale,
    theoretical_strike_scale,
)


def _snap(
    *,
    date: str = "2026-01-02",
    spot: float = 590.0,
    net_bn: float = -2.0,
    flip: float = 600.0,
    regime: str = "short_gamma",
) -> GEXSnapshot:
    net_internal = net_bn * 1e9 / 0.01
    return GEXSnapshot(
        date=date,
        spot=spot,
        net_gex_dollars_per_dollar=net_internal,
        net_gex_bn_per_1pct=net_bn,
        flip_level=flip,
        spot_above_flip=spot > flip,
        call_wall_strike=600.0,
        put_wall_strike=580.0,
        regime=regime,
    )


def test_theoretical_gex_scale_is_spot_ratio_squared() -> None:
    assert theoretical_gex_scale(590.0, 5900.0) == pytest.approx(100.0)


def test_theoretical_strike_scale() -> None:
    assert theoretical_strike_scale(590.0, 5900.0) == pytest.approx(10.0)


def test_spy_to_spx_proxy_theoretical() -> None:
    spy = _snap(spot=590.0, net_bn=-2.0, flip=600.0)
    proxy = spy_to_spx_proxy(spy, default_params(), spx_spot=5900.0)
    assert proxy.net_gex_bn_per_1pct == pytest.approx(-200.0)
    assert proxy.flip_level == pytest.approx(6000.0)
    assert proxy.regime == "short_gamma"
    assert proxy.gex_scale_k == pytest.approx(100.0)
    assert proxy.method == "theoretical_proxy"


def test_spy_to_spx_proxy_fixed_k() -> None:
    params = SPXCalibrationParams(gex_scale_k=85.0, strike_scale=10.0)
    spy = _snap(net_bn=1.0)
    proxy = spy_to_spx_proxy(spy, params, spx_spot=5900.0)
    assert proxy.net_gex_bn_per_1pct == pytest.approx(85.0)
    assert proxy.method == "empirical_fixed_k"


def test_calibrate_paired_day_uses_empirical_when_spx_usable() -> None:
    spy = _snap(spot=590.0, net_bn=-2.0, regime="short_gamma")
    spx = _snap(spot=5900.0, net_bn=-180.0, flip=6000.0, regime="short_gamma")
    paired = calibrate_paired_day(spy, spx, spx_usable=True)
    assert paired.gex_scale_k == pytest.approx(90.0)
    assert paired.strike_scale == pytest.approx(10.0)
    assert paired.regime_match is True


def test_calibrate_paired_day_falls_back_when_spx_unusable() -> None:
    spy = _snap(spot=590.0, net_bn=-2.0)
    spx = _snap(spot=5900.0, net_bn=0.0, flip=6000.0)
    paired = calibrate_paired_day(spy, spx, spx_usable=False)
    assert paired.gex_scale_k == pytest.approx(100.0)


def test_spx_chain_quality_gate() -> None:
    q = spx_chain_quality([0, 0, 100, 50], min_oi_rows=100)
    assert q.oi_rows == 2
    assert q.usable is False


def test_aggregate_paired_calibration_median_k() -> None:
    spy = _snap()
    spx = _snap(spot=5900.0, net_bn=-200.0)
    p1 = calibrate_paired_day(spy, spx, spx_usable=True)
    p2 = calibrate_paired_day(spy, spx, spx_usable=True)
    agg = aggregate_paired_calibration([p1, p2])
    assert agg.method == "empirical_median"
    assert agg.gex_scale_k == pytest.approx(p1.gex_scale_k)
    assert agg.n_paired_days == 2


def test_list_paired_snapshot_dates_non_empty() -> None:
    dates = list_paired_snapshot_dates()
    assert isinstance(dates, list)
