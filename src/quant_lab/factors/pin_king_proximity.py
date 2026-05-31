"""Pin score → King proximity metrics (Phase 3e).

Measures whether high ``pin_score`` days see underlying close land nearer
``king_dte1`` than low-pin days.  Supports:

- ``same_day``: EoD spot vs same-day King (descriptive; uses closing OI book).
- ``next_session``: signal at EoD *t* → outcome close on next session *t+1*
  vs ``king_dte1`` at *t* (aligns with EoD backtest signal timing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from quant_lab.factors.ic import spearman_ic

ProximityMode = Literal["same_day", "next_session"]
PinTier = Literal["high", "mid", "low", "unknown"]

MIN_DTE1_CONTRACTS = 50


@dataclass(frozen=True)
class StratumComparison:
    """Mann-Whitney comparison of proximity between pin strata."""

    mode: ProximityMode
    high_label: str
    low_label: str
    high_n: int
    low_n: int
    high_median_abs_dist_pct: float
    low_median_abs_dist_pct: float
    u_statistic: float
    p_value: float
    alternative: str

    @property
    def passes_median_test(self) -> bool:
        """High-pin median distance strictly less than low-pin, p < 0.05."""
        if not np.isfinite(self.p_value):
            return False
        return (
            self.high_median_abs_dist_pct < self.low_median_abs_dist_pct
            and self.p_value < 0.05
        )


@dataclass(frozen=True)
class Phase3eGate:
    """Exit criteria from docs/PIN_PLAY_SPEC.md § Phase 3e."""

    high_pin_long_gamma_n: int
    min_high_pin_long_gamma_n: int
    comparison: StratumComparison
    spearman_ic_pin_vs_neg_dist: float
    spearman_n: int

    @property
    def passes_sample_size(self) -> bool:
        return self.high_pin_long_gamma_n >= self.min_high_pin_long_gamma_n

    @property
    def passes(self) -> bool:
        return self.passes_sample_size and self.comparison.passes_median_test


def pin_tier(pin_score: float) -> PinTier:
    if not np.isfinite(pin_score):
        return "unknown"
    if pin_score >= 70.0:
        return "high"
    if pin_score >= 50.0:
        return "mid"
    return "low"


def _normalize_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.normalize()


def _underlying_close_series(underlying: pd.DataFrame, *, price_col: str = "close") -> pd.Series:
    if not isinstance(underlying.index, pd.DatetimeIndex):
        raise ValueError("underlying must have a DatetimeIndex")
    close = underlying[price_col].astype("float64").copy()
    if close.index.tz is not None:
        close.index = close.index.tz_convert(None)
    close.index = close.index.normalize()
    return close[~close.index.duplicated(keep="last")].sort_index()


def _next_session_close(close: pd.Series) -> pd.Series:
    """Map each session date to the following session's close."""
    out = close.shift(-1)
    out.name = "close_next"
    return out


def build_proximity_frame(
    terminal: pd.DataFrame,
    underlying: pd.DataFrame,
    *,
    mode: ProximityMode = "next_session",
    min_dte1_contracts: int = MIN_DTE1_CONTRACTS,
    price_col: str = "close",
) -> pd.DataFrame:
    """Join terminal history to outcome close and compute King distance metrics."""
    if terminal.empty:
        raise ValueError("terminal history is empty")

    required = {"date", "spot", "king_dte1", "pin_score", "regime", "n_contracts_dte1"}
    missing = required - set(terminal.columns)
    if missing:
        raise ValueError(f"terminal missing columns: {sorted(missing)}")

    term = terminal.copy()
    term["date"] = _normalize_dates(term["date"])
    term = term.sort_values("date").reset_index(drop=True)

    close = _underlying_close_series(underlying, price_col=price_col)
    close_df = close.rename("close_same").reset_index()
    close_df.columns = ["date", "close_same"]
    close_df["date"] = _normalize_dates(close_df["date"])

    next_close = _next_session_close(close).reset_index()
    next_close.columns = ["date", "close_next"]
    next_close["date"] = _normalize_dates(next_close["date"])

    merged = term.merge(close_df, on="date", how="left")
    merged = merged.merge(next_close, on="date", how="left")

    if mode == "same_day":
        merged["outcome_close"] = merged["close_same"]
    elif mode == "next_session":
        merged["outcome_close"] = merged["close_next"]
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    king = merged["king_dte1"].astype("float64")
    outcome = merged["outcome_close"].astype("float64")
    merged["abs_dist_pts"] = (outcome - king).abs()
    merged["abs_dist_pct"] = np.where(
        outcome > 0,
        merged["abs_dist_pts"] / outcome * 100.0,
        np.nan,
    )
    merged["signed_dist_pct"] = np.where(
        outcome > 0,
        (outcome - king) / outcome * 100.0,
        np.nan,
    )

    em = merged.get("expected_move_1sd")
    if em is not None:
        em = em.astype("float64")
        merged["within_em"] = merged["abs_dist_pts"] <= em
        merged["within_half_em"] = merged["abs_dist_pts"] <= (0.5 * em)
    else:
        merged["within_em"] = False
        merged["within_half_em"] = False

    merged["pin_tier"] = merged["pin_score"].map(lambda x: pin_tier(float(x)))
    merged["valid"] = (
        np.isfinite(king)
        & np.isfinite(outcome)
        & (outcome > 0)
        & (merged["n_contracts_dte1"] >= min_dte1_contracts)
    )
    merged["mode"] = mode
    return merged


