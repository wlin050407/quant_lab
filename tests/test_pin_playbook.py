"""Tests for Pin Play Terminal playbook."""

from __future__ import annotations

from datetime import date

import pytest

from quant_lab.terminal.pin_playbook import (
    build_pin_playbook,
    session_phase,
)


def test_session_phase_entry_window() -> None:
    phase, title, _ = session_phase("13:30:00")
    assert phase == "entry_window"
    assert title == "Entry window"


def test_session_phase_manage_after_1400() -> None:
    phase, _, _ = session_phase("14:15:00")
    assert phase == "manage"


def test_pin_playbook_sizing_long_gamma_high_pin() -> None:
    pb = build_pin_playbook(
        symbol="^SPX",
        session_date=date(2023, 7, 11),
        time_of_day="13:30:00",
        regime="long_gamma",
        pin_score=78.0,
        pct_gex_dte1=45.0,
        spot=4500.0,
        put_wall=4450.0,
        call_wall=4550.0,
        king=4500.0,
        max_pain=4495.0,
        expected_move=25.0,
        gate_should_trade=True,
        gate_reason="ok",
        trinity_score=80.0,
        trinity_direction="aligned",
    )
    assert pb.size_multiplier == pytest.approx(1.0)
    assert pb.actionable is True
    assert pb.structure is not None
    assert pb.structure.center == 4500.0
    assert pb.structure.wing_width == 25.0


def test_pin_playbook_short_gamma_zero_size() -> None:
    pb = build_pin_playbook(
        symbol="^SPX",
        session_date=date(2023, 7, 11),
        time_of_day="13:30:00",
        regime="short_gamma",
        pin_score=80.0,
        pct_gex_dte1=50.0,
        spot=4500.0,
        put_wall=4450.0,
        call_wall=4550.0,
        king=4500.0,
        max_pain=4495.0,
        expected_move=25.0,
        gate_should_trade=True,
        gate_reason="ok",
    )
    assert pb.size_multiplier == 0.0
    assert pb.actionable is False


def test_pin_playbook_low_pin_caps_gate() -> None:
    pb = build_pin_playbook(
        symbol="SPY",
        session_date=date(2023, 7, 11),
        time_of_day="13:30:00",
        regime="long_gamma",
        pin_score=55.0,
        pct_gex_dte1=40.0,
        spot=450.0,
        put_wall=440.0,
        call_wall=460.0,
        king=452.0,
        max_pain=450.0,
        expected_move=2.5,
        gate_should_trade=True,
        gate_reason="ok",
    )
    # pin 0.5 × regime 1.0 × gate cap 0.25 (pin < 70)
    assert pb.size_multiplier == pytest.approx(0.125)
