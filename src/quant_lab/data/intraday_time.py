"""US equity session time helpers for 0DTE intraday greeks."""

from __future__ import annotations

from datetime import date, datetime, time

from quant_lab.data.base import MARKET_TZ

# Regular session: 09:30–16:00 ET (6.5 hours).
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
SESSION_HOURS = 6.5
TRADING_DAYS_PER_YEAR = 365.0


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
