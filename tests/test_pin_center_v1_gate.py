"""V1/V2 tiered gate evaluation tests."""

from __future__ import annotations

from quant_lab.terminal.pin_center_replay import evaluate_v1_gate, evaluate_v2_gate


def test_v1_full_pass() -> None:
    out = evaluate_v1_gate(
        n_sessions=250,
        n_hist_terminal_overlap=79,
        median_fused=2.0,
        median_king=2.5,
        median_primary=3.0,
        fused_beats_king_rate=0.98,
    )
    assert out["v1_pass"] is True
    assert out["v1_tier"] == "full"


def test_v1_hist_pilot_pass() -> None:
    out = evaluate_v1_gate(
        n_sessions=53,
        n_hist_terminal_overlap=79,
        median_fused=1.3,
        median_king=1.3,
        median_primary=2.5,
        fused_beats_king_rate=1.0,
    )
    assert out["v1_hist_pilot_min_n"] == 39
    assert out["v1_pass"] is True
    assert out["v1_tier"] == "hist_pilot"


def test_v1_fail_low_n() -> None:
    out = evaluate_v1_gate(
        n_sessions=10,
        n_hist_terminal_overlap=79,
        median_fused=1.0,
        median_king=2.0,
        median_primary=3.0,
        fused_beats_king_rate=1.0,
    )
    assert out["v1_pass"] is False
    assert out["v1_tier"] == "fail"


def test_v2_hist_pilot_pass() -> None:
    out = evaluate_v2_gate(
        n_sessions=50,
        n_hist_terminal_overlap=79,
        primary_hit_30m_rate=0.92,
    )
    assert out["v2_pass"] is True
    assert out["v2_tier"] == "hist_pilot"
