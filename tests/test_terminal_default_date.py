"""Tests for default terminal date selection."""

from datetime import date
from unittest.mock import patch

from quant_lab.terminal.snapshot import is_trading_weekday, list_terminal_dates, resolve_default_terminal_date


def test_is_trading_weekday() -> None:
    assert is_trading_weekday(date(2026, 5, 29)) is True  # Fri
    assert is_trading_weekday(date(2026, 5, 31)) is False  # Sun


def test_default_date_weekend_uses_latest() -> None:
    dates = ["2026-05-27", "2026-05-28", "2026-05-29"]
    sunday = date(2026, 5, 31)
    with patch("quant_lab.terminal.snapshot.market_today", return_value=sunday):
        with patch("quant_lab.terminal.snapshot.is_live_session", return_value=True):
            assert resolve_default_terminal_date("^SPX", dates) == "2026-05-29"


def test_default_date_skips_weekend_latest() -> None:
    """EoD parquet may include Sat/Sun rows — default must not land on them."""
    dates = ["2026-05-27", "2026-05-29", "2026-05-30"]
    sunday = date(2026, 5, 31)
    with patch("quant_lab.terminal.snapshot.market_today", return_value=sunday):
        with patch("quant_lab.terminal.snapshot.is_live_session", return_value=True):
            assert resolve_default_terminal_date("^SPX", dates) == "2026-05-29"


def test_default_date_weekend_uses_calendar_when_parquet_sparse() -> None:
    """Live default on Sunday is Fri 29 even if stored history stops at Mon 25."""
    dates = ["2026-05-19", "2026-05-20", "2026-05-25", "2026-05-30"]
    sunday = date(2026, 5, 31)
    with patch("quant_lab.terminal.snapshot.market_today", return_value=sunday):
        with patch("quant_lab.terminal.snapshot.is_live_session", return_value=True):
            assert resolve_default_terminal_date("^SPX", dates) == "2026-05-29"


def test_default_date_weekday_prefers_today() -> None:
    dates = ["2026-05-27", "2026-05-28", "2026-05-29"]
    friday = date(2026, 5, 29)
    with patch("quant_lab.terminal.snapshot.market_today", return_value=friday):
        with patch("quant_lab.terminal.snapshot.is_live_session", return_value=True):
            assert resolve_default_terminal_date("^SPX", dates) == "2026-05-29"


def test_list_terminal_dates_skips_weekend_today(monkeypatch) -> None:
    sunday = date(2026, 5, 31)

    def fake_list_option_snapshots(symbol: str) -> list[str]:
        return ["2026-05-29"]

    monkeypatch.setattr("quant_lab.terminal.snapshot.list_option_snapshots", fake_list_option_snapshots)
    monkeypatch.setattr(
        "quant_lab.terminal.snapshot.list_intraday_chain_dates",
        lambda **_: [],
    )
    monkeypatch.setattr("quant_lab.terminal.snapshot._terminal_path", lambda _: type("P", (), {"exists": lambda self: False})())

    with patch("quant_lab.terminal.snapshot.market_today", return_value=sunday):
        out = list_terminal_dates("^SPX")
    assert "2026-05-31" not in out
    assert out[-1] == "2026-05-29"
