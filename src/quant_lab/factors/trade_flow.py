"""Signed option flow from OPRA trades (FlashAlpha-aligned effective OI input).

ThetaData does not ship a native buy/sell flag. We classify aggressor side with
Lee-Ready (trade price vs contemporaneous NBBO) and fall back to a tick rule
when quotes are missing.

Output is **per (strike, right)** cumulative signed size from session open:
positive = net buyer-initiated volume, negative = net seller-initiated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PRICE_EPS = 1e-4


def classify_lee_ready(
    price: float,
    bid: float,
    ask: float,
    *,
    prev_sign: int = 0,
) -> int:
    """Return +1 buy, -1 sell, or 0 unknown from trade price vs NBBO."""
    if not np.isfinite(price):
        return 0
    if np.isfinite(bid) and np.isfinite(ask) and ask >= bid:
        mid = (bid + ask) / 2.0
        if price >= ask - PRICE_EPS:
            return 1
        if price <= bid + PRICE_EPS:
            return -1
        if price > mid + PRICE_EPS:
            return 1
        if price < mid - PRICE_EPS:
            return -1
        return prev_sign
    if np.isfinite(bid) and price <= bid + PRICE_EPS:
        return -1
    if np.isfinite(ask) and price >= ask - PRICE_EPS:
        return 1
    return prev_sign


def classify_tick_rule(price: float, prev_price: float | None, *, prev_sign: int = 0) -> int:
    """Tick rule when NBBO is unavailable."""
    if not np.isfinite(price) or prev_price is None or not np.isfinite(prev_price):
        return prev_sign
    if price > prev_price + PRICE_EPS:
        return 1
    if price < prev_price - PRICE_EPS:
        return -1
    return prev_sign


def _trade_size_column(trades: pd.DataFrame) -> str:
    for col in ("size", "volume"):
        if col in trades.columns:
            return col
    raise ValueError("trades missing size/volume column")


def _trade_time_column(trades: pd.DataFrame) -> str | None:
    for col in ("ms_of_day", "timestamp", "time"):
        if col in trades.columns:
            return col
    return None


def _quote_time_column(quotes: pd.DataFrame) -> str | None:
    for col in ("ms_of_day", "timestamp", "time"):
        if col in quotes.columns:
            return col
    return None


def _normalize_ms(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        base = series.dt.normalize()
        return (series - base).dt.total_seconds() * 1000.0
    return pd.to_numeric(series, errors="coerce")


def _prepare_trades(trades: pd.DataFrame) -> pd.DataFrame:
    req = {"strike", "right", "price"}
    missing = req - set(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    size_col = _trade_size_column(trades)
    out = trades.copy()
    out["right"] = out["right"].astype(str).str.upper().str[0]
    out["strike"] = out["strike"].astype("float64")
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out["trade_sz"] = pd.to_numeric(out[size_col], errors="coerce").fillna(0.0)
    time_col = _trade_time_column(out)
    if time_col is not None:
        out["t_ms"] = _normalize_ms(out[time_col])
    else:
        out["t_ms"] = np.arange(len(out), dtype="float64")
    return out


def _prepare_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    if quotes.empty:
        return pd.DataFrame(columns=["strike", "right", "bid", "ask", "t_ms"])
    req = {"strike", "right", "bid", "ask"}
    missing = req - set(quotes.columns)
    if missing:
        raise ValueError(f"quotes missing columns: {sorted(missing)}")
    out = quotes.copy()
    out["right"] = out["right"].astype(str).str.upper().str[0]
    out["strike"] = out["strike"].astype("float64")
    out["bid"] = pd.to_numeric(out["bid"], errors="coerce")
    out["ask"] = pd.to_numeric(out["ask"], errors="coerce")
    time_col = _quote_time_column(out)
    if time_col is not None:
        out["t_ms"] = _normalize_ms(out[time_col])
    else:
        out["t_ms"] = 0.0
    return out.sort_values(["strike", "right", "t_ms"])


def aggregate_signed_flow(
    trades: pd.DataFrame,
    quotes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Cumulative signed and unsigned volume by (strike, right).

    Returns columns: ``strike``, ``right``, ``signed_flow``, ``volume``.
    """
    if trades is None or trades.empty:
        return pd.DataFrame(columns=["strike", "right", "signed_flow", "volume"])

    work = _prepare_trades(trades)
    quote_lookup: dict[tuple[float, str], pd.DataFrame] = {}
    if quotes is not None and not quotes.empty:
        qprep = _prepare_quotes(quotes)
        for (strike, right), grp in qprep.groupby(["strike", "right"], sort=False):
            quote_lookup[(float(strike), str(right))] = grp.reset_index(drop=True)

    signed_parts: list[float] = []
    volume_parts: list[float] = []
    prev_price_by_key: dict[tuple[float, str], float] = {}
    prev_sign_by_key: dict[tuple[float, str], int] = {}

    for row in work.sort_values(["strike", "right", "t_ms"]).itertuples(index=False):
        key = (float(row.strike), str(row.right))
        size = float(row.trade_sz)
        if size <= 0:
            signed_parts.append(0.0)
            volume_parts.append(0.0)
            continue

        bid = ask = float("nan")
        qdf = quote_lookup.get(key)
        if qdf is not None and not qdf.empty:
            t_ms = float(row.t_ms)
            sub = qdf[qdf["t_ms"] <= t_ms]
            if sub.empty:
                sub = qdf.iloc[:1]
            else:
                sub = sub.iloc[-1:]
            bid = float(sub["bid"].iloc[0])
            ask = float(sub["ask"].iloc[0])

        prev_sign = prev_sign_by_key.get(key, 0)
        prev_price = prev_price_by_key.get(key)
        sign = classify_lee_ready(float(row.price), bid, ask, prev_sign=prev_sign)
        if sign == 0:
            sign = classify_tick_rule(float(row.price), prev_price, prev_sign=prev_sign)
        if sign == 0:
            sign = 1

        signed_parts.append(sign * size)
        volume_parts.append(size)
        prev_price_by_key[key] = float(row.price)
        prev_sign_by_key[key] = sign

    work["signed_contrib"] = signed_parts
    work["volume_contrib"] = volume_parts
    grouped = (
        work.groupby(["strike", "right"], as_index=False)
        .agg(signed_flow=("signed_contrib", "sum"), volume=("volume_contrib", "sum"))
        .astype({"strike": "float64", "signed_flow": "float64", "volume": "float64"})
    )
    return grouped
