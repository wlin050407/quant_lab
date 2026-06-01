"""Tests for multi-horizon synthesis."""

from __future__ import annotations

import pandas as pd

from quant_lab.factors.equity.ma_structure import ma_structure
from quant_lab.factors.equity.relative_strength import relative_strength_vs_benchmark
from quant_lab.factors.equity.session_structure import OpeningSegment, opening_30m_rs
from quant_lab.factors.equity.synthesize import synthesize_horizons
from quant_lab.factors.equity.vol_regime import realized_vol_regime
from quant_lab.factors.equity.volume_profile import volume_profile
from quant_lab.factors.equity.vwap import session_vwap_metrics


def _intraday(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=pd.date_range("2026-01-02 14:30", periods=len(closes), freq="5min", tz="UTC"),
    )


def test_opening_30m_rs_outperforms() -> None:
    ticker = _intraday([100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    bench = _intraday([100.0, 100.1, 100.1, 100.2, 100.2, 100.3])
    seg = opening_30m_rs(ticker, bench)
    assert seg.rs_open_30m > 0


def test_synthesize_weakest_link_low_adv() -> None:
    idx = pd.date_range("2025-01-01", periods=130, freq="B", tz="UTC")
    daily = pd.DataFrame({"close": [100 + i * 0.2 for i in range(130)]}, index=idx)
    bench = pd.DataFrame({"close": [100 + i * 0.05 for i in range(130)]}, index=idx)
    intraday = _intraday([150.0, 150.5, 151.0, 151.2, 151.5, 152.0])
    vwap = session_vwap_metrics(intraday)
    profile = volume_profile(intraday)
    rs = relative_strength_vs_benchmark(daily, bench)
    ma = ma_structure(daily)
    vol = realized_vol_regime(daily)
    out = synthesize_horizons(
        vwap=vwap,
        profile=profile,
        rs=rs,
        ma=ma,
        vol=vol,
        options=None,
        intraday_source="yfinance",
        intraday_bars=len(intraday),
        adv=500_000.0,
        amihud=1.0,
        earnings_risk=False,
        macro_labels=(),
        opening=OpeningSegment(0.5, 1.0, 0.5, 6),
        n_daily=len(daily),
    )
    assert out["weakest_link"] == {"layer": "L0", "reason": "Low dollar volume — execution risk"}


def test_synthesize_macro_risk_in_mid() -> None:
    idx = pd.date_range("2025-01-01", periods=130, freq="B", tz="UTC")
    daily = pd.DataFrame({"close": [100 + i * 0.2 for i in range(130)]}, index=idx)
    bench = pd.DataFrame({"close": [100 + i * 0.05 for i in range(130)]}, index=idx)
    intraday = _intraday([150.0, 150.5, 151.0, 151.2, 151.5, 152.0])
    vwap = session_vwap_metrics(intraday)
    profile = volume_profile(intraday)
    rs = relative_strength_vs_benchmark(daily, bench)
    ma = ma_structure(daily)
    vol = realized_vol_regime(daily)
    out = synthesize_horizons(
        vwap=vwap,
        profile=profile,
        rs=rs,
        ma=ma,
        vol=vol,
        options=None,
        intraday_source="thetadata",
        intraday_bars=len(intraday),
        adv=20_000_000.0,
        amihud=0.1,
        earnings_risk=False,
        macro_labels=("FOMC",),
        opening=None,
        n_daily=len(daily),
    )
    assert any("FOMC" in r for r in out["mid"]["risks"])
