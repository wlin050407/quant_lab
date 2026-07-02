"""Tests for GEXBot historical cache normalization."""

from __future__ import annotations

from quant_lab.data.gexbot_history_cache import _normalize_hist_rows, snapshot_at_unix


def test_normalize_hist_rows_sorted() -> None:
    rows = [
        {"timestamp": 100, "spot": 1.0, "zero_gamma": 0.5, "strikes": []},
        {"timestamp": 99, "spot": 1.0, "zero_gamma": 0.4, "strikes": []},
    ]
    df = _normalize_hist_rows(rows)
    assert list(df["timestamp_unix"]) == [99, 100]


def test_snapshot_at_unix_nearest_before() -> None:
    df = _normalize_hist_rows(
        [
            {"timestamp": 100, "spot": 5000.0, "zero_gamma": 4980.0},
            {"timestamp": 105, "spot": 5005.0, "zero_gamma": 4985.0},
        ]
    )
    snap = snapshot_at_unix(df, 103)
    assert snap["spot"] == 5000.0
