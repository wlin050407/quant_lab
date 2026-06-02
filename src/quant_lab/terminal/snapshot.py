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
    ChainMode,
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
    resolve_intraday_clock,
)
from quant_lab.factors.gex import (
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
from quant_lab.terminal.live_chain import live_chain_poll_meta
from quant_lab.terminal.live_pin_quality import (
    assess_live_pin_quality,
    cap_pin_reliability,
    live_pin_quality_to_dict,
)
from quant_lab.terminal.model_metadata import build_model_metadata, compute_flip_result_for_chain
from quant_lab.factors.gex import diagnose_cohort_time_to_expiry
from quant_lab.factors.positioning import (
    PIN_SCORE_MODEL_VERSION,
    atm_iv_from_chain,
    expected_move_1sd,
    pin_magnet_ranking,
    pin_score_components,
    pin_score_from_chain,
    resolve_cohort_time_years,
)
from quant_lab.factors.rates import resolve_gex_inputs
from quant_lab.factors.trinity import trinity_from_kings
from quant_lab.terminal.pin_playbook import build_pin_playbook, pin_playbook_to_dict
from quant_lab.terminal.session_status import (
    SessionHoldReason,
    session_hold_message,
    session_hold_reason,
    session_hold_title,
)
from quant_lab.terminal.strategy_hint import StrategyHint, recommend_strategy
from quant_lab.data.base import MARKET_TZ

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


def _trading_session_dates_only(dates: list[str]) -> list[str]:
    """Keep Mon–Fri only — raw snapshot dirs / parquet can contain Sat/Sun junk."""
    return sorted({d for d in dates if is_trading_weekday(date.fromisoformat(d))})


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
    retained = filter_dates_by_retention(sorted(dates))
    return _trading_session_dates_only(retained)


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
    symbol: str | None = None,
    asof: date | None = None,
    dte_max: int = 1,
    strike_range_pct: float = 0.04,
    prev_chain: pd.DataFrame | None = None,
    prev_spot: float | None = None,
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
    with_greeks = add_bs_gamma_column(work, spot, symbol=symbol, asof=asof)
    with_greeks = add_bs_vanna_column(with_greeks, spot, symbol=symbol, asof=asof)
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
            prev_greeks = add_bs_gamma_column(
                prev_work, prev_spot, symbol=symbol, asof=asof
            )
            prev_greeks = add_bs_vanna_column(
                prev_greeks, prev_spot, symbol=symbol, asof=asof
            )
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
    symbol: str | None = None,
    asof: date | None = None,
    dte_max: int = 1,
) -> list[dict[str, float]]:
    """SpotGamma gamma profile: total net GEX vs hypothetical spot (±10%)."""
    if chain.empty or "dte" not in chain.columns:
        return []
    work = filter_chain_by_dte(chain, dte_max=dte_max)
    if work.empty:
        work = chain.copy()
    try:
        curve = compute_gamma_profile_curve(work, spot, symbol=symbol, asof=asof)
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


def _thetadata_unavailable(exc: BaseException) -> bool:
    """True when ThetaData has no usable intraday chain (not a server bug)."""
    from thetadata.errors import NoDataFoundError

    if isinstance(exc, NoDataFoundError):
        return True
    if isinstance(exc, FileNotFoundError):
        return True
    msg = str(exc)
    needles = (
        "NoDataFound",
        "INVALID_ARGUMENT",
        "start time less than current time",
        "UNAUTHENTICATED",
        "Invalid session ID",
        "StatusCode",
        "UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "_MultiThreadedRendezvous",
    )
    return any(n in msg for n in needles)


