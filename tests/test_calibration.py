"""Calibration tests — UW hand example + reference direction checks."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from quant_lab.factors.calibration import (
    GEXSnapshot,
    check_against_reference,
    compute_gex_snapshot,
)
from quant_lab.factors.gex import uw_gamma_notional_per_1pct


def test_uw_gamma_notional_matches_published_example() -> None:
    """Unusual Whales: 25_000 × 100 × 0.0589 = $147,250 per 1% move."""
    got = uw_gamma_notional_per_1pct(gamma=0.0589, open_interest=25_000)
    assert got == pytest.approx(147_250.0)


def test_net_gex_bn_per_1pct_scaling() -> None:
    from quant_lab.factors.gex import net_gex_bn_per_1pct

    assert net_gex_bn_per_1pct(1e12) == pytest.approx(10.0)


def _minimal_chain() -> pd.DataFrame:
    rows = []
    for k in (510.0, 515.0, 520.0, 525.0, 530.0):
        rows.append(
            {
                "strike": k,
                "right": "C",
                "open_interest": 5000,
                "dte": 7,
                "implied_volatility": 0.18,
            }
        )
        rows.append(
            {
                "strike": k,
                "right": "P",
                "open_interest": 8000,
                "dte": 7,
                "implied_volatility": 0.18,
            }
        )
    return pd.DataFrame(rows)


def test_compute_gex_snapshot_returns_finite_metrics() -> None:
    snap = compute_gex_snapshot(_minimal_chain(), spot=520.0, asof_date="2024-01-02")
    assert snap.regime in ("long_gamma", "short_gamma")
    assert math.isfinite(snap.net_gex_dollars_per_dollar)
    assert math.isfinite(snap.call_wall_strike)
    assert math.isfinite(snap.put_wall_strike)


def test_check_against_reference_direction_short_gamma() -> None:
    snap = GEXSnapshot(
        date="2024-08-05",
        spot=517.0,
        net_gex_dollars_per_dollar=-1e11,
        net_gex_bn_per_1pct=-1.0,
        flip_level=560.0,
        spot_above_flip=False,
        call_wall_strike=520.0,
        put_wall_strike=500.0,
        regime="short_gamma",
    )
    ref = {"regime": "short_gamma", "spot_below_flip": True}
    result = check_against_reference(snap, ref)
    assert result.passed


def test_check_against_reference_magnitude_within_tolerance() -> None:
    snap = GEXSnapshot(
        date="2024-01-01",
        spot=500.0,
        net_gex_dollars_per_dollar=0.0,
        net_gex_bn_per_1pct=-9.0,
        flip_level=510.0,
        spot_above_flip=False,
        call_wall_strike=505.0,
        put_wall_strike=495.0,
        regime="short_gamma",
    )
    ref = {"net_gex_bn_per_1pct": -10.0}
    result = check_against_reference(snap, ref, tolerance_pct=0.30)
    assert result.passed

    ref_fail = {"net_gex_bn_per_1pct": -20.0}
    result_fail = check_against_reference(snap, ref_fail, tolerance_pct=0.30)
    assert not result_fail.passed
