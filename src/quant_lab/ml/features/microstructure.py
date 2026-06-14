"""Quote microstructure, trade flow proxy, and Greeks/IV features."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import SESSION_OPEN
from quant_lab.data.point_in_time_replay import PointInTimeState
from quant_lab.ml.features.raw_frames import FeatureRawFrames, filter_at_or_before
from quant_lab.ml.features.schemas import FeatureConfig


def _ensure_tz_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series)
    if ts.dt.tz is None:
        return ts.dt.tz_localize(MARKET_TZ)
    return ts


def _window_slice(frame: pd.DataFrame, as_of: datetime, window_sec: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    start = as_of - timedelta(seconds=window_sec)
    ts = _ensure_tz_ts(frame["event_timestamp"])
    return frame.loc[(ts > start) & (ts <= as_of)].copy()


def _since_open_slice(frame: pd.DataFrame, as_of: datetime, trade_date) -> pd.DataFrame:
    if frame.empty:
        return frame
    filtered = filter_at_or_before(frame, as_of)
    open_dt = datetime.combine(trade_date, SESSION_OPEN, tzinfo=MARKET_TZ)
    ts = _ensure_tz_ts(filtered["event_timestamp"])
    return filtered.loc[ts >= open_dt].copy()


def _dedupe_quotes_for_spread(quotes: pd.DataFrame) -> pd.DataFrame:
    """Deterministic last row per (contract, event_timestamp) for spread stats.

    Raw duplicate rows are counted in ``quote_update_count`` but spread stats
    use this deduped view (documented in feature_catalog).
    """
    if quotes.empty:
        return quotes
    work = quotes.copy()
    work["_ts"] = _ensure_tz_ts(work["event_timestamp"])
    return (
        work.sort_values(["contract_identifier", "_ts", "sequence"], kind="mergesort")
        .groupby(["contract_identifier", "_ts"], as_index=False)
        .last()
        .drop(columns=["_ts"])
    )


def compute_quote_microstructure_features(
    raw: FeatureRawFrames,
    as_of: datetime,
    config: FeatureConfig,
) -> dict[str, Any]:
    quotes = raw.quote_tick if raw.quote_tick is not None else pd.DataFrame()
    if quotes.empty and raw.quote_1s is not None:
        quotes = raw.quote_1s
    out: dict[str, Any] = {}
    for window in config.quote_windows_sec:
        win = _window_slice(quotes, as_of, window)
        prefix = f"quote_{window}s"
        if win.empty:
            for suffix in _QUOTE_SUFFIXES:
                out[f"{prefix}_{suffix}"] = None
            continue
        deduped = _dedupe_quotes_for_spread(win)
        bid = pd.to_numeric(deduped["bid"], errors="coerce")
        ask = pd.to_numeric(deduped["ask"], errors="coerce")
        spread = ask - bid
        mid = (bid + ask) / 2.0
        valid_spread = spread[(spread > 0) & spread.notna()]

        out[f"{prefix}_quote_update_count"] = int(len(win))
        out[f"{prefix}_quote_update_rate"] = len(win) / window
        out[f"{prefix}_median_bid_ask_spread"] = float(valid_spread.median()) if not valid_spread.empty else None
        out[f"{prefix}_mean_bid_ask_spread"] = float(valid_spread.mean()) if not valid_spread.empty else None
        out[f"{prefix}_spread_p90"] = float(valid_spread.quantile(0.9)) if len(valid_spread) >= 2 else None
        out[f"{prefix}_wide_spread_ratio"] = (
            float((valid_spread > config.wide_spread_points).mean()) if not valid_spread.empty else None
        )
        out[f"{prefix}_bid_size_mean"] = float(pd.to_numeric(win["bid_size"], errors="coerce").mean())
        out[f"{prefix}_ask_size_mean"] = float(pd.to_numeric(win["ask_size"], errors="coerce").mean())
        if len(deduped) >= 2:
            mid_sorted = mid.sort_index()
            out[f"{prefix}_quote_mid_change"] = float(mid_sorted.iloc[-1] - mid_sorted.iloc[0])
            m0 = mid_sorted.iloc[0]
            out[f"{prefix}_quote_mid_return"] = float((mid_sorted.iloc[-1] - m0) / m0) if m0 and m0 > 0 else None
        else:
            out[f"{prefix}_quote_mid_change"] = None
            out[f"{prefix}_quote_mid_return"] = None
        ages = (as_of - _ensure_tz_ts(win["event_timestamp"])).dt.total_seconds()
        out[f"{prefix}_quote_age_seconds_mean"] = float(ages.mean())
        out[f"{prefix}_stale_quote_ratio"] = float((ages > config.max_quote_age_seconds).mean())
    return out


_QUOTE_SUFFIXES = (
    "quote_update_count",
    "quote_update_rate",
    "median_bid_ask_spread",
    "mean_bid_ask_spread",
    "spread_p90",
    "wide_spread_ratio",
    "bid_size_mean",
    "ask_size_mean",
    "quote_mid_change",
    "quote_mid_return",
    "quote_age_seconds_mean",
    "stale_quote_ratio",
)


def compute_trade_flow_features(
    raw: FeatureRawFrames,
    state: PointInTimeState,
    as_of: datetime,
    config: FeatureConfig,
    *,
    spot: float | None,
    primary_pin: float | None,
) -> dict[str, Any]:
    trades = raw.trade_tick if raw.trade_tick is not None else pd.DataFrame()
    out: dict[str, Any] = {}
    windows: list[tuple[str, pd.DataFrame]] = [
        (f"{w}s", _window_slice(trades, as_of, w)) for w in config.trade_windows_sec
    ]
    windows.append(("since_open", _since_open_slice(trades, as_of, state.session.trade_date)))

    total_oi = float(pd.to_numeric(state.option_chain["open_interest"], errors="coerce").fillna(0).sum())

    for suffix, win in windows:
        prefix = f"trade_{suffix}"
        if win.empty:
            for name in _TRADE_SUFFIXES:
                out[f"{prefix}_{name}"] = None
            continue
        size = pd.to_numeric(win["size"], errors="coerce").fillna(0)
        price = pd.to_numeric(win["price"], errors="coerce").fillna(0)
        rights = win["right"].astype(str).str.upper()
        call_vol = float(size[rights.isin(["C", "CALL"])].sum())
        put_vol = float(size[rights.isin(["P", "PUT"])].sum())
        strikes = pd.to_numeric(win["strike"], errors="coerce")

        out[f"{prefix}_trade_count"] = int(len(win))
        out[f"{prefix}_trade_volume"] = float(size.sum())
        out[f"{prefix}_trade_notional_proxy"] = float((price * size * 100).sum())
        out[f"{prefix}_call_trade_volume"] = call_vol
        out[f"{prefix}_put_trade_volume"] = put_vol
        out[f"{prefix}_call_put_trade_volume_ratio"] = call_vol / put_vol if put_vol > 0 else None

        if spot is not None and np.isfinite(spot):
            near_spot = strikes.abs() - spot
            out[f"{prefix}_near_spot_trade_volume"] = float(size[near_spot.abs() <= spot * config.near_spot_pct].sum())
        else:
            out[f"{prefix}_near_spot_trade_volume"] = None
        if primary_pin is not None and np.isfinite(primary_pin):
            out[f"{prefix}_near_pin_trade_volume"] = float(
                size[(strikes - primary_pin).abs() <= primary_pin * config.near_pin_pct].sum()
            )
        else:
            out[f"{prefix}_near_pin_trade_volume"] = None

        vol_by_strike = size.groupby(strikes).sum()
        if vol_by_strike.sum() > 0:
            shares = vol_by_strike / vol_by_strike.sum()
            out[f"{prefix}_volume_hhi"] = float((shares**2).sum())
        else:
            out[f"{prefix}_volume_hhi"] = None
        out[f"{prefix}_volume_to_oi_ratio"] = float(size.sum()) / total_oi if total_oi > 0 else None
        last_ts = _ensure_tz_ts(win["event_timestamp"]).max()
        if hasattr(last_ts, "to_pydatetime"):
            last_ts = last_ts.to_pydatetime()
        out[f"{prefix}_last_trade_age_seconds"] = (as_of - last_ts).total_seconds()
    return out


_TRADE_SUFFIXES = (
    "trade_count",
    "trade_volume",
    "trade_notional_proxy",
    "call_trade_volume",
    "put_trade_volume",
    "call_put_trade_volume_ratio",
    "near_spot_trade_volume",
    "near_pin_trade_volume",
    "volume_hhi",
    "volume_to_oi_ratio",
    "last_trade_age_seconds",
)


def compute_greeks_iv_features(
    raw: FeatureRawFrames,
    state: PointInTimeState,
    as_of: datetime,
    *,
    spot: float | None,
) -> dict[str, Any]:
    greeks = raw.greeks_1m if raw.greeks_1m is not None else pd.DataFrame()
    chain = state.option_chain
    out: dict[str, Any] = {}

    if greeks.empty or spot is None:
        return {n: None for n in _GREEKS_NAMES}

    latest = (
        greeks.assign(_ts=_ensure_tz_ts(greeks["event_timestamp"]))
        .sort_values(["contract_identifier", "_ts"], kind="mergesort")
        .groupby("contract_identifier", as_index=False)
        .last()
    )
    oi = pd.to_numeric(chain.set_index("contract_identifier")["open_interest"], errors="coerce")
    merged = latest.set_index("contract_identifier").join(oi.rename("oi"), how="left")
    iv_vals = pd.to_numeric(merged["implied_vol"], errors="coerce")
    oi_vals = pd.to_numeric(merged["oi"], errors="coerce").fillna(0)
    strikes = pd.to_numeric(merged["strike"], errors="coerce")
    dist = (strikes - spot).abs()
    atm_idx = dist.idxmin() if not dist.empty else None
    out["iv_atm"] = float(iv_vals.loc[atm_idx]) if atm_idx is not None and atm_idx in iv_vals.index else None
    if oi_vals.sum() > 0:
        out["iv_weighted_mean"] = float((iv_vals * oi_vals).sum() / oi_vals.sum())
    else:
        out["iv_weighted_mean"] = None

    call_iv = iv_vals[merged["right"].astype(str).str.upper().isin(["C", "CALL"])]
    put_iv = iv_vals[merged["right"].astype(str).str.upper().isin(["P", "PUT"])]
    if not call_iv.empty and not put_iv.empty:
        out["iv_skew_call_put"] = float(call_iv.mean() - put_iv.mean())
    else:
        out["iv_skew_call_put"] = None

    out["iv_change_1m"] = _iv_change(greeks, as_of, 60)
    out["iv_change_5m"] = _iv_change(greeks, as_of, 300)

    for greek, col in [("delta", "delta"), ("theta", "theta"), ("vega", "vega")]:
        if col in merged.columns:
            vals = pd.to_numeric(merged[col], errors="coerce")
            out[f"{greek}_weighted_exposure"] = float((vals * oi_vals).sum())
        else:
            out[f"{greek}_weighted_exposure"] = None

    gamma_ok = chain["gamma"].notna().sum() / max(len(chain), 1)
    out["gamma_available_ratio"] = float(gamma_ok)
    if "gamma_method" in chain.columns:
        methods = chain["gamma_method"].dropna().astype(str)
        out["gamma_method_black76_share"] = float((methods == "black76").mean()) if not methods.empty else None
    else:
        out["gamma_method_black76_share"] = None

    return out


_GREEKS_NAMES = (
    "iv_atm",
    "iv_weighted_mean",
    "iv_skew_call_put",
    "iv_change_1m",
    "iv_change_5m",
    "delta_weighted_exposure",
    "theta_weighted_exposure",
    "vega_weighted_exposure",
    "gamma_available_ratio",
    "gamma_method_black76_share",
)


def _iv_change(greeks: pd.DataFrame, as_of: datetime, lookback_sec: int) -> float | None:
    if greeks.empty:
        return None
    current = _window_slice(greeks, as_of, lookback_sec)
    prior_end = as_of - timedelta(seconds=lookback_sec)
    prior = _window_slice(greeks, prior_end, lookback_sec)
    if current.empty or prior.empty:
        return None
    cur_iv = pd.to_numeric(current["implied_vol"], errors="coerce").mean()
    prev_iv = pd.to_numeric(prior["implied_vol"], errors="coerce").mean()
    if pd.isna(cur_iv) or pd.isna(prev_iv):
        return None
    return float(cur_iv - prev_iv)