def _fetch_thetadata_intraday_chain(
    session: date,
    iso: str,
    symbol: str,
    *,
    time_of_day: str,
    chain_mode: ChainMode = "full",
) -> tuple[pd.DataFrame, float, str, str]:
    if not is_date_in_history_window(session):
        raise FileNotFoundError(f"no intraday chain for {symbol} on {iso} (outside history window)")
    try:
        chain, spot, time_used, _cached = fetch_intraday_chain_from_thetadata(
            session, time_of_day, symbol=symbol, chain_mode=chain_mode
        )
    except Exception as exc:
        log.warning(
            "ThetaData chain fetch failed for %s on %s @ %s: %s",
            symbol,
            iso,
            time_of_day,
            exc,
        )
        raise FileNotFoundError(
            f"no intraday chain for {symbol} on {iso} @ {time_of_day}"
        ) from exc
    source = "live" if is_live_session(session) else "thetadata"
    return chain, spot, time_used, source


@dataclass(frozen=True)
class _ChainRequest:
    symbol: str
    session: date
    time_of_day: str
    chain_mode: ChainMode = "pin"


ChainLoad = tuple[pd.DataFrame, float, str, str]


def _load_intraday_chain_fallbacks(
    session: date,
    iso: str,
    symbol: str,
    *,
    clock: str,
    option_root: str,
    chain_mode: ChainMode,
) -> ChainLoad:
    """After live cache misses: remote ThetaData (honors ``chain_mode``), then local parquet."""
    remote_exc: FileNotFoundError | None = None
    if is_date_in_history_window(session):
        try:
            return _fetch_thetadata_intraday_chain(
                session, iso, symbol, time_of_day=clock, chain_mode=chain_mode
            )
        except FileNotFoundError as exc:
            remote_exc = exc
        except Exception as exc:
            log.warning(
                "remote ThetaData failed for %s %s @ %s: %s — trying local parquet",
                symbol,
                iso,
                clock,
                exc,
            )

    try:
        return _load_local_intraday_chain(session, clock, option_root)
    except FileNotFoundError as exc:
        if remote_exc is not None:
            raise remote_exc from exc
        raise FileNotFoundError(f"no intraday chain for {symbol} on {iso}") from exc


def _load_intraday_chain_safe(
    iso: str,
    symbol: str,
    *,
    time_of_day: str = DEFAULT_INTRADAY_TIME,
    chain_mode: ChainMode = "pin",
) -> ChainLoad:
    """Load 0DTE intraday chain for the terminal dashboard.

    Order: **live** in-memory cache → **remote** ThetaData (respects ``chain_mode``) →
    **local** intraday parquet. Default ``chain_mode="pin"`` uses 09:30 reference OI;
    ``full`` adds session trade flow; ``gex`` skips flow for aux heatmaps only.
    """
    spec = resolve_intraday_spec(symbol)
    if spec is None:
        raise ValueError(f"symbol {symbol!r} has no intraday chain spec")

    session = date.fromisoformat(iso)
    clock = resolve_intraday_clock(session, time_of_day)

    if is_live_session(session):
        try:
            chain, spot, time_used, _cached = fetch_live_intraday_chain(
                session, time_of_day, symbol=symbol, chain_mode=chain_mode
            )
            return chain, spot, time_used, "live"
        except Exception as exc:
            log.warning(
                "live ThetaData fetch failed for %s %s @ %s: %s — trying fallbacks",
                symbol,
                iso,
                clock,
                exc,
            )

    return _load_intraday_chain_fallbacks(
        session,
        iso,
        symbol,
        clock=clock,
        option_root=spec.option_root,
        chain_mode=chain_mode,
    )


