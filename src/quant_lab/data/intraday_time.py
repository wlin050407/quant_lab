"""US equity session time helpers for 0DTE intraday greeks."""

from __future__ import annotations

from datetime import date, datetime, time

from quant_lab.data.base import MARKET_TZ

# Regular session: 09:30–16:00 ET (6.5 hours).
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
SESSION_HOURS = 6.5
TRADING_DAYS_PER_YEAR = 365.0

# Pin time sub-score (FlashAlpha ``time_to_close_hours`` semantics).
PIN_TIME_CURVE_EXPONENT = 0.65
PIN_TIME_LAST_2H_HOURS = 2.0
PIN_TIME_LAST_2H_EXPONENT = 0.45


def parse_time_of_day(value: str) -> time:
    """Parse ``HH:MM`` or ``HH:MM:SS`` into a ``time``."""
    parts = value.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    second = int(parts[2]) if len(parts) > 2 else 0
    return time(hour, minute, second)


def session_datetime(session_date: date, time_of_day: str | time) -> datetime:
    """Combine session date + ET clock time."""
    tod = parse_time_of_day(time_of_day) if isinstance(time_of_day, str) else time_of_day
    return datetime.combine(session_date, tod, tzinfo=MARKET_TZ)


def hours_to_close(session_date: date, time_of_day: str | time) -> float:
    """Trading hours remaining until 16:00 ET on ``session_date``."""
    now = session_datetime(session_date, time_of_day)
    close = datetime.combine(session_date, SESSION_CLOSE, tzinfo=MARKET_TZ)
    open_dt = datetime.combine(session_date, SESSION_OPEN, tzinfo=MARKET_TZ)
    if now < open_dt:
        return SESSION_HOURS
    if now >= close:
        return 0.0
    return max(0.0, (close - now).total_seconds() / 3600.0)


def intraday_time_to_expiry_years(session_date: date, time_of_day: str | time) -> float:
    """Year fraction for 0DTE BS inputs using remaining session hours."""
    hrs = hours_to_close(session_date, time_of_day)
    if hrs <= 0.0:
        return 0.0
    return hrs / (TRADING_DAYS_PER_YEAR * SESSION_HOURS)


def pin_time_remaining_score(
    hours_to_close: float,
    *,
    session_hours: float = SESSION_HOURS,
) -> float:
    """Pin time sub-score 0–100 from **hours to close** (FlashAlpha-aligned).

    Base curve: ``(1 - hrs/session)^0.65``. Inside the final **2 hours** (Pin Play
    entry window), acceleration uses a steeper exponent so afternoon pin ramps faster.
    """
    import numpy as np

    hrs = float(np.clip(hours_to_close, 0.0, session_hours))
    if session_hours <= 0:
        return 100.0 if hrs <= 0 else 0.0
    if hrs <= 0.0:
        return 100.0

    elapsed = 1.0 - hrs / session_hours
    base = float(elapsed**PIN_TIME_CURVE_EXPONENT)

    if hrs <= PIN_TIME_LAST_2H_HOURS:
        window_elapsed = 1.0 - hrs / PIN_TIME_LAST_2H_HOURS
        boost = float(window_elapsed**PIN_TIME_LAST_2H_EXPONENT)
        base_at_2h = float(
            (1.0 - PIN_TIME_LAST_2H_HOURS / session_hours) ** PIN_TIME_CURVE_EXPONENT
        )
        blended = base_at_2h + (1.0 - base_at_2h) * boost
        return float(np.clip(blended * 100.0, 0.0, 100.0))

    return float(np.clip(base * 100.0, 0.0, 100.0))
