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
from quant_lab.data.thetadata_chain import build_0dte_chain_snapshot, ChainMode
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

DEFAULT_PIN_PLAY_TIME = "13:00:00"
"""Default intraday slot when UI sends ``live`` on a non-live session day."""

STALE_CACHE_MAX_SECONDS = 300.0
"""Max age past TTL we will still serve a cached chain when the live pull fails.

Stale-while-error: if ThetaData hiccups (UNAVAILABLE / DEADLINE_EXCEEDED /
session expiry / NoDataFound during a transient gap), serve the most recent
successful chain rather than cascading the request all the way back to
yesterday's EoD parquet. 5 minutes is well past one ``LIVE_REFRESH_SECONDS``
tick but short enough that we never display badly out-of-date pin levels.
"""

# Key: (terminal_symbol, session_date_iso, time_label, chain_mode)
# Value: (expires_at_monotonic, chain, spot, time_used)
_CacheKey = tuple[str, str, str, str]
_CacheValue = tuple[float, pd.DataFrame, float, str]
_live_cache: dict[_CacheKey, _CacheValue] = {}


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


def resolve_intraday_clock(session_date: date, time_of_day: str) -> str:
    """Resolve ``live`` / pin-play token to ``HH:MM:SS`` for chain loads and session math."""
    if time_of_day.strip().lower() == LIVE_TIME_OF_DAY:
        if not is_live_session(session_date):
            return DEFAULT_PIN_PLAY_TIME
        now = datetime.now(MARKET_TZ)
        open_dt = session_datetime(session_date, "09:30:00")
        close_dt = session_datetime(session_date, "16:00:00")
        clamped = min(max(now, open_dt), close_dt)
        return clamped.strftime("%H:%M:%S")
    return time_of_day


def _effective_time_of_day(session_date: date, time_of_day: str) -> str:
    """Resolve pull clock: ``live`` → now ET; cap future; floor pre-open on live day."""
    if time_of_day.strip().lower() == LIVE_TIME_OF_DAY:
        return resolve_intraday_clock(session_date, time_of_day)
    if not is_live_session(session_date):
        return time_of_day
    now = datetime.now(MARKET_TZ)
    open_dt = session_datetime(session_date, "09:30:00")
    req = session_datetime(session_date, time_of_day)
    if req > now:
        return now.strftime("%H:%M:%S")
    if req < open_dt:
        return "09:30:00"
    return time_of_day


def clear_live_cache() -> None:
    """Clear in-memory live chain cache (tests)."""
    _live_cache.clear()


def _serve_stale_cache(
    cache_key: _CacheKey,
    symbol: str,
    effective_time: str,
    chain_mode: ChainMode,
    exc: BaseException,
    now_mono: float,
) -> tuple[pd.DataFrame, float, str, bool] | None:
    """Return last successful cached chain when within ``STALE_CACHE_MAX_SECONDS``.

    Stale-while-error: a single ThetaData hiccup should not bounce the UI
    back to yesterday's EoD parquet when we have a 30-second-old good chain
    sitting in memory. ``None`` means no usable stale entry — caller should
    propagate the original exception.
    """
    stale = _live_cache.get(cache_key)
    if stale is None:
        return None
    expires_at, chain, spot, time_used = stale
    overdue = now_mono - expires_at
    if overdue > STALE_CACHE_MAX_SECONDS:
        return None
    log.warning(
        "ThetaData fetch failed for %s @ %s mode=%s — serving stale cache "
        "(%.0fs past TTL, max %.0fs): %s",
        symbol,
        effective_time,
        chain_mode,
        max(0.0, overdue),
        STALE_CACHE_MAX_SECONDS,
        exc,
    )
    return chain.copy(), spot, time_used, True


def fetch_intraday_chain_from_thetadata(
    session_date: date,
    time_of_day: str,
    *,
    symbol: str = "^SPX",
    strike_range: int | None = None,
    cache_ttl_seconds: float | None = None,
    chain_mode: ChainMode = "pin",
) -> tuple[pd.DataFrame, float, str, bool]:
    """Build 0DTE chain from ThetaData for any recent session date.

    Returns ``(chain, spot, time_used, from_cache)``.

    On a transient ThetaData failure we serve the most recent cached chain
    (see ``_serve_stale_cache``) instead of letting the error propagate up to
    ``build_dashboard``'s EoD fallback path.
    """
    spec = resolve_intraday_spec(symbol)
    if spec is None:
        raise ValueError(f"no live intraday spec for {symbol!r}")

    effective_time = _effective_time_of_day(session_date, time_of_day)
    live_follow = (
        time_of_day.strip().lower() == LIVE_TIME_OF_DAY and is_live_session(session_date)
    )
    cache_key: _CacheKey = (
        spec.terminal_symbol,
        session_date.isoformat(),
        "live" if live_follow else effective_time,
        chain_mode,
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
            log.debug(
                "ThetaData chain cache hit %s %s @ %s mode=%s",
                spec.terminal_symbol,
                session_date.isoformat(),
                time_used,
                chain_mode,
            )
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
            chain_mode=chain_mode,
        )

    t0 = time.monotonic()
    try:
        snapshot = _build(client)
    except Exception as exc:
        if _is_session_error(exc):
            log.warning(
                "ThetaData session expired during intraday fetch — reconnecting"
            )
            try:
                client = refresh_thetadata_client(dataframe_type="pandas")
                snapshot = _build(client)
            except Exception as retry_exc:
                stale = _serve_stale_cache(
                    cache_key,
                    spec.terminal_symbol,
                    effective_time,
                    chain_mode,
                    retry_exc,
                    now_mono,
                )
                if stale is not None:
                    return stale
                raise
        else:
            stale = _serve_stale_cache(
                cache_key,
                spec.terminal_symbol,
                effective_time,
                chain_mode,
                exc,
                now_mono,
            )
            if stale is not None:
                return stale
            raise

    elapsed_ms = (time.monotonic() - t0) * 1000.0
    chain = snapshot.chain.copy()
    spot = float(snapshot.spot)
    _live_cache[cache_key] = (
        now_mono + ttl,
        chain.copy(),
        spot,
        effective_time,
    )
    log.info(
        "ThetaData intraday chain %s %s @ %s mode=%s (%d rows, %.0fms)",
        spec.terminal_symbol,
        session_date.isoformat(),
        effective_time,
        chain_mode,
        len(chain),
        elapsed_ms,
    )
    return chain, spot, effective_time, False


def fetch_live_intraday_chain(
    session_date: date,
    time_of_day: str,
    *,
    symbol: str = "^SPX",
    strike_range: int | None = None,
    cache_ttl_seconds: float | None = None,
    chain_mode: ChainMode = "pin",
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
        chain_mode=chain_mode,
    )