def _parallel_load_chains(
    requests: list[_ChainRequest],
) -> dict[tuple[str, str], ChainLoad]:
    """Load multiple intraday chains concurrently (deduped by symbol+date+mode)."""
    unique: dict[tuple[str, str, ChainMode], _ChainRequest] = {}
    for req in requests:
        if not supports_live_intraday(req.symbol):
            continue
        key = (req.symbol, req.session.isoformat(), req.chain_mode)
        unique[key] = req
    if not unique:
        return {}

    def _run(req: _ChainRequest) -> tuple[tuple[str, str], ChainLoad | None]:
        iso = req.session.isoformat()
        try:
            payload = _load_intraday_chain_safe(
                iso,
                req.symbol,
                time_of_day=req.time_of_day,
                chain_mode=req.chain_mode,
            )
            return (req.symbol, iso), payload
        except FileNotFoundError:
            return (req.symbol, iso), None
        except Exception as exc:
            log.warning(
                "aux chain load failed for %s %s: %s",
                req.symbol,
                iso,
                exc,
            )
            return (req.symbol, iso), None

    out: dict[tuple[str, str], ChainLoad] = {}
    items = list(unique.values())
    if len(items) == 1:
        key, payload = _run(items[0])
        if payload is not None:
            out[key] = payload
        return out

    with ThreadPoolExecutor(max_workers=min(6, len(items))) as pool:
        futures = [pool.submit(_run, req) for req in items]
        for fut in as_completed(futures):
            try:
                key, payload = fut.result()
            except Exception as exc:
                log.warning("parallel chain worker failed: %s", exc)
                continue
            if payload is not None:
                out[key] = payload
    return out


def _chain_from_cache(
    cache: dict[tuple[str, str], ChainLoad],
    symbol: str,
    session: date,
) -> ChainLoad | None:
    return cache.get((symbol, session.isoformat()))


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
    symbol: str | None = None,
    asof: date | None = None,
    hours_to_close: float | None = None,
    time_to_close_pct: float | None = None,
    compute_flip: bool = True,
    prior_flip: float | None = None,
) -> dict[str, Any]:
    """Terminal factor row from a 0DTE chain (full recompute — regime, levels, pin)."""
    from quant_lab.factors.positioning import max_pain, oi_concentration, put_call_ratio

    profile = compute_gex_profile(
        chain, spot, symbol=symbol, asof=asof, dte_max=1, compute_flip=compute_flip
    )
    profile_all = compute_gex_profile(
        chain, spot, symbol=symbol, asof=asof, dte_max=None, compute_flip=False
    )
    profile_vex = compute_vex_profile(chain, spot, symbol=symbol, asof=asof, dte_max=1)
    profile_vex_all = compute_vex_profile(
        chain, spot, symbol=symbol, asof=asof, dte_max=None
    )
    mp = max_pain(chain, dte_max=1)
    pcr = put_call_ratio(chain, kind="open_interest")
    oi_conc = oi_concentration(chain, dte_max=1, top_n=3)
    king = profile.king_node
    t_years = resolve_cohort_time_years(chain, dte_max=1, hours_to_close=hours_to_close)
    iv = atm_iv_from_chain(chain, spot, dte_max=1)
    em = expected_move_1sd(spot, iv, time_years=t_years, dte=1)
    pct_dte = pct_dte_cohort_of_total(profile.net_gex, profile_all.net_gex)
    pct_vex = pct_dte_cohort_of_total(profile_vex.net_vex, profile_vex_all.net_vex)
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
    flip = profile.flip_level
    if (
        not compute_flip
        and prior_flip is not None
        and np.isfinite(prior_flip)
        and not np.isfinite(flip)
    ):
        flip = float(prior_flip)
    spot_vs_king = float((spot - king) / spot * 100.0) if np.isfinite(king) and spot > 0 else float("nan")
    spot_vs_flip = (
        float((spot - flip) / spot * 100.0) if np.isfinite(flip) and spot > 0 else float("nan")
    )
    em_source = "intraday_t" if np.isfinite(t_years) and t_years < 2.0 / 365.0 else "eod_dte1"
    return {
        "spot": spot,
        "regime": regime_from_net_gex(profile.net_gex),
        "flip_dte1": flip,
        "call_wall_dte1": profile.call_wall,
        "put_wall_dte1": profile.put_wall,
        "king_dte1": king,
        "magnet_dte1": pin_result.magnet_strike,
        "floor_dte1": profile.floor_strike,
        "ceiling_dte1": profile.ceiling_strike,
        "max_pain_dte1": mp,
        "pin_score": pin,
        "expected_move_1sd": em,
        "pct_gex_dte1": pct_dte,
        "net_gex_dte1": profile.net_gex,
        "pct_vex_dte1": pct_vex,
        "net_vex_dte1": profile_vex.net_vex,
        "vanna_interp_dte1": profile_vex.interpretation,
        "pcr_oi": pcr,
        "oi_conc_dte1": oi_conc,
        "spot_vs_king_pct": spot_vs_king,
        "spot_vs_flip_pct": spot_vs_flip,
        "distance_to_magnet_pct": pin_result.distance_to_magnet_pct,
        "magnet_gex_bn": pin_result.magnet_gex_bn,
        "t_years_at_calc": t_years,
        "em_source": em_source,
    }


