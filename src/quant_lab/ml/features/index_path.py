"""Index path features (as-of only, no forward path)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import SESSION_OPEN
from quant_lab.data.point_in_time_replay import PointInTimeState
from quant_lab.ml.features.raw_frames import FeatureRawFrames, filter_at_or_before
from quant_lab.ml.features.schemas import FeatureConfig


def _index_frame(raw: FeatureRawFrames) -> pd.DataFrame:
    if raw.index_1s is not None and not raw.index_1s.empty:
        return raw.index_1s
    if raw.index_tick is not None and not raw.index_tick.empty:
        return raw.index_tick
    return pd.DataFrame()


def _ensure_tz(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series)
    if ts.dt.tz is None:
        return ts.dt.tz_localize(MARKET_TZ)
    return ts


def compute_index_path_features(
    raw: FeatureRawFrames,
    state: PointInTimeState,
    as_of: datetime,
    config: FeatureConfig,
    *,
    spot: float | None,
) -> dict[str, Any]:
    idx = _index_frame(raw)
    out: dict[str, Any] = {}
    if idx.empty or spot is None:
        return _null_index_features(config)

    idx = filter_at_or_before(idx, as_of)
    ts = _ensure_tz(idx["event_timestamp"])
    open_dt = datetime.combine(state.session.trade_date, SESSION_OPEN, tzinfo=MARKET_TZ)
    since_open = idx.loc[ts >= open_dt]

    for window in config.index_windows_sec:
        start = as_of - timedelta(seconds=window)
        win = idx.loc[(ts > start) & (ts <= as_of)]
        prefix = f"index_{window}s"
        out[f"{prefix}_spot_return_{window}s"] = _return(win, spot)
        if window >= 60:
            out[f"index_{window}s_realized_vol_{window}s"] = _realized_vol(win)
        if window >= 60:
            out[f"index_{window}s_momentum_{window}s"] = _momentum(win)

    so_prefix = "index_since_open"
    if not since_open.empty:
        so_prices = pd.to_numeric(since_open["price"], errors="coerce")
        hi = float(so_prices.max())
        lo = float(so_prices.min())
        first_price = float(so_prices.iloc[0])
        out[f"{so_prefix}_spot_return_from_open"] = (spot - first_price) / first_price if first_price else None
        out[f"{so_prefix}_session_high_so_far"] = hi
        out[f"{so_prefix}_session_low_so_far"] = lo
        out[f"{so_prefix}_distance_to_session_high"] = hi - spot
        out[f"{so_prefix}_distance_to_session_low"] = spot - lo
        out[f"{so_prefix}_range_so_far"] = hi - lo
        last_ts = _ensure_tz(since_open["event_timestamp"]).max()
        if hasattr(last_ts, "to_pydatetime"):
            last_ts = last_ts.to_pydatetime()
        out[f"{so_prefix}_index_age_seconds"] = (as_of - last_ts).total_seconds()
    else:
        for k in (
            "spot_return_from_open",
            "session_high_so_far",
            "session_low_so_far",
            "distance_to_session_high",
            "distance_to_session_low",
            "range_so_far",
            "index_age_seconds",
        ):
            out[f"{so_prefix}_{k}"] = None

    return out


def _return(win: pd.DataFrame, spot: float) -> float | None:
    if win.empty or len(win) < 2:
        return None
    prices = pd.to_numeric(win["price"], errors="coerce")
    p0 = float(prices.iloc[0])
    if p0 <= 0:
        return None
    return (spot - p0) / p0


def _realized_vol(win: pd.DataFrame) -> float | None:
    prices = pd.to_numeric(win["price"], errors="coerce").dropna()
    if len(prices) < 2:
        return None
    rets = prices.pct_change().dropna()
    if rets.empty:
        return None
    return float(rets.std() * math.sqrt(len(rets)))


def _momentum(win: pd.DataFrame) -> float | None:
    prices = pd.to_numeric(win["price"], errors="coerce").dropna()
    if len(prices) < 2:
        return None
    return float(prices.iloc[-1] - prices.iloc[0])


def _null_index_features(config: FeatureConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for window in config.index_windows_sec:
        out[f"index_{window}s_spot_return_{window}s"] = None
        if window >= 60:
            out[f"index_{window}s_realized_vol_{window}s"] = None
            out[f"index_{window}s_momentum_{window}s"] = None
    for k in (
        "spot_return_from_open",
        "session_high_so_far",
        "session_low_so_far",
        "distance_to_session_high",
        "distance_to_session_low",
        "range_so_far",
        "index_age_seconds",
    ):
        out[f"index_since_open_{k}"] = None
    return out
