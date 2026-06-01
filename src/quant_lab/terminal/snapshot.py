"""Assemble terminal dashboard payloads from processed factors + option chains."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.config import settings
from quant_lab.data.storage import load_option_chain, list_option_snapshots
from quant_lab.data.thetadata_chain import (
    TERMINAL_SYMBOL as THETADATA_TERMINAL_SYMBOL,
    list_intraday_chain_dates,
    load_built_intraday_chain,
)
from quant_lab.data.thetadata_intraday import PIN_PLAY_TIMES_ET
from quant_lab.terminal.intraday_spec import LIVE_INTRADAY_SYMBOLS, resolve_intraday_spec, supports_live_intraday
from quant_lab.terminal.deploy import (
    filter_dates_by_retention,
    history_retention_days,
    is_date_in_history_window,
    last_trading_session_date,
    prefer_thetadata_intraday,
    recent_trading_dates,
)
from quant_lab.factors.effective_oi import EFFECTIVE_OI_COL, FLOW_SOURCE_COL
from quant_lab.terminal.live_chain import (
    LIVE_TIME_OF_DAY,
    fetch_intraday_chain_from_thetadata,
    fetch_live_intraday_chain,
    is_live_session,
    live_refresh_seconds,
    market_today,
)
from quant_lab.factors.gex import (
    DEFAULT_DIVIDEND_YIELD,
    DEFAULT_RISK_FREE_RATE,
    add_bs_gamma_column,
    add_bs_vanna_column,
    compute_dealer_gamma_exposure,
    compute_dealer_vanna_exposure,
    compute_gamma_profile_curve,
    compute_gex_profile,
    compute_vex_profile,
    filter_chain_by_dte,
    net_gex_bn_per_1pct,
    net_vex_bn_per_1pct,
    pct_dte_cohort_of_total,
    vanna_interpretation,
)
from quant_lab.factors.regime import (
    pin_reliability,
    pin_score_regime_adjusted,
    regime_from_net_gex,
    should_trade_zdte,
)
from quant_lab.terminal.magnet_state import record_magnet_shift
from quant_lab.factors.positioning import pin_magnet_ranking, pin_score_components, pin_score_from_chain
from quant_lab.factors.trinity import trinity_from_kings
from quant_lab.terminal.pin_playbook import build_pin_playbook, pin_playbook_to_dict
from quant_lab.terminal.strategy_hint import StrategyHint, recommend_strategy

log = logging.getLogger(__name__)

TRINITY_SYMBOLS = ("SPY", "^SPX", "QQQ")
DEFAULT_INTRADAY_TIME = "13:00:00"
# Back-compat alias
SPX_INTRADAY_SYMBOLS = LIVE_INTRADAY_SYMBOLS


def _resolve_oi_mode(chain: pd.DataFrame) -> str:
    """Prefer flow-adjusted OI when the chain was enriched."""
    if EFFECTIVE_OI_COL in chain.columns:
        return "effective"
    return "settled"


def _volume_source_label(chain: pd.DataFrame) -> str:
    """Map chain flow provenance to API meta (trade | quote_proxy | oi_delta | settled)."""
    if chain.empty:
        return "settled"
    if FLOW_SOURCE_COL in chain.columns:
        raw = chain[FLOW_SOURCE_COL].dropna()
        if not raw.empty:
            src = str(raw.mode().iloc[0])
            if src == "trade_signed":
                return "trade_signed"
            if src == "trade":
                return "trade"
            if src == "quote_size":
                return "quote_proxy"
            if src == "oi_delta":
                return "oi_delta"
    vol = pd.to_numeric(chain.get("volume"), errors="coerce").fillna(0.0).sum()
    if vol > 0 and _resolve_oi_mode(chain) == "effective":
        return "trade"
    return "settled"


def _positioning_data_meta(chain: pd.DataFrame) -> dict[str, str]:
    oi_mode = _resolve_oi_mode(chain)
    return {"oi_mode": oi_mode, "volume_source": _volume_source_label(chain)}


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "").replace("/", "_")


def _terminal_path(symbol: str) -> Path:
    return settings.paths.processed / "terminal" / f"{_safe_symbol(symbol)}.parquet"


def is_trading_weekday(session_date: date) -> bool:
    """US equity session calendar day (Mon–Fri). Holidays not filtered here."""
    return session_date.weekday() < 5


def resolve_default_terminal_date(symbol: str, dates: list[str]) -> str:
    """Default UI date: live today on trading days, else last calendar session day."""
    if not dates:
        return market_today().isoformat()
    today = market_today()
    if (
        supports_live_intraday(symbol)
        and is_live_session(today)
        and is_trading_weekday(today)
    ):
        return today.isoformat()
    if supports_live_intraday(symbol):
        return last_trading_session_date(anchor=today).isoformat()
    for iso in reversed(dates):
        if is_trading_weekday(date.fromisoformat(iso)):
            return iso
    return dates[-1]


def list_terminal_dates(symbol: str) -> list[str]:
    """Available dates in terminal history (ISO strings, ascending)."""
    dates: set[str] = set()
    path = _terminal_path(symbol)
    if path.exists():
        df = pd.read_parquet(path, columns=["date"])
        df["date"] = pd.to_datetime(df["date"]).dt.date
        dates.update(d.isoformat() for d in df["date"].unique())
    dates.update(list_option_snapshots(symbol))
    spec = resolve_intraday_spec(symbol)
    if spec is not None:
        dates.update(list_intraday_chain_dates(option_root=spec.option_root))
        # Recent weekdays for ThetaData pull when local parquet has gaps (same as cloud).
        dates.update(recent_trading_dates())
        today = market_today()
        if is_trading_weekday(today):
            dates.add(today.isoformat())
    return filter_dates_by_retention(sorted(dates))


def _load_terminal_row(symbol: str, asof: date) -> dict[str, Any] | None:
    path = _terminal_path(symbol)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    row = df[df["date"] == asof]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def build_strike_heatmap(
    chain: pd.DataFrame,
    spot: float,
    *,
    dte_max: int = 1,
    strike_range_pct: float = 0.04,
    prev_chain: pd.DataFrame | None = None,
    prev_spot: float | None = None,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> tuple[list[dict[str, float | None]], bool]:
    """Strike-level net GEX + VEX for SpotGamma strike plot (Skylit rows).

    Returns ``(rows, cohort_fallback)``. Each row includes ``net_gex_bn`` —
    SpotGamma billions per 1% move — for display parity with headline metrics.
    """
    if chain.empty or "dte" not in chain.columns:
        return [], False
    work = chain[chain["dte"] <= dte_max].copy()
    cohort_fallback = False
    if work.empty:
        work = chain.copy()
        cohort_fallback = True
    with_greeks = add_bs_gamma_column(work, spot, r=r, q=q)
    with_greeks = add_bs_vanna_column(with_greeks, spot, r=r, q=q)
    gex_ps = compute_dealer_gamma_exposure(with_greeks, spot)
    vex_ps = compute_dealer_vanna_exposure(with_greeks, spot)
    if gex_ps.empty:
        return [], cohort_fallback

    prev_gex_by_strike: dict[float, float] = {}
    prev_vex_by_strike: dict[float, float] = {}
    if prev_chain is not None and prev_spot is not None and np.isfinite(prev_spot):
        prev_work = prev_chain[prev_chain["dte"] <= dte_max].copy()
        if prev_work.empty:
            prev_work = prev_chain.copy()
        if not prev_work.empty:
            prev_greeks = add_bs_gamma_column(prev_work, prev_spot, r=r, q=q)
            prev_greeks = add_bs_vanna_column(prev_greeks, prev_spot, r=r, q=q)
            prev_gex = compute_dealer_gamma_exposure(prev_greeks, prev_spot)
            prev_vex = compute_dealer_vanna_exposure(prev_greeks, prev_spot)
            prev_gex_by_strike = {
                float(k): float(v) for k, v in prev_gex["net_gex"].items()
            }
            prev_vex_by_strike = {
                float(k): float(v) for k, v in prev_vex["net_vex"].items()
            }

    lo = spot * (1.0 - strike_range_pct)
    hi = spot * (1.0 + strike_range_pct)
    subset = gex_ps[(gex_ps.index >= lo) & (gex_ps.index <= hi)]
    if subset.empty:
        subset = gex_ps

    rows: list[dict[str, float | None]] = []
    for strike, srow in subset.sort_index().iterrows():
        strike_f = float(strike)
        net_gex = float(srow["net_gex"])
        vex_row = vex_ps.loc[strike] if strike in vex_ps.index else None
        net_vex = float(vex_row["net_vex"]) if vex_row is not None else float("nan")

        roc_pct: float | None = None
        prev_gex = prev_gex_by_strike.get(strike_f)
        if prev_gex is not None and abs(prev_gex) > 1_000.0:
            roc_pct = float((net_gex - prev_gex) / abs(prev_gex) * 100.0)

        roc_vex: float | None = None
        prev_vex = prev_vex_by_strike.get(strike_f)
        if prev_vex is not None and abs(prev_vex) > 1_000.0:
            roc_vex = float((net_vex - prev_vex) / abs(prev_vex) * 100.0)

        rows.append(
            {
                "strike": strike_f,
                "net_gex": net_gex,
                "net_gex_bn": net_gex_bn_per_1pct(net_gex),
                "net_vex": net_vex,
                "net_vex_bn": net_vex_bn_per_1pct(net_vex) if np.isfinite(net_vex) else None,
                "call_gex": float(srow["call_gex"]),
                "put_gex": float(srow["put_gex"]),
                "total_oi": float(srow["total_oi"]),
                "roc_pct": roc_pct,
                "roc_pct_vex": roc_vex,
            }
        )
    return rows, cohort_fallback


def build_gamma_profile(
    chain: pd.DataFrame,
    spot: float,
    *,
    dte_max: int = 1,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> list[dict[str, float]]:
    """SpotGamma gamma profile: total net GEX vs hypothetical spot (±10%)."""
    if chain.empty or "dte" not in chain.columns:
        return []
    work = filter_chain_by_dte(chain, dte_max=dte_max)
    if work.empty:
        work = chain.copy()
    try:
        curve = compute_gamma_profile_curve(work, spot, r=r, q=q)
    except ValueError:
        return []
    return [
        {"spot": p.spot, "net_gex": p.net_gex, "net_gex_bn": p.net_gex_bn}
        for p in curve
    ]


def king_distance(spot: float, king: float) -> dict[str, float | str] | None:
    """Skylit-style King distance: pct from spot + direction."""
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(king):
        return None
    pct = float(abs(king - spot) / spot * 100.0)
    direction = "up" if king > spot else "down" if king < spot else "flat"
    return {"pct": pct, "direction": direction, "signed_pct": float((king - spot) / spot * 100.0)}


def _prev_trading_date(symbol: str, asof: date) -> date | None:
    dates = list_terminal_dates(symbol)
    iso = asof.isoformat()
    if iso not in dates:
        return None
    idx = dates.index(iso)
    if idx == 0:
        return None
    return date.fromisoformat(dates[idx - 1])


@dataclass
class PanelSnapshot:
    symbol: str
    spot: float
    regime: str
    king: float
    flip: float
    call_wall: float
    put_wall: float
    pin_score: float
    heatmap: list[dict[str, float | None]]
    available: bool
    king_distance: dict[str, float | str] | None
    spot_change_pct: float | None
    gamma_profile: list[dict[str, float]] = field(default_factory=list)
    data_source: str = "unavailable"
    data_mode: str = ""
    intraday_time: str | None = None


def _load_chain_safe(symbol: str, iso: str) -> tuple[pd.DataFrame, float]:
    chain, meta = load_option_chain(symbol, iso)
    spot = float(meta["spot"].iloc[0]) if not meta.empty else float("nan")
    return chain, spot


def _fetch_thetadata_intraday_chain(
    session: date,
    iso: str,
    symbol: str,
    *,
    time_of_day: str,
) -> tuple[pd.DataFrame, float, str, str]:
    if not is_date_in_history_window(session):
        raise FileNotFoundError(f"no intraday chain for {symbol} on {iso} (outside history window)")
    try:
        chain, spot, time_used, _cached = fetch_intraday_chain_from_thetadata(
            session, time_of_day, symbol=symbol
        )
    except Exception as exc:
        from thetadata.errors import NoDataFoundError

        if isinstance(exc, NoDataFoundError):
            raise FileNotFoundError(
                f"no intraday chain for {symbol} on {iso} @ {time_of_day}"
            ) from exc
        raise
    source = "live" if is_live_session(session) else "thetadata"
    return chain, spot, time_used, source


def _load_intraday_chain_safe(
    iso: str,
    symbol: str,
    *,
    time_of_day: str = DEFAULT_INTRADAY_TIME,
) -> tuple[pd.DataFrame, float, str, str]:
    """Load 0DTE intraday chain: ThetaData for recent sessions, local parquet for deep history.

    Returns ``(chain, spot, time_used, source)`` where ``source`` is ``live``, ``local``,
    or ``thetadata`` (remote historical fetch when parquet is absent).
    """
    spec = resolve_intraday_spec(symbol)
    if spec is None:
        raise ValueError(f"symbol {symbol!r} has no intraday chain spec")

    session = date.fromisoformat(iso)
    if is_live_session(session):
        try:
            chain, spot, time_used, _cached = fetch_live_intraday_chain(
                session, time_of_day, symbol=symbol
            )
            return chain, spot, time_used, "live"
        except Exception as exc:
            log.warning(
                "live ThetaData fetch failed for %s %s @ %s: %s — trying fallbacks",
                symbol,
                iso,
                time_of_day,
                exc,
            )

    if prefer_thetadata_intraday(session):
        try:
            return _fetch_thetadata_intraday_chain(
                session, iso, symbol, time_of_day=time_of_day
            )
        except FileNotFoundError as exc:
            log.warning(
                "ThetaData intraday unavailable for %s %s @ %s: %s — trying local",
                symbol,
                iso,
                time_of_day,
                exc,
            )

    try:
        return _load_local_intraday_chain(session, time_of_day, spec.option_root)
    except FileNotFoundError:
        return _fetch_thetadata_intraday_chain(
            session, iso, symbol, time_of_day=time_of_day
        )


def _load_local_intraday_chain(
    session: date,
    time_of_day: str,
    option_root: str,
) -> tuple[pd.DataFrame, float, str, str]:
    chain, meta = load_built_intraday_chain(session, time_of_day, option_root=option_root)
    spot = float(meta["spot"].iloc[0]) if not meta.empty and "spot" in meta.columns else float("nan")
    return chain, spot, time_of_day, "local"


def _row_from_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    hours_to_close: float | None = None,
    time_to_close_pct: float | None = None,
) -> dict[str, Any]:
    """Terminal factor row from a 0DTE chain when no processed history exists."""
    from quant_lab.factors.positioning import (
        atm_iv_from_chain,
        expected_move_1sd,
        max_pain,
        oi_concentration,
        pin_score_from_chain,
        put_call_ratio,
    )

    profile = compute_gex_profile(chain, spot, dte_max=1)
    profile_all = compute_gex_profile(chain, spot, dte_max=None)
    profile_vex = compute_vex_profile(chain, spot, dte_max=1)
    mp = max_pain(chain, dte_max=1)
    pcr = put_call_ratio(chain, kind="open_interest")
    oi_conc = oi_concentration(chain, dte_max=1, top_n=3)
    king = profile.king_node
    iv = atm_iv_from_chain(chain, spot, dte=1)
    em = expected_move_1sd(spot, iv, dte=1)
    pct_dte = pct_dte_cohort_of_total(profile.net_gex, profile_all.net_gex)
    oi_mode = _resolve_oi_mode(chain)
    pin_result = pin_score_from_chain(
        chain,
        spot,
        dte_max=1,
        hours_to_close=hours_to_close,
        time_to_close_pct=time_to_close_pct,
        pct_gex_dte1=pct_dte,
        oi_mode=oi_mode,
    )
    pin = pin_result.score
    spot_vs_king = float((spot - king) / spot * 100.0) if np.isfinite(king) and spot > 0 else float("nan")
    flip = profile.flip_level
    spot_vs_flip = (
        float((spot - flip) / spot * 100.0) if np.isfinite(flip) and spot > 0 else float("nan")
    )
    return {
        "spot": spot,
        "regime": regime_from_net_gex(profile.net_gex),
        "flip_dte1": flip,
        "call_wall_dte1": profile.call_wall,
        "put_wall_dte1": profile.put_wall,
        "king_dte1": king,
        "floor_dte1": profile.floor_strike,
        "ceiling_dte1": profile.ceiling_strike,
        "max_pain_dte1": mp,
        "pin_score": pin,
        "expected_move_1sd": em,
        "pct_gex_dte1": pct_dte,
        "net_gex_dte1": profile.net_gex,
        "pct_vex_dte1": float("nan"),
        "net_vex_dte1": profile_vex.net_vex,
        "vanna_interp_dte1": profile_vex.interpretation,
        "pcr_oi": pcr,
        "oi_conc_dte1": oi_conc,
        "spot_vs_king_pct": spot_vs_king,
        "spot_vs_flip_pct": spot_vs_flip,
        "distance_to_magnet_pct": pin_result.distance_to_magnet_pct,
        "magnet_gex_bn": pin_result.magnet_gex_bn,
    }


def _session_hours_to_close(session: date, time_of_day: str | None) -> float:
    """Trading hours remaining until 16:00 ET."""
    if not time_of_day:
        return 0.0
    from quant_lab.data.intraday_time import hours_to_close

    return hours_to_close(session, time_of_day)


def _session_time_to_close_pct(session: date, time_of_day: str | None) -> float:
    """Legacy pct helper (0=open, 100=close)."""
    from quant_lab.data.intraday_time import SESSION_HOURS

    hours = _session_hours_to_close(session, time_of_day)
    return float(np.clip((1.0 - hours / SESSION_HOURS) * 100.0, 0.0, 100.0))


def _apply_live_pin_row(
    row: dict[str, Any],
    chain: pd.DataFrame,
    spot: float,
    *,
    hours_to_close: float | None = None,
    time_to_close_pct: float | None = None,
) -> dict[str, Any]:
    """Recompute pin score from the active chain (intraday-accurate)."""
    if chain.empty or not np.isfinite(spot):
        return row
    pct = float(row.get("pct_gex_dte1", np.nan))
    oi_mode = _resolve_oi_mode(chain)
    result = pin_score_from_chain(
        chain,
        spot,
        dte_max=1,
        hours_to_close=hours_to_close,
        time_to_close_pct=time_to_close_pct,
        pct_gex_dte1=pct if np.isfinite(pct) else None,
        oi_mode=oi_mode,
    )
    merged = dict(row)
    merged["pin_score"] = result.score
    merged["distance_to_magnet_pct"] = result.distance_to_magnet_pct
    merged["magnet_gex_bn"] = result.magnet_gex_bn
    merged["king_dte1"] = result.magnet_strike
    merged["max_pain_dte1"] = result.max_pain_strike
    return merged


def _intraday_data_labels(chain_source: str, time_used: str) -> tuple[str, str]:
    """Map intraday load result to ``(data_source, data_mode)``."""
    tshort = time_used[:5] if time_used else "??:??"
    if chain_source == "live":
        return "thetadata_live", f"ThetaData live @ {tshort} ET"
    return "thetadata", f"ThetaData intraday @ {tshort} ET"


def _unavailable_panel_meta(sym: str, session: date) -> tuple[str, str]:
    if supports_live_intraday(sym) and is_live_session(session):
        return "unavailable", "No intraday chain · live session"
    return "unavailable", "No chain for this date"


def _is_live_follow_request(session: date, time_of_day: str) -> bool:
    return is_live_session(session) and time_of_day.strip().lower() == LIVE_TIME_OF_DAY


def _prefetch_trinity_chains(
    iso: str,
    time_of_day: str,
    *,
    main_symbol: str,
) -> dict[str, tuple[pd.DataFrame, float, str, str, str | None]]:
    """Parallel ThetaData pulls for SPY/QQQ/^SPX (excludes ``main_symbol``)."""
    session = date.fromisoformat(iso)
    if not _is_live_follow_request(session, time_of_day):
        return {}

    def _load(sym: str) -> tuple[str, tuple[pd.DataFrame, float, str, str, str | None] | None]:
        try:
            chain, spot, time_used, chain_source = _load_intraday_chain_safe(
                iso, sym, time_of_day=time_of_day
            )
            ds, dm = _intraday_data_labels(chain_source, time_used)
            tshort = time_used[:5] if time_used else None
            return sym, (chain, spot, ds, dm, tshort)
        except FileNotFoundError:
            return sym, None

    out: dict[str, tuple[pd.DataFrame, float, str, str, str | None]] = {}
    workers = [sym for sym in TRINITY_SYMBOLS if sym != main_symbol and supports_live_intraday(sym)]
    if not workers:
        return out
    with ThreadPoolExecutor(max_workers=min(3, len(workers))) as pool:
        futures = [pool.submit(_load, sym) for sym in workers]
        for fut in as_completed(futures):
            sym, payload = fut.result()
            if payload is not None:
                out[sym] = payload
    return out


def _load_sym_panel_chain(
    sym: str,
    iso: str,
    time_of_day: str,
    *,
    main_symbol: str,
    main_chain: pd.DataFrame,
    main_spot: float,
    main_intraday_time: str | None,
    main_chain_source: str | None,
    prefetched: dict[str, tuple[pd.DataFrame, float, str, str, str | None]] | None = None,
) -> tuple[pd.DataFrame | None, float, str, str, str | None]:
    """Load chain for one Trinity symbol; returns chain, spot, source, mode, time label."""
    session = date.fromisoformat(iso)
    if sym == main_symbol:
        if not main_chain.empty:
            if supports_live_intraday(sym):
                t_used = main_intraday_time or time_of_day
                src = main_chain_source or "local"
                ds, dm = _intraday_data_labels(src, t_used)
                return main_chain, main_spot, ds, dm, t_used[:5] if t_used else None
            return main_chain, main_spot, "eod", "EoD close", None
        ds, dm = _unavailable_panel_meta(sym, session)
        return None, float("nan"), ds, dm, None

    if prefetched and sym in prefetched:
        chain, spot, ds, dm, tshort = prefetched[sym]
        return chain, spot, ds, dm, tshort

    try:
        if supports_live_intraday(sym):
            chain, spot, time_used, chain_source = _load_intraday_chain_safe(
                iso, sym, time_of_day=time_of_day
            )
            ds, dm = _intraday_data_labels(chain_source, time_used)
            return chain, spot, ds, dm, time_used[:5] if time_used else None
        chain, spot = _load_chain_safe(sym, iso)
        return chain, spot, "eod", "EoD close", None
    except FileNotFoundError:
        ds, dm = _unavailable_panel_meta(sym, session)
        return None, float("nan"), ds, dm, None


def _panel_from_row_and_chain(
    symbol: str,
    row: dict[str, Any] | None,
    chain: pd.DataFrame | None,
    *,
    spot: float,
    prev_chain: pd.DataFrame | None = None,
    prev_spot: float | None = None,
    prev_row: dict[str, Any] | None = None,
    data_source: str = "unavailable",
    data_mode: str = "",
    intraday_time: str | None = None,
) -> PanelSnapshot:
    if row is None:
        return PanelSnapshot(
            symbol=symbol,
            spot=spot,
            regime="undetermined",
            king=float("nan"),
            flip=float("nan"),
            call_wall=float("nan"),
            put_wall=float("nan"),
            pin_score=float("nan"),
            heatmap=[],
            gamma_profile=[],
            available=False,
            king_distance=None,
            spot_change_pct=None,
            data_source=data_source,
            data_mode=data_mode,
            intraday_time=intraday_time,
        )
    king = float(row.get("king_dte1", np.nan))
    panel_spot = float(row.get("spot", spot))
    if chain is not None and not chain.empty:
        heatmap, _cohort_fb = build_strike_heatmap(
            chain,
            panel_spot,
            dte_max=1,
            prev_chain=prev_chain,
            prev_spot=prev_spot,
        )
        gamma_profile = build_gamma_profile(chain, panel_spot, dte_max=1)
    else:
        heatmap = []
        gamma_profile = []
    spot_chg: float | None = None
    if prev_row is not None:
        prev_s = float(prev_row.get("spot", np.nan))
        if np.isfinite(prev_s) and prev_s > 0 and np.isfinite(panel_spot):
            spot_chg = float((panel_spot - prev_s) / prev_s * 100.0)

    return PanelSnapshot(
        symbol=symbol,
        spot=panel_spot,
        regime=str(row.get("regime", "undetermined")),
        king=king,
        flip=_f(row.get("flip_dte1")),
        call_wall=float(row.get("call_wall_dte1", np.nan)),
        put_wall=float(row.get("put_wall_dte1", np.nan)),
        pin_score=float(row.get("pin_score", np.nan)),
        heatmap=heatmap,
        gamma_profile=gamma_profile,
        available=True,
        king_distance=king_distance(panel_spot, king),
        spot_change_pct=spot_chg,
        data_source=data_source,
        data_mode=data_mode,
        intraday_time=intraday_time,
    )


def build_pin_targets(
    heatmap: list[dict[str, float | None]],
    spot: float,
    *,
    king: float | None,
    max_pain: float | None,
    pin_score: float | None,
    oi_concentration_top3: float | None,
    hours_to_close: float | None = None,
    time_to_close_pct: float | None = None,
    magnet_gex_bn: float | None = None,
    expected_move_1sd: float | None = None,
    max_gex_bn_reference: float | None = None,
    pct_gex_dte1: float | None = None,
    oi_near_magnet: float | None = None,
    net_gex_bn_per_1pct: float | None = None,
    regime: str = "undetermined",
    top_n: int = 5,
) -> dict[str, Any]:
    """Pin magnet ladder for terminal UI (relative weights, not calibrated probability)."""
    magnet = king if king is not None and np.isfinite(king) else max_pain
    if magnet is None or not np.isfinite(float(magnet)):
        magnet = float("nan")

    breakdown = pin_score_components(
        spot=spot,
        magnet_strike=float(magnet),
        oi_concentration_top3=oi_concentration_top3 if oi_concentration_top3 is not None else 0.0,
        magnet_gex_bn_per_1pct=magnet_gex_bn if magnet_gex_bn is not None else float("nan"),
        hours_to_close=hours_to_close,
        time_to_close_pct=time_to_close_pct,
        expected_move_1sd=expected_move_1sd,
        max_gex_bn_reference=max_gex_bn_reference,
        max_pain_strike=max_pain,
        pct_gex_dte1=pct_gex_dte1,
        oi_near_magnet=oi_near_magnet,
        net_gex_bn_per_1pct=net_gex_bn_per_1pct,
    )
    rankings = pin_magnet_ranking(
        heatmap,
        spot,
        king=king,
        max_pain=max_pain,
        top_n=top_n,
    )
    primary = king if king is not None and np.isfinite(king) else None
    if primary is None and rankings:
        primary = float(rankings[0]["strike"])

    raw_pin = pin_score
    adjusted_pin = (
        pin_score_regime_adjusted(float(raw_pin), regime)  # type: ignore[arg-type]
        if raw_pin is not None and np.isfinite(raw_pin)
        else None
    )
    reliability_tier, reliability_detail = (
        pin_reliability(float(raw_pin), regime)  # type: ignore[arg-type]
        if raw_pin is not None and np.isfinite(raw_pin)
        else ("unknown", "Insufficient pin data")
    )

    return {
        "method": "gex_times_oi_heuristic",
        "disclaimer": "Relative magnet weight from |GEX|×OI — not a calibrated close probability.",
        "primary_strike": _f(primary) if primary is not None else None,
        "primary_label": "king" if king is not None and np.isfinite(king) else "top_magnet",
        "max_pain": _f(max_pain),
        "pin_score": _f(raw_pin),
        "pin_score_adjusted": _f(adjusted_pin),
        "pin_reliability": reliability_tier,
        "pin_reliability_detail": reliability_detail,
        "pin_score_breakdown": {k: _f(v) for k, v in breakdown.items()},
        "rankings": rankings,
    }


def build_dashboard(
    symbol: str,
    asof: date,
    *,
    time_of_day: str = DEFAULT_INTRADAY_TIME,
) -> dict[str, Any]:
    """Full dashboard JSON for one symbol and date."""
    iso = asof.isoformat()
    row = _load_terminal_row(symbol, asof)
    data_mode = "EoD snapshot"
    intraday_time: str | None = None
    main_chain_source: str | None = None

    chain = pd.DataFrame()
    spot = float(row.get("spot", np.nan)) if row else float("nan")
    session_hours = _session_hours_to_close(asof, time_of_day)

    if supports_live_intraday(symbol):
        try:
            chain, spot, intraday_time, main_chain_source = _load_intraday_chain_safe(
                iso, symbol, time_of_day=time_of_day
            )
            session_hours = _session_hours_to_close(asof, intraday_time or time_of_day)
            if main_chain_source == "live":
                if _is_live_follow_request(asof, time_of_day):
                    data_mode = f"ThetaData live follow @ {intraday_time[:5]} ET"
                else:
                    data_mode = f"ThetaData snapshot @ {intraday_time[:5]} ET"
            else:
                data_mode = f"ThetaData intraday @ {intraday_time[:5]} ET"
            if main_chain_source in ("live", "thetadata") and not chain.empty:
                row = _row_from_chain(chain, spot, hours_to_close=session_hours)
            elif row is None and not chain.empty:
                row = _row_from_chain(chain, spot, hours_to_close=session_hours)
        except FileNotFoundError:
            pass

    if chain.empty and not (
        supports_live_intraday(symbol) and prefer_thetadata_intraday(asof)
    ):
        try:
            chain, meta = load_option_chain(symbol, iso)
            spot = float(meta["spot"].iloc[0]) if not meta.empty else spot
        except FileNotFoundError:
            chain = pd.DataFrame()

    if row is None and chain.empty:
        raise FileNotFoundError(f"no data for {symbol} on {iso}")

    if row is None and not chain.empty:
        row = _row_from_chain(chain, spot, hours_to_close=session_hours)
    elif row is not None and not chain.empty and np.isfinite(spot):
        row = _apply_live_pin_row(row, chain, spot, hours_to_close=session_hours)

    prev_date = _prev_trading_date(symbol, asof)
    prev_row_main = _load_terminal_row(symbol, prev_date) if prev_date else None
    prev_chain_main: pd.DataFrame | None = None
    prev_spot_main: float | None = None
    compare_time = intraday_time
    if not compare_time:
        compare_time = (
            DEFAULT_INTRADAY_TIME
            if time_of_day.strip().lower() == LIVE_TIME_OF_DAY
            else time_of_day
        )
    if prev_date is not None:
        try:
            if supports_live_intraday(symbol):
                prev_chain_main, prev_spot_main, _, _ = _load_intraday_chain_safe(
                    prev_date.isoformat(),
                    symbol,
                    time_of_day=compare_time,
                )
            else:
                prev_chain_main, prev_spot_main = _load_chain_safe(symbol, prev_date.isoformat())
        except FileNotFoundError:
            pass

    roc_prev_chain: pd.DataFrame | None = prev_chain_main
    roc_prev_spot: float | None = prev_spot_main

    heatmap: list[dict[str, float | None]] = []
    cohort_fallback = False
    gamma_profile: list[dict[str, float]] = []
    if not chain.empty:
        heatmap, cohort_fallback = build_strike_heatmap(
            chain,
            spot,
            dte_max=1,
            prev_chain=roc_prev_chain,
            prev_spot=roc_prev_spot,
        )
        gamma_profile = build_gamma_profile(chain, spot, dte_max=1)

    king_val = float(row.get("king_dte1", np.nan))
    king_dist = king_distance(spot, king_val)
    spot_change_pct: float | None = None
    if prev_row_main is not None:
        prev_s = float(prev_row_main.get("spot", np.nan))
        if np.isfinite(prev_s) and prev_s > 0:
            spot_change_pct = float((spot - prev_s) / prev_s * 100.0)

    regime = str(row.get("regime", regime_from_net_gex(float(row.get("net_gex_dte1", 0)))))
    pin = float(row.get("pin_score", np.nan))
    pct_dte = float(row.get("pct_gex_dte1", np.nan))
    trade_ok, trade_reason = should_trade_zdte(
        pct_gex_dte1=pct_dte if np.isfinite(pct_dte) else 100.0,
        pin_score=pin if np.isfinite(pin) else 50.0,
        regime=regime,  # type: ignore[arg-type]
    )

    hint = recommend_strategy(
        regime=regime,
        pin_score=pin,
        spot=spot,
        put_wall=float(row.get("put_wall_dte1", np.nan)),
        call_wall=float(row.get("call_wall_dte1", np.nan)),
        king=float(row.get("king_dte1", np.nan)),
        flip=_f(row.get("flip_dte1")),
        pct_gex_dte1=pct_dte,
        should_trade=trade_ok,
        net_vex=float(row.get("net_vex_dte1", np.nan)),
        vanna_interpretation=str(row.get("vanna_interp_dte1", "")),
    )

    net_dte = float(row.get("net_gex_dte1", np.nan))
    net_vex_dte = float(row.get("net_vex_dte1", np.nan))
    pct_vex = float(row.get("pct_vex_dte1", np.nan))
    vanna_interp = str(row.get("vanna_interp_dte1", vanna_interpretation(net_vex_dte)))
    trinity_prefetch = _prefetch_trinity_chains(iso, time_of_day, main_symbol=symbol)
    panels: list[dict[str, Any]] = []
    trinity_inputs: dict[str, tuple[float, float]] = {}
    trinity_live_count = 0
    for sym in TRINITY_SYMBOLS:
        sym_row = _load_terminal_row(sym, asof) if sym != symbol else row
        sym_prev_row = _load_terminal_row(sym, prev_date) if prev_date else None
        sym_chain, sym_spot, sym_data_source, sym_data_mode, sym_intraday_time = _load_sym_panel_chain(
            sym,
            iso,
            time_of_day,
            main_symbol=symbol,
            main_chain=chain,
            main_spot=spot,
            main_intraday_time=intraday_time,
            main_chain_source=main_chain_source,
            prefetched=trinity_prefetch,
        )
        if sym_data_source == "thetadata_live":
            trinity_live_count += 1
        sym_prev_chain: pd.DataFrame | None = prev_chain_main if sym == symbol else None
        sym_prev_spot: float | None = prev_spot_main if sym == symbol else None
        if sym != symbol and prev_date is not None:
            try:
                if supports_live_intraday(sym):
                    sym_prev_chain, sym_prev_spot, _, _ = _load_intraday_chain_safe(
                        prev_date.isoformat(), sym, time_of_day=compare_time
                    )
                else:
                    sym_prev_chain, sym_prev_spot = _load_chain_safe(sym, prev_date.isoformat())
            except FileNotFoundError:
                sym_prev_chain = None
        if (
            supports_live_intraday(sym)
            and sym_chain is not None
            and not sym_chain.empty
            and np.isfinite(sym_spot)
            and sym_data_source not in ("eod", "unavailable")
        ):
            sym_row = _row_from_chain(sym_chain, sym_spot, hours_to_close=session_hours)
        elif sym_row is not None and sym_chain is not None and not sym_chain.empty and np.isfinite(sym_spot):
            sym_row = _apply_live_pin_row(sym_row, sym_chain, sym_spot, hours_to_close=session_hours)
        panel = _panel_from_row_and_chain(
            sym,
            sym_row,
            sym_chain,
            spot=sym_spot,
            prev_chain=sym_prev_chain,
            prev_spot=sym_prev_spot,
            prev_row=sym_prev_row,
            data_source=sym_data_source,
            data_mode=sym_data_mode,
            intraday_time=sym_intraday_time,
        )
        panels.append(asdict(panel))
        if panel.available and np.isfinite(panel.king) and np.isfinite(panel.spot):
            key = sym.replace("^", "")
            trinity_inputs[key] = (panel.spot, panel.king)

    align = trinity_from_kings(
        spy=trinity_inputs.get("SPY"),
        spx=trinity_inputs.get("SPX"),
        qqq=trinity_inputs.get("QQQ"),
    )

    em = float(row.get("expected_move_1sd", np.nan))
    levels = {
        "flip": _f(row.get("flip_dte1")),
        "call_wall": _f(row.get("call_wall_dte1")),
        "put_wall": _f(row.get("put_wall_dte1")),
        "king": _f(row.get("king_dte1")),
        "floor": _f(row.get("floor_dte1")),
        "ceiling": _f(row.get("ceiling_dte1")),
        "max_pain": _f(row.get("max_pain_dte1")),
        "expected_move": em,
        "expected_upper": spot + em if np.isfinite(em) else None,
        "expected_lower": spot - em if np.isfinite(em) else None,
    }

    playbook_time = intraday_time or (
        DEFAULT_INTRADAY_TIME if time_of_day.strip().lower() == LIVE_TIME_OF_DAY else time_of_day
    )
    pos_meta = _positioning_data_meta(chain) if not chain.empty else {"oi_mode": "settled", "volume_source": "settled"}
    refresh_secs = live_refresh_seconds() if main_chain_source == "live" else None
    chain_time_requested = (
        "now" if time_of_day.strip().lower() == LIVE_TIME_OF_DAY else time_of_day[:5]
    )
    pin_playbook = build_pin_playbook(
        symbol=symbol,
        session_date=asof,
        time_of_day=playbook_time,
        regime=regime,
        pin_score=pin if np.isfinite(pin) else float("nan"),
        pct_gex_dte1=pct_dte if np.isfinite(pct_dte) else float("nan"),
        spot=spot,
        put_wall=levels["put_wall"],
        call_wall=levels["call_wall"],
        king=levels["king"],
        max_pain=levels["max_pain"],
        expected_move=levels["expected_move"],
        gate_should_trade=trade_ok,
        gate_reason=trade_reason,
        trinity_score=_f(align.score),
        trinity_direction=align.direction,
    )

    session_hours = pin_playbook.hours_to_close
    pin_targets = build_pin_targets(
        heatmap,
        spot,
        king=levels["king"],
        max_pain=levels["max_pain"],
        pin_score=pin if np.isfinite(pin) else None,
        oi_concentration_top3=_f(row.get("oi_conc_dte1")),
        hours_to_close=session_hours,
        magnet_gex_bn=_f(row.get("magnet_gex_bn")),
        expected_move_1sd=em if np.isfinite(em) else None,
        pct_gex_dte1=pct_dte if np.isfinite(pct_dte) else None,
        net_gex_bn_per_1pct=_f(net_gex_bn_per_1pct(net_dte)),
        regime=regime,
    )

    magnet_shift = None
    if _is_live_follow_request(asof, time_of_day) and main_chain_source == "live":
        magnet_shift = record_magnet_shift(symbol, iso, levels["king"])

    payload = {
        "symbol": symbol,
        "date": iso,
        "spot": spot,
        "regime": regime,
        "levels": levels,
        "king_distance": king_dist,
        "spot_change_pct": _f(spot_change_pct),
        "metrics": {
            "pin_score": _f(pin),
            "pct_gex_dte1": _f(pct_dte),
            "net_gex_dte1_bn": _f(net_gex_bn_per_1pct(net_dte)),
            "pct_vex_dte1": _f(pct_vex),
            "net_vex_dte1_bn": _f(net_vex_bn_per_1pct(net_vex_dte)),
            "vanna_interpretation": vanna_interp if vanna_interp else None,
            "pcr_oi": _f(row.get("pcr_oi")),
            "oi_conc_dte1": _f(row.get("oi_conc_dte1")),
            "spot_vs_king_pct": _f(row.get("spot_vs_king_pct")),
            "spot_vs_flip_pct": _f(row.get("spot_vs_flip_pct")),
        },
        "gate": {"should_trade": trade_ok, "reason": trade_reason},
        "strategy": asdict(hint),
        "trinity": {
            "score": _f(align.score),
            "direction": align.direction,
            "n_symbols": align.n_symbols,
            "distance_pcts": align.distance_pcts,
        },
        "heatmap": heatmap,
        "gamma_profile": gamma_profile,
        "panels": panels,
        "pin_playbook": pin_playbook_to_dict(pin_playbook),
        "pin_targets": pin_targets,
        "meta": {
            "cohort": "dte≤1 (0DTE proxy)" if not cohort_fallback else "full chain (dte≤1 filter empty)",
            "cohort_fallback": cohort_fallback,
            "gex_display_unit": "bn_per_1pct",
            "gex_formula": "0.01 × Σ dealer_sign × Γ × OI × 100 × S²",
            "dealer_sign": "SpotGamma: dealer long calls (+1), short puts (-1)",
            "data_mode": data_mode,
            "data_source": (
                "thetadata_live"
                if "live" in data_mode.lower()
                else ("thetadata" if "ThetaData" in data_mode else "eod")
            ),
            "n_strikes": len(heatmap),
            "intraday_time": intraday_time[:5] if intraday_time else None,
            "chain_time_requested": chain_time_requested,
            "intraday_times_available": ["live", *list(PIN_PLAY_TIMES_ET)],
            "quote_granularity": "1m" if main_chain_source in ("live", "local", "thetadata") else None,
            "live_refresh_seconds": refresh_secs,
            "oi_mode": pos_meta["oi_mode"],
            "volume_source": pos_meta["volume_source"],
            "live_follow": _is_live_follow_request(asof, time_of_day) and main_chain_source == "live",
            "trinity_live_panels": trinity_live_count,
            "server_pulled_at": datetime.now(timezone.utc).isoformat(),
            "magnet_shift": magnet_shift is not None,
            "magnet_previous": _f(magnet_shift.previous) if magnet_shift else None,
            "magnet_delta_pts": _f(magnet_shift.delta_pts) if magnet_shift else None,
        },
    }
    return json_safe(payload)


def _f(val: Any) -> float | None:
    if val is None:
        return None
    v = float(val)
    if not np.isfinite(v):
        return None
    return v


def json_safe(value: Any) -> Any:
    """Convert numpy/pandas scalars to JSON-native types (FastAPI-safe)."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        native = value.item()
        if isinstance(native, float) and not np.isfinite(native):
            return None
        return json_safe(native)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value
