"""Playbook fusion structure gate tests."""

from __future__ import annotations

from datetime import date

from quant_lab.terminal.pin_playbook import build_pin_playbook


def _playbook(**kwargs):
    defaults = dict(
        symbol="^SPX",
        session_date=date(2024, 1, 19),
        time_of_day="13:30:00",
        regime="long_gamma",
        pin_score=78.0,
        pct_gex_dte1=45.0,
        spot=7130.0,
        put_wall=7100.0,
        call_wall=7160.0,
        king=7135.0,
        max_pain=7130.0,
        expected_move=35.0,
        gate_should_trade=True,
        gate_reason="ok",
    )
    defaults.update(kwargs)
    return build_pin_playbook(**defaults)


def test_playbook_structure_check_blocks_momentum_conflict() -> None:
    pb = _playbook(
        fusion_entry_blocked=True,
        fusion_entry_blocked_reason="structure_momentum_conflict",
        fusion_execution_state="dynamic_conflict_pin_wait",
    )
    structure_check = next(c for c in pb.checks if c.id == "structure")
    assert structure_check.passed is False
    assert pb.actionable is False


def test_playbook_structure_check_passes_when_aligned() -> None:
    pb = _playbook(
        fusion_center_confidence="high",
        fusion_execution_state="macro_target_watch",
        pin_center=7135.0,
    )
    structure_check = next(c for c in pb.checks if c.id == "structure")
    assert structure_check.passed is True
