"""Philipp Dubach historical EoD options dataset adapter.

Source: https://github.com/lambdaclass/options_portfolio_backtester (release data-v1),
mirror of the now-deleted philippdubach/options-data repository (MIT licensed).

This is **not** a live `DataSource` in the same sense as `yfinance_source` —
the dataset is a single monolithic parquet covering 2008-01-02 → 2025-12-12
of EoD SPY/IWM/QQQ option chains. We treat it as a one-shot **historical
importer**: read the file once, slice by snapshot date, convert each day to
the project's canonical `OptionChainSnapshot` shape, and let
`quant_lab.data.storage.save_option_chain` persist it under
`data/raw/options/<symbol>/<date>/chain.parquet` exactly like a yfinance fetch.

Why we like this file:
- 18 years of daily SPY chains, 24.7M rows
- Greeks already precomputed (delta, gamma, theta, vega, rho) — critical for
  GEX / positioning factors. We still cross-check against our own BS76 model,
  but having a reference vector saves an entire bootstrapping iteration.
- Zero nulls across all fields in the rows we sampled.
- Continuous daily coverage with only 2 small gaps (Hurricane Sandy 2012-10
  and a 2019-09 hole).

Known issues to handle on import:
- 2024-01-15 contains 2 obviously synthetic placeholder rows (US market closed
  for MLK Day, IVs are round-number 0.15/0.12). The `import_philippdubach_history`
  script skips snapshots with fewer than `MIN_ROWS_PER_SNAPSHOT` rows.
- 0DTE same-day expiries are only well-populated from ~2022 onwards (SPY went
  fully daily-expiration in late 2022). Earlier years still have monthly /
  weekly chains, which are useful for longer-horizon positioning research but
  not for 0DTE alpha sweeps.
- The dataset is SPY only here; SPX (`^SPX`) is **not** available from this
  source. Per `AGENTS.md`, SPY serves as a free historical proxy for SPX 0DTE
  research, and SPX is fetched live via yfinance for the in-sample period.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd
import pyarrow.dataset as pds
from zoneinfo import ZoneInfo

from quant_lab.data.base import (
    REQUIRED_OPTION_COLUMNS,
    REQUIRED_UNDERLYING_COLUMNS,
    OptionChainSnapshot,
)

log = logging.getLogger(__name__)

MARKET_TZ = ZoneInfo("America/New_York")
US_EQUITY_CLOSE = time(16, 0)
MIN_ROWS_PER_SNAPSHOT = 50

OPTIONS_COLUMNS = (
    "contract_id",
    "symbol",
    "expiration",
    "strike",
    "type",
    "last",
    "mark",
    "bid",
    "bid_size",
    "ask",
    "ask_size",
    "volume",
    "open_interest",
    "date",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "in_the_money",
)


def _snapshot_asof(d: date) -> datetime:
    """16:00 ET on the snapshot date, converted to a tz-aware UTC datetime.

    The dataset stores `date` as a naive midnight timestamp. We anchor the
    snapshot at the US equity close so `market_date(asof)` returns the
    snapshot's session date regardless of how the consumer converts timezones
    (this is the contract `storage._option_dir` depends on).
    """
    local = datetime.combine(d, US_EQUITY_CLOSE, tzinfo=MARKET_TZ)
    return local.astimezone(ZoneInfo("UTC"))


def _right_from_type(type_value: object) -> str:
    """Map the dataset's `type` column ('call' / 'put') to 'C' / 'P'.

    We normalize to lowercase first so 'Call' / 'CALL' aren't surprises.
    Anything else raises — we don't want silent drops.
    """
    t = str(type_value).strip().lower()
    if t == "call":
        return "C"
    if t == "put":
        return "P"
    raise ValueError(f"unrecognized option type from dataset: {type_value!r}")


def _normalize_chain_frame(df: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    """Rename and type-coerce a daily slice into the project's canonical schema.

    Input is whatever the source parquet hands back; output matches
    `REQUIRED_OPTION_COLUMNS` plus the Greeks and mark/sizes as extras.
    """
    if df.empty:
        return pd.DataFrame(columns=list(REQUIRED_OPTION_COLUMNS))

    out = df.copy()
    out["right"] = out["type"].map(_right_from_type)
    out["expiry"] = pd.to_datetime(out["expiration"]).dt.date
    snapshot_date = pd.to_datetime(out["date"].iloc[0]).date()
    out["dte"] = (pd.to_datetime(out["expiration"]).dt.date.map(
        lambda d: (d - snapshot_date).days
    )).astype("int64")

    out = out.rename(
        columns={
            "contract_id": "contract_symbol",
            "last": "last_price",
        }
    )

    out["symbol"] = symbol
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce").astype("float64")
    out["bid"] = pd.to_numeric(out["bid"], errors="coerce").astype("float64")
    out["ask"] = pd.to_numeric(out["ask"], errors="coerce").astype("float64")
    out["last_price"] = pd.to_numeric(out["last_price"], errors="coerce").astype("float64")
    out["mark"] = pd.to_numeric(out["mark"], errors="coerce").astype("float64")
    out["implied_volatility"] = pd.to_numeric(
        out["implied_volatility"], errors="coerce"
    ).astype("float64")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0).astype("int64")
    out["open_interest"] = (
        pd.to_numeric(out["open_interest"], errors="coerce").fillna(0).astype("int64")
    )
    out["in_the_money"] = out["in_the_money"].astype("boolean").fillna(False)

    extras = [
        "contract_symbol",
        "mark",
        "bid_size",
        "ask_size",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
    ]
    ordered = list(REQUIRED_OPTION_COLUMNS) + [c for c in extras if c in out.columns]
    return out.reindex(columns=ordered)


def _read_underlying_frame(parquet_path: Path) -> pd.DataFrame:
    """Load SPY underlying daily bars and shape them into our underlying schema."""
    raw = pd.read_parquet(parquet_path)
    df = raw.copy()
    df["datetime"] = pd.to_datetime(df["date"]).dt.tz_localize("UTC")
    df = df.rename(columns={"adjusted_close": "adj_close"})

    df["adj_close"] = pd.to_numeric(df["adj_close"], errors="coerce").astype("float64")
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")

    df = df.set_index("datetime")
    df.index.name = "datetime"
    df = df.sort_index()

    keep = list(REQUIRED_UNDERLYING_COLUMNS) + ["symbol"]
    return df.reindex(columns=keep)


def load_underlying_dataframe(parquet_path: Path, *, symbol: str = "SPY") -> pd.DataFrame:
    """Public: read the underlying parquet and return our canonical OHLCV frame.

    The returned frame has a tz-aware UTC `DatetimeIndex` and the
    `REQUIRED_UNDERLYING_COLUMNS` plus a `symbol` column, matching what
    `yfinance_source.get_underlying` produces. Pass it straight to
    `storage.save_underlying`.
    """
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(parquet_path)
    df = _read_underlying_frame(parquet_path)

    if "symbol" in df.columns and df["symbol"].notna().any():
        symbols_present = set(df["symbol"].dropna().unique())
        if symbols_present != {symbol}:
            log.warning(
                "underlying parquet contained symbols %s; expected only %s",
                sorted(symbols_present),
                symbol,
            )
    df["symbol"] = symbol
    return df


def iter_option_snapshots(
    parquet_path: Path,
    *,
    symbol: str = "SPY",
    start_date: date | None = None,
    end_date: date | None = None,
    skip_min_rows: int = MIN_ROWS_PER_SNAPSHOT,
) -> Iterator[OptionChainSnapshot]:
    """Yield one `OptionChainSnapshot` per trading day in `[start_date, end_date]`.

    Streams day-by-day so memory stays low even for the full 600 MB file.
    We first read just the `date` column to enumerate distinct snapshot dates,
    then pull each day with a predicate-pushdown filter on the pyarrow dataset.

    Args:
        parquet_path: Path to the SPY options parquet downloaded from the
            lambdaclass release mirror (or the original philippdubach repo if
            it ever comes back).
        symbol: Symbol to embed in the resulting snapshots and used to filter
            the source (rows where `symbol` mismatches are skipped).
        start_date: Inclusive lower bound on the snapshot date. None = no lower
            bound.
        end_date: Inclusive upper bound. None = no upper bound.
        skip_min_rows: Snapshots with fewer than this many rows are dropped
            (e.g. the synthetic 2024-01-15 placeholder day). Set to 0 to keep
            everything.

    Yields:
        Snapshots in ascending date order. Spot is set to NaN because this
        adapter does not have access to the underlying price within the
        options file (we get spot from `philippdubach_spy_underlying.parquet`
        at import time, not here).
    """
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(parquet_path)

    dataset = pds.dataset(str(parquet_path), format="parquet")

    date_col = dataset.to_table(columns=["date"]).column("date").to_pandas()
    unique_dates = sorted({pd.Timestamp(d).date() for d in date_col})
    if start_date is not None:
        unique_dates = [d for d in unique_dates if d >= start_date]
    if end_date is not None:
        unique_dates = [d for d in unique_dates if d <= end_date]

    for snap_date in unique_dates:
        midnight = datetime.combine(snap_date, time.min)
        next_midnight = midnight + timedelta(days=1)
        day_filter = (pds.field("date") >= midnight) & (pds.field("date") < next_midnight)
        if "symbol" in dataset.schema.names:
            day_filter = day_filter & (pds.field("symbol") == symbol)

        day_df = dataset.to_table(
            filter=day_filter,
            columns=list(OPTIONS_COLUMNS),
        ).to_pandas()

        if day_df.empty:
            continue
        if skip_min_rows and len(day_df) < skip_min_rows:
            log.warning(
                "skipping sparse snapshot %s (%d rows < %d)",
                snap_date,
                len(day_df),
                skip_min_rows,
            )
            continue

        chain = _normalize_chain_frame(day_df, symbol=symbol)
        yield OptionChainSnapshot(
            symbol=symbol,
            asof=_snapshot_asof(snap_date),
            spot=float("nan"),
            chain=chain,
        )


def list_available_snapshot_dates(
    parquet_path: Path,
    *,
    symbol: str = "SPY",
) -> list[date]:
    """Return all snapshot dates present in the source file (for inspection)."""
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(parquet_path)
    dataset = pds.dataset(str(parquet_path), format="parquet")
    filt = pds.field("symbol") == symbol if "symbol" in dataset.schema.names else None
    date_col = dataset.to_table(
        columns=["date"],
        filter=filt,
    ).column("date").to_pandas()
    return sorted({pd.Timestamp(d).date() for d in date_col})
