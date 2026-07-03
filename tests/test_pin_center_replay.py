"""Tests for pin center offline replay."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant_lab.terminal.pin_center_replay import replay_session


def _hist_day() -> pd.DataFrame:
    base = 1_700_000_000
    rows = []
    for i, spot in enumerate([7125.0, 7130.0, 7132.0, 7135.0, 7133.0]):
        rows.append(
            {
                "timestamp_unix": base + i * 60,
                "spot": spot,
                "zero_gamma": 7130.0,
                "major_pos_vol": 7135.0,
                "major_neg_vol": 7100.0,
                "sum_gex_vol": 1_200_000.0,
            }
        )
    return pd.DataFrame(rows)


def _terminal_row() -> pd.Series:
    return pd.Series(
        {
            "spot": 7133.0,
            "king_dte1": 7135.0,
            "flip_dte1": 7125.0,
            "max_pain_dte1": 7130.0,
            "pin_score": 78.0,
            "regime": "long_gamma",
            "pct_gex_dte1": 45.0,
        }
    )


def test_replay_session_computes_pin_errors() -> None:
    from quant_lab.data.intraday_time import session_datetime

    session = date(2024, 1, 19)
    t0 = int(session_datetime(session, "13:00:00").timestamp())
    hist = _hist_day().copy()
    hist["timestamp_unix"] = t0 + hist.index.to_numpy(dtype=int) * 60

    row = replay_session(
        terminal_symbol="^SPX",
        session_date=session,
        terminal_row=_terminal_row(),
        hist=hist,
        entry_clock="13:00:00",
        close_clock="13:04:00",
    )
    assert row is not None
    assert row.king_err >= 0.0
    assert row.fused_err >= 0.0


def test_replay_session_respects_pin_min() -> None:
    from quant_lab.data.intraday_time import session_datetime

    session = date(2024, 1, 19)
    t0 = int(session_datetime(session, "13:00:00").timestamp())
    hist = _hist_day().copy()
    hist["timestamp_unix"] = t0 + hist.index.to_numpy(dtype=int) * 60
    row = _terminal_row().copy()
    row["pin_score"] = 55.0

    assert (
        replay_session(
            terminal_symbol="^SPX",
            session_date=session,
            terminal_row=row,
            hist=hist,
            entry_clock="13:00:00",
            close_clock="13:04:00",
            pin_min=70.0,
        )
        is None
    )
    assert (
        replay_session(
            terminal_symbol="^SPX",
            session_date=session,
            terminal_row=row,
            hist=hist,
            entry_clock="13:00:00",
            close_clock="13:04:00",
            pin_min=50.0,
        )
        is not None
    )
