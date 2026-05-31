"""Tests for Terminal cloud deploy helpers."""

from __future__ import annotations

from datetime import date

import pytest

from quant_lab.terminal import deploy


def test_recent_trading_dates_two_week_window() -> None:
    friday = date(2026, 5, 29)
    out = deploy.recent_trading_dates(days=14, today=friday)
    assert out[0] == "2026-05-15"
    assert out[-1] == "2026-05-29"
    assert "2026-05-16" not in out  # Saturday
    assert "2026-05-17" not in out  # Sunday


def test_filter_dates_by_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    friday = date(2026, 5, 29)
    dates = ["2026-05-01", "2026-05-20", "2026-05-29"]
    monkeypatch.setenv("TERMINAL_HISTORY_DAYS", "14")
    filtered = deploy.filter_dates_by_retention(dates, today=friday)
    assert "2026-05-01" not in filtered
    assert filtered == ["2026-05-20", "2026-05-29"]


def test_history_retention_unset_means_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TERMINAL_HISTORY_DAYS", raising=False)
    assert deploy.history_retention_days() is None
    assert deploy.is_date_in_history_window(date(2020, 1, 1)) is True


def test_basic_auth_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TERMINAL_AUTH_USER", raising=False)
    monkeypatch.delenv("TERMINAL_AUTH_PASSWORD", raising=False)
    assert deploy.basic_auth_credentials() is None

    monkeypatch.setenv("TERMINAL_AUTH_USER", "ops")
    monkeypatch.setenv("TERMINAL_AUTH_PASSWORD", "secret")
    assert deploy.basic_auth_credentials() == ("ops", "secret")
