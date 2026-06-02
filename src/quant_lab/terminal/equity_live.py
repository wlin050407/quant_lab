"""Assemble live equity research API payloads."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
import yfinance as yf

from quant_lab.data.equity_fetch import EquityBarBundle, fetch_equity_bars
from quant_lab.data.macro_calendar import macro_events_on, macro_calendar_meta
from quant_lab.factors.equity.evidence_grades import grade_l1, grade_l2, grade_l3, grade_l5, grade_l6
from quant_lab.factors.equity.intraday_quality import intraday_session_quality
from quant_lab.factors.equity.layer_signals import compute_module_signals
from quant_lab.factors.equity.liquidity import (
    amihud_illiquidity,
    amihud_percentile_threshold,
    average_dollar_volume,
    liquidity_quality_flags,
)
from quant_lab.factors.equity.liquidity_thresholds import ADV_ELIGIBLE_USD, grade_l0
from quant_lab.factors.equity.ma_structure import ma_structure
from quant_lab.factors.equity.options_overlay import options_overlay_metrics
from quant_lab.factors.equity.relative_strength import relative_strength_vs_benchmark
from quant_lab.factors.equity.session_structure import opening_30m_rs
from quant_lab.factors.equity.synthesize import synthesize_horizons
from quant_lab.factors.equity.vol_regime import realized_vol_regime
from quant_lab.factors.equity.volume_profile import volume_profile
from quant_lab.factors.equity.vwap import session_vwap_metrics


def _bars_to_chart(intraday: Any, *, limit: int = 120) -> list[dict[str, float | str]]:
    if intraday.empty:
        return []
    tail = intraday.tail(limit)
    out: list[dict[str, float | str]] = []
    for ts, row in tail.iterrows():
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        if not all(np.isfinite(v) for v in (o, h, l, c)):
            continue
        out.append(
            {
                "t": ts.isoformat(),
                "o": o,
                "h": h,
                "l": l,
                "c": c,
                "v": float(row["volume"]) if np.isfinite(float(row["volume"])) else 0.0,
            }
        )
    return out


def _daily_bars_to_chart(daily: Any, *, limit: int = 1260) -> list[dict[str, float | str]]:
    if daily.empty:
        return []
    tail = daily.tail(limit)
    out: list[dict[str, float | str]] = []
    for ts, row in tail.iterrows():
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        if not all(np.isfinite(v) for v in (o, h, l, c)):
            continue
        day = ts.date() if hasattr(ts, "date") else ts
        out.append(
            {
                "t": day.isoformat(),
                "o": o,
                "h": h,
                "l": l,
                "c": c,
                "v": float(row["volume"]) if np.isfinite(float(row["volume"])) else 0.0,
            }
        )
    return out


def _earnings_within_days(ticker: str, *, days: int = 7) -> bool:
    try:
        cal = yf.Ticker(ticker).calendar
    except Exception:
        return False
    if not cal or "Earnings Date" not in cal:
        return False
    raw = cal["Earnings Date"]
    if isinstance(raw, (list, tuple)):
        dates = raw
    else:
        dates = [raw]
    today = datetime.now(tz=timezone.utc).date()
    for item in dates:
        try:
            ed = item.date() if hasattr(item, "date") else item
            if abs((ed - today).days) <= days:
                return True
        except Exception:
            continue
    return False


def _layer_payload(
    bundle: EquityBarBundle,
    vwap_m: Any,
    profile: Any,
    rs: Any,
    ma: Any,
    vol: Any,
    options: Any,
) -> dict[str, Any]:
    adv = average_dollar_volume(bundle.daily)
    illiq = amihud_illiquidity(bundle.daily)
    illiq_threshold = amihud_percentile_threshold(bundle.daily)
    eligible = bool(np.isfinite(adv) and adv >= ADV_ELIGIBLE_USD)
    macro = macro_events_on(bundle.session_date)
    opening = opening_30m_rs(bundle.intraday, bundle.benchmark_intraday)
    l0_grade = grade_l0(
        adv_usd=adv,
        amihud=illiq,
        eligible=eligible,
        amihud_threshold=illiq_threshold,
    )
    l1_grade = grade_l1(
        earnings_window=_earnings_within_days(bundle.ticker),
        macro_count=len(macro),
        vol_regime=vol.regime,
    )
    l2_grade = grade_l2(
        intraday_source=bundle.intraday_source,
        n_bars=len(bundle.intraday),
    )
    l3_grade = grade_l3(n_bars=len(bundle.intraday))
    l5_grade = grade_l5(n_daily=len(bundle.daily))
    return {
        "L0": {
            "adv_usd": adv,
            "amihud": illiq,
            "amihud_threshold": illiq_threshold,
            "eligible": eligible,
            "grade": l0_grade,
            "liquidity_quality": liquidity_quality_flags(bundle.daily),
        },
        "L1": {
            "macro_events": [{"type": e.event_type, "label": e.label} for e in macro],
            "macro_calendar": macro_calendar_meta(),
            "earnings_window": _earnings_within_days(bundle.ticker),
            "vol_regime": vol.regime,
            "grade": l1_grade,
        },
        "L2": {
            "vwap": vwap_m.vwap,
            "last": vwap_m.last_close,
            "deviation_pct": vwap_m.deviation_pct,
            "above_vwap": vwap_m.above_vwap,
            "rs_open_30m": opening.rs_open_30m,
            "open_ret_pct": opening.ticker_ret_pct,
            "benchmark_open_ret_pct": opening.benchmark_ret_pct,
            "grade": l2_grade,
            "intraday_quality": asdict(
                intraday_session_quality(
                    bundle.intraday,
                    bundle.session_date,
                    intraday_source=bundle.intraday_source,
                )
            ),
        },
        "L3": {
            "poc": profile.poc,
            "vah": profile.vah,
            "val": profile.val,
            "grade": l3_grade,
        },
        "L5": {
            "rs_1d": rs.rs_1d,
            "rs_5d": rs.rs_5d,
            "rs_20d": rs.rs_20d,
            "rs_60d": rs.rs_60d,
            "rs_120d": rs.rs_120d,
            "ma20": ma.ma20,
            "ma50": ma.ma50,
            "ma200": ma.ma200,
            "grade": l5_grade,
        },
        "L6": None
        if options is None
        else {
            "pcr_volume": options.pcr_volume,
            "pcr_oi": options.pcr_oi,
            "max_pain": options.max_pain,
            "n_contracts": options.n_contracts,
            "n_expiries": options.n_expiries,
            "source": options.source,
            "oi_timestamp_known": options.oi_timestamp_known,
            "warning": options.warning,
            "grade": options.evidence_grade,
        },
    }


def build_equity_analysis(ticker: str, *, refresh: bool = False) -> dict[str, Any]:
    """Fetch live data, compute factors, return JSON-serializable snapshot."""
    bundle = fetch_equity_bars(ticker, refresh=refresh)
    vwap_m = session_vwap_metrics(bundle.intraday)
    profile = volume_profile(bundle.intraday)
    rs = relative_strength_vs_benchmark(bundle.daily, bundle.benchmark_daily)
    ma = ma_structure(bundle.daily)
    vol = realized_vol_regime(bundle.daily)
    options = options_overlay_metrics(bundle.option_chain)
    earnings_risk = _earnings_within_days(bundle.ticker)
    adv = average_dollar_volume(bundle.daily)
    illiq = amihud_illiquidity(bundle.daily)
    illiq_threshold = amihud_percentile_threshold(bundle.daily)
    macro = macro_events_on(bundle.session_date)
    macro_labels = tuple(e.label for e in macro)
    opening = opening_30m_rs(bundle.intraday, bundle.benchmark_intraday)
    layers = _layer_payload(bundle, vwap_m, profile, rs, ma, vol, options)
    modules = compute_module_signals(
        vwap=vwap_m,
        profile=profile,
        rs=rs,
        ma=ma,
        vol=vol,
        options=options,
        spot=bundle.spot,
        eligible=bool(layers["L0"]["eligible"]),
        adv_usd=adv,
        amihud=illiq,
        earnings_window=earnings_risk,
        macro_count=len(macro),
        amihud_threshold=illiq_threshold,
    )
    horizons = synthesize_horizons(
        vwap=vwap_m,
        profile=profile,
        rs=rs,
        ma=ma,
        vol=vol,
        options=options,
        intraday_source=bundle.intraday_source,
        intraday_bars=len(bundle.intraday),
        adv=adv,
        amihud=illiq,
        earnings_risk=earnings_risk,
        macro_labels=macro_labels,
        opening=opening,
        n_daily=len(bundle.daily),
        amihud_threshold=illiq_threshold,
    )

    asof = datetime.now(tz=timezone.utc).astimezone().isoformat()
    return {
        "ticker": bundle.ticker,
        "benchmark": bundle.benchmark,
        "session_date": bundle.session_date.isoformat(),
        "asof": asof,
        "spot": bundle.spot,
        "product_stance": "trading_structure",
        "product_title": "Trading Structure",
        "provenance": {
            "daily_bars": bundle.daily_source,
            "intraday_bars": bundle.intraday_source,
            "options": "yfinance" if bundle.option_chain is not None else "unavailable",
            "events": "yfinance+calendar",
        },
        "layers": layers,
        "modules": modules,
        "horizons": horizons,
        "chart": {
            "interval": "5m",
            "bars": _bars_to_chart(bundle.intraday),
            "bars_5d": _bars_to_chart(bundle.intraday_5d, limit=390),
            "daily_bars": _daily_bars_to_chart(bundle.daily),
            "benchmark_daily_bars": _daily_bars_to_chart(bundle.benchmark_daily),
            "overlays": {
                "vwap": vwap_m.vwap,
                "poc": profile.poc,
                "ma20": ma.ma20,
                "ma50": ma.ma50,
                "ma200": ma.ma200,
            },
        },
    }
