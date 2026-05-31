"""Data source abstraction.

Every concrete provider (yfinance, Polygon, Tradier, IBKR) implements this
protocol. Upstream code (factors, backtests, scripts) only depends on the
protocol, never on the concrete provider — so we can swap data vendors without
rewriting the pipeline.

Two return shapes:

- Underlying OHLCV: a `pd.DataFrame` indexed by tz-aware UTC `DatetimeIndex`
  with columns `open, high, low, close, adj_close, volume`.

- Option chain snapshot: an `OptionChainSnapshot` value object carrying:
    - `asof`: snapshot timestamp (UTC, tz-aware)
    - `spot`: underlying spot at snapshot time (float, may be NaN)
    - `chain`: long-form DataFrame with one row per (expiry, strike, right)
      and at least these columns:
        symbol, expiry (date), strike (float), right ('C'/'P'),
        dte (int, days to expiry computed against asof.date()),
        bid, ask, last_price, implied_volatility,
        volume, open_interest, in_the_money (bool)

`dte` is part of the contract because 0DTE-aware code is the project's whole
point — every downstream factor / strategy filters or stratifies by it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

import pandas as pd


MARKET_TZ = ZoneInfo("America/New_York")


def market_date(ts: datetime) -> date:
    """Map a tz-aware timestamp to the US equity options market session date.

    The market session is anchored in ET, not UTC. A 17:00 PT run
    (= 00:00 UTC next day) still belongs to 'today's' market session, and a
    Beijing-noon run is yesterday's ET session, not today's UTC.

    Using UTC-based dating for snapshot directories caused 5/19 EoD data to
    land in `2026-05-20/` when the fetch ran after 20:00 ET. This helper is
    the single source of truth for 'which session does this snapshot belong
    to' across the project — `storage._option_dir` and the yfinance dte
    calculation both go through it.
    """
    if ts.tzinfo is None:
        raise ValueError("market_date requires a tz-aware datetime")
    return ts.astimezone(MARKET_TZ).date()


REQUIRED_UNDERLYING_COLUMNS: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
)

REQUIRED_OPTION_COLUMNS: tuple[str, ...] = (
    "symbol",
    "expiry",
    "strike",
    "right",
    "dte",
    "bid",
    "ask",
    "last_price",
    "implied_volatility",
    "volume",
    "open_interest",
    "in_the_money",
)


@dataclass(frozen=True)
class OptionChainSnapshot:
    symbol: str
    asof: datetime
    spot: float
    chain: pd.DataFrame

    def __post_init__(self) -> None:
        missing = [c for c in REQUIRED_OPTION_COLUMNS if c not in self.chain.columns]
        if missing:
            raise ValueError(
                f"OptionChainSnapshot.chain is missing required columns: {missing}"
            )


@runtime_checkable
class DataSource(Protocol):
    name: str

    def get_underlying(
        self,
        symbol: str,
        *,
        period: str = "5y",
        interval: str = "1d",
    ) -> pd.DataFrame: ...

    def get_option_expiries(self, symbol: str) -> list[str]: ...

    def get_option_chain(
        self,
        symbol: str,
        *,
        max_expiries: int | None = None,
    ) -> OptionChainSnapshot: ...
