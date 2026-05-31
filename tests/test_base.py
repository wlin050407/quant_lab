"""Unit tests for quant_lab.data.base helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from quant_lab.data.base import market_date


def test_market_date_utc_midday_maps_to_same_et_date() -> None:
    ts = datetime(2026, 5, 19, 18, 0, tzinfo=timezone.utc)
    assert market_date(ts) == date(2026, 5, 19)


def test_market_date_pacific_evening_stays_today() -> None:
    """17:00 PT == 00:00 UTC next day; ET session date is still today."""
    ts = datetime(2026, 5, 20, 0, 0, tzinfo=timezone.utc)
    assert market_date(ts) == date(2026, 5, 19)


def test_market_date_beijing_morning_is_previous_et_day() -> None:
    """09:00 Beijing on 5/20 == 21:00 UTC on 5/19 == 17:00 ET on 5/19."""
    beijing = ZoneInfo("Asia/Shanghai")
    ts = datetime(2026, 5, 20, 9, 0, tzinfo=beijing)
    assert market_date(ts) == date(2026, 5, 19)


def test_market_date_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        market_date(datetime(2026, 5, 19, 12, 0))


def test_market_date_after_midnight_et_advances() -> None:
    """01:00 ET on 5/20 is a new market session day."""
    ts = datetime(2026, 5, 20, 5, 0, tzinfo=timezone.utc)
    assert market_date(ts) == date(2026, 5, 20)