def _resolve_session_clock(session: date, time_of_day: str | None) -> str | None:
    if not time_of_day:
        return None
    return resolve_intraday_clock(session, time_of_day)


def _session_hours_to_close(session: date, time_of_day: str | None) -> float:
    """Trading hours remaining until 16:00 ET."""
    clock = _resolve_session_clock(session, time_of_day)
    if not clock:
        return 0.0
    from quant_lab.data.intraday_time import hours_to_close

    return hours_to_close(session, clock)


def _session_time_to_close_pct(session: date, time_of_day: str | None) -> float:
    """Legacy pct helper (0=open, 100=close)."""
    from quant_lab.data.intraday_time import SESSION_HOURS

    hours = _session_hours_to_close(session, time_of_day)
    return float(np.clip((1.0 - hours / SESSION_HOURS) * 100.0, 0.0, 100.0))


def _intraday_chain_sources() -> frozenset[str]:
    return frozenset({"live", "local", "thetadata", "thetadata_live"})


def _skip_flip_on_live_poll(chain_source: str | None) -> bool:
    """Gamma flip search is expensive — reuse prior flip on 30s live polls."""
    return chain_source in ("live", "thetadata_live")


def _refresh_row_from_intraday_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    hours_to_close: float | None,
    main_chain_source: str | None,
    prior: dict[str, Any] | None,
    symbol: str | None = None,
    asof: date | None = None,
) -> dict[str, Any]:
    """Full factor row from intraday chain; skip expensive flip on live polls."""
    skip_flip = _skip_flip_on_live_poll(main_chain_source)
    prior_flip = None
    if prior is not None and skip_flip:
        prior_flip = float(prior.get("flip_dte1", np.nan))
    return _row_from_chain(
        chain,
        spot,
        symbol=symbol,
        asof=asof,
        hours_to_close=hours_to_close,
        compute_flip=not skip_flip,
        prior_flip=prior_flip,
    )


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
            symbol=symbol,
            asof=None,
            dte_max=1,
            prev_chain=prev_chain,
            prev_spot=prev_spot,
        )
        gamma_profile = build_gamma_profile(chain, panel_spot, symbol=symbol, dte_max=1)
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


