"""Tests for vendor startup background tasks."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from quant_lab.terminal import startup_tasks
from quant_lab.terminal.startup_tasks import is_us_rth_now, prewarm_gexbot_history


@pytest.fixture(autouse=True)
def _reset_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERMINAL_GEXBOT_WS", "0")
    startup_tasks._threads.clear()
    startup_tasks._shutdown.clear()
    yield
    startup_tasks.stop_background_tasks()


def test_prewarm_counts_ok_and_skipped() -> None:
    client = MagicMock()
    dates = [date(2026, 6, 30), date(2026, 7, 1)]

    with patch(
        "quant_lab.terminal.startup_tasks.recent_trading_dates",
        return_value=[d.isoformat() for d in dates],
    ):
        with patch(
            "quant_lab.terminal.startup_tasks.load_or_fetch_hist_day",
            side_effect=[MagicMock(), FileNotFoundError("holiday")],
        ) as mock_load:
            with patch("quant_lab.terminal.startup_tasks.time.sleep"):
                stats = prewarm_gexbot_history(symbols=("^SPX",), client=client, days=2)
    assert mock_load.call_count == 2
    assert stats["ok"] == 1
    assert stats["skipped"] == 1


def test_start_background_tasks_vendor_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERMINAL_PREWARM_HIST", "0")
    monkeypatch.setenv("TERMINAL_VENDOR_LIVE_POLLER", "0")
    with patch(
        "quant_lab.terminal.startup_tasks.resolve_terminal_chain_provider",
        return_value="vendor",
    ):
        startup_tasks.start_background_tasks()
    assert startup_tasks._threads == []


def test_start_background_tasks_spawns_prewarm_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERMINAL_PREWARM_HIST", "1")
    monkeypatch.setenv("TERMINAL_VENDOR_LIVE_POLLER", "0")
    with patch(
        "quant_lab.terminal.startup_tasks.resolve_terminal_chain_provider",
        return_value="vendor",
    ):
        with patch("quant_lab.terminal.startup_tasks._run_prewarm") as mock_prewarm:
            startup_tasks.start_background_tasks()
            assert len(startup_tasks._threads) == 1
            startup_tasks._threads[0].join(timeout=1.0)
            mock_prewarm.assert_called_once()


def test_is_us_rth_now_weekend_false() -> None:
    from quant_lab.data.base import MARKET_TZ
    from datetime import datetime

    sat = datetime(2026, 7, 4, 12, 0, tzinfo=MARKET_TZ)
    with patch("quant_lab.terminal.startup_tasks.datetime") as mock_dt:
        mock_dt.now.return_value = sat
        assert is_us_rth_now() is False
