"""Tests for pin time sub-score and session hour helpers."""

from __future__ import annotations

from datetime import date

import pytest

from quant_lab.data.intraday_time import (
    SESSION_HOURS,
    hours_to_close,
    pin_time_remaining_score,
)


def test_pin_time_remaining_score_at_close() -> None:
    assert pin_time_remaining_score(0.0) == pytest.approx(100.0)


def test_pin_time_remaining_score_at_open() -> None:
    assert pin_time_remaining_score(SESSION_HOURS) == pytest.approx(0.0, abs=1e-6)


def test_pin_time_last_2h_steeper_than_linear_pct() -> None:
    """Inside Pin Play window, score should exceed legacy pct-only curve."""
    at_1h = pin_time_remaining_score(1.0)
    legacy_pct = (1.0 - 1.0 / SESSION_HOURS) * 100.0
    legacy_score = (legacy_pct / 100.0) ** 0.65 * 100.0
    assert at_1h > legacy_score


def test_hours_to_close_fractional_minutes() -> None:
    d = date(2026, 5, 24)
    hrs_1300 = hours_to_close(d, "13:00:00")
    hrs_1301 = hours_to_close(d, "13:01:00")
    assert hrs_1300 == pytest.approx(3.0)
    assert hrs_1301 == pytest.approx(2.983333, rel=1e-4)
    assert pin_time_remaining_score(hrs_1301) > pin_time_remaining_score(hrs_1300)
