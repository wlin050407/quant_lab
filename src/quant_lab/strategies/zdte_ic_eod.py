"""EoD-approximate 0DTE iron condor simulation (Phase 3b).

Industry-aligned policy (FlashAlpha / SpotGamma / Vilkov):

1. **Regime filter** — only sell premium on ``long_gamma`` days (``net_gex_bs > 0``).
2. **Structure** — short iron condor on **dte=1** cohort (next-session 0DTE proxy).
3. **Strikes** — short legs at call/put **gamma walls** when valid; else
   ``spot ± 1-day expected move`` from ATM IV.

Signal at EoD *t-1* → enter IC at prior snapshot mids → hold through session *t*
→ exit at intrinsic with underlying **close** on *t*.

Still an approximation (no intraday timing); compares regime-appropriate
premium selling vs the failed directional flip hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.backtest.bs76 import intrinsic_value
from quant_lab.factors.gex import (
    DEFAULT_DIVIDEND_YIELD,
    DEFAULT_RISK_FREE_RATE,
    add_bs_gamma_column,
    call_wall,
    compute_dealer_gamma_exposure,
    put_wall,
)

RegimeFilter = Literal["none", "short_gamma_only", "long_gamma_only"]
StrikeSource = Literal["walls", "expected_move"]

MIN_IV = 0.05
MAX_IV = 3.0
TRADING_DAYS_PER_YEAR = 365
DEFAULT_COMMISSION_PER_CONTRACT = 0.65
CONTRACT_MULTIPLIER = 100
DEFAULT_WING_WIDTH = 2.0


@dataclass(frozen=True)
class IceTrade:
    signal_date: str
    trade_date: str
    short_call: float
    long_call: float
    short_put: float
    long_put: float
    entry_credit: float
    exit_cost: float
    pnl_per_contract: float
    net_gex_bs: float
    regime: str
    strike_source: StrikeSource


def _mid_price(row: pd.Series) -> float:
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    last = float(row.get("last_price", 0) or 0)
    if last > 0:
        return last
    return float("nan")


def _sanitize_iv(iv: float) -> float:
    if not np.isfinite(iv) or iv < MIN_IV or iv > MAX_IV:
        return 0.20
    return float(iv)


def passes_regime_filter(
    net_gex_bs: float,
    *,
    regime_filter: RegimeFilter,
) -> bool:
    if regime_filter == "none":
        return True
    if regime_filter == "short_gamma_only":
        return net_gex_bs < 0
    if regime_filter == "long_gamma_only":
        return net_gex_bs > 0
    raise ValueError(f"unknown regime_filter: {regime_filter!r}")


def compute_gamma_walls(
    chain: pd.DataFrame,
    spot: float,
    *,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> tuple[float, float]:
    """Return (call_wall, put_wall) from dealer GEX per strike."""
    if chain.empty or "open_interest" not in chain.columns:
        return float("nan"), float("nan")
    with_gamma = add_bs_gamma_column(chain, spot, r=r, q=q)
    per_strike = compute_dealer_gamma_exposure(with_gamma, spot)
    if per_strike.empty:
        return float("nan"), float("nan")
    return call_wall(per_strike), put_wall(per_strike)


def atm_iv(chain: pd.DataFrame, spot: float, *, dte: int = 1) -> float:
    """ATM implied vol for ``dte`` cohort."""
    if chain.empty or "dte" not in chain.columns:
        return float("nan")
    cohort = chain[chain["dte"] == dte].copy()
    if cohort.empty:
        return float("nan")
    cohort = cohort.assign(dist=(cohort["strike"] - spot).abs())
    row = cohort.loc[cohort["dist"].idxmin()]
    return _sanitize_iv(float(row.get("implied_volatility", np.nan)))


def expected_move_dollars(spot: float, iv: float, *, dte: int = 1) -> float:
    """1σ expected move in dollars for ``dte`` calendar days."""
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(iv):
        return float("nan")
    t = dte / TRADING_DAYS_PER_YEAR
    return float(spot * iv * np.sqrt(t))


def _nearest_strike(
    chain: pd.DataFrame,
    *,
    target: float,
    right: str,
    dte: int,
    direction: Literal["at_or_above", "at_or_below", "nearest"],
) -> float | None:
    cohort = chain[(chain["dte"] == dte) & (chain["right"] == right)].copy()
    if cohort.empty or not np.isfinite(target):
        return None
    strikes = sorted(cohort["strike"].unique())
    if direction == "nearest":
        return float(min(strikes, key=lambda k: abs(k - target)))
    if direction == "at_or_above":
        above = [s for s in strikes if s >= target]
        return float(min(above)) if above else None
    if direction == "at_or_below":
        below = [s for s in strikes if s <= target]
        return float(max(below)) if below else None
    raise ValueError(f"unknown direction: {direction!r}")


def resolve_ic_strikes(
    chain: pd.DataFrame,
    *,
    spot: float,
    call_wall_strike: float,
    put_wall_strike: float,
    wing_width: float,
    dte: int = 1,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> tuple[float, float, float, float, StrikeSource] | None:
    """Pick iron condor strikes from walls or expected-move fallback."""
    short_call = _nearest_strike(
        chain,
        target=call_wall_strike,
        right="C",
        dte=dte,
        direction="at_or_above",
    )
    short_put = _nearest_strike(
        chain,
        target=put_wall_strike,
        right="P",
        dte=dte,
        direction="at_or_below",
    )
    source: StrikeSource = "walls"

    walls_valid = (
        short_call is not None
        and short_put is not None
        and short_call > spot
        and short_put < spot
        and short_call - short_put >= wing_width + 1.0
    )
    if not walls_valid:
        iv = atm_iv(chain, spot, dte=dte)
        move = expected_move_dollars(spot, iv, dte=dte)
        if not np.isfinite(move):
            return None
        short_call = _nearest_strike(
            chain,
            target=spot + move,
            right="C",
            dte=dte,
            direction="at_or_above",
        )
        short_put = _nearest_strike(
            chain,
            target=spot - move,
            right="P",
            dte=dte,
            direction="at_or_below",
        )
        source = "expected_move"

    if short_call is None or short_put is None:
        return None
    if short_call <= spot or short_put >= spot:
        return None

    long_call = short_call + wing_width
    long_put = short_put - wing_width
    if long_call <= short_call or long_put >= short_put:
        return None
    if short_call - short_put < wing_width + 1.0:
        return None

    return float(short_call), float(long_call), float(short_put), float(long_put), source


def select_contract(
    chain: pd.DataFrame,
    *,
    strike: float,
    right: str,
    dte: int = 1,
) -> pd.Series | None:
    cohort = chain[
        (chain["dte"] == dte)
        & (chain["right"] == right)
        & (chain["strike"] == strike)
    ]
    if cohort.empty:
        return None
    return cohort.iloc[0]


def credit_spread_entry_credit(
    short_row: pd.Series,
    long_row: pd.Series,
) -> float:
    """Credit received per share for a short vertical spread."""
    short_mid = _mid_price(short_row)
    long_mid = _mid_price(long_row)
    if not np.isfinite(short_mid) or not np.isfinite(long_mid):
        return float("nan")
    return float(short_mid - long_mid)


def credit_spread_exit_cost(
    spot: float,
    short_strike: float,
    long_strike: float,
    right: str,
) -> float:
    """Intrinsic cost to close a short credit spread at expiry (per share)."""
    short_intr = intrinsic_value(spot, short_strike, right)
    long_intr = intrinsic_value(spot, long_strike, right)
    return float(max(short_intr - long_intr, 0.0))


def iron_condor_pnl(
    *,
    spot_exit: float,
    short_call: float,
    long_call: float,
    short_put: float,
    long_put: float,
    entry_credit: float,
    commission_per_contract: float,
) -> tuple[float, float]:
    """Return (exit_cost, pnl_per_contract) for a short iron condor at expiry."""
    call_cost = credit_spread_exit_cost(spot_exit, short_call, long_call, "C")
    put_cost = credit_spread_exit_cost(spot_exit, short_put, long_put, "P")
    exit_cost = call_cost + put_cost
    fees = 8.0 * commission_per_contract
    pnl = (entry_credit - exit_cost) * CONTRACT_MULTIPLIER - fees
    return exit_cost, pnl


def simulate_ic_trade(
    chain_signal: pd.DataFrame,
    *,
    signal_date: str,
    trade_date: str,
    spot_signal: float,
    spot_exit: float,
    net_gex_bs: float,
    regime_filter: RegimeFilter,
    wing_width: float = DEFAULT_WING_WIDTH,
    commission_per_contract: float = DEFAULT_COMMISSION_PER_CONTRACT,
    r: float = DEFAULT_RISK_FREE_RATE,
    q: float = DEFAULT_DIVIDEND_YIELD,
) -> IceTrade | None:
    """Simulate one short iron condor from signal EoD to next close."""
    if not passes_regime_filter(net_gex_bs, regime_filter=regime_filter):
        return None

    cw, pw = compute_gamma_walls(chain_signal, spot_signal, r=r, q=q)
    resolved = resolve_ic_strikes(
        chain_signal,
        spot=spot_signal,
        call_wall_strike=cw,
        put_wall_strike=pw,
        wing_width=wing_width,
        dte=1,
        r=r,
        q=q,
    )
    if resolved is None:
        return None
    short_call, long_call, short_put, long_put, source = resolved

    sc_row = select_contract(chain_signal, strike=short_call, right="C", dte=1)
    lc_row = select_contract(chain_signal, strike=long_call, right="C", dte=1)
    sp_row = select_contract(chain_signal, strike=short_put, right="P", dte=1)
    lp_row = select_contract(chain_signal, strike=long_put, right="P", dte=1)
    if sc_row is None or lc_row is None or sp_row is None or lp_row is None:
        return None

    call_credit = credit_spread_entry_credit(sc_row, lc_row)
    put_credit = credit_spread_entry_credit(sp_row, lp_row)
    if not np.isfinite(call_credit) or not np.isfinite(put_credit):
        return None
    entry_credit = call_credit + put_credit
    if entry_credit <= 0:
        return None

    exit_cost, pnl = iron_condor_pnl(
        spot_exit=spot_exit,
        short_call=short_call,
        long_call=long_call,
        short_put=short_put,
        long_put=long_put,
        entry_credit=entry_credit,
        commission_per_contract=commission_per_contract,
    )
    regime = "long_gamma" if net_gex_bs > 0 else "short_gamma"

    return IceTrade(
        signal_date=signal_date,
        trade_date=trade_date,
        short_call=short_call,
        long_call=long_call,
        short_put=short_put,
        long_put=long_put,
        entry_credit=entry_credit,
        exit_cost=exit_cost,
        pnl_per_contract=pnl,
        net_gex_bs=net_gex_bs,
        regime=regime,
        strike_source=source,
    )


def trades_to_daily_returns(
    trades: pd.DataFrame,
    *,
    initial_cash: float = 100_000.0,
    contracts: int = 1,
) -> pd.Series:
    """Map per-trade PnL to daily return series indexed by ``trade_date``."""
    if trades.empty:
        return pd.Series(dtype="float64")
    pnl = trades["pnl_per_contract"] * contracts
    dates = pd.to_datetime(trades["trade_date"])
    ret = pnl / initial_cash
    return pd.Series(ret.values, index=dates).sort_index()


def split_is_oos(
    daily_returns: pd.Series,
    *,
    oos_fraction: float = 0.20,
) -> tuple[pd.Series, pd.Series]:
    """Chronological IS/OOS split."""
    if daily_returns.empty:
        return daily_returns, daily_returns
    n = len(daily_returns)
    cut = max(1, int(n * (1.0 - oos_fraction)))
    is_ret = daily_returns.iloc[:cut]
    oos_ret = daily_returns.iloc[cut:]
    return is_ret, oos_ret
