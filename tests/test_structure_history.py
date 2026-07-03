"""Tests for structure history ring buffer."""

from __future__ import annotations

from unittest.mock import patch

from quant_lab.terminal.structure_history import (
    clear_structure_history,
    record_structure_sample,
    samples_for,
    trend_pct,
)


def test_record_structure_sample_coalesces_within_window() -> None:
    clear_structure_history()
    classic = {"spot": 7000.0, "sum_gex_vol": 100.0, "zero_gamma": 6990.0}
    record_structure_sample("^SPX", classic=classic, orderflow={"gex_orderflow": 10.0})
    record_structure_sample("^SPX", classic={**classic, "sum_gex_vol": 200.0})
    rows = samples_for("^SPX")
    assert len(rows) == 1
    assert rows[0].sum_gex_vol == 200.0


def test_trend_pct_after_two_samples() -> None:
    clear_structure_history()
    with patch("quant_lab.terminal.structure_history.time.monotonic", side_effect=[100.0, 200.0]):
        record_structure_sample("^SPX", classic={"spot": 7000.0, "sum_gex_vol": 100.0})
        record_structure_sample("^SPX", classic={"spot": 7010.0, "sum_gex_vol": 150.0})
    pct = trend_pct("^SPX", "sum_gex_vol", lookback_sec=60.0)
    assert pct is not None
    assert pct == 0.5
