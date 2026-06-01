"""Session hold (pre-market) dashboard — no 404 before the open."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from quant_lab.terminal.api import app
from quant_lab.terminal.session_status import session_hold_reason

ET = ZoneInfo("America/New_York")


@patch("quant_lab.terminal.session_status.market_today", return_value=date(2026, 6, 2))
@patch("quant_lab.terminal.session_status.datetime")
def test_session_hold_reason_pre_market(mock_dt: object, _today: object) -> None:
    mock_dt.now.return_value = datetime(2026, 6, 2, 8, 15, tzinfo=ET)
    assert session_hold_reason(date(2026, 6, 2), time_of_day="live") == "pre_market"


@patch("quant_lab.terminal.session_status.market_today", return_value=date(2026, 6, 2))
@patch("quant_lab.terminal.session_status.datetime")
def test_session_hold_reason_none_after_open_window(mock_dt: object, _today: object) -> None:
    mock_dt.now.return_value = datetime(2026, 6, 2, 10, 0, tzinfo=ET)
    assert session_hold_reason(date(2026, 6, 2), time_of_day="live") is None


@patch("quant_lab.terminal.snapshot.list_terminal_dates", return_value=["2026-06-02"])
@patch("quant_lab.terminal.snapshot.is_live_session", return_value=True)
@patch("quant_lab.terminal.snapshot.session_hold_reason", return_value="pre_market")
@patch("quant_lab.terminal.snapshot.supports_live_intraday", return_value=True)
@patch("quant_lab.terminal.snapshot._load_terminal_row", return_value={"spot": 5900.0, "pin_score": 80.0})
@patch("quant_lab.terminal.snapshot._load_intraday_chain_safe", side_effect=FileNotFoundError("x"))
@patch("quant_lab.terminal.snapshot.load_option_chain", side_effect=FileNotFoundError("x"))
def test_api_returns_hold_not_404_pre_market_even_with_stale_row(
    _load_chain: object,
    _load_eod: object,
    _live: object,
    _hold: object,
    _row: object,
    _live_sess: object,
    _dates: object,
) -> None:
    client = TestClient(app)
    r = client.get("/api/snapshot?symbol=%5ESPX&date=2026-06-02&time=live")
    assert r.status_code == 200
    body = r.json()
    assert body["availability"] == "hold"
    assert body["meta"]["session_status"] == "pre_market"
    assert body["meta"]["session_status_title"] == "Market not open yet"
    assert "09:30 ET" in body["meta"]["session_status_message"]