def build_session_hold_dashboard(
    symbol: str,
    asof: date,
    reason: SessionHoldReason,
    *,
    time_of_day: str = DEFAULT_INTRADAY_TIME,
    chain_mode: ChainMode = "pin",
) -> dict[str, Any]:
    """Placeholder dashboard when today's chain is not available yet (pre-open / warming up)."""
    iso = asof.isoformat()
    now_et = datetime.now(MARKET_TZ).strftime("%H:%M")
    title = session_hold_title(reason)
    detail = session_hold_message(reason)
    hint = StrategyHint(
        label="observe",
        title=title,
        summary=detail,
        structures=(),
        confidence="low",
        sources=("session",),
    )
    payload: dict[str, Any] = {
        "symbol": symbol,
        "date": iso,
        "spot": None,
        "availability": "hold",
        "regime": "undetermined",
        "levels": {
            "flip": None,
            "call_wall": None,
            "put_wall": None,
            "king": None,
            "floor": None,
            "ceiling": None,
            "max_pain": None,
            "expected_move": None,
            "expected_upper": None,
            "expected_lower": None,
        },
        "king_distance": None,
        "spot_change_pct": None,
        "metrics": {
            "pin_score": None,
            "pct_gex_dte1": None,
            "net_gex_dte1_bn": None,
            "pct_vex_dte1": None,
            "net_vex_dte1_bn": None,
            "vanna_interpretation": None,
            "pcr_oi": None,
            "oi_conc_dte1": None,
            "spot_vs_king_pct": None,
            "spot_vs_flip_pct": None,
        },
        "gate": {"should_trade": False, "reason": detail},
        "strategy": asdict(hint),
        "trinity": {"score": None, "direction": "mixed", "n_symbols": 0, "distance_pcts": {}},
        "heatmap": [],
        "gamma_profile": [],
        "panels": [],
        "pin_playbook": None,
        "pin_targets": None,
        "meta": {
            "cohort": "dte≤1 (0DTE proxy)",
            "data_mode": title,
            "data_source": "hold",
            "session_status": reason,
            "session_status_title": title,
            "session_status_message": detail,
            "session_status_detail_en": detail,
            "clock_et": now_et,
            "chain_mode": chain_mode,
            "chain_time_requested": time_of_day,
            "intraday_times_available": ["live", *list(PIN_PLAY_TIMES_ET)],
            "live_refresh_seconds": live_refresh_seconds(),
            "oi_mode": "settled",
            "volume_source": "settled",
            "live_follow": _is_live_follow_request(asof, time_of_day),
            "include_trinity": False,
            "n_strikes": 0,
        },
    }
    return json_safe(payload)


