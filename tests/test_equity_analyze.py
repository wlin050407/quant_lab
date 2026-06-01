"""API tests for /api/equity/analyze (mocked fetch)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quant_lab.data.base import OptionChainSnapshot
from quant_lab.data.equity_fetch import EquityBarBundle, clear_equity_fetch_cache
from quant_lab.terminal.api import app


def _sample_bundle() -> EquityBarBundle:
    idx_d = pd.date_range("2025-01-01", periods=130, freq="B", tz="UTC")
    daily = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": [100 + i * 0.2 for i in range(130)],
            "adj_close": [100 + i * 0.2 for i in range(130)],
            "volume": 1_000_000,
            "symbol": "TST",
        },
        index=idx_d,
    )
    idx_i = pd.date_range("2026-05-29 13:30", periods=10, freq="5min", tz="UTC")
    intraday = pd.DataFrame(
        {
            "open": 150.0,
            "high": 151.0,
            "low": 149.0,
            "close": [150 + i * 0.1 for i in range(10)],
            "adj_close": [150 + i * 0.1 for i in range(10)],
            "volume": 50_000,
            "symbol": "TST",
        },
        index=idx_i,
    )
    bench = daily.copy()
    bench["symbol"] = "SPY"
    chain = pd.DataFrame(
        {
            "symbol": ["TST"] * 4,
            "expiry": [date(2026, 6, 20)] * 4,
            "strike": [150.0, 155.0, 150.0, 155.0],
            "right": ["C", "C", "P", "P"],
            "dte": [22] * 4,
            "bid": [1.0] * 4,
            "ask": [1.1] * 4,
            "last_price": [1.05] * 4,
            "implied_volatility": [0.25] * 4,
            "volume": [1000, 800, 400, 600],
            "open_interest": [5000, 4000, 3000, 2000],
            "in_the_money": [True, False, False, True],
        }
    )
    snap = OptionChainSnapshot(
        symbol="TST",
        asof=pd.Timestamp("2026-05-29", tz="UTC"),
        spot=151.0,
        chain=chain,
    )
    return EquityBarBundle(
        ticker="TST",
        benchmark="SPY",
        session_date=date(2026, 5, 29),
        daily=daily,
        intraday=intraday,
        intraday_5d=intraday,
        benchmark_daily=bench,
        benchmark_intraday=bench.iloc[:0].copy(),
        daily_source="yfinance",
        intraday_source="thetadata",
        spot=151.0,
        option_chain=snap,
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_equity_fetch_cache()


def test_api_equity_analyze_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _sample_bundle()
    monkeypatch.setattr(
        "quant_lab.terminal.equity_live.fetch_equity_bars",
        lambda ticker, refresh=False: bundle,
    )
    monkeypatch.setattr(
        "quant_lab.terminal.equity_live._earnings_within_days",
        lambda ticker, days=7: False,
    )

    client = TestClient(app)
    res = client.get("/api/equity/analyze?ticker=TST")
    assert res.status_code == 200
    body = res.json()
    assert body["ticker"] == "TST"
    assert "horizons" in body
    assert body["horizons"]["short"]["bias"] in ("bullish", "neutral", "bearish")
    assert body["horizons"]["mid"]["bias"] in ("bullish", "neutral", "bearish")
    assert body["horizons"]["long"]["bias"] in ("bullish", "neutral", "bearish")
    assert body["layers"]["L2"]["vwap"] > 0
    assert len(body["chart"]["bars"]) == 10
    assert len(body["chart"]["daily_bars"]) == 130
    assert body["chart"]["overlays"]["ma20"] > 0
    assert "modules" in body
    assert body["modules"]["vwap_flow"]["bias"] in ("bullish", "neutral", "bearish")


def test_bars_to_chart_skips_incomplete_ohlc() -> None:
    from quant_lab.terminal.equity_live import _bars_to_chart

    idx = pd.date_range("2026-05-29 13:30", periods=3, freq="5min", tz="UTC")
    intraday = pd.DataFrame(
        {
            "open": [150.0, 151.0, None],
            "high": [151.0, 152.0, None],
            "low": [149.0, 150.0, None],
            "close": [150.5, 151.5, None],
            "adj_close": [150.5, 151.5, None],
            "volume": [1000, 2000, 0],
            "symbol": "TST",
        },
        index=idx,
    )
    bars = _bars_to_chart(intraday)
    assert len(bars) == 2
    assert all(b["c"] is not None for b in bars)
