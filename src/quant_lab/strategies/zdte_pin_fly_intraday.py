"""Intraday 0DTE iron butterfly @ King (Phase 4 / Pin Play).

Uses ThetaData SPXW intraday chains (``dte=0``) with entry @ 13:00 ET and
path-dependent exits per ``docs/PIN_PLAY_SPEC.md`` §3.3:

- **50% max profit** on mid or BS mark
- **2× credit** stop
- **EM / gamma-flip** spot stop (when SPX 1m available)
- **14:00** thesis exit
- **15:30** force flat (chain mids when available)

Limitations (document in reports):

- Without SPX 1m, EM/flip and 14:00 stops use 15:30 chain marks only.
- ``expected_move_1sd`` uses ATM IV × remaining session time (not EoD dte=1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.backtest.bs76 import mark_price
from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_time import (
    SESSION_HOURS,
    hours_to_close,
    intraday_time_to_expiry_years,
    session_datetime,
)
from quant_lab.data.thetadata_storage import load_parquet, spx_price_1m_path
from quant_lab.factors.gex import compute_gex_profile, net_gex_bn_per_1pct, pct_dte_cohort_of_total
from quant_lab.factors.positioning import atm_iv_from_chain, max_pain, oi_concentration, pin_score
from quant_lab.factors.regime import regime_from_net_gex
from quant_lab.strategies.zdte_ic_eod import (
    CONTRACT_MULTIPLIER,
    DEFAULT_COMMISSION_PER_CONTRACT,
    _mid_price,
    select_contract,
)
from quant_lab.strategies.zdte_pin_fly_eod import (
    FlyCenterSource,
    iron_butterfly_entry_credit,
    resolve_fly_center,
    resolve_fly_strikes,
    wing_width_from_expected_move,
)

ExitReason = Literal[
    "no_entry",
    "profit_50pct",
    "stop_2x_credit",
    "stop_em_flip",
    "time_1400",
    "time_1530",
]

DEFAULT_ENTRY_TIME = "13:00:00"
DEFAULT_EXIT_TIME = "15:30:00"
THESIS_EXIT_TIME = "14:00:00"
INTRADAY_DTE = 0


@dataclass(frozen=True)
class PinFlyIntradayTrade:
    session_date: str
    entry_time: str
    exit_time: str
    exit_reason: ExitReason
    center_strike: float
    long_call: float
    long_put: float
    wing_width: float
    entry_credit: float
    exit_cost: float
    pnl_per_contract: float
    pin_score: float
    regime: str
    pct_gex_dte1: float
    center_source: FlyCenterSource
    king_dte1: float
    expected_move_1sd: float
    skip_reason: str = ""


def expected_move_intraday(
    spot: float,
    atm_iv: float,
    *,
    session_date: date,
    time_of_day: str,
) -> float:
    """1σ expected move using remaining session fraction (0DTE)."""
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(atm_iv) or atm_iv <= 0:
        return float("nan")
    t_years = intraday_time_to_expiry_years(session_date, time_of_day)
    if t_years <= 0:
        return float("nan")
    return float(spot * atm_iv * np.sqrt(t_years))


def intraday_context_from_chain(
    chain: pd.DataFrame,
    *,
    spot: float,
    session_date: date,
    time_of_day: str,
) -> dict[str, float | str]:
    """Pin Play signal fields from a built 0DTE intraday chain."""
    profile = compute_gex_profile(chain, spot, dte_max=1)
    profile_all = compute_gex_profile(chain, spot, dte_max=None)
    mp = max_pain(chain, dte_max=1)
    oi_conc = oi_concentration(chain, dte_max=1, top_n=3)
    king = profile.king_node
    hours_left = hours_to_close(session_date, time_of_day)
    time_to_close_pct = float(max(0.0, min(100.0, hours_left / SESSION_HOURS * 100.0)))
    pin = pin_score(
        spot=spot,
        magnet_strike=king if np.isfinite(king) else mp,
        oi_concentration_top3=oi_conc if np.isfinite(oi_conc) else 0.0,
        net_gex_bn_per_1pct=net_gex_bn_per_1pct(profile.net_gex),
        time_to_close_pct=time_to_close_pct,
    )
    iv = atm_iv_from_chain(chain, spot, dte=INTRADAY_DTE)
    em = expected_move_intraday(spot, iv, session_date=session_date, time_of_day=time_of_day)
    return {
        "regime": regime_from_net_gex(profile.net_gex),
        "king_dte1": float(king),
        "max_pain_dte1": float(mp),
        "flip_dte1": float(profile.flip_level),
        "call_wall_dte1": float(profile.call_wall),
        "put_wall_dte1": float(profile.put_wall),
        "pin_score": float(pin),
        "expected_move_1sd": float(em),
        "pct_gex_dte1": float(pct_dte_cohort_of_total(profile.net_gex, profile_all.net_gex)),
        "net_gex_dte1": float(profile.net_gex),
    }


def iron_butterfly_mark_to_close(
    chain: pd.DataFrame,
    *,
    center: float,
    long_call: float,
    long_put: float,
    dte: int = INTRADAY_DTE,
) -> float:
    """Debit per share to buy back a short iron butterfly at mids."""
    return iron_butterfly_entry_credit(
        chain,
        center=center,
        long_call=long_call,
        long_put=long_put,
        dte=dte,
    )


def _leg_iv(chain: pd.DataFrame, strike: float, right: str, *, dte: int = INTRADAY_DTE) -> float:
    row = select_contract(chain, strike=strike, right=right, dte=dte)
    if row is None:
        return float("nan")
    iv = float(row.get("implied_volatility", np.nan))
    if np.isfinite(iv) and 0.05 <= iv <= 3.0:
        return iv
    return float("nan")


def iron_butterfly_mark_bs(
    chain: pd.DataFrame,
    *,
    center: float,
    long_call: float,
    long_put: float,
    spot: float,
    time_to_expiry_years: float,
    dte: int = INTRADAY_DTE,
) -> float:
    """BS mark debit to close fly when chain mids unavailable."""
    legs = (
        (center, "C"),
        (center, "P"),
        (long_call, "C"),
        (long_put, "P"),
    )
    signs = (+1, +1, -1, -1)  # cost = long shorts - long longs
    total = 0.0
    fallback_iv = atm_iv_from_chain(chain, spot, dte=dte)
    for (strike, right), sign in zip(legs, signs, strict=True):
        iv = _leg_iv(chain, strike, right, dte=dte)
        if not np.isfinite(iv):
            iv = fallback_iv
        px = mark_price(spot, strike, right, time_to_expiry_years, iv)
        if not np.isfinite(px):
            return float("nan")
        total += sign * px
    return float(total)


def _round_trip_fees(commission_per_contract: float) -> float:
    return 8.0 * commission_per_contract


def unrealized_pnl_per_contract(
    *,
    entry_credit: float,
    exit_mark: float,
    commission_per_contract: float,
) -> float:
    """Mark-to-market PnL for short iron fly (per 1-lot)."""
    if not np.isfinite(exit_mark):
        return float("nan")
    return (entry_credit - exit_mark) * CONTRACT_MULTIPLIER - _round_trip_fees(commission_per_contract)


def spot_stop_triggered(
    *,
    spot: float,
    spot_entry: float,
    king: float,
    flip: float,
    expected_move_1sd: float,
) -> bool:
    """EM or gamma-flip breach stop (Pin Play §3.3)."""
    if np.isfinite(flip):
        if spot_entry >= flip and spot < flip:
            return True
        if spot_entry <= flip and spot > flip:
            return True
    if np.isfinite(expected_move_1sd) and np.isfinite(king):
        if abs(spot - king) > expected_move_1sd:
            return True
    return False


def load_spx_1m_session(session_date: date) -> pd.Series:
    """SPX 1m close prices indexed by ET timestamp."""
    path = spx_price_1m_path(session_date)
    if not path.is_file():
        return pd.Series(dtype="float64")
    bars = load_parquet(path)
    if bars.empty or "timestamp" not in bars.columns or "price" not in bars.columns:
        return pd.Series(dtype="float64")
    ts = pd.to_datetime(bars["timestamp"])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(MARKET_TZ)
    else:
        ts = ts.dt.tz_convert(MARKET_TZ)
    out = pd.Series(bars["price"].astype("float64").values, index=ts)
    return out.sort_index()


def _mark_at_time(
    chain: pd.DataFrame,
    *,
    center: float,
    long_call: float,
    long_put: float,
    spot: float,
    session_date: date,
    time_of_day: str,
) -> float:
    mid = iron_butterfly_mark_to_close(
        chain,
        center=center,
        long_call=long_call,
        long_put=long_put,
    )
    if np.isfinite(mid):
        return mid
    t_years = intraday_time_to_expiry_years(session_date, time_of_day)
    return iron_butterfly_mark_bs(
        chain,
        center=center,
        long_call=long_call,
        long_put=long_put,
        spot=spot,
        time_to_expiry_years=t_years,
    )


def simulate_pin_fly_intraday_session(
    chain_entry: pd.DataFrame,
    *,
    session_date: date,
    spot_entry: float,
    chain_exit: pd.DataFrame | None = None,
    spot_path: pd.Series | None = None,
    entry_time: str = DEFAULT_ENTRY_TIME,
    exit_time: str = DEFAULT_EXIT_TIME,
    commission_per_contract: float = DEFAULT_COMMISSION_PER_CONTRACT,
    require_long_gamma: bool = True,
) -> PinFlyIntradayTrade | None:
    """Simulate one Pin Play session from 13:00 entry through intraday exits."""
    ctx = intraday_context_from_chain(
        chain_entry,
        spot=spot_entry,
        session_date=session_date,
        time_of_day=entry_time,
    )
    regime = str(ctx["regime"])
    if require_long_gamma and regime == "short_gamma":
        return None

    king = float(ctx["king_dte1"])
    max_pain = float(ctx["max_pain_dte1"])
    resolved = resolve_fly_center(
        chain_entry,
        spot=spot_entry,
        center_mode="king",
        king_dte1=king,
        max_pain_dte1=max_pain,
        dte=INTRADAY_DTE,
    )
    if resolved is None:
        return None
    center, center_source = resolved

    wing_width = wing_width_from_expected_move(
        float(ctx["expected_move_1sd"]),
        spx_notional=True,
    )
    wings = resolve_fly_strikes(
        chain_entry,
        center=center,
        wing_width=wing_width,
        dte=INTRADAY_DTE,
    )
    if wings is None:
        return None
    long_call, long_put = wings

    entry_credit = iron_butterfly_entry_credit(
        chain_entry,
        center=center,
        long_call=long_call,
        long_put=long_put,
        dte=INTRADAY_DTE,
    )
    if not np.isfinite(entry_credit) or entry_credit <= 0:
        return None

    profit_target = 0.5 * entry_credit * CONTRACT_MULTIPLIER
    stop_loss = 2.0 * entry_credit * CONTRACT_MULTIPLIER
    flip = float(ctx["flip_dte1"])
    em = float(ctx["expected_move_1sd"])

    if spot_path is None or spot_path.empty:
        spot_path = load_spx_1m_session(session_date)

    entry_dt = session_datetime(session_date, entry_time)
    thesis_dt = session_datetime(session_date, THESIS_EXIT_TIME)
    exit_dt = session_datetime(session_date, exit_time)

    exit_reason: ExitReason = "time_1530"
    exit_mark = float("nan")
    exit_at = exit_time

    path = spot_path[(spot_path.index >= entry_dt) & (spot_path.index <= exit_dt)]
    for ts, spot in path.items():
        t_str = ts.strftime("%H:%M:%S")
        t_years = intraday_time_to_expiry_years(session_date, t_str)
        mark = iron_butterfly_mark_bs(
            chain_entry,
            center=center,
            long_call=long_call,
            long_put=long_put,
            spot=float(spot),
            time_to_expiry_years=t_years,
        )
        pnl = unrealized_pnl_per_contract(
            entry_credit=entry_credit,
            exit_mark=mark,
            commission_per_contract=commission_per_contract,
        )
        if not np.isfinite(pnl):
            continue
        if spot_stop_triggered(
            spot=float(spot),
            spot_entry=spot_entry,
            king=king,
            flip=flip,
            expected_move_1sd=em,
        ):
            exit_reason = "stop_em_flip"
            exit_mark = mark
            exit_at = t_str
            break
        if pnl >= profit_target:
            exit_reason = "profit_50pct"
            exit_mark = mark
            exit_at = t_str
            break
        if pnl <= -stop_loss:
            exit_reason = "stop_2x_credit"
            exit_mark = mark
            exit_at = t_str
            break
        if ts >= thesis_dt and exit_reason == "time_1530":
            exit_reason = "time_1400"
            exit_mark = mark
            exit_at = THESIS_EXIT_TIME
            break

    if not np.isfinite(exit_mark):
        spot_exit = float(path.iloc[-1]) if not path.empty else spot_entry
        if chain_exit is not None and not chain_exit.empty:
            exit_mark = _mark_at_time(
                chain_exit,
                center=center,
                long_call=long_call,
                long_put=long_put,
                spot=spot_exit,
                session_date=session_date,
                time_of_day=exit_time,
            )
            exit_reason = "time_1530"
            exit_at = exit_time
        else:
            t_years = intraday_time_to_expiry_years(session_date, exit_time)
            exit_mark = iron_butterfly_mark_bs(
                chain_entry,
                center=center,
                long_call=long_call,
                long_put=long_put,
                spot=spot_exit,
                time_to_expiry_years=t_years,
            )
            exit_reason = "time_1530"
            exit_at = exit_time

    pnl = unrealized_pnl_per_contract(
        entry_credit=entry_credit,
        exit_mark=exit_mark,
        commission_per_contract=commission_per_contract,
    )
    if not np.isfinite(pnl):
        return None

    return PinFlyIntradayTrade(
        session_date=session_date.isoformat(),
        entry_time=entry_time,
        exit_time=exit_at,
        exit_reason=exit_reason,
        center_strike=center,
        long_call=long_call,
        long_put=long_put,
        wing_width=wing_width,
        entry_credit=entry_credit,
        exit_cost=float(exit_mark),
        pnl_per_contract=float(pnl),
        pin_score=float(ctx["pin_score"]),
        regime=regime,
        pct_gex_dte1=float(ctx["pct_gex_dte1"]),
        center_source=center_source,
        king_dte1=king,
        expected_move_1sd=em,
    )
