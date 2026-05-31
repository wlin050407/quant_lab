"""EoD-approximate 0DTE iron butterfly @ King (Phase 3f / Pin Play).

Industry-aligned policy (``docs/PIN_PLAY_SPEC.md``):

1. **Structure** — short iron butterfly on **dte=1** (next-session 0DTE proxy).
2. **Center** — ``king_dte1`` (fallback ``max_pain_dte1``); compare vs ``spot`` control.
3. **Wings** — ``max(1.5, min(3.0, round(expected_move_1sd)))`` on SPY
   (SPX 15–30pt scaled ÷10).
4. **Signal** — EoD *t-1* → enter at signal mids → exit intrinsic at close *t*.

Still an approximation: no intraday 13:00 entry, 50% profit take, or credit filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.strategies.zdte_ic_eod import (
    CONTRACT_MULTIPLIER,
    DEFAULT_COMMISSION_PER_CONTRACT,
    RegimeFilter,
    _mid_price,
    _nearest_strike,
    credit_spread_entry_credit,
    credit_spread_exit_cost,
    iron_condor_pnl,
    passes_regime_filter,
    select_contract,
)

CenterMode = Literal["king", "spot"]
FlyCenterSource = Literal["king", "max_pain", "spot"]

SPY_WING_MIN = 1.5
SPY_WING_MAX = 3.0
SPX_WING_MIN = 15.0
SPX_WING_MAX = 30.0
DEFAULT_SPY_WING_WIDTH = 2.0


@dataclass(frozen=True)
class PinFlyTrade:
    signal_date: str
    trade_date: str
    center_strike: float
    long_call: float
    long_put: float
    wing_width: float
    entry_credit: float
    exit_cost: float
    pnl_per_contract: float
    net_gex_bs: float
    regime: str
    center_source: FlyCenterSource
    center_mode: CenterMode


def wing_width_from_expected_move(
    expected_move_1sd: float,
    *,
    spx_notional: bool = False,
) -> float:
    """Wing half-width from 1σ expected move (Pin Play spec)."""
    if not np.isfinite(expected_move_1sd) or expected_move_1sd <= 0:
        return DEFAULT_SPY_WING_WIDTH if not spx_notional else SPX_WING_MIN

    w_min = SPX_WING_MIN if spx_notional else SPY_WING_MIN
    w_max = SPX_WING_MAX if spx_notional else SPY_WING_MAX
    return float(max(w_min, min(w_max, round(expected_move_1sd))))


def resolve_fly_center(
    chain: pd.DataFrame,
    *,
    spot: float,
    center_mode: CenterMode,
    king_dte1: float,
    max_pain_dte1: float,
    dte: int = 1,
) -> tuple[float, FlyCenterSource] | None:
    """Pick butterfly body strike from King / max pain / spot."""
    if center_mode == "spot":
        target = spot
        source: FlyCenterSource = "spot"
    else:
        if np.isfinite(king_dte1):
            target = king_dte1
            source = "king"
        elif np.isfinite(max_pain_dte1):
            target = max_pain_dte1
            source = "max_pain"
        else:
            return None

    center = _nearest_strike(
        chain,
        target=target,
        right="C",
        dte=dte,
        direction="nearest",
    )
    if center is None:
        return None
    if select_contract(chain, strike=center, right="P", dte=dte) is None:
        return None
    return float(center), source


def resolve_fly_strikes(
    chain: pd.DataFrame,
    *,
    center: float,
    wing_width: float,
    dte: int = 1,
) -> tuple[float, float] | None:
    """Return (long_call, long_put) for iron fly centered at ``center``."""
    long_call = _nearest_strike(
        chain,
        target=center + wing_width,
        right="C",
        dte=dte,
        direction="at_or_above",
    )
    long_put = _nearest_strike(
        chain,
        target=center - wing_width,
        right="P",
        dte=dte,
        direction="at_or_below",
    )
    if long_call is None or long_put is None:
        return None
    if long_call <= center or long_put >= center:
        return None
    if (
        select_contract(chain, strike=long_call, right="C", dte=dte) is None
        or select_contract(chain, strike=long_put, right="P", dte=dte) is None
    ):
        return None
    return float(long_call), float(long_put)


def iron_butterfly_entry_credit(
    chain: pd.DataFrame,
    *,
    center: float,
    long_call: float,
    long_put: float,
    dte: int = 1,
) -> float:
    """Net credit per share for short iron butterfly."""
    sc = select_contract(chain, strike=center, right="C", dte=dte)
    sp = select_contract(chain, strike=center, right="P", dte=dte)
    lc = select_contract(chain, strike=long_call, right="C", dte=dte)
    lp = select_contract(chain, strike=long_put, right="P", dte=dte)
    if sc is None or sp is None or lc is None or lp is None:
        return float("nan")

    short_call_mid = _mid_price(sc)
    short_put_mid = _mid_price(sp)
    long_call_mid = _mid_price(lc)
    long_put_mid = _mid_price(lp)
    if not all(np.isfinite(x) for x in (short_call_mid, short_put_mid, long_call_mid, long_put_mid)):
        return float("nan")
    return float(short_call_mid + short_put_mid - long_call_mid - long_put_mid)


def iron_butterfly_pnl(
    *,
    spot_exit: float,
    center: float,
    long_call: float,
    long_put: float,
    entry_credit: float,
    commission_per_contract: float,
) -> tuple[float, float]:
    """Return (exit_cost, pnl_per_contract) for short iron butterfly at expiry."""
    return iron_condor_pnl(
        spot_exit=spot_exit,
        short_call=center,
        long_call=long_call,
        short_put=center,
        long_put=long_put,
        entry_credit=entry_credit,
        commission_per_contract=commission_per_contract,
    )


def iron_butterfly_pnl_hand(
    *,
    spot_exit: float,
    center: float,
    wing_width: float,
    entry_credit: float,
    commission_per_contract: float = 0.0,
) -> tuple[float, float]:
    """Hand-compute iron fly PnL without a chain (tests)."""
    long_call = center + wing_width
    long_put = center - wing_width
    return iron_butterfly_pnl(
        spot_exit=spot_exit,
        center=center,
        long_call=long_call,
        long_put=long_put,
        entry_credit=entry_credit,
        commission_per_contract=commission_per_contract,
    )


def simulate_pin_fly_trade(
    chain_signal: pd.DataFrame,
    *,
    signal_date: str,
    trade_date: str,
    spot_signal: float,
    spot_exit: float,
    net_gex_bs: float,
    center_mode: CenterMode,
    king_dte1: float = float("nan"),
    max_pain_dte1: float = float("nan"),
    expected_move_1sd: float = float("nan"),
    wing_width: float | None = None,
    regime_filter: RegimeFilter = "none",
    commission_per_contract: float = DEFAULT_COMMISSION_PER_CONTRACT,
    spx_notional: bool = False,
) -> PinFlyTrade | None:
    """Simulate one short iron butterfly from signal EoD to next close."""
    if not passes_regime_filter(net_gex_bs, regime_filter=regime_filter):
        return None

    resolved_center = resolve_fly_center(
        chain_signal,
        spot=spot_signal,
        center_mode=center_mode,
        king_dte1=king_dte1,
        max_pain_dte1=max_pain_dte1,
    )
    if resolved_center is None:
        return None
    center, center_source = resolved_center

    width = (
        wing_width
        if wing_width is not None
        else wing_width_from_expected_move(expected_move_1sd, spx_notional=spx_notional)
    )
    wings = resolve_fly_strikes(chain_signal, center=center, wing_width=width, dte=1)
    if wings is None:
        return None
    long_call, long_put = wings

    entry_credit = iron_butterfly_entry_credit(
        chain_signal,
        center=center,
        long_call=long_call,
        long_put=long_put,
        dte=1,
    )
    if not np.isfinite(entry_credit) or entry_credit <= 0:
        return None

    exit_cost, pnl = iron_butterfly_pnl(
        spot_exit=spot_exit,
        center=center,
        long_call=long_call,
        long_put=long_put,
        entry_credit=entry_credit,
        commission_per_contract=commission_per_contract,
    )
    regime = "long_gamma" if net_gex_bs > 0 else "short_gamma"

    return PinFlyTrade(
        signal_date=signal_date,
        trade_date=trade_date,
        center_strike=center,
        long_call=long_call,
        long_put=long_put,
        wing_width=width,
        entry_credit=entry_credit,
        exit_cost=exit_cost,
        pnl_per_contract=pnl,
        net_gex_bs=net_gex_bs,
        regime=regime,
        center_source=center_source,
        center_mode=center_mode,
    )
