"""Session / calendar context features."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import SESSION_CLOSE, SESSION_OPEN
from quant_lab.data.point_in_time_replay import PointInTimeState


def _minutes_between(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds() / 60.0, 0.0)


def compute_context_features(state: PointInTimeState) -> dict[str, Any]:
    as_of = state.as_of_timestamp
    session = state.session
    trade_date = session.trade_date
    open_dt = datetime.combine(trade_date, session.rth_start or SESSION_OPEN, tzinfo=MARKET_TZ)
    close_dt = datetime.combine(trade_date, session.rth_end or SESSION_CLOSE, tzinfo=MARKET_TZ)
    early_close = session.rth_end < SESSION_CLOSE if session.rth_end else False

    minutes_since_open = _minutes_between(open_dt, as_of)
    minutes_to_close = _minutes_between(as_of, close_dt)
    minutes_to_expiry = minutes_to_close  # 0DTE: expiry at session close

    day_of_week = trade_date.weekday()
    fraction = minutes_since_open / max(_minutes_between(open_dt, close_dt), 1.0)
    angle = 2.0 * math.pi * fraction

    return {
        "trade_date": trade_date.isoformat(),
        "as_of_timestamp": as_of.isoformat(),
        "minutes_since_open": minutes_since_open,
        "minutes_to_close": minutes_to_close,
        "minutes_to_expiry": minutes_to_expiry,
        "session_status": session.phase,
        "early_close": early_close,
        "day_of_week": day_of_week,
        "time_bucket": _time_bucket(minutes_since_open),
        "time_sin": math.sin(angle),
        "time_cos": math.cos(angle),
    }


def _time_bucket(minutes_since_open: float) -> str:
    if minutes_since_open < 30:
        return "open_30m"
    if minutes_since_open < 120:
        return "mid_morning"
    if minutes_since_open < 330:
        return "midday"
    return "close_window"
