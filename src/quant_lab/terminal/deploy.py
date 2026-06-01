"""Terminal cloud deploy helpers (history window, optional basic auth)."""

from __future__ import annotations

import os
from datetime import date, timedelta

from quant_lab.config import env_var
from quant_lab.terminal.live_chain import market_today

DEFAULT_HISTORY_DAYS = 14


def prefer_thetadata_intraday(session: date, *, today: date | None = None) -> bool:
    """Recent sessions match cloud: pull intraday from ThetaData, not local parquet."""
    anchor = today or market_today()
    cutoff = history_cutoff_date(today=anchor)
    if cutoff is None:
        cutoff = anchor - timedelta(days=DEFAULT_HISTORY_DAYS)
    return session >= cutoff


def is_trading_weekday(session_date: date) -> bool:
    """US equity session calendar day (Mon–Fri). Holidays not filtered here."""
    return session_date.weekday() < 5


def last_trading_session_date(*, anchor: date | None = None) -> date:
    """Most recent Mon–Fri on or before ``anchor`` (default: today ET)."""
    cursor = anchor or market_today()
    while not is_trading_weekday(cursor):
        cursor -= timedelta(days=1)
    return cursor


def history_retention_days() -> int | None:
    """When set, terminal only exposes dates within this many calendar days."""
    raw = env_var("TERMINAL_HISTORY_DAYS")
    if raw is None:
        return None
    try:
        days = int(raw)
    except ValueError as exc:
        raise ValueError(f"TERMINAL_HISTORY_DAYS must be an integer, got {raw!r}") from exc
    if days < 1:
        raise ValueError("TERMINAL_HISTORY_DAYS must be >= 1")
    return days


def history_cutoff_date(*, today: date | None = None) -> date | None:
    """Earliest session date still visible in cloud mode."""
    days = history_retention_days()
    if days is None:
        return None
    anchor = today or market_today()
    return anchor - timedelta(days=days)


def is_date_in_history_window(session_date: date, *, today: date | None = None) -> bool:
    """True when ``session_date`` is within configured retention (or retention disabled)."""
    cutoff = history_cutoff_date(today=today)
    if cutoff is None:
        return True
    return session_date >= cutoff


def recent_trading_dates(*, days: int | None = None, today: date | None = None) -> list[str]:
    """ISO session dates from ``cutoff`` through ``today`` (Mon–Fri only)."""
    window = days if days is not None else history_retention_days()
    if window is None:
        window = DEFAULT_HISTORY_DAYS
    anchor = today or market_today()
    start = anchor - timedelta(days=window)
    out: list[str] = []
    cursor = start
    while cursor <= anchor:
        if is_trading_weekday(cursor):
            out.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return out


def filter_dates_by_retention(dates: list[str], *, today: date | None = None) -> list[str]:
    """Drop dates older than ``TERMINAL_HISTORY_DAYS`` when configured."""
    cutoff = history_cutoff_date(today=today)
    if cutoff is None:
        return dates
    kept = [d for d in dates if date.fromisoformat(d) >= cutoff]
    return sorted(set(kept))


def basic_auth_credentials() -> tuple[str, str] | None:
    """Optional HTTP basic auth for public deploys."""
    user = env_var("TERMINAL_AUTH_USER")
    password = env_var("TERMINAL_AUTH_PASSWORD")
    if user and password:
        return user, password
    return None


def listen_port(default: int = 8765) -> int:
    """``PORT`` env (Railway/Render) with fallback."""
    raw = os.environ.get("PORT", str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"PORT must be an integer, got {raw!r}") from exc
