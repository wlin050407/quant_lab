"""Tests for Ultimate Terminal M4."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quant_lab.terminal.api import app
from quant_lab.terminal.strategy_hint import recommend_strategy


def _minimal_terminal_row() -> dict[str, float | str]:
    return {
        "spot": 100.0,
        "regime": "long_gamma",
        "king_dte1": 100.0,
        "pin_score": 70.0,
        "pct_gex_dte1": 45.0,
        "net_gex_dte1": 1e9,
        "put_wall_dte1": 95.0,
        "call_wall_dte1": 105.0,
        "flip_dte1": 98.0,
        "floor_dte1": 90.0,
        "ceiling_dte1": 110.0,
        "max_pain_dte1": 100.0,
        "expected_move_1sd": 2.0,
        "pct_vex_dte1": 50.0,
        "net_vex_dte1": 0.0,
        "vanna_interp_dte1": "",
        "pcr_oi": 1.0,
        "oi_conc_dte1": 0.3,
        "spot_vs_king_pct": 0.0,
        "spot_vs_flip_pct": 0.0,
    }


def _minimal_terminal_chain(*, session_date: date) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["SPY", "SPY"],
            "expiry": [session_date, session_date],
            "strike": [100.0, 100.0],
            "right": ["C", "P"],
            "dte": [0, 0],
            "bid": [1.0, 1.0],
            "ask": [1.1, 1.1],
            "last_price": [1.05, 1.05],
            "implied_volatility": [0.2, 0.2],
            "volume": [10, 10],
            "open_interest": [100, 100],
            "in_the_money": [True, False],
        }
    )


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


def test_recommend_short_gamma_none_flip_does_not_crash() -> None:
    """Live deploy hit 503 when flip was None but short_gamma + high 0DTE GEX."""
    hint = recommend_strategy(
        regime="short_gamma",
        pin_score=40.0,
        spot=5000.0,
        put_wall=4900.0,
        call_wall=5100.0,
        king=5020.0,
        flip=None,
        pct_gex_dte1=60.0,
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
    """Normal snapshot with mocked chain — no ThetaData, no calendar dependency."""
    session = "2026-05-29"
    row = _minimal_terminal_row()
    chain = _minimal_terminal_chain(session_date=date(2026, 5, 29))

    with (
        patch("quant_lab.terminal.snapshot.list_terminal_dates", return_value=[session]),
        patch("quant_lab.terminal.snapshot._load_terminal_row", return_value=row),
        patch(
            "quant_lab.terminal.snapshot._load_intraday_chain_safe",
            return_value=(chain, 100.0, "13:00:00", "local"),
        ),
        patch("quant_lab.terminal.snapshot._prev_trading_date", return_value=None),
    ):
        client = TestClient(app)
        res = client.get(
            f"/api/snapshot?symbol=SPY&date={session}&time=13:00:00"
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["symbol"] == "SPY"
    assert body["date"] == session
    assert "levels" in body
    assert "strategy" in body
    assert "pin_playbook" in body
    assert body.get("availability") != "hold"
    assert body["pin_playbook"] is not None
    assert body["pin_playbook"]["size_multiplier"] is not None
    assert body["meta"]["data_source"] in {"thetadata", "thetadata_live", "eod", "local"}


@patch("quant_lab.terminal.snapshot.list_terminal_dates", return_value=["2026-06-02"])
@patch("quant_lab.terminal.snapshot.is_live_session", return_value=True)
@patch("quant_lab.terminal.snapshot.session_hold_reason", return_value="pre_market")
@patch("quant_lab.terminal.snapshot.supports_live_intraday", return_value=True)
@patch("quant_lab.terminal.snapshot._load_terminal_row", return_value=_minimal_terminal_row())
@patch("quant_lab.terminal.snapshot._load_intraday_chain_safe", side_effect=FileNotFoundError("no intraday"))
@patch("quant_lab.terminal.snapshot.load_option_chain", side_effect=FileNotFoundError("no eod"))
def test_api_snapshot_hold_fallback(
    _load_eod: object,
    _load_intraday: object,
    _row: object,
    _supports: object,
    _hold: object,
    _live_sess: object,
    _dates: object,
) -> None:
    """Hold dashboard when chain unavailable — HTTP 200, playbook null, UI fallback fields."""
    client = TestClient(app)
    res = client.get("/api/snapshot?symbol=SPY&date=2026-06-02&time=live")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["availability"] == "hold"
    assert body["pin_playbook"] is None
    assert body["meta"]["session_status"] == "pre_market"
    assert body["meta"]["session_status_title"]
    assert body["meta"]["session_status_message"]
    assert "strategy" in body
    assert body["gate"]["should_trade"] is False


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
    rows, cohort_fallback = build_strike_heatmap(chain, 100.0, dte_max=1)
    assert cohort_fallback is False
    assert len(rows) == 3
    assert all("net_gex" in r and "net_vex" in r for r in rows)
    assert {r["strike"] for r in rows} == {98.0, 100.0, 102.0}


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
    rows, cohort_fallback = build_strike_heatmap(
        curr, 100.0, prev_chain=prev, prev_spot=100.0
    )
    assert cohort_fallback is False
    assert len(rows) == 1
    assert rows[0]["roc_pct"] is not None
    assert rows[0]["roc_pct"] > 0
