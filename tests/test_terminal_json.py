"""Dashboard JSON must serialize for FastAPI (no numpy.bool_)."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import numpy as np

from quant_lab.terminal.pin_playbook import build_pin_playbook, pin_playbook_to_dict
from quant_lab.terminal.snapshot import json_safe


def test_json_safe_converts_numpy_bool() -> None:
    assert json_safe(np.bool_(True)) is True
    assert json_safe(np.bool_(False)) is False
    assert isinstance(json_safe({"ok": np.bool_(True)})["ok"], bool)


def test_pin_playbook_dict_is_json_serializable() -> None:
    pb = build_pin_playbook(
        symbol="^SPX",
        session_date=date(2026, 5, 29),
        time_of_day="13:00:00",
        regime="long_gamma",
        pin_score=75.0,
        pct_gex_dte1=45.0,
        spot=5900.0,
        put_wall=5850.0,
        call_wall=5950.0,
        king=5900.0,
        max_pain=5900.0,
        expected_move=30.0,
        gate_should_trade=True,
        gate_reason="ok",
    )
    data = json_safe(pin_playbook_to_dict(pb))
    text = json.dumps(data)
    assert "passed" in text
    for check in data["checks"]:
        assert isinstance(check["passed"], bool)


def test_build_dashboard_json_serializable() -> None:
    from quant_lab.terminal.snapshot import build_dashboard

    with patch("quant_lab.terminal.snapshot._load_terminal_row", return_value=None):
        with patch(
            "quant_lab.terminal.snapshot._load_intraday_chain_safe",
            return_value=(_minimal_chain(), 5900.0, "13:00:00", "thetadata"),
        ):
            with patch("quant_lab.terminal.snapshot._prev_trading_date", return_value=None):
                dash = build_dashboard("^SPX", date(2026, 5, 29), time_of_day="13:00:00")
    json.dumps(dash)


def test_session_hours_accepts_live_sentinel() -> None:
    from quant_lab.terminal.snapshot import _session_hours_to_close

    with patch("quant_lab.terminal.snapshot.is_live_session", return_value=True):
        hrs = _session_hours_to_close(date(2026, 5, 29), "live")
    assert 0.0 <= hrs <= 6.5

    hrs_hist = _session_hours_to_close(date(2023, 7, 11), "live")
    assert 0.0 <= hrs_hist <= 6.5


def test_build_dashboard_live_time_does_not_crash() -> None:
    from quant_lab.terminal.snapshot import build_dashboard

    with patch("quant_lab.terminal.snapshot._load_terminal_row", return_value=_minimal_row()):
        with patch(
            "quant_lab.terminal.snapshot._load_intraday_chain_safe",
            return_value=(_minimal_chain(), 5900.0, "13:00:00", "live"),
        ):
            with patch("quant_lab.terminal.snapshot._prev_trading_date", return_value=None):
                with patch("quant_lab.terminal.snapshot.is_live_session", return_value=True):
                    dash = build_dashboard("^SPX", date(2026, 5, 29), time_of_day="live")
    json.dumps(dash)
    assert dash["meta"]["chain_time_requested"] == "now"


def _minimal_row() -> dict:
    return {
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


def _minimal_chain():
    import pandas as pd

    return pd.DataFrame(
        {
            "symbol": ["SPXW", "SPXW"],
            "expiry": [date(2026, 5, 29), date(2026, 5, 29)],
            "strike": [5900.0, 5900.0],
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
