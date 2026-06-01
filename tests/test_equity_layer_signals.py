"""Tests for per-module bias signals."""

from __future__ import annotations

import pandas as pd

from quant_lab.factors.equity.layer_signals import (
    compute_module_signals,
    context_signal,
    volume_profile_signal,
    vwap_flow_signal,
)
from quant_lab.factors.equity.ma_structure import ma_structure
from quant_lab.factors.equity.relative_strength import relative_strength_vs_benchmark
from quant_lab.factors.equity.vol_regime import VolRegimeResult, realized_vol_regime
from quant_lab.factors.equity.volume_profile import volume_profile
from quant_lab.factors.equity.vwap import session_vwap_metrics


def test_vwap_flow_bullish_when_above_vwap() -> None:
    df = pd.DataFrame(
        {
            "open": [100.0, 102.0],
            "high": [101.0, 103.0],
            "low": [99.0, 101.0],
            "close": [100.0, 104.0],
            "adj_close": [100.0, 104.0],
            "volume": [1000.0, 3000.0],
            "symbol": "X",
        },
        index=pd.date_range("2026-01-02 14:30", periods=2, freq="5min", tz="UTC"),
    )
    vwap = session_vwap_metrics(df)
    sig = vwap_flow_signal(vwap)
    assert sig["bias"] == "bullish"
    assert sig["score"] > 0


def test_volume_profile_bearish_below_poc() -> None:
    profile = volume_profile(
        pd.DataFrame(
            {
                "open": [100.0] * 4,
                "high": [101.0] * 4,
                "low": [99.0] * 4,
                "close": [100.0, 100.5, 99.0, 98.5],
                "volume": [1000.0, 500.0, 2000.0, 1500.0],
            },
            index=pd.date_range("2026-01-02 14:30", periods=4, freq="5min", tz="UTC"),
        )
    )
    sig = volume_profile_signal(profile=profile, last_close=98.5)
    assert sig["bias"] in ("bearish", "neutral")


def test_context_elevated_vol_bearish() -> None:
    vol = VolRegimeResult("elevated", 0.25, 80.0)
    sig = context_signal(vol=vol, earnings_window=False, macro_count=0)
    assert sig["score"] < 0


def test_compute_module_signals_keys() -> None:
    idx = pd.date_range("2025-01-01", periods=130, freq="B", tz="UTC")
    daily = pd.DataFrame({"close": [100 + i * 0.2 for i in range(130)]}, index=idx)
    bench = pd.DataFrame({"close": [100 + i * 0.05 for i in range(130)]}, index=idx)
    intraday = pd.DataFrame(
        {
            "open": [150.0] * 6,
            "high": [151.0] * 6,
            "low": [149.0] * 6,
            "close": [150.0, 150.5, 151.0, 151.2, 151.5, 152.0],
            "adj_close": [150.0, 150.5, 151.0, 151.2, 151.5, 152.0],
            "volume": [1000.0] * 6,
            "symbol": "X",
        },
        index=pd.date_range("2026-01-02 14:30", periods=6, freq="5min", tz="UTC"),
    )
    vwap = session_vwap_metrics(intraday)
    profile = volume_profile(intraday)
    rs = relative_strength_vs_benchmark(daily, bench)
    ma = ma_structure(daily)
    vol = realized_vol_regime(daily)
    out = compute_module_signals(
        vwap=vwap,
        profile=profile,
        rs=rs,
        ma=ma,
        vol=vol,
        options=None,
        spot=152.0,
        eligible=True,
        adv_usd=10_000_000.0,
        amihud=0.5,
        earnings_window=False,
        macro_count=0,
    )
    assert set(out) == {"liquidity", "context", "vwap_flow", "volume_profile", "trend", "options_flow"}
    for mod in out.values():
        assert mod["bias"] in ("bullish", "neutral", "bearish")
        assert -1.0 <= mod["score"] <= 1.0