def build_dashboard(
    symbol: str,
    asof: date,
    *,
    time_of_day: str = DEFAULT_INTRADAY_TIME,
    include_trinity: bool = False,
    chain_mode: ChainMode = "pin",
) -> dict[str, Any]:
    """Full dashboard JSON for one symbol and date."""
    if not is_trading_weekday(asof):
        asof = last_trading_session_date(anchor=asof)
    iso = asof.isoformat()
    row = _load_terminal_row(symbol, asof)
    data_mode = "EoD snapshot"
    intraday_time: str | None = None
    main_chain_source: str | None = None

    chain = pd.DataFrame()
    spot = float(row.get("spot", np.nan)) if row else float("nan")
    session_hours = _session_hours_to_close(asof, time_of_day)

    compare_time = (
        DEFAULT_INTRADAY_TIME
        if time_of_day.strip().lower() == LIVE_TIME_OF_DAY
        else time_of_day
    )

    if supports_live_intraday(symbol):
        try:
            chain, spot, intraday_time, main_chain_source = _load_intraday_chain_safe(
                iso, symbol, time_of_day=time_of_day, chain_mode=chain_mode
            )
            session_hours = _session_hours_to_close(asof, intraday_time or time_of_day)
            if main_chain_source == "live":
                if _is_live_follow_request(asof, time_of_day):
                    data_mode = f"ThetaData live follow @ {intraday_time[:5]} ET"
                else:
                    data_mode = f"ThetaData snapshot @ {intraday_time[:5]} ET"
            else:
                data_mode = f"ThetaData intraday @ {intraday_time[:5]} ET"
            if (
                main_chain_source in _intraday_chain_sources()
                and not chain.empty
                and np.isfinite(spot)
            ):
                row = _refresh_row_from_intraday_chain(
                    chain,
                    spot,
                    hours_to_close=session_hours,
                    main_chain_source=main_chain_source,
                    prior=row,
                    symbol=symbol,
                    asof=asof,
                )
            elif row is None and not chain.empty and np.isfinite(spot):
                row = _row_from_chain(
                    chain, spot, symbol=symbol, asof=asof, hours_to_close=session_hours
                )
        except FileNotFoundError:
            log.info("intraday unavailable for %s %s — falling back to EoD", symbol, iso)
        except Exception as exc:
            log.warning(
                "intraday load error for %s %s: %s — falling back to EoD",
                symbol,
                iso,
                exc,
            )

    if chain.empty:
        try:
            chain, meta = load_option_chain(symbol, iso)
            spot = float(meta["spot"].iloc[0]) if not meta.empty else spot
            if not chain.empty:
                data_mode = "EoD snapshot"
                main_chain_source = "eod"
        except FileNotFoundError:
            chain = pd.DataFrame()

    if chain.empty and supports_live_intraday(symbol) and is_live_session(asof):
        hold = session_hold_reason(asof, time_of_day=time_of_day)
        if hold is not None:
            return build_session_hold_dashboard(
                symbol,
                asof,
                hold,
                time_of_day=time_of_day,
                chain_mode=chain_mode,
            )

    if row is None and chain.empty:
        raise FileNotFoundError(f"no data for {symbol} on {iso}")

    prev_date = _prev_trading_date(symbol, asof)

    chain_cache: dict[tuple[str, str], ChainLoad] = {}
    if include_trinity:
        aux_requests: list[_ChainRequest] = []
        for sym in TRINITY_SYMBOLS:
            if sym == symbol:
                continue
            aux_requests.append(_ChainRequest(sym, asof, time_of_day, "gex"))
            if prev_date is not None:
                aux_requests.append(_ChainRequest(sym, prev_date, compare_time, "gex"))
        chain_cache = _parallel_load_chains(aux_requests)

    if (
        not chain.empty
        and np.isfinite(spot)
        and main_chain_source in _intraday_chain_sources()
    ):
        row = _refresh_row_from_intraday_chain(
            chain,
            spot,
            hours_to_close=session_hours,
            main_chain_source=main_chain_source,
            prior=row,
            symbol=symbol,
            asof=asof,
        )
    elif row is None and not chain.empty and np.isfinite(spot):
        row = _row_from_chain(
            chain, spot, symbol=symbol, asof=asof, hours_to_close=session_hours
        )

    prev_row_main = _load_terminal_row(symbol, prev_date) if prev_date else None
    prev_chain_main: pd.DataFrame | None = None
    prev_spot_main: float | None = None
    if prev_date is not None:
        try:
            prev_chain_main, prev_spot_main = _load_chain_safe(symbol, prev_date.isoformat())
        except FileNotFoundError:
            pass

    roc_prev_chain: pd.DataFrame | None = None
    roc_prev_spot: float | None = None
    if prev_chain_main is not None and main_chain_source not in ("live", "local"):
        roc_prev_chain = prev_chain_main
        roc_prev_spot = prev_spot_main

    heatmap: list[dict[str, float | None]] = []
    cohort_fallback = False
    gamma_profile: list[dict[str, float]] = []
    if not chain.empty:
        heatmap, cohort_fallback = build_strike_heatmap(
            chain,
            spot,
            symbol=symbol,
            asof=asof,
            dte_max=1,
            prev_chain=roc_prev_chain,
            prev_spot=roc_prev_spot,
        )
        gamma_profile = build_gamma_profile(chain, spot, symbol=symbol, asof=asof, dte_max=1)

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
    panels: list[dict[str, Any]] = []
    trinity_inputs: dict[str, tuple[float, float]] = {}
    trinity_live_count = 0
    for sym in TRINITY_SYMBOLS:
        sym_row = _load_terminal_row(sym, asof) if sym != symbol else row
        sym_prev_row = _load_terminal_row(sym, prev_date) if prev_date else None
        sym_chain: pd.DataFrame | None = None
        sym_spot = float("nan")
        sym_data_source = "unavailable"
        sym_data_mode = ""
        sym_intraday_time: str | None = None

        if sym == symbol:
            sym_chain = chain if not chain.empty else None
            sym_spot = spot
            if sym_chain is not None and main_chain_source:
                sym_data_source, sym_data_mode = _intraday_data_labels(
                    main_chain_source, intraday_time or time_of_day
                )
                sym_intraday_time = intraday_time[:5] if intraday_time else None
            elif sym_chain is not None:
                sym_data_source, sym_data_mode = "eod", "EoD close"
        elif include_trinity:
            loaded = _chain_from_cache(chain_cache, sym, asof)
            if loaded is not None:
                sym_chain, sym_spot, time_used, chain_source = loaded
                sym_data_source, sym_data_mode = _intraday_data_labels(chain_source, time_used)
                sym_intraday_time = time_used[:5] if time_used else None
            else:
                sym_data_source, sym_data_mode = _unavailable_panel_meta(sym, asof)
        else:
            sym_chain = None
            if sym_row is not None:
                sym_spot = float(sym_row.get("spot", np.nan))
                sym_data_source, sym_data_mode = "eod", "EoD snapshot"
            else:
                sym_data_source, sym_data_mode = _unavailable_panel_meta(sym, asof)

        if sym_data_source == "thetadata_live":
            trinity_live_count += 1
        sym_prev_chain: pd.DataFrame | None = prev_chain_main if sym == symbol else None
        sym_prev_spot: float | None = prev_spot_main if sym == symbol else None
        if sym != symbol and prev_date is not None and include_trinity:
            prev_loaded = _chain_from_cache(chain_cache, sym, prev_date)
            if prev_loaded is not None:
                sym_prev_chain, sym_prev_spot, _, _ = prev_loaded
            elif not supports_live_intraday(sym):
                try:
                    sym_prev_chain, sym_prev_spot = _load_chain_safe(sym, prev_date.isoformat())
                except FileNotFoundError:
                    sym_prev_chain = None
        if (
            sym_chain is not None
            and not sym_chain.empty
            and np.isfinite(sym_spot)
            and sym_data_source in _intraday_chain_sources()
        ):
            sym_row = _refresh_row_from_intraday_chain(
                sym_chain,
                sym_spot,
                hours_to_close=session_hours,
                main_chain_source=sym_data_source,
                prior=sym_row,
                symbol=sym,
                asof=asof,
            )
        elif sym_row is None and sym_chain is not None and not sym_chain.empty and np.isfinite(sym_spot):
            sym_row = _row_from_chain(
                sym_chain, sym_spot, symbol=sym, asof=asof, hours_to_close=session_hours
            )
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
        king_for_trinity = float(sym_row.get("king_dte1", np.nan)) if sym_row else float("nan")
        panel_spot_for_trinity = float(sym_row.get("spot", sym_spot)) if sym_row else sym_spot
        if panel.available and np.isfinite(panel.king) and np.isfinite(panel.spot):
            key = sym.replace("^", "")
            trinity_inputs[key] = (panel.spot, panel.king)
        elif (
            not include_trinity
            and sym_row is not None
            and np.isfinite(king_for_trinity)
            and np.isfinite(panel_spot_for_trinity)
        ):
            key = sym.replace("^", "")
            trinity_inputs[key] = (panel_spot_for_trinity, king_for_trinity)

    align = trinity_from_kings(
        spy=trinity_inputs.get("SPY"),
        spx=trinity_inputs.get("SPX"),
        qqq=trinity_inputs.get("QQQ"),
    )

    em = float(row.get("expected_move_1sd", np.nan))
    magnet_level = _f(row.get("magnet_dte1"))
    if magnet_level is None:
        magnet_level = _f(row.get("king_dte1"))
    gex_inputs = resolve_gex_inputs(symbol, asof=asof)
    meta_warnings: list[str] = []
    if cohort_fallback:
        meta_warnings.append("Cohort fallback: dte≤1 filter empty; full chain used.")
    flip_result = (
        compute_flip_result_for_chain(
            chain,
            spot,
            symbol=symbol,
            asof=asof,
            gex_inputs=gex_inputs,
            dte_max=1,
        )
        if not chain.empty
        else None
    )
    levels = {
        "flip": _f(row.get("flip_dte1")),
        "call_wall": _f(row.get("call_wall_dte1")),
        "put_wall": _f(row.get("put_wall_dte1")),
        "king": _f(row.get("king_dte1")),
        "magnet_strike": magnet_level,
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
        magnet_strike=levels.get("magnet_strike"),
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

    live_follow = _is_live_follow_request(asof, time_of_day)
    live_poll = (
        live_chain_poll_meta(symbol, asof, time_of_day, chain_mode=chain_mode)
        if live_follow and main_chain_source == "live"
        else None
    )
    t_diag = diagnose_cohort_time_to_expiry(
        chain if not chain.empty else pd.DataFrame(),
        dte_max=1,
        hours_to_close=session_hours,
    )
    flip_conf = flip_result.confidence if flip_result is not None else None
    live_quality = assess_live_pin_quality(
        is_live_poll=live_follow,
        live_follow=live_follow,
        data_source=(
            "thetadata_live"
            if main_chain_source == "live"
            else ("thetadata" if "ThetaData" in data_mode else "eod")
        ),
        cohort_fallback=cohort_fallback,
        t_diag=t_diag,
        n_strikes=len(heatmap),
        flip_confidence=flip_conf,
        chain_poll=live_poll,
        hours_to_close=session_hours,
        main_chain_source=main_chain_source,
    )
    if live_quality is not None and pin_targets is not None:
        tier, detail = cap_pin_reliability(
            pin_targets["pin_reliability"],  # type: ignore[arg-type]
            str(pin_targets.get("pin_reliability_detail", "")),
            live_quality,
        )
        pin_targets["pin_reliability"] = tier
        pin_targets["pin_reliability_detail"] = detail
        pin_targets["live_data_quality"] = live_pin_quality_to_dict(live_quality)

    magnet_shift = None
    if _is_live_follow_request(asof, time_of_day) and main_chain_source == "live":
        magnet_shift = record_magnet_shift(symbol, iso, levels["king"])

    ds_meta = (
        "thetadata_live"
        if "live" in data_mode.lower()
        else ("thetadata" if "ThetaData" in data_mode else "eod")
    )
    model_metadata = build_model_metadata(
        gex_inputs=gex_inputs,
        chain=chain,
        spot=spot,
        hours_to_close=session_hours,
        data_source=ds_meta,
        oi_mode=pos_meta.get("oi_mode"),
        flip_result=flip_result,
        extra_warnings=meta_warnings or None,
        live_pin_quality=live_pin_quality_to_dict(live_quality),
        live_chain_poll=live_poll,
    )

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
            "gex_model": gex_inputs.model,
            "risk_free_rate": _f(gex_inputs.r),
            "dividend_yield": _f(gex_inputs.q),
            "risk_free_rate_source": gex_inputs.r_source,
            "dividend_yield_source": gex_inputs.q_source,
            "data_mode": data_mode,
            "data_source": ds_meta,
            "n_strikes": len(heatmap),
            "intraday_time": intraday_time[:5] if intraday_time else None,
            "hours_to_close": _f(session_hours),
            "chain_clock_used": (
                str(live_poll.get("chain_time_used"))
                if live_poll and live_poll.get("chain_time_used")
                else (intraday_time[:8] if intraday_time else None)
            ),
            "chain_time_requested": chain_time_requested,
            "intraday_times_available": ["live", *list(PIN_PLAY_TIMES_ET)],
            "quote_granularity": "1m" if main_chain_source in ("live", "local", "thetadata") else None,
            "live_refresh_seconds": refresh_secs,
            "oi_mode": pos_meta["oi_mode"],
            "volume_source": pos_meta["volume_source"],
            "live_follow": (
                _is_live_follow_request(asof, time_of_day)
                and main_chain_source == "live"
            ),
            "include_trinity": include_trinity,
            "chain_mode": chain_mode,
            "trinity_live_panels": trinity_live_count,
            "server_pulled_at": datetime.now(timezone.utc).isoformat(),
            "magnet_shift": magnet_shift is not None,
            "magnet_previous": _f(magnet_shift.previous) if magnet_shift else None,
            "magnet_delta_pts": _f(magnet_shift.delta_pts) if magnet_shift else None,
            "pin_score_model": PIN_SCORE_MODEL_VERSION,
            "t_years_at_calc": _f(row.get("t_years_at_calc")),
            "em_source": row.get("em_source"),
            "model_metadata": model_metadata,
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
