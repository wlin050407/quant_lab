"""Live ThetaData intraday chain fetch for Terminal (today only).

Historical sessions use local parquet via ``load_built_intraday_chain``.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import TYPE_CHECKING

import pandas as pd

from quant_lab.config import env_var
from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.thetadata_chain import build_0dte_chain_snapshot
from quant_lab.data.thetadata_client import get_thetadata_client, refresh_thetadata_client
from quant_lab.terminal.intraday_spec import resolve_intraday_spec

if TYPE_CHECKING:
    from thetadata import ThetaClient

log = logging.getLogger(__name__)

DEFAULT_STRIKE_RANGE = 80
DEFAULT_CACHE_TTL_SECONDS = 30.0
HISTORICAL_CACHE_TTL_SECONDS = 3600.0
LIVE_REFRESH_SECONDS = 30
"""Default live REST poll interval (override via ``TERMINAL_LIVE_REFRESH_SECONDS``)."""

LIVE_TIME_OF_DAY = "live"
"""Sentinel: on today's session, pull chain at current ET clock (not a fixed pin-play slot)."""

_live_cache: dict[tuple[str, str, str], tuple[float, pd.DataFrame, float, str]] = {}


def live_refresh_seconds() -> float:
    """Seconds between live snapshot polls (REST pull; WebSocket not required for pin)."""
    raw = env_var("TERMINAL_LIVE_REFRESH_SECONDS")
    if raw is None:
        return LIVE_REFRESH_SECONDS
    try:
        secs = float(raw)
    except ValueError as exc:
        raise ValueError(f"TERMINAL_LIVE_REFRESH_SECONDS must be numeric, got {raw!r}") from exc
    if secs < 15.0:
        raise ValueError("TERMINAL_LIVE_REFRESH_SECONDS must be >= 15")
    return secs


def market_today() -> date:
    """Current calendar date in US/Eastern (session timezone)."""
    return datetime.now(MARKET_TZ).date()


def is_live_session(session_date: date) -> bool:
    """True when ``session_date`` is today ET — use ThetaData pull, not historical parquet."""
    return session_date == market_today()


def _is_session_error(exc: BaseException) -> bool:
    msg = str(exc)
    return "Invalid session ID" in msg or "UNAUTHENTICATED" in msg


def _effective_time_of_day(session_date: date, time_of_day: str) -> str:
    """Resolve pull clock: ``live`` → now ET; cap future; floor pre-open on live day."""
    if not is_live_session(session_date):
        return time_of_day
    now = datetime.now(MARKET_TZ)
    open_dt = session_datetime(session_date, "09:30:00")
    close_dt = session_datetime(session_date, "16:00:00")
    if time_of_day.strip().lower() == LIVE_TIME_OF_DAY:
        clamped = min(max(now, open_dt), close_dt)
        return clamped.strftime("%H:%M:%S")
    req = session_datetime(session_date, time_of_day)
    if req > now:
        return now.strftime("%H:%M:%S")
    if req < open_dt:
        return "09:30:00"
    return time_of_day


def clear_live_cache() -> None:
    """Clear in-memory live chain cache (tests)."""
    _live_cache.clear()


def fetch_intraday_chain_from_thetadata(
    session_date: date,
    time_of_day: str,
    *,
    symbol: str = "^SPX",
    strike_range: int | None = None,
    cache_ttl_seconds: float | None = None,
) -> tuple[pd.DataFrame, float, str, bool]:
    """Build 0DTE chain from ThetaData for any recent session date.

    Returns ``(chain, spot, time_used, from_cache)``.
    """
    spec = resolve_intraday_spec(symbol)
    if spec is None:
        raise ValueError(f"no live intraday spec for {symbol!r}")

    effective_time = _effective_time_of_day(session_date, time_of_day)
    live_follow = (
        time_of_day.strip().lower() == LIVE_TIME_OF_DAY and is_live_session(session_date)
    )
    cache_key = (
        spec.terminal_symbol,
        session_date.isoformat(),
        "live" if live_follow else effective_time,
    )
    ttl = (
        cache_ttl_seconds
        if cache_ttl_seconds is not None
        else (
            live_refresh_seconds()
            if is_live_session(session_date)
            else HISTORICAL_CACHE_TTL_SECONDS
        )
    )
    now_mono = time.monotonic()
    cached = _live_cache.get(cache_key)
    if cached is not None:
        expires_at, chain, spot, time_used = cached
        if now_mono < expires_at:
            return chain.copy(), spot, time_used, True

    client = get_thetadata_client(dataframe_type="pandas")
    range_used = strike_range if strike_range is not None else spec.strike_range

    def _build(c: ThetaClient):
        return build_0dte_chain_snapshot(
            c,
            session_date=session_date,
            time_of_day=effective_time,
            option_root=spec.option_root,
            terminal_symbol=spec.terminal_symbol,
            underlying_kind=spec.underlying_kind,
            underlying_symbol=spec.underlying_symbol,
            strike_range=range_used,
        )

    try:
        snapshot = _build(client)
    except Exception as exc:
        if not _is_session_error(exc):
            raise
        log.warning("ThetaData session expired during intraday fetch — reconnecting")
        client = refresh_thetadata_client(dataframe_type="pandas")
        snapshot = _build(client)

    chain = snapshot.chain.copy()
    spot = float(snapshot.spot)
    _live_cache[cache_key] = (
        now_mono + ttl,
        chain.copy(),
        spot,
        effective_time,
    )
    log.info(
        "ThetaData intraday chain %s %s @ %s (%d rows)",
        spec.terminal_symbol,
        session_date.isoformat(),
        effective_time,
        len(chain),
    )
    return chain, spot, effective_time, False


def fetch_live_intraday_chain(
    session_date: date,
    time_of_day: str,
    *,
    symbol: str = "^SPX",
    strike_range: int | None = None,
    cache_ttl_seconds: float | None = None,
) -> tuple[pd.DataFrame, float, str, bool]:
    """Build 0DTE chain from ThetaData for ``session_date`` (today).

    Returns ``(chain, spot, time_used, from_cache)``.
    """
    if not is_live_session(session_date):
        raise ValueError(f"fetch_live_intraday_chain is for today only, got {session_date}")

    return fetch_intraday_chain_from_thetadata(
        session_date,
        time_of_day,
        symbol=symbol,
        strike_range=strike_range,
        cache_ttl_seconds=cache_ttl_seconds if cache_ttl_seconds is not None else live_refresh_seconds(),
    )
