"""EoD-approximate 0DTE directional simulation (Phase 3).

## Model (intentionally rough)

Signal at EoD *t-1* → enter ATM **dte=1** option (next-session 0DTE cohort)
at the prior snapshot's mid quote → hold through session *t* → exit at intrinsic
with underlying **close** on *t* (0DTE expiry proxy).

No intraday chain: entry/exit timing error can be ±50% per ROADMAP.

## Default policy

1. **Regime filter** — only trade ``short_gamma`` days (``net_gex_bs < 0``).
2. **Direction** — ``spot_vs_flip``: spot above flip → ATM call (+1),
   below → ATM put (-1).

Alternate direction: ``spot_vs_max_pain`` (fade away from max pain strike).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.backtest.bs76 import intrinsic_value, mark_price
from quant_lab.factors.gex import DEFAULT_DIVIDEND_YIELD, DEFAULT_RISK_FREE_RATE

DirectionSignal = Literal["spot_vs_flip", "spot_vs_max_pain"]
RegimeFilter = Literal["none", "short_gamma_only", "long_gamma_only"]
ExitMode = Literal["intrinsic", "bs_mark"]

MIN_IV = 0.05
MAX_IV = 3.0
TRADING_DAYS_PER_YEAR = 365
DEFAULT_COMMISSION_PER_CONTRACT = 0.65
CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class ZdteTrade:
    signal_date: str
    trade_date: str
    direction: int
    right: str
    strike: float
    entry_premium: float
    exit_spot: float
    exit_value: float
    pnl_per_contract: float
    net_gex_bs: float
    regime: str


@dataclass(frozen=True)
class ZdteSimulationResult:
    trades: pd.DataFrame
    daily_returns: pd.Series
    stats_is: dict[str, float]
    stats_oos: dict[str, float]
    signal_ic: float
    signal_ic_n: int


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


def compute_direction(
    *,
    spot: float,
    flip_level: float,
    max_pain: float,
    signal: DirectionSignal,
) -> int:
    """Return +1 (call), -1 (put), or 0 (flat / no signal)."""
    if signal == "spot_vs_flip":
        if not np.isfinite(flip_level):
            return 0
        if spot > flip_level:
            return 1
        if spot < flip_level:
            return -1
        return 0

    if signal == "spot_vs_max_pain":
        if not np.isfinite(max_pain):
            return 0
        if spot > max_pain:
            return -1
        if spot < max_pain:
            return 1
        return 0

    raise ValueError(f"unknown direction signal: {signal!r}")


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


def select_atm_contract(
    chain: pd.DataFrame,
    *,
    spot: float,
    right: str,
    dte: int = 1,
) -> pd.Series | None:
    """Pick nearest-strike ``dte`` row for ``right``."""
    if chain.empty or "dte" not in chain.columns:
        return None
    cohort = chain[(chain["dte"] == dte) & (chain["right"] == right)].copy()
    if cohort.empty:
        return None
    cohort = cohort.assign(dist=(cohort["strike"] - spot).abs())
    idx = cohort["dist"].idxmin()
    return cohort.loc[idx]


def simulate_one_trade(
    chain_signal: pd.DataFrame,
    *,
    signal_date: str,
    trade_date: str,
    spot_signal: float,
    spot_exit: float,
    net_gex_bs: float,
    flip_level: float,
    max_pain: float,
    direction_signal: DirectionSignal,
    regime_filter: RegimeFilter,
    exit_mode: ExitMode,
    commission_per_contract: float,
    r: float,
    q: float,
) -> ZdteTrade | None:
    """Simulate a single 0DTE hold from signal EoD to next close."""
    if not passes_regime_filter(net_gex_bs, regime_filter=regime_filter):
        return None

    direction = compute_direction(
        spot=spot_signal,
        flip_level=flip_level,
        max_pain=max_pain,
        signal=direction_signal,
    )
    if direction == 0:
        return None

    right = "C" if direction > 0 else "P"
    row = select_atm_contract(chain_signal, spot=spot_signal, right=right, dte=1)
    if row is None:
        return None

    entry = _mid_price(row)
    if not np.isfinite(entry) or entry <= 0:
        return None

    strike = float(row["strike"])
    iv = _sanitize_iv(float(row.get("implied_volatility", np.nan)))

    if exit_mode == "intrinsic":
        exit_value = intrinsic_value(spot_exit, strike, right)
    else:
        t_exit = 1.0 / (6.5 * 60.0 * TRADING_DAYS_PER_YEAR)
        exit_value = mark_price(spot_exit, strike, right, t_exit, iv, r=r, q=q)

    fees = 2.0 * commission_per_contract
    pnl = (exit_value - entry) * CONTRACT_MULTIPLIER - fees
    regime = "long_gamma" if net_gex_bs > 0 else "short_gamma"

    return ZdteTrade(
        signal_date=signal_date,
        trade_date=trade_date,
        direction=direction,
        right=right,
        strike=strike,
        entry_premium=entry,
        exit_spot=spot_exit,
        exit_value=exit_value,
        pnl_per_contract=pnl,
        net_gex_bs=net_gex_bs,
        regime=regime,
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


def _stats_dict(net_ret: pd.Series, initial_cash: float) -> dict[str, float]:
    from quant_lab.backtest.engine import summarize_returns

    s = summarize_returns(net_ret, initial_cash=initial_cash)
    return {
        "total_return": s.total_return,
        "sharpe": s.sharpe,
        "max_drawdown": s.max_drawdown,
        "hit_rate": s.hit_rate,
        "n_days": float(s.n_days),
    }
