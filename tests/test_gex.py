"""Unit tests for factors/gex.py.

Covers:
- Single-contract BS gamma against hand-computed values
- Put-call gamma symmetry (calls and puts share the same gamma in BS)
- NaN propagation on degenerate inputs (dte=0, IV=0)
- Aggregator schema, sign convention, custom dealer_sign override
- Gamma flip level finds zero crossings (and returns NaN when there is none)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from quant_lab.factors.gex import (
    DEFAULT_DEALER_SIGN,
    add_bs_gamma_column,
    bs_gamma,
    bs_vanna,
    compute_dealer_gamma_exposure,
    compute_dealer_vanna_exposure,
    compute_gamma_profile_curve,
    compute_vex_profile,
    compute_gamma_flip,
    diagnose_cohort_time_to_expiry,
    gamma_flip_level,
    net_gex_bn_per_1pct,
    total_net_gex,
    total_net_vex,
    vanna_interpretation,
)


def _hand_compute_atm_gamma(
    s: float = 100.0,
    k: float = 100.0,
    t: float = 30 / 365,
    sigma: float = 0.20,
    r: float = 0.05,
    q: float = 0.0,
) -> float:
    """Hand BS gamma for the ATM-ish reference case used in the first test."""
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))
    pdf = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
    return math.exp(-q * t) * pdf / (s * sigma * math.sqrt(t))


def test_bs_gamma_atm_matches_hand_computation() -> None:
    expected = _hand_compute_atm_gamma()
    got = bs_gamma(spot=100.0, strike=100.0, time_to_expiry=30 / 365, volatility=0.20, r=0.05, q=0.0)
    assert got == pytest.approx(expected, rel=1e-12)


def test_bs_gamma_call_put_symmetry() -> None:
    """Same strike, same T, same IV → identical gamma whether read as call or put."""
    g = bs_gamma(spot=470.0, strike=475.0, time_to_expiry=14 / 365, volatility=0.18)
    g_again = bs_gamma(spot=470.0, strike=475.0, time_to_expiry=14 / 365, volatility=0.18)
    assert g == g_again


def test_bs_gamma_peaks_at_atm() -> None:
    """Gamma is maximized at-the-money (slightly below spot for non-zero r-q)."""
    spot = 100.0
    strikes = np.array([80.0, 90.0, 95.0, 100.0, 105.0, 110.0, 120.0])
    gammas = bs_gamma(
        spot=spot, strike=strikes, time_to_expiry=30 / 365, volatility=0.20, r=0.05, q=0.0
    )
    atm_idx = np.argmax(gammas)
    assert 2 <= atm_idx <= 4
    assert gammas[atm_idx] > gammas[0]
    assert gammas[atm_idx] > gammas[-1]


def test_bs_gamma_returns_nan_for_degenerate_inputs() -> None:
    """T=0 / sigma=0 / negative strike must yield NaN, not +inf or junk."""
    assert math.isnan(bs_gamma(100.0, 100.0, 0.0, 0.20))
    assert math.isnan(bs_gamma(100.0, 100.0, 30 / 365, 0.0))
    assert math.isnan(bs_gamma(100.0, -100.0, 30 / 365, 0.20))
    assert math.isnan(bs_gamma(-100.0, 100.0, 30 / 365, 0.20))


def test_bs_gamma_vectorizes() -> None:
    strikes = np.array([90.0, 100.0, 110.0])
    out = bs_gamma(spot=100.0, strike=strikes, time_to_expiry=30 / 365, volatility=0.20)
    assert isinstance(out, np.ndarray)
    assert out.shape == (3,)
    assert np.all(out > 0)


def _make_chain(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_add_bs_gamma_column_eod_dte0_uses_one_hour_proxy() -> None:
    """EoD dte=0 rows use ~1 trading hour T so 0DTE snapshots stay computable."""
    chain = _make_chain(
        [
            {"strike": 470.0, "dte": 0, "implied_volatility": 0.20, "right": "C", "open_interest": 100},
            {"strike": 470.0, "dte": 7, "implied_volatility": 0.20, "right": "C", "open_interest": 100},
        ]
    )
    out = add_bs_gamma_column(chain, spot=470.0)
    assert out.loc[0, "bs_gamma"] > 0
    assert out.loc[1, "bs_gamma"] > 0


def test_add_bs_gamma_column_requires_input_columns() -> None:
    bad = pd.DataFrame({"strike": [1.0], "dte": [5]})
    with pytest.raises(ValueError, match="implied_volatility"):
        add_bs_gamma_column(bad, spot=100.0)


def test_compute_dealer_gex_signs_calls_positive_puts_negative() -> None:
    chain = _make_chain(
        [
            {"strike": 470.0, "right": "C", "open_interest": 100, "bs_gamma": 0.01},
            {"strike": 470.0, "right": "P", "open_interest": 100, "bs_gamma": 0.01},
        ]
    )
    per_strike = compute_dealer_gamma_exposure(chain, spot=470.0)
    assert per_strike.loc[470.0, "call_gex"] > 0
    assert per_strike.loc[470.0, "put_gex"] < 0
    assert per_strike.loc[470.0, "net_gex"] == pytest.approx(0.0, abs=1e-9)
    assert per_strike.loc[470.0, "call_oi"] == 100
    assert per_strike.loc[470.0, "put_oi"] == 100
    assert per_strike.loc[470.0, "total_oi"] == 200


def test_compute_dealer_gex_magnitudes_match_closed_form() -> None:
    """gex = gamma · oi · multiplier · spot²."""
    chain = _make_chain(
        [{"strike": 470.0, "right": "C", "open_interest": 1000, "bs_gamma": 0.02}]
    )
    per_strike = compute_dealer_gamma_exposure(chain, spot=470.0)
    expected = 0.02 * 1000 * 100 * 470.0**2
    assert per_strike.loc[470.0, "call_gex"] == pytest.approx(expected)


def test_compute_dealer_gex_dealer_sign_override_flips_result() -> None:
    chain = _make_chain(
        [
            {"strike": 470.0, "right": "C", "open_interest": 100, "bs_gamma": 0.01},
            {"strike": 470.0, "right": "P", "open_interest": 200, "bs_gamma": 0.01},
        ]
    )
    default = compute_dealer_gamma_exposure(chain, spot=470.0)
    flipped = compute_dealer_gamma_exposure(
        chain, spot=470.0, dealer_sign={"C": -1, "P": 1}
    )
    assert default.loc[470.0, "net_gex"] == pytest.approx(-flipped.loc[470.0, "net_gex"])


def test_compute_dealer_gex_drops_nan_gamma_rows() -> None:
    chain = _make_chain(
        [
            {"strike": 470.0, "right": "C", "open_interest": 100, "bs_gamma": float("nan")},
            {"strike": 475.0, "right": "C", "open_interest": 100, "bs_gamma": 0.02},
        ]
    )
    per_strike = compute_dealer_gamma_exposure(chain, spot=470.0)
    assert 470.0 not in per_strike.index
    assert per_strike.loc[475.0, "call_gex"] > 0


def test_compute_dealer_gex_rejects_bad_spot() -> None:
    chain = _make_chain(
        [{"strike": 470.0, "right": "C", "open_interest": 100, "bs_gamma": 0.01}]
    )
    with pytest.raises(ValueError, match="spot"):
        compute_dealer_gamma_exposure(chain, spot=0.0)
    with pytest.raises(ValueError, match="spot"):
        compute_dealer_gamma_exposure(chain, spot=float("nan"))


def test_compute_dealer_gex_rejects_unknown_right() -> None:
    chain = _make_chain(
        [{"strike": 470.0, "right": "X", "open_interest": 100, "bs_gamma": 0.01}]
    )
    with pytest.raises(ValueError, match="unrecognized right"):
        compute_dealer_gamma_exposure(chain, spot=470.0)


def test_compute_dealer_gex_empty_chain_returns_schema() -> None:
    out = compute_dealer_gamma_exposure(
        pd.DataFrame(columns=["strike", "right", "open_interest", "bs_gamma"]),
        spot=470.0,
    )
    assert list(out.columns) == ["call_oi", "put_oi", "call_gex", "put_gex", "net_gex", "total_oi"]
    assert len(out) == 0


def test_total_net_gex_sums_strikes() -> None:
    chain = _make_chain(
        [
            {"strike": 470.0, "right": "C", "open_interest": 100, "bs_gamma": 0.01},
            {"strike": 475.0, "right": "C", "open_interest": 200, "bs_gamma": 0.02},
            {"strike": 470.0, "right": "P", "open_interest": 50, "bs_gamma": 0.01},
        ]
    )
    per_strike = compute_dealer_gamma_exposure(chain, spot=470.0)
    expected = (
        0.01 * 100 * 100 * 470**2
        + 0.02 * 200 * 100 * 470**2
        - 0.01 * 50 * 100 * 470**2
    )
    assert total_net_gex(per_strike) == pytest.approx(expected)


def _make_realistic_chain(
    spot: float,
    *,
    call_oi_by_strike: dict[float, int] | None = None,
    put_oi_by_strike: dict[float, int] | None = None,
    flat_call_oi: int = 0,
    flat_put_oi: int = 0,
) -> pd.DataFrame:
    """Build a chain with strikes around spot, dte=7, ATM IV ≈ 18%.

    Pass `call_oi_by_strike` / `put_oi_by_strike` to set per-strike OI; any
    unspecified strikes fall back to `flat_call_oi` / `flat_put_oi`.
    """
    call_oi_by_strike = call_oi_by_strike or {}
    put_oi_by_strike = put_oi_by_strike or {}
    rows = []
    for k in np.arange(spot - 30, spot + 30 + 1, 5):
        rows.append(
            {
                "strike": float(k),
                "right": "C",
                "open_interest": call_oi_by_strike.get(float(k), flat_call_oi),
                "dte": 7,
                "implied_volatility": 0.18,
            }
        )
        rows.append(
            {
                "strike": float(k),
                "right": "P",
                "open_interest": put_oi_by_strike.get(float(k), flat_put_oi),
                "dte": 7,
                "implied_volatility": 0.18,
            }
        )
    return pd.DataFrame(rows)


def test_compute_gamma_flip_primary_is_nearest_to_spot() -> None:
    """With two crossings, primary must be closest to spot (not first grid crossing)."""
    spot = 470.0
    chain = _make_realistic_chain(
        spot,
        put_oi_by_strike={k: 5000 for k in [420.0, 430.0, 440.0]},
        call_oi_by_strike={k: 5000 for k in [500.0, 510.0, 520.0]},
    )
    chain = add_bs_gamma_column(chain, spot=spot)
    result = compute_gamma_flip(chain, spot=spot, search_radius_pct=0.15, n_search_points=61)
    if len(result.all_flips) >= 2:
        primary = result.primary_flip
        assert primary == min(result.all_flips, key=lambda f: abs(f - spot))
        assert result.primary_rule == "nearest_to_spot"


def test_diagnose_cohort_time_fallback_1h_warns() -> None:
    chain = _make_realistic_chain(470.0, flat_call_oi=100, flat_put_oi=100)
    chain["dte"] = 0
    diag = diagnose_cohort_time_to_expiry(chain, dte_max=1)
    assert diag.mode == "fallback_1h"
    assert diag.fallback_used is True
    assert diag.warning is not None


def test_diagnose_cohort_time_exact_intraday() -> None:
    chain = _make_realistic_chain(470.0, flat_call_oi=100, flat_put_oi=100)
    chain["dte"] = 0
    chain["time_to_expiry_years"] = 2.0 / (365 * 6.5)
    diag = diagnose_cohort_time_to_expiry(chain, dte_max=1)
    assert diag.mode == "exact_intraday"
    assert diag.fallback_used is False


def test_gamma_flip_level_finds_crossing_with_split_oi() -> None:
    """Puts heavy below spot, calls heavy above spot → gamma sign flips somewhere in between.

    Walking spot upward, calls (above) get closer to ATM → call_gex grows;
    puts (below) move further OTM → |put_gex| shrinks. Net flips from
    negative to positive at some interior price.
    """
    spot = 470.0
    chain = _make_realistic_chain(
        spot,
        put_oi_by_strike={k: 2000 for k in [440.0, 445.0, 450.0, 455.0]},
        call_oi_by_strike={k: 2000 for k in [485.0, 490.0, 495.0, 500.0]},
    )
    chain = add_bs_gamma_column(chain, spot=spot)
    flip = gamma_flip_level(chain, spot=spot, search_radius_pct=0.10)
    assert not math.isnan(flip)
    assert spot * 0.9 <= flip <= spot * 1.1


def test_gamma_flip_level_returns_nan_when_no_crossing() -> None:
    """All calls, no puts → net gex strictly positive across ±10% → no flip in range."""
    spot = 470.0
    chain = _make_realistic_chain(spot, flat_call_oi=1000, flat_put_oi=0)
    chain = add_bs_gamma_column(chain, spot=spot)
    flip = gamma_flip_level(chain, spot=spot, search_radius_pct=0.10)
    assert math.isnan(flip)


def test_gamma_flip_level_rejects_static_gamma_column() -> None:
    chain = _make_realistic_chain(470.0, flat_call_oi=100, flat_put_oi=100)
    chain["gamma"] = 0.01
    with pytest.raises(ValueError, match="bs_gamma"):
        gamma_flip_level(chain, spot=470.0, gamma_col="gamma")


def test_gamma_profile_uses_intraday_time_to_expiry() -> None:
    """Flip/profile must match add_bs_gamma_column T — not dte/365 when dte=0."""
    spot = 470.0
    chain = _make_realistic_chain(spot, flat_call_oi=800, flat_put_oi=1200)
    chain["dte"] = 0
    chain["time_to_expiry_years"] = 2.0 / (365 * 6.5)

    curve_short_t = compute_gamma_profile_curve(chain, spot)
    assert len(curve_short_t) >= 2

    chain_long = chain.copy()
    chain_long["time_to_expiry_years"] = 20.0 / (365 * 6.5)
    curve_long_t = compute_gamma_profile_curve(chain_long, spot)
    mid_short = curve_short_t[len(curve_short_t) // 2].net_gex
    mid_long = curve_long_t[len(curve_long_t) // 2].net_gex
    assert mid_short != mid_long


def test_net_gex_bn_per_1pct_matches_spotgamma_factor() -> None:
    raw = 1e11
    assert net_gex_bn_per_1pct(raw) == pytest.approx(1.0)


def _hand_compute_atm_vanna(
    s: float = 100.0,
    k: float = 100.0,
    t: float = 30 / 365,
    sigma: float = 0.20,
    r: float = 0.05,
    q: float = 0.0,
) -> float:
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma**2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    pdf = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
    return -math.exp(-q * t) * pdf * d2 / sigma


def _finite_diff_vanna(
    s: float,
    k: float,
    t: float,
    sigma: float,
    r: float = 0.05,
    q: float = 0.0,
    eps: float = 1e-5,
) -> float:
    def _delta_call(sig: float) -> float:
        d1 = (math.log(s / k) + (r - q + 0.5 * sig**2) * t) / (sig * math.sqrt(t))
        return math.exp(-q * t) * norm.cdf(d1)

    return (_delta_call(sigma + eps) - _delta_call(sigma - eps)) / (2 * eps)


def test_bs_vanna_atm_matches_hand_computation() -> None:
    expected = _hand_compute_atm_vanna()
    got = bs_vanna(spot=100.0, strike=100.0, time_to_expiry=30 / 365, volatility=0.20, r=0.05, q=0.0)
    assert got == pytest.approx(expected, rel=1e-10)


def test_bs_vanna_matches_finite_difference() -> None:
    analytic = bs_vanna(
        spot=470.0,
        strike=475.0,
        time_to_expiry=14 / 365,
        volatility=0.18,
        q=0.0,
    )
    fd = _finite_diff_vanna(470.0, 475.0, 14 / 365, 0.18, q=0.0)
    assert analytic == pytest.approx(fd, rel=1e-4)


def test_compute_dealer_vex_magnitudes_match_closed_form() -> None:
    spot = 470.0
    vanna = 0.015
    chain = pd.DataFrame(
        [{"strike": 470.0, "right": "C", "open_interest": 1000, "bs_vanna": vanna}]
    )
    per_strike = compute_dealer_vanna_exposure(chain, spot)
    expected = vanna * 0.01 * 1000 * 100 * spot
    assert per_strike.loc[470.0, "call_vex"] == pytest.approx(expected)
    assert total_net_vex(per_strike) == pytest.approx(expected)


def test_vanna_interpretation_negative_vex() -> None:
    assert vanna_interpretation(-1.0) == "vol_down_dealers_buy"
    assert vanna_interpretation(1.0) == "vol_down_dealers_sell"


def test_compute_vex_profile_empty_chain() -> None:
    profile = compute_vex_profile(pd.DataFrame(), spot=100.0, dte_max=1)
    assert profile.net_vex == 0.0
    assert profile.n_contracts == 0
    assert profile.interpretation == "undetermined"
