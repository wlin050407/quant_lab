"""EoD-approximate long call butterfly @ King (Pin Play buyer leg).

**Long call butterfly** (debit): buy ``K-W`` call, sell ``2× K`` call, buy ``K+W`` call.
Max payoff when spot pins at body ``K`` at expiry — aligned with Phase 3e King
proximity evidence.  **Not** the mirror of short iron fly (long iron fly loses
at the pin).

Signal at EoD *t-1* → pay debit at signal mids → hold through session *t* →
exit at intrinsic with underlying **close** on *t*.
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
    passes_regime_filter,
    select_contract,
)
from quant_lab.strategies.zdte_pin_fly_eod import (
    CenterMode,
    FlyCenterSource,
    resolve_fly_center,
    resolve_fly_strikes,
    wing_width_from_expected_move,
)

LEGS_PER_BUTTERFLY = 4


@dataclass(frozen=True)
class LongFlyTrade:
    signal_date: str
    trade_date: str
    center_strike: float
    lower_call: float
    upper_call: float
    wing_width: float
    entry_debit: float
    exit_value: float
    pnl_per_contract: float
    net_gex_bs: float
    regime: str
    center_source: FlyCenterSource
    center_mode: CenterMode
    spot_vs_center_pct: float


def long_call_butterfly_entry_debit(
    chain: pd.DataFrame,
    *,
    lower_call: float,
    center: float,
    upper_call: float,
    dte: int = 1,
) -> float:
    """Net debit per share for one long call butterfly."""
    lc = select_contract(chain, strike=lower_call, right="C", dte=dte)
    mc = select_contract(chain, strike=center, right="C", dte=dte)
    uc = select_contract(chain, strike=upper_call, right="C", dte=dte)
    if lc is None or mc is None or uc is None:
        return float("nan")

    lower_mid = _mid_price(lc)
    center_mid = _mid_price(mc)
    upper_mid = _mid_price(uc)
    if not all(np.isfinite(x) for x in (lower_mid, center_mid, upper_mid)):
        return float("nan")
    return float(lower_mid - 2.0 * center_mid + upper_mid)


def long_call_butterfly_expiry_value(
    spot: float,
    *,
    lower_call: float,
    center: float,
    upper_call: float,
) -> float:
    """Intrinsic value per share at expiry."""
    lower = max(spot - lower_call, 0.0)
    body = max(spot - center, 0.0)
    upper = max(spot - upper_call, 0.0)
    return float(lower - 2.0 * body + upper)


def long_call_butterfly_pnl(
    *,
    spot_exit: float,
    lower_call: float,
    center: float,
    upper_call: float,
    entry_debit: float,
    commission_per_contract: float,
) -> tuple[float, float]:
    """Return (exit_value, pnl_per_contract) for long call butterfly at expiry."""
    exit_value = long_call_butterfly_expiry_value(
        spot_exit,
        lower_call=lower_call,
        center=center,
        upper_call=upper_call,
    )
    fees = float(LEGS_PER_BUTTERFLY * 2 * commission_per_contract)
    pnl = (exit_value - entry_debit) * CONTRACT_MULTIPLIER - fees
    return exit_value, pnl


def long_call_butterfly_pnl_hand(
    *,
    spot_exit: float,
    center: float,
    wing_width: float,
    entry_debit: float,
    commission_per_contract: float = 0.0,
) -> tuple[float, float]:
    """Hand-compute long call butterfly PnL (tests)."""
    return long_call_butterfly_pnl(
        spot_exit=spot_exit,
        lower_call=center - wing_width,
        center=center,
        upper_call=center + wing_width,
        entry_debit=entry_debit,
        commission_per_contract=commission_per_contract,
    )


def spot_vs_center_pct(spot: float, center: float) -> float:
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(center):
        return float("nan")
    return float((spot - center) / spot * 100.0)


def simulate_long_fly_trade(
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
    min_spot_center_dist_pct: float = 0.0,
    max_debit_to_wing_ratio: float | None = None,
) -> LongFlyTrade | None:
    """Simulate one long call butterfly from signal EoD to next close."""
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

    dist_pct = abs(spot_vs_center_pct(spot_signal, center))
    if np.isfinite(min_spot_center_dist_pct) and dist_pct < min_spot_center_dist_pct:
        return None

    width = (
        wing_width
        if wing_width is not None
        else wing_width_from_expected_move(expected_move_1sd, spx_notional=spx_notional)
    )
    wings = resolve_fly_strikes(chain_signal, center=center, wing_width=width, dte=1)
    if wings is None:
        return None
    upper_call, _long_put_unused = wings
    lower_call = center - width

    if select_contract(chain_signal, strike=lower_call, right="C", dte=1) is None:
        return None

    entry_debit = long_call_butterfly_entry_debit(
        chain_signal,
        lower_call=lower_call,
        center=center,
        upper_call=upper_call,
        dte=1,
    )
    if not np.isfinite(entry_debit) or entry_debit <= 0:
        return None
    if max_debit_to_wing_ratio is not None and entry_debit > width * max_debit_to_wing_ratio:
        return None

    exit_value, pnl = long_call_butterfly_pnl(
        spot_exit=spot_exit,
        lower_call=lower_call,
        center=center,
        upper_call=upper_call,
        entry_debit=entry_debit,
        commission_per_contract=commission_per_contract,
    )
    regime = "long_gamma" if net_gex_bs > 0 else "short_gamma"

    return LongFlyTrade(
        signal_date=signal_date,
        trade_date=trade_date,
        center_strike=center,
        lower_call=lower_call,
        upper_call=upper_call,
        wing_width=width,
        entry_debit=entry_debit,
        exit_value=exit_value,
        pnl_per_contract=pnl,
        net_gex_bs=net_gex_bs,
        regime=regime,
        center_source=center_source,
        center_mode=center_mode,
        spot_vs_center_pct=spot_vs_center_pct(spot_signal, center),
    )
