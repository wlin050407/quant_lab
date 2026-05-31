"""Live ThetaData intraday chain fetch for Terminal (today only).

Historical sessions use local parquet via ``load_built_intraday_chain``.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import TYPE_CHECKING

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.thetadata_chain import build_0dte_chain_snapshot
from quant_lab.data.thetadata_client import get_thetadata_client, refresh_thetadata_client
from quant_lab.terminal.intraday_spec import resolve_intraday_spec

if TYPE_CHECKING:
    from thetadata import ThetaClient

log = logging.getLogger(__name__)

DEFAULT_STRIKE_RANGE = 80
DEFAULT_CACHE_TTL_SECONDS = 60.0
HISTORICAL_CACHE_TTL_SECONDS = 3600.0
"""UI poll interval — matches 1m quote granularity and server cache TTL."""
LIVE_REFRESH_SECONDS = 60

_live_cache: dict[tuple[str, str, str], tuple[float, pd.DataFrame, float, str]] = {}


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
    """On live day, do not request a future clock time (cap to now ET)."""
    if not is_live_session(session_date):
        return time_of_day
    now = datetime.now(MARKET_TZ)
    req = session_datetime(session_date, time_of_day)
    if req > now:
        return now.strftime("%H:%M:%S")
    open_dt = session_datetime(session_date, "09:30:00")
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
    cache_key = (spec.terminal_symbol, session_date.isoformat(), effective_time)
    ttl = (
        cache_ttl_seconds
        if cache_ttl_seconds is not None
        else (
            DEFAULT_CACHE_TTL_SECONDS
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
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
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
        cache_ttl_seconds=cache_ttl_seconds,
    )