def summarize_by_stratum(
    frame: pd.DataFrame,
    *,
    valid_only: bool = True,
) -> pd.DataFrame:
    """Aggregate proximity metrics by pin_tier and regime."""
    work = frame.copy()
    if valid_only:
        work = work.loc[work["valid"]]

    rows: list[dict[str, object]] = []
    group_cols = ["pin_tier", "regime"]
    for keys, group in work.groupby(group_cols, dropna=False):
        pin_t, regime = keys if isinstance(keys, tuple) else (keys, "")
        dist = group["abs_dist_pct"].dropna()
        rows.append(
            {
                "pin_tier": pin_t,
                "regime": regime,
                "n": len(group),
                "median_abs_dist_pct": float(dist.median()) if len(dist) else float("nan"),
                "mean_abs_dist_pct": float(dist.mean()) if len(dist) else float("nan"),
                "within_em_rate": float(group["within_em"].mean()) if len(group) else float("nan"),
                "within_half_em_rate": float(group["within_half_em"].mean())
                if len(group)
                else float("nan"),
            }
        )
    return pd.DataFrame(rows).sort_values(["pin_tier", "regime"]).reset_index(drop=True)


def compare_pin_strata(
    frame: pd.DataFrame,
    *,
    mode: ProximityMode,
    high_pin_min: float = 70.0,
    low_pin_max: float = 50.0,
    regime: str | None = "long_gamma",
    valid_only: bool = True,
    alternative: str = "less",
) -> StratumComparison:
    """Compare proximity: high pin (≥70) vs low pin (<50), optional regime filter."""
    work = frame.copy()
    if valid_only:
        work = work.loc[work["valid"]]

    high = work.loc[work["pin_score"] >= high_pin_min, "abs_dist_pct"].dropna()
    low = work.loc[work["pin_score"] < low_pin_max, "abs_dist_pct"].dropna()

    high_label = f"pin>={high_pin_min:.0f}"
    low_label = f"pin<{low_pin_max:.0f}"
    if regime is not None:
        work_reg = work.loc[work["regime"] == regime]
        high = work_reg.loc[work_reg["pin_score"] >= high_pin_min, "abs_dist_pct"].dropna()
        low = work.loc[work["pin_score"] < low_pin_max, "abs_dist_pct"].dropna()
        high_label = f"{high_label}+{regime}"
        # Low-pin control: all regimes (broader control per spec)
        low = work.loc[work["pin_score"] < low_pin_max, "abs_dist_pct"].dropna()

    if len(high) < 2 or len(low) < 2:
        return StratumComparison(
            mode=mode,
            high_label=high_label,
            low_label=low_label,
            high_n=len(high),
            low_n=len(low),
            high_median_abs_dist_pct=float(high.median()) if len(high) else float("nan"),
            low_median_abs_dist_pct=float(low.median()) if len(low) else float("nan"),
            u_statistic=float("nan"),
            p_value=float("nan"),
            alternative=alternative,
        )

    result = mannwhitneyu(high, low, alternative=alternative)
    return StratumComparison(
        mode=mode,
        high_label=high_label,
        low_label=low_label,
        high_n=len(high),
        low_n=len(low),
        high_median_abs_dist_pct=float(high.median()),
        low_median_abs_dist_pct=float(low.median()),
        u_statistic=float(result.statistic),
        p_value=float(result.pvalue),
        alternative=alternative,
    )


def proximity_ic(frame: pd.DataFrame, *, valid_only: bool = True) -> tuple[float, int]:
    """Spearman IC: pin_score vs -abs_dist_pct (expect positive if pin works)."""
    work = frame.copy()
    if valid_only:
        work = work.loc[work["valid"]]
    neg_dist = -work["abs_dist_pct"]
    return spearman_ic(work["pin_score"], neg_dist)


def evaluate_phase3e_gate(
    frame: pd.DataFrame,
    *,
    mode: ProximityMode,
    min_high_pin_long_gamma_n: int = 200,
) -> Phase3eGate:
    """Evaluate Phase 3e exit criteria on a proximity frame."""
    work = frame.loc[frame["valid"]].copy()
    high_n = int(
        (
            (work["pin_score"] >= 70.0)
            & (work["regime"] == "long_gamma")
        ).sum()
    )
    comparison = compare_pin_strata(frame, mode=mode, regime="long_gamma")
    ic, n = proximity_ic(frame)
    return Phase3eGate(
        high_pin_long_gamma_n=high_n,
        min_high_pin_long_gamma_n=min_high_pin_long_gamma_n,
        comparison=comparison,
        spearman_ic_pin_vs_neg_dist=ic,
        spearman_n=n,
    )
