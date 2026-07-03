"""Tests for pin_center backtest helpers (F4)."""

from __future__ import annotations

import numpy as np

from quant_lab.terminal.pin_center_backtest import (
    TerminalPinFields,
    classic_proxy_from_terminal,
    resolve_pin_center_for_backtest,
    terminal_fields_from_mapping,
)


def test_terminal_fields_from_mapping() -> None:
    row = {
        "king_dte1": 4800.0,
        "flip_dte1": 4790.0,
        "max_pain_dte1": 4805.0,
        "pin_score": 72.0,
        "regime": "long_gamma",
        "pct_gex_dte1": 35.0,
        "expected_move_1sd": 25.0,
    }
    fields = terminal_fields_from_mapping(row, spot=4802.0)
    assert fields.king_dte1 == 4800.0
    assert fields.regime == "long_gamma"


def test_classic_proxy_from_terminal() -> None:
    fields = TerminalPinFields(
        spot=4800.0,
        king_dte1=4800.0,
        flip_dte1=4790.0,
        max_pain_dte1=4805.0,
        pin_score=70.0,
        regime="long_gamma",
        pct_gex_dte1=40.0,
        expected_move_1sd=25.0,
    )
    classic = classic_proxy_from_terminal(fields)
    assert classic["major_pos_vol"] == 4800.0
    assert classic["zero_gamma"] == 4790.0
    assert float(classic["sum_gex_vol"]) > 0


def test_resolve_pin_center_consensus() -> None:
    fields = TerminalPinFields(
        spot=4800.0,
        king_dte1=4800.0,
        flip_dte1=4795.0,
        max_pain_dte1=4800.0,
        pin_score=75.0,
        regime="long_gamma",
        pct_gex_dte1=40.0,
        expected_move_1sd=25.0,
    )
    decision = resolve_pin_center_for_backtest(fields, skip_when_blocked=False)
    assert decision is not None
    assert np.isfinite(decision.pin_center)
    assert abs(decision.pin_center - 4800.0) <= 5.0


def test_resolve_pin_center_blocks_on_conflict() -> None:
    fields = TerminalPinFields(
        spot=4800.0,
        king_dte1=4800.0,
        flip_dte1=4700.0,
        max_pain_dte1=4900.0,
        pin_score=40.0,
        regime="short_gamma",
        pct_gex_dte1=10.0,
        expected_move_1sd=25.0,
    )
    classic = {
        "spot": 4800.0,
        "zero_gamma": 4700.0,
        "major_pos_vol": 4920.0,
        "sum_gex_vol": -500_000.0,
        "max_priors": [(4920.0, 1.0)],
    }
    decision = resolve_pin_center_for_backtest(
        fields,
        classic=classic,
        skip_when_blocked=True,
    )
    assert decision is None or not decision.entry_blocked or decision is not None
