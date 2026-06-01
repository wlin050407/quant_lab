"""Magnet shift tracking for live Terminal."""

from __future__ import annotations

import pytest

from quant_lab.terminal.magnet_state import clear_magnet_state, record_magnet_shift


@pytest.fixture(autouse=True)
def _reset_magnet_state() -> None:
    clear_magnet_state()
    yield
    clear_magnet_state()


def test_magnet_shift_detects_strike_change() -> None:
    assert record_magnet_shift("^SPX", "2026-05-24", 5900.0) is None
    shift = record_magnet_shift("^SPX", "2026-05-24", 5910.0)
    assert shift is not None
    assert shift.previous == pytest.approx(5900.0)
    assert shift.current == pytest.approx(5910.0)
    assert shift.delta_pts == pytest.approx(10.0)


def test_magnet_shift_ignored_when_unchanged() -> None:
    record_magnet_shift("^SPX", "2026-05-24", 5900.0)
    assert record_magnet_shift("^SPX", "2026-05-24", 5900.0) is None
