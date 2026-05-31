"""Phase 3c conditional IC filters and tail diagnostics (M3).

Applies terminal parquet gates (regime, pin, walls, trinity) on top of the
Phase 3b iron-condor simulator.  Pure functions only — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.backtest.engine import summarize_returns
from quant_lab.factors.regime import RegimeLabel, should_trade_zdte
from quant_lab.strategies.zdte_ic_eod import (
    CONTRACT_MULTIPLIER,
    DEFAULT_WING_WIDTH,
    split_is_oos,
    trades_to_daily_returns,
)

ConditionalRejectReason = Literal[
    "ok",
    "not_long_gamma",
    "gate_failed",
    "no_setup",
    "trinity_mixed",
    "trinity_low",
]
SetupMode = Literal["pin_or_walls", "pin_only", "walls_only"]


@dataclass(frozen=True)
class TradeTailStats:
    n_trades: int
    max_loss_per_trade: float
    worst_pnl: float
    cvar_5pct: float
    mean_pnl: float


def _between_walls(spot: float, put_wall: float, call_wall: float) -> bool:
    if not all(np.isfinite(x) for x in (spot, put_wall, call_wall)):
        return False
    return put_wall < spot < call_wall


def passes_m3_conditional_filter(
    *,
    regime: RegimeLabel | str,
    pin_score: float,
    pct_gex_dte1: float,
    spot: float,
    put_wall: float,
    call_wall: float,
    trinity_score: float | None = None,
    trinity_direction: str | None = None,
    min_pin: float = 70.0,
    min_trinity: float = 60.0,
    min_pct_gex_dte1: float = 40.0,
    setup_mode: SetupMode = "pin_only",
    require_trinity: bool = False,
) -> tuple[bool, ConditionalRejectReason]:
    """M3 gate: long-gamma + FlashAlpha tradeability + pin or range setup.

    Default (2026-05 sensitivity): ``pin_only`` with ``min_pin=70`` and
    ``min_pct_gex_dte1=40`` — outperformed ``pin_or_walls`` on walk-forward folds.
    Use ``setup_mode='pin_or_walls'`` for the original combined rule.
    """
    if regime != "long_gamma":
        return False, "not_long_gamma"

    ok, reason = should_trade_zdte(
        pct_gex_dte1=pct_gex_dte1,
        pin_score=pin_score,
        regime=regime if regime in ("long_gamma", "short_gamma", "undetermined") else "undetermined",
        min_pct_gex_dte1=min_pct_gex_dte1,
    )
    if not ok:
        return False, "gate_failed"

    pin_play = np.isfinite(pin_score) and pin_score >= min_pin
    gamma_fade = _between_walls(spot, put_wall, call_wall)
    if setup_mode == "pin_only":
        setup_ok = pin_play
    elif setup_mode == "walls_only":
        setup_ok = gamma_fade
    else:
        setup_ok = pin_play or gamma_fade
    if not setup_ok:
        return False, "no_setup"

    if require_trinity:
        if trinity_score is None or not np.isfinite(trinity_score):
            return False, "trinity_low"
        if trinity_score < min_trinity:
            return False, "trinity_low"
        if trinity_direction in ("mixed", "insufficient_data"):
            return False, "trinity_mixed"

    return True, "ok"


def max_loss_per_trade(
    *,
    entry_credit: float,
    wing_width: float = DEFAULT_WING_WIDTH,
    commission_per_contract: float = 0.65,
) -> float:
    """Theoretical worst-case loss per iron condor (one wing fully breached)."""
    if not np.isfinite(entry_credit) or not np.isfinite(wing_width):
        return float("nan")
    fees = 8.0 * commission_per_contract
    return float((wing_width - entry_credit) * CONTRACT_MULTIPLIER - fees)


def trade_tail_stats(
    trades: pd.DataFrame,
    *,
    wing_width: float = DEFAULT_WING_WIDTH,
    commission_per_contract: float = 0.65,
    cvar_alpha: float = 0.05,
) -> TradeTailStats:
    """Tail diagnostics on per-trade PnL (M3)."""
    if trades.empty:
        return TradeTailStats(
            n_trades=0,
            max_loss_per_trade=float("nan"),
            worst_pnl=float("nan"),
            cvar_5pct=float("nan"),
            mean_pnl=float("nan"),
        )

    pnl = trades["pnl_per_contract"].astype("float64")
    if "entry_credit" in trades.columns:
        theoretical = trades["entry_credit"].map(
            lambda c: max_loss_per_trade(
                entry_credit=float(c),
                wing_width=wing_width,
                commission_per_contract=commission_per_contract,
            )
        )
        max_loss = float(theoretical.max())
    else:
        max_loss = float("nan")

    worst = float(pnl.min())
    n_tail = max(1, int(np.ceil(len(pnl) * cvar_alpha)))
    sorted_pnl = np.sort(pnl.to_numpy())
    cvar = float(sorted_pnl[:n_tail].mean())

    return TradeTailStats(
        n_trades=len(trades),
        max_loss_per_trade=max_loss,
        worst_pnl=worst,
        cvar_5pct=cvar,
        mean_pnl=float(pnl.mean()),
    )


@dataclass(frozen=True)
class PeriodStats:
    n_trades: int
    sharpe: float
    hit_rate: float
    mean_pnl: float
    total_pnl: float


@dataclass(frozen=True)
class YearlyComparisonRow:
    year: int
    uncond: PeriodStats
    cond: PeriodStats

    @property
    def sharpe_delta(self) -> float:
        return self.cond.sharpe - self.uncond.sharpe


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    oos_start: str
    oos_end: str
    uncond: PeriodStats
    cond: PeriodStats

    @property
    def sharpe_delta(self) -> float:
        return self.cond.sharpe - self.uncond.sharpe


@dataclass(frozen=True)
class RobustnessSummary:
    n_years: int
    n_years_cond_wins: int
    n_folds: int
    n_folds_cond_wins: int
    median_yearly_sharpe_delta: float
    median_fold_sharpe_delta: float


def period_stats(
    trades: pd.DataFrame,
    *,
    initial_cash: float = 100_000.0,
    contracts: int = 1,
) -> PeriodStats:
    """Sharpe / hit rate for a trade subset."""
    if trades.empty:
        return PeriodStats(
            n_trades=0,
            sharpe=0.0,
            hit_rate=0.0,
            mean_pnl=float("nan"),
            total_pnl=0.0,
        )
    daily_ret = trades_to_daily_returns(
        trades,
        initial_cash=initial_cash,
        contracts=contracts,
    )
    stats = summarize_returns(daily_ret, initial_cash=initial_cash)
    pnl = trades["pnl_per_contract"].astype("float64") * contracts
    return PeriodStats(
        n_trades=len(trades),
        sharpe=stats.sharpe,
        hit_rate=stats.hit_rate,
        mean_pnl=float(pnl.mean()),
        total_pnl=float(pnl.sum()),
    )


def yearly_breakdown(
    trades: pd.DataFrame,
    *,
    conditional_col: str = "conditional_pass",
    initial_cash: float = 100_000.0,
    contracts: int = 1,
    min_trades: int = 5,
) -> list[YearlyComparisonRow]:
    """Calendar-year unconditional vs conditional stats."""
    if trades.empty or "trade_date" not in trades.columns:
        return []

    df = trades.copy()
    df["trade_ts"] = pd.to_datetime(df["trade_date"])
    df["year"] = df["trade_ts"].dt.year

    rows: list[YearlyComparisonRow] = []
    for year, group in df.groupby("year", sort=True):
        uncond = group
        cond = group[group[conditional_col].astype(bool)] if conditional_col in group.columns else group.iloc[0:0]
        if len(uncond) < min_trades:
            continue
        rows.append(
            YearlyComparisonRow(
                year=int(year),
                uncond=period_stats(uncond, initial_cash=initial_cash, contracts=contracts),
                cond=period_stats(cond, initial_cash=initial_cash, contracts=contracts),
            )
        )
    return rows


def walk_forward_folds(
    trades: pd.DataFrame,
    *,
    n_folds: int = 5,
    conditional_col: str = "conditional_pass",
    initial_cash: float = 100_000.0,
    contracts: int = 1,
    min_oos_trades: int = 10,
) -> list[WalkForwardFold]:
    """Chronological OOS folds: compare conditional vs unconditional Sharpe."""
    if trades.empty or n_folds < 1:
        return []

    df = trades.sort_values("trade_date").reset_index(drop=True)
    n = len(df)
    fold_size = max(min_oos_trades, n // n_folds)
    folds: list[WalkForwardFold] = []

    for fold_idx in range(n_folds):
        start = fold_idx * fold_size
        end = n if fold_idx == n_folds - 1 else min((fold_idx + 1) * fold_size, n)
        if end - start < min_oos_trades:
            continue
        oos = df.iloc[start:end]
        uncond = oos
        cond = oos[oos[conditional_col].astype(bool)] if conditional_col in oos.columns else oos.iloc[0:0]
        folds.append(
            WalkForwardFold(
                fold=fold_idx + 1,
                oos_start=str(oos["trade_date"].iloc[0]),
                oos_end=str(oos["trade_date"].iloc[-1]),
                uncond=period_stats(uncond, initial_cash=initial_cash, contracts=contracts),
                cond=period_stats(cond, initial_cash=initial_cash, contracts=contracts),
            )
        )
    return folds


def robustness_summary(
    trades: pd.DataFrame,
    *,
    n_folds: int = 5,
    conditional_col: str = "conditional_pass",
    initial_cash: float = 100_000.0,
    contracts: int = 1,
) -> RobustnessSummary:
    """Aggregate how often conditional beats unconditional."""
    yearly = yearly_breakdown(
        trades,
        conditional_col=conditional_col,
        initial_cash=initial_cash,
        contracts=contracts,
    )
    folds = walk_forward_folds(
        trades,
        n_folds=n_folds,
        conditional_col=conditional_col,
        initial_cash=initial_cash,
        contracts=contracts,
    )

    yearly_deltas = [r.sharpe_delta for r in yearly if r.cond.n_trades >= 5]
    fold_deltas = [f.sharpe_delta for f in folds if f.cond.n_trades >= 5]

    return RobustnessSummary(
        n_years=len(yearly_deltas),
        n_years_cond_wins=sum(1 for d in yearly_deltas if d > 0),
        n_folds=len(fold_deltas),
        n_folds_cond_wins=sum(1 for d in fold_deltas if d > 0),
        median_yearly_sharpe_delta=float(np.median(yearly_deltas)) if yearly_deltas else float("nan"),
        median_fold_sharpe_delta=float(np.median(fold_deltas)) if fold_deltas else float("nan"),
    )


@dataclass(frozen=True)
class M3Config:
    min_pin: float
    setup_mode: SetupMode
    min_pct_gex_dte1: float
    require_trinity: bool = False
    min_trinity: float = 60.0


@dataclass(frozen=True)
class M3SensitivityResult:
    config: M3Config
    n_trades: int
    all_sharpe: float
    oos_sharpe: float
    oos_hit: float
    oos_sharpe_delta: float
    years_wins: int
    n_years: int
    folds_wins: int
    n_folds: int
    median_fold_delta: float


def enrich_trades_with_terminal(
    trades: pd.DataFrame,
    terminal: pd.DataFrame,
) -> pd.DataFrame:
    """Join signal-day terminal levels needed for M3 filter sweeps."""
    term = terminal.copy()
    term["date"] = pd.to_datetime(term["date"]).dt.normalize()
    term = term.set_index("date")
    keep = ["spot", "put_wall_dte1", "call_wall_dte1"]
    missing = [c for c in keep if c not in term.columns]
    if missing:
        raise ValueError(f"terminal missing columns: {missing}")

    out = trades.copy()
    out["signal_ts"] = pd.to_datetime(out["signal_date"]).dt.normalize()
    for col in keep:
        out[col] = out["signal_ts"].map(lambda d, c=col: float(term.loc[d, c]) if d in term.index else float("nan"))
    return out


def m3_filter_mask(
    trades: pd.DataFrame,
    config: M3Config,
) -> pd.Series:
    """Boolean mask: trades passing M3 filter under ``config``."""
    mask = []
    for row in trades.itertuples(index=False):
        passed, _ = passes_m3_conditional_filter(
            regime=str(getattr(row, "terminal_regime", getattr(row, "regime", ""))),
            pin_score=float(row.pin_score),
            pct_gex_dte1=float(row.pct_gex_dte1),
            spot=float(row.spot),
            put_wall=float(row.put_wall_dte1),
            call_wall=float(row.call_wall_dte1),
            trinity_score=(
                float(row.trinity_score)
                if hasattr(row, "trinity_score") and pd.notna(row.trinity_score)
                else None
            ),
            trinity_direction=(
                str(row.trinity_direction)
                if hasattr(row, "trinity_direction") and pd.notna(row.trinity_direction)
                else None
            ),
            min_pin=config.min_pin,
            min_trinity=config.min_trinity,
            min_pct_gex_dte1=config.min_pct_gex_dte1,
            setup_mode=config.setup_mode,
            require_trinity=config.require_trinity,
        )
        mask.append(passed)
    return pd.Series(mask, index=trades.index)


def evaluate_m3_config(
    trades: pd.DataFrame,
    config: M3Config,
    *,
    baseline_oos_sharpe: float,
    oos_fraction: float = 0.20,
    initial_cash: float = 100_000.0,
    contracts: int = 1,
    n_folds: int = 5,
    min_trades: int = 20,
) -> M3SensitivityResult | None:
    """Evaluate one M3 parameter set; None if too few trades."""
    filtered = trades.loc[m3_filter_mask(trades, config)].copy()
    if len(filtered) < min_trades:
        return None

    all_stats = period_stats(filtered, initial_cash=initial_cash, contracts=contracts)
    daily_ret = trades_to_daily_returns(
        filtered,
        initial_cash=initial_cash,
        contracts=contracts,
    )
    _, oos_ret = split_is_oos(daily_ret, oos_fraction=oos_fraction)
    oos_stats = summarize_returns(oos_ret, initial_cash=initial_cash)

    eval_df = trades.copy()
    eval_df["_pass"] = m3_filter_mask(trades, config)
    robust = robustness_summary(
        eval_df,
        n_folds=n_folds,
        conditional_col="_pass",
        initial_cash=initial_cash,
        contracts=contracts,
    )

    return M3SensitivityResult(
        config=config,
        n_trades=len(filtered),
        all_sharpe=all_stats.sharpe,
        oos_sharpe=oos_stats.sharpe,
        oos_hit=oos_stats.hit_rate,
        oos_sharpe_delta=oos_stats.sharpe - baseline_oos_sharpe,
        years_wins=robust.n_years_cond_wins,
        n_years=robust.n_years,
        folds_wins=robust.n_folds_cond_wins,
        n_folds=robust.n_folds,
        median_fold_delta=robust.median_fold_sharpe_delta,
    )


def sweep_m3_parameters(
    trades: pd.DataFrame,
    *,
    min_pins: tuple[float, ...] = (60.0, 65.0, 70.0, 75.0, 80.0),
    setup_modes: tuple[SetupMode, ...] = ("pin_or_walls", "pin_only", "walls_only"),
    min_pct_gex_values: tuple[float, ...] = (20.0, 30.0, 40.0),
    oos_fraction: float = 0.20,
    initial_cash: float = 100_000.0,
    contracts: int = 1,
    min_trades: int = 20,
) -> list[M3SensitivityResult]:
    """Grid search M3 filter parameters on precomputed IC trades."""
    baseline_ret = trades_to_daily_returns(
        trades,
        initial_cash=initial_cash,
        contracts=contracts,
    )
    _, baseline_oos = split_is_oos(baseline_ret, oos_fraction=oos_fraction)
    baseline_oos_sharpe = summarize_returns(baseline_oos, initial_cash=initial_cash).sharpe

    results: list[M3SensitivityResult] = []
    for min_pin in min_pins:
        for setup_mode in setup_modes:
            for min_pct in min_pct_gex_values:
                config = M3Config(
                    min_pin=min_pin,
                    setup_mode=setup_mode,
                    min_pct_gex_dte1=min_pct,
                )
                row = evaluate_m3_config(
                    trades,
                    config,
                    baseline_oos_sharpe=baseline_oos_sharpe,
                    oos_fraction=oos_fraction,
                    initial_cash=initial_cash,
                    contracts=contracts,
                    min_trades=min_trades,
                )
                if row is not None:
                    results.append(row)
    return results


@dataclass(frozen=True)
class StratifiedStats:
    label: str
    n_trades: int
    sharpe: float
    hit_rate: float
    mean_pnl: float
    total_pnl: float


def split_oos_by_cutoff(
    daily_returns: pd.Series,
    *,
    oos_fraction: float = 0.20,
) -> tuple[pd.Series, pd.Series, pd.Timestamp]:
    """OOS split by calendar cutoff (last ``oos_fraction`` of date range)."""
    if daily_returns.empty:
        ts = pd.Timestamp("1970-01-01")
        return daily_returns, daily_returns, ts
    ordered = daily_returns.sort_index()
    start = ordered.index.min()
    end = ordered.index.max()
    span = (end - start).days
    cut = start + pd.Timedelta(days=int(span * (1.0 - oos_fraction)))
    is_ret = ordered[ordered.index < cut]
    oos_ret = ordered[ordered.index >= cut]
    return is_ret, oos_ret, cut


def stratified_stats(
    trades: pd.DataFrame,
    labels: pd.Series,
    *,
    initial_cash: float = 100_000.0,
    contracts: int = 1,
    min_trades: int = 20,
) -> list[StratifiedStats]:
    """Performance by bucket — every trade stays in exactly one bucket."""
    rows: list[StratifiedStats] = []
    for label in sorted(labels.dropna().unique(), key=str):
        subset = trades.loc[labels == label]
        if len(subset) < min_trades:
            continue
        stats = period_stats(subset, initial_cash=initial_cash, contracts=contracts)
        rows.append(
            StratifiedStats(
                label=str(label),
                n_trades=stats.n_trades,
                sharpe=stats.sharpe,
                hit_rate=stats.hit_rate,
                mean_pnl=stats.mean_pnl,
                total_pnl=stats.total_pnl,
            )
        )
    return rows


def pin_tier(pin_score: float) -> str:
    """Pin buckets for daily-participation analysis (no sit-out)."""
    if not np.isfinite(pin_score):
        return "pin_unknown"
    if pin_score >= 70.0:
        return "pin_high"
    if pin_score >= 40.0:
        return "pin_mid"
    return "pin_low"


DEFAULT_PIN_TIER_WEIGHTS: dict[str, float] = {
    "pin_high": 3.0,
    "pin_mid": 0.5,
    "pin_low": 0.25,
    "pin_unknown": 0.5,
}

DEFAULT_REGIME_MULTIPLIERS: dict[str, float] = {
    "long_gamma": 1.0,
    "short_gamma": 0.25,
    "undetermined": 0.75,
    "unknown": 0.75,
}


def pin_tier_contract_weights(
    trades: pd.DataFrame,
    *,
    weights: dict[str, float] | None = None,
    tier_col: str = "pin_tier",
) -> pd.Series:
    """Per-trade contract multiplier from pin tier (daily participation sizing)."""
    scheme = weights if weights is not None else DEFAULT_PIN_TIER_WEIGHTS
    if tier_col not in trades.columns:
        raise ValueError(f"trades missing {tier_col!r}")
    return trades[tier_col].map(lambda t: float(scheme.get(str(t), 1.0)))


def weighted_trades_to_daily_returns(
    trades: pd.DataFrame,
    contract_weights: pd.Series,
    *,
    initial_cash: float = 100_000.0,
) -> pd.Series:
    """Map weighted PnL to daily returns (participate every day, size by pin)."""
    if trades.empty:
        return pd.Series(dtype="float64")
    pnl = trades["pnl_per_contract"].astype("float64") * contract_weights.astype("float64")
    dates = pd.to_datetime(trades["trade_date"])
    ret = pnl / initial_cash
    return pd.Series(ret.values, index=dates).sort_index()


def add_terminal_context(trades: pd.DataFrame, terminal: pd.DataFrame) -> pd.DataFrame:
    """Join signal-day terminal fields + derived tiers."""
    enriched = enrich_trades_with_terminal(trades, terminal)
    if "terminal_regime" not in enriched.columns and "regime" in enriched.columns:
        enriched["terminal_regime"] = enriched["regime"]
    if "pin_score" not in enriched.columns:
        raise ValueError("trades need pin_score from terminal join")
    enriched["pin_tier"] = enriched["pin_score"].map(lambda x: pin_tier(float(x)))
    return enriched


@dataclass(frozen=True)
class PinWeightConfig:
    w_high: float
    w_mid: float
    w_low: float

    def as_dict(self) -> dict[str, float]:
        return {
            "pin_high": self.w_high,
            "pin_mid": self.w_mid,
            "pin_low": self.w_low,
            "pin_unknown": self.w_mid,
        }


@dataclass(frozen=True)
class SizingConfig:
    """Pin tier weights × regime multiplier (daily participation, no sit-out)."""

    pin: PinWeightConfig
    long_gamma_mult: float = 1.0
    short_gamma_mult: float = 0.5
    undetermined_mult: float = 0.75

    @classmethod
    def from_defaults(cls) -> SizingConfig:
        pin = PinWeightConfig(
            w_high=DEFAULT_PIN_TIER_WEIGHTS["pin_high"],
            w_mid=DEFAULT_PIN_TIER_WEIGHTS["pin_mid"],
            w_low=DEFAULT_PIN_TIER_WEIGHTS["pin_low"],
        )
        return cls(
            pin=pin,
            long_gamma_mult=DEFAULT_REGIME_MULTIPLIERS["long_gamma"],
            short_gamma_mult=DEFAULT_REGIME_MULTIPLIERS["short_gamma"],
            undetermined_mult=DEFAULT_REGIME_MULTIPLIERS["undetermined"],
        )


def regime_contract_multipliers(
    trades: pd.DataFrame,
    config: SizingConfig,
    *,
    regime_col: str = "terminal_regime",
) -> pd.Series:
    mapping = {
        "long_gamma": config.long_gamma_mult,
        "short_gamma": config.short_gamma_mult,
        "undetermined": config.undetermined_mult,
    }
    col = regime_col if regime_col in trades.columns else "regime"
    if col not in trades.columns:
        raise ValueError("trades need terminal_regime or regime column")
    return trades[col].map(lambda r: float(mapping.get(str(r), config.undetermined_mult)))


def contract_weights_from_sizing(
    trades: pd.DataFrame,
    config: SizingConfig,
    *,
    base_contracts: float = 1.0,
) -> pd.Series:
    pin_w = pin_tier_contract_weights(trades, weights=config.pin.as_dict())
    regime_w = regime_contract_multipliers(trades, config)
    return pin_w * regime_w * base_contracts


@dataclass(frozen=True)
class SizingResult:
    config: SizingConfig
    n_trades: int
    all_sharpe: float
    oos_sharpe: float
    oos_hit: float
    max_drawdown: float
    folds_positive: int
    n_folds: int
    median_fold_sharpe: float
    total_pnl: float
    is_pareto: bool = False


@dataclass(frozen=True)
class PinWeightResult:
    config: PinWeightConfig
    n_trades: int
    all_sharpe: float
    oos_sharpe: float
    oos_hit: float
    max_drawdown: float
    folds_positive: int
    n_folds: int
    median_fold_sharpe: float
    total_pnl: float
    is_pareto: bool = False


def _fold_sharpes(
    trades: pd.DataFrame,
    contract_weights: pd.Series,
    *,
    n_folds: int,
    initial_cash: float,
) -> list[float]:
    df = trades.copy()
    df["_w"] = contract_weights.values
    df = df.sort_values("trade_date").reset_index(drop=True)
    n = len(df)
    fold_size = max(10, n // n_folds)
    sharpes: list[float] = []
    for fold_idx in range(n_folds):
        start = fold_idx * fold_size
        end = n if fold_idx == n_folds - 1 else min((fold_idx + 1) * fold_size, n)
        if end - start < 10:
            continue
        chunk = df.iloc[start:end]
        ret = weighted_trades_to_daily_returns(chunk, chunk["_w"], initial_cash=initial_cash)
        stats = summarize_returns(ret, initial_cash=initial_cash)
        sharpes.append(stats.sharpe)
    return sharpes


def evaluate_sizing(
    trades: pd.DataFrame,
    config: SizingConfig,
    *,
    base_contracts: float = 1.0,
    oos_fraction: float = 0.20,
    initial_cash: float = 100_000.0,
    n_folds: int = 5,
) -> SizingResult:
    """Evaluate pin × regime sizing on a daily-participation trade book."""
    sized = contract_weights_from_sizing(trades, config, base_contracts=base_contracts)
    daily = weighted_trades_to_daily_returns(trades, sized, initial_cash=initial_cash)
    stats_all = summarize_returns(daily, initial_cash=initial_cash)
    _, oos, _ = split_oos_by_cutoff(daily, oos_fraction=oos_fraction)
    stats_oos = summarize_returns(oos, initial_cash=initial_cash)
    fold_sh = _fold_sharpes(trades, sized, n_folds=n_folds, initial_cash=initial_cash)
    total_pnl = float((trades["pnl_per_contract"] * sized).sum())
    return SizingResult(
        config=config,
        n_trades=len(trades),
        all_sharpe=stats_all.sharpe,
        oos_sharpe=stats_oos.sharpe,
        oos_hit=stats_oos.hit_rate,
        max_drawdown=stats_all.max_drawdown,
        folds_positive=sum(1 for s in fold_sh if s > 0),
        n_folds=len(fold_sh),
        median_fold_sharpe=float(np.median(fold_sh)) if fold_sh else float("nan"),
        total_pnl=total_pnl,
    )


def evaluate_pin_weights(
    trades: pd.DataFrame,
    config: PinWeightConfig,
    *,
    base_contracts: float = 1.0,
    oos_fraction: float = 0.20,
    initial_cash: float = 100_000.0,
    n_folds: int = 5,
) -> PinWeightResult:
    """Evaluate pin weights only (regime multipliers = 1)."""
    res = evaluate_sizing(
        trades,
        SizingConfig(
            pin=config,
            long_gamma_mult=1.0,
            short_gamma_mult=1.0,
            undetermined_mult=1.0,
        ),
        base_contracts=base_contracts,
        oos_fraction=oos_fraction,
        initial_cash=initial_cash,
        n_folds=n_folds,
    )
    return PinWeightResult(
        config=config,
        n_trades=res.n_trades,
        all_sharpe=res.all_sharpe,
        oos_sharpe=res.oos_sharpe,
        oos_hit=res.oos_hit,
        max_drawdown=res.max_drawdown,
        folds_positive=res.folds_positive,
        n_folds=res.n_folds,
        median_fold_sharpe=res.median_fold_sharpe,
        total_pnl=res.total_pnl,
        is_pareto=res.is_pareto,
    )


def mark_pareto_frontier(results: list[PinWeightResult]) -> list[PinWeightResult]:
    """Mark configs not dominated on (OOS Sharpe ↑, max drawdown ↑ closer to 0)."""
    marked: list[PinWeightResult] = []
    for i, a in enumerate(results):
        dominated = False
        for j, b in enumerate(results):
            if i == j:
                continue
            if (
                b.oos_sharpe >= a.oos_sharpe
                and b.max_drawdown >= a.max_drawdown
                and (b.oos_sharpe > a.oos_sharpe or b.max_drawdown > a.max_drawdown)
            ):
                dominated = True
                break
        marked.append(
            PinWeightResult(
                config=a.config,
                n_trades=a.n_trades,
                all_sharpe=a.all_sharpe,
                oos_sharpe=a.oos_sharpe,
                oos_hit=a.oos_hit,
                max_drawdown=a.max_drawdown,
                folds_positive=a.folds_positive,
                n_folds=a.n_folds,
                median_fold_sharpe=a.median_fold_sharpe,
                total_pnl=a.total_pnl,
                is_pareto=not dominated,
            )
        )
    return marked


def sweep_pin_weights(
    trades: pd.DataFrame,
    *,
    w_high_grid: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0),
    w_mid_grid: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25),
    w_low_grid: tuple[float, ...] = (0.25, 0.5, 0.75),
    min_w_low: float = 0.25,
    oos_fraction: float = 0.20,
    initial_cash: float = 100_000.0,
    n_folds: int = 5,
) -> list[PinWeightResult]:
    """Grid search with monotonic constraint w_high >= w_mid >= w_low."""
    results: list[PinWeightResult] = []
    for wh in w_high_grid:
        for wm in w_mid_grid:
            for wl in w_low_grid:
                if wl < min_w_low or wh < wm or wm < wl:
                    continue
                cfg = PinWeightConfig(w_high=wh, w_mid=wm, w_low=wl)
                results.append(
                    evaluate_pin_weights(
                        trades,
                        cfg,
                        oos_fraction=oos_fraction,
                        initial_cash=initial_cash,
                        n_folds=n_folds,
                    )
                )
    return mark_pareto_frontier(results)


def pick_stable_pin_weights(
    results: list[PinWeightResult],
    *,
    min_folds_positive: int = 3,
) -> PinWeightResult | None:
    """Best OOS Sharpe among configs with enough positive walk-forward folds."""
    viable = [r for r in results if r.folds_positive >= min_folds_positive]
    if not viable:
        return None
    return max(viable, key=lambda r: (r.oos_sharpe, r.median_fold_sharpe, r.max_drawdown))


def mark_pareto_sizing(results: list[SizingResult]) -> list[SizingResult]:
    """Pareto on OOS Sharpe vs max drawdown for full sizing configs."""
    marked: list[SizingResult] = []
    for i, a in enumerate(results):
        dominated = False
        for j, b in enumerate(results):
            if i == j:
                continue
            if (
                b.oos_sharpe >= a.oos_sharpe
                and b.max_drawdown >= a.max_drawdown
                and (b.oos_sharpe > a.oos_sharpe or b.max_drawdown > a.max_drawdown)
            ):
                dominated = True
                break
        marked.append(
            SizingResult(
                config=a.config,
                n_trades=a.n_trades,
                all_sharpe=a.all_sharpe,
                oos_sharpe=a.oos_sharpe,
                oos_hit=a.oos_hit,
                max_drawdown=a.max_drawdown,
                folds_positive=a.folds_positive,
                n_folds=a.n_folds,
                median_fold_sharpe=a.median_fold_sharpe,
                total_pnl=a.total_pnl,
                is_pareto=not dominated,
            )
        )
    return marked


def sweep_regime_multipliers(
    trades: pd.DataFrame,
    pin: PinWeightConfig,
    *,
    short_gamma_grid: tuple[float, ...] = (0.25, 0.35, 0.5, 0.65, 0.75),
    undetermined_grid: tuple[float, ...] = (0.5, 0.75),
    long_gamma_mult: float = 1.0,
    oos_fraction: float = 0.20,
    initial_cash: float = 100_000.0,
    n_folds: int = 5,
) -> list[SizingResult]:
    """Grid search regime multipliers with fixed pin weights."""
    results: list[SizingResult] = []
    for short_m in short_gamma_grid:
        for und_m in undetermined_grid:
            if long_gamma_mult < short_m:
                continue
            cfg = SizingConfig(
                pin=pin,
                long_gamma_mult=long_gamma_mult,
                short_gamma_mult=short_m,
                undetermined_mult=und_m,
            )
            results.append(
                evaluate_sizing(
                    trades,
                    cfg,
                    oos_fraction=oos_fraction,
                    initial_cash=initial_cash,
                    n_folds=n_folds,
                )
            )
    return mark_pareto_sizing(results)


def pick_stable_sizing(
    results: list[SizingResult],
    *,
    min_folds_positive: int = 3,
) -> SizingResult | None:
    viable = [r for r in results if r.folds_positive >= min_folds_positive]
    if not viable:
        return None
    return max(viable, key=lambda r: (r.oos_sharpe, r.median_fold_sharpe, r.max_drawdown))

