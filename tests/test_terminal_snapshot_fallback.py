"""Snapshot must degrade gracefully (no 500) when intraday fails."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quant_lab.terminal.api import app


def test_live_intraday_fail_falls_back_to_eod_row() -> None:
    row = {
        "spot": 5900.0,
        "regime": "long_gamma",
        "king_dte1": 5900.0,
        "pin_score": 70.0,
        "pct_gex_dte1": 45.0,
        "net_gex_dte1": 1e9,
        "put_wall_dte1": 5850.0,
        "call_wall_dte1": 5950.0,
        "flip_dte1": 5880.0,
        "floor_dte1": 5800.0,
        "ceiling_dte1": 6000.0,
        "max_pain_dte1": 5900.0,
        "expected_move_1sd": 30.0,
        "pct_vex_dte1": 50.0,
        "net_vex_dte1": 0.0,
        "vanna_interp_dte1": "",
        "pcr_oi": 1.0,
        "oi_conc_dte1": 0.3,
        "spot_vs_king_pct": 0.0,
        "spot_vs_flip_pct": 0.0,
    }
    chain = pd.DataFrame(
        {
            "symbol": ["SPXW"],
            "expiry": [date(2026, 5, 29)],
            "strike": [5900.0],
            "right": ["C"],
            "dte": [0],
            "bid": [1.0],
            "ask": [1.1],
            "last_price": [1.05],
            "implied_volatility": [0.2],
            "volume": [0],
            "open_interest": [100],
            "in_the_money": [True],
        }
    )
    meta = pd.DataFrame({"spot": [5900.0]})

    with patch("quant_lab.terminal.snapshot.list_terminal_dates", return_value=["2026-05-29"]):
        with patch("quant_lab.terminal.snapshot._load_terminal_row", return_value=row):
            with patch(
                "quant_lab.terminal.snapshot._load_intraday_chain_safe",
                side_effect=FileNotFoundError("no intraday"),
            ):
                with patch(
                    "quant_lab.terminal.snapshot.load_option_chain",
                    return_value=(chain, meta),
                ):
                    with patch("quant_lab.terminal.snapshot._prev_trading_date", return_value=None):
                        client = TestClient(app)
                        r = client.get("/api/snapshot?symbol=%5ESPX&date=2026-05-29&time=13%3A00%3A00")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["date"] == "2026-05-29"
    assert "EoD snapshot" in body["meta"]["data_mode"]


def test_missing_date_returns_404_not_silent_fallback() -> None:
    """Do not silently jump to an older date when the requested session has no data."""
    with patch("quant_lab.terminal.snapshot.list_terminal_dates", return_value=["2026-05-25", "2026-05-29"]):
        with patch("quant_lab.terminal.snapshot._load_terminal_row", return_value=None):
            with patch(
                "quant_lab.terminal.snapshot._load_intraday_chain_safe",
                side_effect=FileNotFoundError("no intraday"),
            ):
                with patch(
                    "quant_lab.terminal.snapshot.load_option_chain",
                    side_effect=FileNotFoundError("no eod"),
                ):
                    with patch("quant_lab.terminal.snapshot._prev_trading_date", return_value=None):
                        client = TestClient(app)
                        r = client.get("/api/snapshot?symbol=%5ESPX&date=2026-05-29&time=13%3A00%3A00")
    assert r.status_code == 404


def test_api_snapshot_forwards_chain_mode() -> None:
    with patch(
        "quant_lab.terminal.api.build_dashboard",
        return_value={"symbol": "^SPX", "date": "2026-05-29", "meta": {"chain_mode": "full"}},
    ) as mock_build:
        client = TestClient(app)
        r = client.get(
            "/api/snapshot?symbol=%5ESPX&date=2026-05-29&time=13%3A00%3A00&chain_mode=full"
        )
    assert r.status_code == 200
    mock_build.assert_called_once()
    assert mock_build.call_args.kwargs["chain_mode"] == "full"


def test_api_snapshot_returns_503_not_500_on_unexpected_build_error() -> None:
    with patch(
        "quant_lab.terminal.api.build_dashboard",
        side_effect=RuntimeError("boom"),
    ):
        client = TestClient(app)
        r = client.get("/api/snapshot?symbol=%5ESPX&date=2026-05-29&time=13%3A00%3A00")
    assert r.status_code == 503
    assert r.status_code != 500
