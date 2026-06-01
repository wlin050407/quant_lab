"""ThetaData US equity bar/quote helpers for the live equity research module."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from quant_lab.data.base import MARKET_TZ, REQUIRED_UNDERLYING_COLUMNS
from quant_lab.data.thetadata_client import ThetaDataConfigError, get_thetadata_client

log = logging.getLogger(__name__)


def _normalize_ohlc_frame(df: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(REQUIRED_UNDERLYING_COLUMNS) + ["symbol"])

    out = df.copy()
    if "timestamp" in out.columns:
        ts = pd.to_datetime(out["timestamp"])
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize(MARKET_TZ)
        else:
            ts = ts.dt.tz_convert("UTC")
        out = out.set_index(ts)
    elif not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError("ThetaData OHLC frame missing timestamp index/column")

    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    for col in ("open", "high", "low", "close", "volume"):
        if col not in out.columns:
            raise ValueError(f"ThetaData OHLC missing column {col!r}")

    for col in ("open", "high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["adj_close"] = out["close"]
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    out["symbol"] = symbol
    out.index.name = "datetime"
    return out[list(REQUIRED_UNDERLYING_COLUMNS) + ["symbol"]].sort_index()


def _normalize_eod_frame(df: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(REQUIRED_UNDERLYING_COLUMNS) + ["symbol"])

    out = df.copy()
    if "last_trade" in out.columns:
        ts = pd.to_datetime(out["last_trade"])
    elif "created" in out.columns:
        ts = pd.to_datetime(out["created"])
    else:
        raise ValueError("ThetaData EOD frame missing last_trade/created")

    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(MARKET_TZ)
    else:
        ts = ts.dt.tz_convert("UTC")
    out = out.set_index(ts)

    for col in ("open", "high", "low", "close", "volume"):
        if col not in out.columns:
            raise ValueError(f"ThetaData EOD missing column {col!r}")

    out["adj_close"] = out["close"]
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    out["symbol"] = symbol
    out.index.name = "datetime"
    return out[list(REQUIRED_UNDERLYING_COLUMNS) + ["symbol"]].sort_index()


def fetch_stock_intraday_ohlc(
    symbol: str,
    session_date: date,
    *,
    interval: str = "5m",
    start_time: str = "09:30:00",
    end_time: str = "16:00:00",
) -> pd.DataFrame:
    """Session intraday OHLCV for ``symbol`` (Stock Value tier)."""
    client = get_thetadata_client()
    raw = client.stock_history_ohlc(
        symbol=symbol,
        date=session_date,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
    )
    return _normalize_ohlc_frame(raw, symbol=symbol)


def fetch_stock_eod_range(
    symbol: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Daily EOD bars; ThetaData allows at most 365 calendar days per request."""
    client = get_thetadata_client()
    raw = client.stock_history_eod(symbol=symbol, start_date=start_date, end_date=end_date)
    return _normalize_eod_frame(raw, symbol=symbol)


def fetch_stock_nbbo_at_time(
    symbol: str,
    session_date: date,
    *,
    time_of_day: str = "15:30:00",
) -> dict[str, Any]:
    """NBBO snapshot at ``time_of_day`` ET."""
    from quant_lab.data.thetadata_intraday import fetch_stock_at_time

    client = get_thetadata_client()
    df = fetch_stock_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        symbol=symbol,
    )
    if df.empty:
        return {"bid": float("nan"), "ask": float("nan"), "mid": float("nan")}
    bid = float(df["bid"].iloc[-1])
    ask = float(df["ask"].iloc[-1])
    mid = (bid + ask) / 2.0 if pd.notna(bid) and pd.notna(ask) else float("nan")
    return {"bid": bid, "ask": ask, "mid": mid}


def thetadata_equity_available() -> bool:
    """True when ThetaData credentials are configured."""
    try:
        get_thetadata_client()
        return True
    except ThetaDataConfigError:
        return False


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
