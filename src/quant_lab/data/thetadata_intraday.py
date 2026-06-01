"""ThetaData intraday fetch helpers for Phase 4 (SPX + 0DTE options).

Value-tier notes (Options Value + Indices Value):

- SPX 1m: ``index_history_price`` (not ``index_history_ohlc`` — needs Indices Standard)
- Options 1m quotes: ``option_history_quote`` with ``max_dte=1``
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import TYPE_CHECKING

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.thetadata_client import DEFAULT_INDEX_SYMBOL, DEFAULT_OPTION_ROOT

if TYPE_CHECKING:
    from thetadata import ThetaClient

from quant_lab.factors.trade_flow import aggregate_signed_flow

log = logging.getLogger(__name__)

PIN_PLAY_TIMES_ET: tuple[str, ...] = ("10:00:00", "13:00:00", "15:30:00")


def _normalize_timestamps(df: pd.DataFrame, col: str = "timestamp") -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    out = df.copy()
    ts = pd.to_datetime(out[col])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(MARKET_TZ)
    else:
        ts = ts.dt.tz_convert(MARKET_TZ)
    out[col] = ts
    return out


def fetch_spx_price_1m(
    client: ThetaClient,
    *,
    session_date: date,
    start_time: str = "09:30:00",
    end_time: str = "16:00:00",
    symbol: str = DEFAULT_INDEX_SYMBOL,
) -> pd.DataFrame:
    """SPX 1-minute price series for one session (Indices Value)."""
    df = client.index_history_price(
        symbol=symbol,
        date=session_date,
        interval="1m",
        start_time=start_time,
        end_time=end_time,
    )
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["timestamp", "price"])
    return _normalize_timestamps(df)


def fetch_spx_at_time(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    symbol: str = DEFAULT_INDEX_SYMBOL,
) -> pd.DataFrame:
    """Single SPX price snapshot at ``time_of_day`` ET."""
    return client.index_at_time_price(
        symbol=symbol,
        start_date=session_date,
        end_date=session_date,
        time_of_day=time_of_day,
    )


def fetch_stock_at_time(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    symbol: str,
) -> pd.DataFrame:
    """Single stock NBBO snapshot at ``time_of_day`` ET."""
    return client.stock_at_time_quote(
        symbol=symbol,
        start_date=session_date,
        end_date=session_date,
        time_of_day=time_of_day,
    )


def fetch_0dte_option_quotes_window(
    client: ThetaClient,
    *,
    session_date: date,
    start_time: str,
    end_time: str,
    option_root: str = DEFAULT_OPTION_ROOT,
    strike_range: int = 40,
    interval: str = "1m",
) -> pd.DataFrame:
    """NBBO quotes for same-day expiry (0DTE) over a time window (Options Value)."""
    df = client.option_history_quote(
        symbol=option_root,
        expiration=session_date,
        date=session_date,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        strike="*",
        right="both",
        max_dte=1,
        strike_range=strike_range,
    )
    if df is None or len(df) == 0:
        return pd.DataFrame()
    out = _normalize_timestamps(df)
    out["session_date"] = session_date.isoformat()
    out["option_root"] = option_root
    return out


def fetch_0dte_raw_trades_at_time(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    option_root: str = DEFAULT_OPTION_ROOT,
    strike_range: int = 40,
) -> pd.DataFrame:
    """Raw OPRA trades for same-day expiry through ``time_of_day`` (Standard tier)."""
    try:
        df = client.option_history_trade(
            symbol=option_root,
            expiration=session_date,
            date=session_date,
            start_time="09:30:00",
            end_time=time_of_day,
            strike="*",
            right="both",
            max_dte=1,
            strike_range=strike_range,
        )
    except Exception as exc:
        log.debug("raw trades unavailable for %s @ %s: %s", session_date, time_of_day, exc)
        return pd.DataFrame()

    if df is None or len(df) == 0:
        return pd.DataFrame()
    return df.copy()


def fetch_0dte_signed_flow_at_time(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    option_root: str = DEFAULT_OPTION_ROOT,
    strike_range: int = 40,
) -> pd.DataFrame:
    """Lee-Ready signed flow + unsigned volume by (strike, right).

    Requires Options **Standard** tier. Returns empty on failure — callers fall
    back to unsigned volume or OI-delta proxy.
    """
    trades = fetch_0dte_raw_trades_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        option_root=option_root,
        strike_range=strike_range,
    )
    if trades.empty:
        return pd.DataFrame(columns=["strike", "right", "signed_flow", "volume"])

    quotes = fetch_0dte_option_quotes_window(
        client,
        session_date=session_date,
        start_time="09:30:00",
        end_time=time_of_day,
        option_root=option_root,
        strike_range=strike_range,
        interval="1m",
    )
    try:
        return aggregate_signed_flow(trades, quotes if not quotes.empty else None)
    except ValueError as exc:
        log.debug("signed flow classification failed for %s @ %s: %s", session_date, time_of_day, exc)
        return pd.DataFrame(columns=["strike", "right", "signed_flow", "volume"])


def fetch_0dte_cumulative_volume_at_time(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    option_root: str = DEFAULT_OPTION_ROOT,
    strike_range: int = 40,
) -> pd.DataFrame:
    """Cumulative contract volume from session open through ``time_of_day``.

    Requires Options **Standard** tier (``option_history_trade``). Returns empty
    on Value tier or missing data — callers should fall back to OI-delta proxy.
    Prefer ``fetch_0dte_signed_flow_at_time`` when Standard tier is available.
    """
    signed = fetch_0dte_signed_flow_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        option_root=option_root,
        strike_range=strike_range,
    )
    if not signed.empty and "volume" in signed.columns:
        return signed[["strike", "right", "volume"]].copy()

    trades = fetch_0dte_raw_trades_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        option_root=option_root,
        strike_range=strike_range,
    )
    if trades.empty:
        return pd.DataFrame(columns=["strike", "right", "volume"])

    out = trades.copy()
    out["right"] = out["right"].astype(str).str.upper().str[0]
    out["strike"] = out["strike"].astype("float64")
    size_col = "size" if "size" in out.columns else "volume" if "volume" in out.columns else None
    if size_col is None:
        return pd.DataFrame(columns=["strike", "right", "volume"])
    grouped = (
        out.groupby(["strike", "right"], as_index=False)[size_col]
        .sum()
        .rename(columns={size_col: "volume"})
    )
    return grouped


def fetch_0dte_chain_at_time(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    option_root: str = DEFAULT_OPTION_ROOT,
    strike_range: int = 40,
) -> pd.DataFrame:
    """Last quote at-or-before ``time_of_day`` for each 0DTE contract."""
    end_parts = time_of_day.split(":")
    hour = int(end_parts[0])
    minute = int(end_parts[1]) if len(end_parts) > 1 else 0
    end_dt = datetime.combine(session_date, time(hour, minute), tzinfo=MARKET_TZ)
    start_dt = end_dt.replace(minute=max(0, end_dt.minute - 1))
    start_time = start_dt.strftime("%H:%M:%S")
    end_time = end_dt.strftime("%H:%M:%S")
    df = fetch_0dte_option_quotes_window(
        client,
        session_date=session_date,
        start_time=start_time,
        end_time=end_time,
        option_root=option_root,
        strike_range=strike_range,
        interval="1m",
    )
    if df.empty:
        return df
    sort_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
    return (
        df.sort_values(sort_col)
        .groupby(["strike", "right"], as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


def list_option_roots(client: ThetaClient) -> pd.DataFrame:
    """Symbols with listed options (probe SPX vs SPXW)."""
    return client.option_list_symbols()


def list_index_symbols(client: ThetaClient) -> pd.DataFrame:
    return client.index_list_symbols()


def resolve_option_root(client: ThetaClient, *, prefer: tuple[str, ...] = ("SPXW", "SPX")) -> str:
    """Pick first available index option root from Theta symbol list.

    Prefer ``SPXW`` — PM-settled weeklies carry 0DTE quote history; ``SPX`` often
    lists expiries without intraday NBBO for same-day weeklies.
    """
    symbols_df = list_option_roots(client)
    if symbols_df.empty or "symbol" not in symbols_df.columns:
        return DEFAULT_OPTION_ROOT
    available = set(symbols_df["symbol"].astype(str))
    for candidate in prefer:
        if candidate in available:
            return candidate
    return DEFAULT_OPTION_ROOT
