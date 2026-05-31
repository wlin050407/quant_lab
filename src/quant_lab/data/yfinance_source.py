"""yfinance implementation of the DataSource protocol.

yfinance is **delayed** (15-min for US equities, end-of-day for many indices)
and the option chain it returns is what Yahoo serves — not a research-grade
feed. We use it because it is free and good enough to bootstrap P0.

When/if we upgrade to Polygon or Tradier, just write a new module that exposes
the same protocol and switch `data_source.active` in `settings.yaml`.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from quant_lab.data.base import (
    REQUIRED_OPTION_COLUMNS,
    DataSource,
    OptionChainSnapshot,
    market_date,
)

log = logging.getLogger(__name__)


_OPTION_COLUMN_MAP = {
    "contractSymbol": "contract_symbol",
    "lastPrice": "last_price",
    "bid": "bid",
    "ask": "ask",
    "volume": "volume",
    "openInterest": "open_interest",
    "impliedVolatility": "implied_volatility",
    "inTheMoney": "in_the_money",
    "strike": "strike",
}


class YFinanceSource(DataSource):
    name = "yfinance"

    def __init__(self, request_sleep_seconds: float = 0.4) -> None:
        self._sleep = request_sleep_seconds

    def get_underlying(
        self,
        symbol: str,
        *,
        period: str = "5y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            period=period,
            interval=interval,
            auto_adjust=False,
            actions=False,
        )
        if df.empty:
            raise RuntimeError(f"yfinance returned empty history for {symbol!r}")

        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )
        if "adj_close" not in df.columns:
            df["adj_close"] = df["close"]

        df = df[["open", "high", "low", "close", "adj_close", "volume"]].copy()

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.index.name = "datetime"

        df["symbol"] = symbol
        return df

    def get_option_expiries(self, symbol: str) -> list[str]:
        ticker = yf.Ticker(symbol)
        expiries = list(ticker.options or [])
        if not expiries:
            raise RuntimeError(f"yfinance returned no option expiries for {symbol!r}")
        return expiries

    def get_option_chain(
        self,
        symbol: str,
        *,
        max_expiries: int | None = None,
    ) -> OptionChainSnapshot:
        ticker = yf.Ticker(symbol)
        expiries = list(ticker.options or [])
        if not expiries:
            raise RuntimeError(f"yfinance returned no option expiries for {symbol!r}")
        if max_expiries is not None:
            expiries = expiries[:max_expiries]

        spot = _safe_spot(ticker, symbol)

        frames: list[pd.DataFrame] = []
        for expiry in expiries:
            log.info("fetching %s option chain for expiry %s", symbol, expiry)
            try:
                opt = ticker.option_chain(expiry)
            except Exception as exc:
                log.warning("skipping expiry %s for %s: %s", expiry, symbol, exc)
                continue

            calls = _normalize_yf_chain(opt.calls, symbol=symbol, expiry=expiry, right="C")
            puts = _normalize_yf_chain(opt.puts, symbol=symbol, expiry=expiry, right="P")
            frames.append(calls)
            frames.append(puts)
            time.sleep(self._sleep)

        if not frames:
            raise RuntimeError(f"failed to fetch any expiry for {symbol!r}")

        asof = datetime.now(tz=timezone.utc)
        chain = pd.concat(frames, ignore_index=True)
        # dte is computed against the ET market session date, not UTC date —
        # otherwise a 17:00 PT run would record dte = -1 for tomorrow's expiry.
        chain["dte"] = (
            pd.to_datetime(chain["expiry"]) - pd.Timestamp(market_date(asof))
        ).dt.days.astype("int64")
        chain = chain.reindex(columns=list(REQUIRED_OPTION_COLUMNS) + _extra_columns(chain))

        return OptionChainSnapshot(
            symbol=symbol,
            asof=asof,
            spot=spot,
            chain=chain,
        )


def _safe_spot(ticker: "yf.Ticker", symbol: str) -> float:
    try:
        hist = ticker.history(period="5d", interval="1d", auto_adjust=False, actions=False)
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as exc:
        log.warning("could not fetch spot for %s: %s", symbol, exc)
    return float("nan")


def _normalize_yf_chain(
    df: pd.DataFrame,
    *,
    symbol: str,
    expiry: str,
    right: str,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(REQUIRED_OPTION_COLUMNS))

    out = df.rename(columns=_OPTION_COLUMN_MAP).copy()
    out["symbol"] = symbol
    out["expiry"] = pd.to_datetime(expiry).date()
    out["right"] = right

    for col in REQUIRED_OPTION_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA

    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["bid"] = pd.to_numeric(out["bid"], errors="coerce")
    out["ask"] = pd.to_numeric(out["ask"], errors="coerce")
    out["last_price"] = pd.to_numeric(out["last_price"], errors="coerce")
    out["implied_volatility"] = pd.to_numeric(out["implied_volatility"], errors="coerce")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0).astype("int64")
    out["open_interest"] = (
        pd.to_numeric(out["open_interest"], errors="coerce").fillna(0).astype("int64")
    )
    out["in_the_money"] = out["in_the_money"].astype("boolean").fillna(False)

    return out


def _extra_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in REQUIRED_OPTION_COLUMNS]
