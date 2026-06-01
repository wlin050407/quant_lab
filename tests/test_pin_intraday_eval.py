"""Tests for intraday pin evaluation helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_lab.factors.positioning import top_oi_strike
from quant_lab.factors.pin_intraday_eval import session_time_to_close_pct


def _row(strike: float, right: str, oi: int, *, dte: int = 0) -> dict:
    return {
        "strike": strike,
        "right": right,
        "open_interest": oi,
        "dte": dte,
    }


def test_top_oi_strike_picks_heaviest_strike() -> None:
    chain = pd.DataFrame(
        [
            _row(100, "C", 10),
            _row(100, "P", 10),
            _row(105, "C", 500),
            _row(105, "P", 500),
        ]
    )
    assert top_oi_strike(chain) == pytest.approx(105.0)


def test_session_time_to_close_pct_open_and_close() -> None:
    from datetime import date

    d = date(2024, 6, 3)
    assert session_time_to_close_pct(d, "09:30:00") == pytest.approx(0.0, abs=1e-6)
    assert session_time_to_close_pct(d, "16:00:00") == pytest.approx(100.0, abs=1e-6)
    mid = session_time_to_close_pct(d, "13:00:00")
    assert 40.0 < mid < 60.0
