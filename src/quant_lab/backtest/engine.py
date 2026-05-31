"""Minimal daily backtest engine.

Signal at EoD *t* earns the close-to-close return on day *t+1* (no look-ahead).
Position changes incur slippage + commission on notional traded.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class BacktestStats:
    total_return: float
    sharpe: float
    max_drawdown: float
    hit_rate: float
    turnover: float
    n_days: int


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pd.Series
    daily_returns: pd.Series
    positions: pd.Series
    stats: BacktestStats


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def run_backtest(
    prices: pd.Series,
    signals: pd.Series,
    *,
    initial_cash: float = 100_000.0,
    slippage_bps: float = 1.0,
    commission_bps: float = 0.0,
) -> BacktestResult:
    """Run a long-only / long-short daily backtest on close prices.

    Args:
        prices: close prices indexed by date (DatetimeIndex).
        signals: target portfolio weight in [-1, 1], same index as ``prices``.
        initial_cash: starting equity.
        slippage_bps: half-spread cost applied per unit of turnover (both sides).
        commission_bps: additional cost per unit turnover.

    Returns:
        ``BacktestResult`` with equity curve and summary stats.
    """
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices must have a DatetimeIndex")
    if prices.empty:
        raise ValueError("prices is empty")

    px = prices.sort_index().astype("float64")
    sig = signals.reindex(px.index).astype("float64").fillna(0.0)

    asset_ret = px.pct_change()
    lagged_pos = sig.shift(1).fillna(0.0)
    gross_ret = lagged_pos * asset_ret

    turnover = sig.diff().abs().fillna(sig.abs())
    cost_rate = (slippage_bps + commission_bps) / 10_000.0
    costs = turnover * cost_rate
    net_ret = gross_ret - costs

    equity = (1.0 + net_ret).cumprod() * initial_cash
    equity.iloc[0] = initial_cash

    valid = net_ret.dropna()
    n = len(valid)
    if n == 0:
        sharpe = 0.0
        hit_rate = 0.0
    else:
        vol = float(valid.std())
        sharpe = float(valid.mean() / vol * np.sqrt(TRADING_DAYS_PER_YEAR)) if vol > 0 else 0.0
        hit_rate = float((valid > 0).mean())

    stats = BacktestStats(
        total_return=float(equity.iloc[-1] / initial_cash - 1.0),
        sharpe=sharpe,
        max_drawdown=_max_drawdown(equity),
        hit_rate=hit_rate,
        turnover=float(turnover.sum()),
        n_days=n,
    )
    return BacktestResult(
        equity_curve=equity,
        daily_returns=net_ret,
        positions=sig,
        stats=stats,
    )


def summarize_returns(
    net_ret: pd.Series,
    *,
    initial_cash: float = 100_000.0,
) -> BacktestStats:
    """Build ``BacktestStats`` from a daily net-return series."""
    net_ret = net_ret.dropna()
    if net_ret.empty:
        return BacktestStats(
            total_return=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            hit_rate=0.0,
            turnover=0.0,
            n_days=0,
        )
    equity = (1.0 + net_ret).cumprod() * initial_cash
    equity.iloc[0] = initial_cash
    vol = float(net_ret.std())
    sharpe = float(net_ret.mean() / vol * np.sqrt(TRADING_DAYS_PER_YEAR)) if vol > 0 else 0.0
    return BacktestStats(
        total_return=float(equity.iloc[-1] / initial_cash - 1.0),
        sharpe=sharpe,
        max_drawdown=_max_drawdown(equity),
        hit_rate=float((net_ret > 0).mean()),
        turnover=0.0,
        n_days=len(net_ret),
    )
