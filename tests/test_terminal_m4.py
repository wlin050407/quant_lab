"""Tests for Ultimate Terminal M4."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quant_lab.terminal.api import app
from quant_lab.terminal.strategy_hint import recommend_strategy


def test_recommend_long_gamma_pin_play() -> None:
    hint = recommend_strategy(
        regime="long_gamma",
        pin_score=75.0,
        spot=100.0,
        put_wall=95.0,
        call_wall=105.0,
        king=100.0,
        flip=98.0,
        pct_gex_dte1=60.0,
        should_trade=True,
    )
    assert hint.label == "pin_play"


def test_recommend_short_gamma_no_premium() -> None:
    hint = recommend_strategy(
        regime="short_gamma",
        pin_score=40.0,
        spot=100.0,
        put_wall=95.0,
        call_wall=105.0,
        king=102.0,
        flip=101.0,
        pct_gex_dte1=20.0,
        should_trade=True,
    )
    assert hint.label == "sit_out"


def test_api_health() -> None:
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_api_dates_spy() -> None:
    client = TestClient(app)
    res = client.get("/api/dates?symbol=SPY")
    if res.status_code == 404:
        pytest.skip("no SPY terminal history")
    body = res.json()
    assert len(body["dates"]) > 0
    assert "latest" in body
    assert "today" in body


def test_api_snapshot_latest() -> None:
    client = TestClient(app)
    dates_res = client.get("/api/dates?symbol=SPY")
    if dates_res.status_code == 404:
        pytest.skip("no SPY terminal history")
    latest = dates_res.json()["latest"]
    res = client.get(f"/api/snapshot?symbol=SPY&date={latest}")
    assert res.status_code == 200
    body = res.json()
    assert body["symbol"] == "SPY"
    assert "levels" in body
    assert "strategy" in body
    assert "pin_playbook" in body
    assert body["pin_playbook"]["size_multiplier"] is not None


def test_build_strike_heatmap_from_chain() -> None:
    from quant_lab.terminal.snapshot import build_strike_heatmap

    chain = pd.DataFrame(
        {
            "strike": [98.0, 100.0, 102.0],
            "right": ["C", "C", "C"],
            "dte": [1, 1, 1],
            "open_interest": [100, 200, 100],
            "implied_volatility": [0.2, 0.2, 0.2],
        }
    )
    rows = build_strike_heatmap(chain, 100.0, dte_max=1)
    assert len(rows) == 3
    assert all("net_gex" in r and "net_vex" in r for r in rows)


def test_king_distance() -> None:
    from quant_lab.terminal.snapshot import king_distance

    kd = king_distance(100.0, 100.6)
    assert kd is not None
    assert kd["pct"] == pytest.approx(0.6, abs=0.01)
    assert kd["direction"] == "up"


def test_heatmap_roc_pct() -> None:
    from quant_lab.terminal.snapshot import build_strike_heatmap

    def _chain(strike: float, oi: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "strike": [strike],
                "right": ["C"],
                "dte": [1],
                "open_interest": [oi],
                "implied_volatility": [0.2],
            }
        )

    prev = _chain(100.0, 100)
    curr = _chain(100.0, 500)
    rows = build_strike_heatmap(curr, 100.0, prev_chain=prev, prev_spot=100.0)
    assert len(rows) == 1
    assert rows[0]["roc_pct"] is not None
    assert rows[0]["roc_pct"] > 0
