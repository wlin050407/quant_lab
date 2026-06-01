"""Ephemeral equity bar fetcher — ThetaData intraday + yfinance daily (no disk writes)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import pandas as pd

from quant_lab.config import env_var, settings
from quant_lab.data.base import MARKET_TZ, OptionChainSnapshot
from quant_lab.data.thetadata_equity import (
    fetch_stock_intraday_ohlc,
    fetch_stock_nbbo_at_time,
    thetadata_equity_available,
)
from quant_lab.data.yfinance_source import YFinanceSource
from quant_lab.terminal.deploy import last_trading_session_date

log = logging.getLogger(__name__)

BarSource = Literal["thetadata", "yfinance"]

_CACHE: dict[str, tuple[float, Any]] = {}


def _cache_ttl_seconds() -> int:
    raw = env_var("EQUITY_CACHE_TTL_SECONDS", default="120")
    try:
        return max(0, int(raw or "120"))
    except ValueError:
        return 120


def _cache_get(key: str) -> Any | None:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return None
    entry = _CACHE.get(key)
    if entry is None:
        return None
    ts, payload = entry
    if time.time() - ts > ttl:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: Any) -> None:
    if _cache_ttl_seconds() <= 0:
        return
    _CACHE[key] = (time.time(), payload)


def clear_equity_fetch_cache() -> None:
    """Reset in-memory cache (tests)."""
    _CACHE.clear()


def default_benchmark_symbol() -> str:
    return env_var("EQUITY_DEFAULT_BENCHMARK", default="SPY") or "SPY"


def normalize_ticker(raw: str) -> str:
    sym = raw.strip().upper().lstrip("^")
    if not sym:
        raise ValueError("ticker is empty")
    return sym


@dataclass(frozen=True)
class EquityBarBundle:
    ticker: str
    benchmark: str
    session_date: date
    daily: pd.DataFrame
    intraday: pd.DataFrame
    intraday_5d: pd.DataFrame
    benchmark_daily: pd.DataFrame
    benchmark_intraday: pd.DataFrame
    daily_source: BarSource
    intraday_source: BarSource
    spot: float
    option_chain: OptionChainSnapshot | None


def _yfinance_source() -> YFinanceSource:
    sleep = float(settings.data_source_config.get("request_sleep_seconds", 0.4))
    return YFinanceSource(request_sleep_seconds=sleep)


def _resolve_session_date() -> date:
    return last_trading_session_date()


def _fetch_daily_yfinance(symbol: str, *, period: str = "5y") -> pd.DataFrame:
    return _yfinance_source().get_underlying(symbol, period=period, interval="1d")


def _fetch_intraday_yfinance(symbol: str, *, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    return _yfinance_source().get_underlying(symbol, period=period, interval=interval)


def _filter_session_bars(intraday: pd.DataFrame, session_date: date) -> pd.DataFrame:
    if intraday.empty:
        return intraday
    idx_et = intraday.index.tz_convert(MARKET_TZ)
    dates = pd.Series([ts.date() for ts in idx_et], index=intraday.index)
    filtered = intraday.loc[dates == session_date]
    return filtered.copy()


def drop_incomplete_ohlc_bars(intraday: pd.DataFrame) -> pd.DataFrame:
    """Remove bars with missing OHLC (e.g. ThetaData 16:00 close placeholder)."""
    if intraday.empty:
        return intraday
    frame = intraday.copy()
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    valid = frame[["open", "high", "low", "close"]].notna().all(axis=1)
    return frame.loc[valid].copy()


def _spot_from_bars(daily: pd.DataFrame, intraday: pd.DataFrame) -> float:
    if not intraday.empty:
        closes = pd.to_numeric(intraday["close"], errors="coerce").dropna()
        if not closes.empty:
            return float(closes.iloc[-1])
    if not daily.empty:
        return float(daily["close"].iloc[-1])
    return float("nan")


def _fetch_option_chain_optional(ticker: str) -> OptionChainSnapshot | None:
    try:
        snap = _yfinance_source().get_option_chain(ticker, max_expiries=8)
    except Exception as exc:
        log.warning("option chain fetch failed for %s: %s", ticker, exc)
        return None
    chain = snap.chain
    if chain.empty:
        return None
    mid = chain[(chain["dte"] >= 7) & (chain["dte"] <= 45)]
    if mid.empty:
        return None
    filtered = chain[chain["dte"].between(7, 45)].copy()
    return OptionChainSnapshot(
        symbol=snap.symbol,
        asof=snap.asof,
        spot=snap.spot,
        chain=filtered,
    )


def fetch_equity_bars(
    ticker: str,
    *,
    refresh: bool = False,
    benchmark: str | None = None,
) -> EquityBarBundle:
    """Fetch daily + intraday bars and optional option chain without persisting."""
    sym = normalize_ticker(ticker)
    bench = normalize_ticker(benchmark or default_benchmark_symbol())
    session_date = _resolve_session_date()
    cache_key = f"bars:{sym}:{bench}:{session_date.isoformat()}"
    if not refresh:
        cached = _cache_get(cache_key)
        if isinstance(cached, EquityBarBundle):
            return cached

    daily = _fetch_daily_yfinance(sym)
    benchmark_daily = _fetch_daily_yfinance(bench)
    daily_source: BarSource = "yfinance"

    intraday_source: BarSource = "yfinance"
    intraday = pd.DataFrame()
    if thetadata_equity_available():
        try:
            intraday = fetch_stock_intraday_ohlc(sym, session_date, interval="5m")
            if not intraday.empty:
                intraday_source = "thetadata"
        except Exception as exc:
            log.warning("ThetaData intraday failed for %s: %s", sym, exc)

    raw_intraday = pd.DataFrame()
    if intraday.empty:
        raw_intraday = _fetch_intraday_yfinance(sym)
        intraday = _filter_session_bars(raw_intraday, session_date)
        if intraday.empty and not raw_intraday.empty:
            intraday = raw_intraday.tail(min(len(raw_intraday), 78)).copy()
        intraday_source = "yfinance"

    intraday = drop_incomplete_ohlc_bars(intraday)

    intraday_5d = pd.DataFrame()
    try:
        raw_5d = _fetch_intraday_yfinance(sym)
        if not raw_5d.empty:
            intraday_5d = drop_incomplete_ohlc_bars(raw_5d)
    except Exception as exc:
        log.debug("5d intraday fetch for %s: %s", sym, exc)
    if intraday_5d.empty and not intraday.empty:
        intraday_5d = intraday.copy()

    benchmark_intraday = pd.DataFrame()
    try:
        raw_bench = _fetch_intraday_yfinance(bench)
        if not raw_bench.empty:
            benchmark_intraday = drop_incomplete_ohlc_bars(
                _filter_session_bars(raw_bench, session_date)
            )
            if benchmark_intraday.empty:
                benchmark_intraday = drop_incomplete_ohlc_bars(raw_bench.tail(min(len(raw_bench), 78)))
    except Exception as exc:
        log.debug("benchmark intraday fetch for %s: %s", bench, exc)

    spot = _spot_from_bars(daily, intraday)
    if thetadata_equity_available() and intraday_source == "thetadata":
        try:
            nbbo = fetch_stock_nbbo_at_time(sym, session_date, time_of_day="15:30:00")
            if pd.notna(nbbo.get("mid")):
                spot = float(nbbo["mid"])
        except Exception as exc:
            log.debug("NBBO spot fallback for %s: %s", sym, exc)

    chain = _fetch_option_chain_optional(sym)
    bundle = EquityBarBundle(
        ticker=sym,
        benchmark=bench,
        session_date=session_date,
        daily=daily,
        intraday=intraday,
        intraday_5d=intraday_5d,
        benchmark_daily=benchmark_daily,
        benchmark_intraday=benchmark_intraday,
        daily_source=daily_source,
        intraday_source=intraday_source,
        spot=spot,
        option_chain=chain,
    )
    _cache_set(cache_key, bundle)
    return bundle
