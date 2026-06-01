"""Build standard option chains from ThetaData quotes + open interest + SPX spot."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from quant_lab.data.base import MARKET_TZ, OptionChainSnapshot
from quant_lab.data.intraday_time import intraday_time_to_expiry_years, session_datetime
from quant_lab.data.iv_solver import implied_volatility_from_mid
from quant_lab.data.thetadata_client import DEFAULT_INDEX_SYMBOL, DEFAULT_OPTION_ROOT
from quant_lab.data.thetadata_intraday import (
    fetch_0dte_chain_at_time,
    fetch_0dte_cumulative_volume_at_time,
    fetch_0dte_signed_flow_at_time,
    fetch_spx_at_time,
    fetch_stock_at_time,
)
from quant_lab.factors.effective_oi import enrich_chain_effective_oi, flow_delta_from_quote_sizes
from quant_lab.data.thetadata_storage import (
    intraday_chain_path,
    load_parquet,
    save_intraday_chain,
)

if TYPE_CHECKING:
    from thetadata import ThetaClient

log = logging.getLogger(__name__)

TERMINAL_SYMBOL = "^SPX"
RIGHT_MAP = {"CALL": "C", "PUT": "P", "C": "C", "P": "P"}


def _normalize_right(series: pd.Series) -> pd.Series:
    return series.astype(str).str.upper().map(RIGHT_MAP).fillna(series.astype(str).str.upper())


def fetch_0dte_open_interest_at_time(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    option_root: str = DEFAULT_OPTION_ROOT,
    strike_range: int = 80,
) -> pd.DataFrame:
    """Latest OI at-or-before ``time_of_day`` for each 0DTE contract."""
    df = client.option_history_open_interest(
        symbol=option_root,
        expiration=session_date,
        date=session_date,
        strike="*",
        right="both",
        max_dte=1,
        strike_range=strike_range,
    )
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["strike", "right", "open_interest", "timestamp"])

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    if out["timestamp"].dt.tz is None:
        out["timestamp"] = out["timestamp"].dt.tz_localize(MARKET_TZ)
    else:
        out["timestamp"] = out["timestamp"].dt.tz_convert(MARKET_TZ)

    cutoff = session_datetime(session_date, time_of_day)
    out = out[out["timestamp"] <= cutoff]
    if out.empty:
        return pd.DataFrame(columns=["strike", "right", "open_interest", "timestamp"])

    out["right"] = _normalize_right(out["right"])
    return (
        out.sort_values("timestamp")
        .groupby(["strike", "right"], as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


def _spot_from_local_1m(session_date: date, time_of_day: str) -> float | None:
    """Read SPX spot from cached 1m parquet when available."""
    from quant_lab.data.intraday_time import session_datetime
    from quant_lab.data.thetadata_storage import load_parquet, spx_price_1m_path

    path = spx_price_1m_path(session_date)
    if not path.is_file():
        return None
    bars = load_parquet(path)
    if bars.empty or "timestamp" not in bars.columns or "price" not in bars.columns:
        return None
    ts = pd.to_datetime(bars["timestamp"])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(MARKET_TZ)
    else:
        ts = ts.dt.tz_convert(MARKET_TZ)
    bars = bars.copy()
    bars["timestamp"] = ts
    cutoff = session_datetime(session_date, time_of_day)
    sub = bars[bars["timestamp"] <= cutoff]
    if sub.empty:
        return None
    return float(sub["price"].iloc[-1])


def _spot_from_quote_df(spot_df: pd.DataFrame) -> float:
    if spot_df is None or spot_df.empty:
        return float("nan")
    if "price" in spot_df.columns:
        val = float(spot_df["price"].iloc[-1])
        if np.isfinite(val):
            return val
    if "bid" in spot_df.columns and "ask" in spot_df.columns:
        bid = pd.to_numeric(spot_df["bid"], errors="coerce").iloc[-1]
        ask = pd.to_numeric(spot_df["ask"], errors="coerce").iloc[-1]
        if np.isfinite(bid) and np.isfinite(ask):
            return float((bid + ask) / 2.0)
    return float("nan")


def _fetch_underlying_spot(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    underlying_kind: Literal["index", "stock"],
    underlying_symbol: str,
) -> float:
    if underlying_kind == "index":
        local = _spot_from_local_1m(session_date, time_of_day)
        if local is not None and np.isfinite(local):
            return local
        spot_df = fetch_spx_at_time(
            client,
            session_date=session_date,
            time_of_day=time_of_day,
            symbol=underlying_symbol,
        )
        return _spot_from_quote_df(spot_df)

    spot_df = fetch_stock_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        symbol=underlying_symbol,
    )
    return _spot_from_quote_df(spot_df)


def _fetch_spx_spot(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
) -> float:
    return _fetch_underlying_spot(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        underlying_kind="index",
        underlying_symbol=DEFAULT_INDEX_SYMBOL,
    )


def build_0dte_chain_snapshot(
    client: ThetaClient,
    *,
    session_date: date,
    time_of_day: str,
    option_root: str = DEFAULT_OPTION_ROOT,
    strike_range: int = 80,
    terminal_symbol: str = TERMINAL_SYMBOL,
    underlying_kind: Literal["index", "stock"] = "index",
    underlying_symbol: str | None = None,
) -> OptionChainSnapshot:
    """Merge ThetaData quotes, OI, and underlying spot into ``OptionChainSnapshot``."""
    und_sym = underlying_symbol or (DEFAULT_INDEX_SYMBOL if underlying_kind == "index" else option_root)
    quotes = fetch_0dte_chain_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        option_root=option_root,
        strike_range=strike_range,
    )
    if quotes.empty:
        raise FileNotFoundError(f"no 0DTE quotes for {option_root} on {session_date} @ {time_of_day}")

    oi = fetch_0dte_open_interest_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        option_root=option_root,
        strike_range=strike_range,
    )
    oi_open = fetch_0dte_open_interest_at_time(
        client,
        session_date=session_date,
        time_of_day="09:30:00",
        option_root=option_root,
        strike_range=strike_range,
    )
    session_vol = fetch_0dte_signed_flow_at_time(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        option_root=option_root,
        strike_range=strike_range,
    )
    if session_vol.empty:
        session_vol = fetch_0dte_cumulative_volume_at_time(
            client,
            session_date=session_date,
            time_of_day=time_of_day,
            option_root=option_root,
            strike_range=strike_range,
        )

    spot = _fetch_underlying_spot(
        client,
        session_date=session_date,
        time_of_day=time_of_day,
        underlying_kind=underlying_kind,
        underlying_symbol=und_sym,
    )
    if not np.isfinite(spot):
        raise ValueError(f"no {und_sym} spot for {session_date} @ {time_of_day}")

    return assemble_chain_from_quotes_oi(
        quotes,
        oi,
        spot=spot,
        session_date=session_date,
        time_of_day=time_of_day,
        terminal_symbol=terminal_symbol,
        option_root=option_root,
        reference_oi=oi_open,
        session_volume=session_vol if not session_vol.empty else None,
        session_signed_flow=session_vol if "signed_flow" in session_vol.columns and not session_vol.empty else None,
    )


def assemble_chain_from_quotes_oi(
    quotes: pd.DataFrame,
    oi: pd.DataFrame,
    *,
    spot: float,
    session_date: date,
    time_of_day: str,
    terminal_symbol: str = TERMINAL_SYMBOL,
    option_root: str = DEFAULT_OPTION_ROOT,
    reference_oi: pd.DataFrame | None = None,
    session_volume: pd.DataFrame | None = None,
    session_signed_flow: pd.DataFrame | None = None,
) -> OptionChainSnapshot:
    """Pure merge helper (also used when rebuilding from saved parquet)."""
    q = quotes.copy()
    q["right"] = _normalize_right(q["right"])
    q["strike"] = q["strike"].astype(float)
    q["bid"] = pd.to_numeric(q["bid"], errors="coerce")
    q["ask"] = pd.to_numeric(q["ask"], errors="coerce")
    q["mid"] = (q["bid"] + q["ask"]) / 2.0

    if not oi.empty:
        oi_work = oi.copy()
        oi_work["right"] = _normalize_right(oi_work["right"])
        oi_work["strike"] = oi_work["strike"].astype(float)
        merged = q.merge(
            oi_work[["strike", "right", "open_interest"]],
            on=["strike", "right"],
            how="left",
        )
    else:
        merged = q.copy()
        merged["open_interest"] = 0

    t_years = intraday_time_to_expiry_years(session_date, time_of_day)
    ivs: list[float] = []
    for row in merged.itertuples(index=False):
        ivs.append(
            implied_volatility_from_mid(
                spot,
                float(row.strike),
                str(row.right),
                float(row.mid) if np.isfinite(row.mid) else float("nan"),
                t_years,
            )
        )
    merged["implied_volatility"] = ivs
    merged["time_to_expiry_years"] = t_years
    merged["dte"] = 0
    merged["expiry"] = session_date
    merged["symbol"] = terminal_symbol
    merged["last_price"] = merged["mid"]
    merged["open_interest"] = (
        pd.to_numeric(merged["open_interest"], errors="coerce").fillna(0).astype("int64")
    )
    merged["in_the_money"] = np.where(
        merged["right"] == "C",
        spot > merged["strike"],
        spot < merged["strike"],
    )

    asof = session_datetime(session_date, time_of_day)
    chain = merged[
        [
            "symbol",
            "expiry",
            "strike",
            "right",
            "dte",
            "bid",
            "ask",
            "last_price",
            "implied_volatility",
            "open_interest",
            "in_the_money",
            "time_to_expiry_years",
        ]
    ].copy()
    chain["volume"] = 0

    vol_series: pd.Series | None = None
    signed_series: pd.Series | None = None
    if session_signed_flow is not None and not session_signed_flow.empty:
        flow_work = session_signed_flow.copy()
        flow_work["right"] = _normalize_right(flow_work["right"])
        flow_work["strike"] = flow_work["strike"].astype("float64")
        merged_flow = chain.merge(
            flow_work[["strike", "right", "signed_flow", "volume"]],
            on=["strike", "right"],
            how="left",
        )
        if "signed_flow" in merged_flow.columns:
            signed_series = pd.to_numeric(merged_flow["signed_flow"], errors="coerce").fillna(0.0)
        if "volume" in merged_flow.columns:
            vol_series = pd.to_numeric(merged_flow["volume"], errors="coerce").fillna(0.0)
    elif session_volume is not None and not session_volume.empty:
        vol_work = session_volume.copy()
        vol_work["right"] = _normalize_right(vol_work["right"])
        vol_work["strike"] = vol_work["strike"].astype("float64")
        merged_vol = chain.merge(
            vol_work[["strike", "right", "volume"]],
            on=["strike", "right"],
            how="left",
            suffixes=("_drop", ""),
        )
        if "volume" in merged_vol.columns:
            vol_series = pd.to_numeric(merged_vol["volume"], errors="coerce").fillna(0.0)

    ref = reference_oi
    if ref is not None and not ref.empty:
        ref = ref.copy()
        ref["right"] = _normalize_right(ref["right"])
        ref["strike"] = ref["strike"].astype("float64")

    chain = enrich_chain_effective_oi(
        chain,
        ref,
        session_volume=vol_series,
        session_signed_flow=signed_series,
        quote_flow=flow_delta_from_quote_sizes(chain, quotes, None) if not quotes.empty else None,
    )

    return OptionChainSnapshot(
        symbol=terminal_symbol,
        asof=asof,
        spot=float(spot),
        chain=chain,
    )


def save_built_intraday_chain(
    snapshot: OptionChainSnapshot,
    *,
    session_date: date,
    time_of_day: str,
    option_root: str = DEFAULT_OPTION_ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Persist chain + meta under SPXW intraday layout."""
    label = time_of_day[:5].replace(":", "")
    chain_path, meta_path = save_intraday_chain(
        snapshot.chain,
        session_date,
        label,
        symbol=option_root,
        spot=snapshot.spot,
        asof=snapshot.asof,
        terminal_symbol=snapshot.symbol,
    )
    log.info("built intraday chain %s @ %s → %s", session_date, time_of_day, chain_path)
    meta = load_parquet(meta_path)
    return snapshot.chain, meta


def load_built_intraday_chain(
    session_date: date,
    time_of_day: str,
    *,
    option_root: str = DEFAULT_OPTION_ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load previously built intraday chain + meta."""
    label = time_of_day[:5].replace(":", "")
    chain_path = intraday_chain_path(session_date, label, symbol=option_root)
    meta_path = chain_path.parent / f"meta_{label}.parquet"
    if not chain_path.is_file():
        raise FileNotFoundError(chain_path)
    chain = load_parquet(chain_path)
    meta = load_parquet(meta_path) if meta_path.is_file() else pd.DataFrame()
    return chain, meta


def list_intraday_chain_dates(*, option_root: str = DEFAULT_OPTION_ROOT) -> list[str]:
    """Session dates with built intraday chains (any time slot)."""
    from quant_lab.config import settings
    from quant_lab.data.thetadata_storage import _safe_symbol

    base = settings.paths.raw / "options" / _safe_symbol(option_root)
    if not base.is_dir():
        return []
    dates: list[str] = []
    for day_dir in base.iterdir():
        if not day_dir.is_dir():
            continue
        intraday = day_dir / "intraday"
        if intraday.is_dir() and any(intraday.glob("chain_*.parquet")):
            dates.append(day_dir.name)
    return sorted(dates)
