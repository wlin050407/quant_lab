"""Intraday pin / magnet evaluation (Phase 1 empirical validation).

Compares pin scores and magnet definitions at fixed session clocks
(10:00 / 13:00 / 15:30 ET) against the cash session close.

Industry references (2026-05 research):
- FlashAlpha magnet = argmax |NetGEX| on 0DTE book (flow-adjusted live;
  we use static OI at snapshot until flow pipeline exists).
- Max pain = static OI attractor; pin score adds gamma + time + proximity.
- Avellaneda–Lipkin / SpotGamma: pinning from dealer delta-hedging at
  concentrated gamma strikes, strongest in positive-gamma regime near expiry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from quant_lab.data.intraday_time import SESSION_HOURS, hours_to_close
from quant_lab.data.thetadata_chain import load_built_intraday_chain, list_intraday_chain_dates
from quant_lab.data.thetadata_intraday import PIN_PLAY_TIMES_ET
from quant_lab.data.thetadata_storage import load_parquet, spx_price_1m_path
from quant_lab.factors.gex import compute_gex_profile
from quant_lab.factors.ic import spearman_ic
from quant_lab.factors.pin_king_proximity import (
    StratumComparison,
    compare_pin_strata,
    pin_tier,
)
from quant_lab.factors.positioning import max_pain, pin_score_from_chain, top_oi_strike
from quant_lab.factors.regime import regime_from_net_gex

MagnetKind = Literal["king", "max_pain", "top_oi"]
DEFAULT_OPTION_ROOT = "SPXW"
MIN_CHAIN_ROWS = 50


@dataclass(frozen=True)
class IntradayPinRow:
    """One session × clock-time evaluation row."""

    session_date: date
    time_of_day: str
    spot: float
    close: float
    pin_score: float
    regime: str
    king: float
    max_pain_strike: float
    top_oi_strike: float
    expected_move_1sd: float
    magnet_strike: float
    abs_dist_king_pct: float
    abs_dist_max_pain_pct: float
    abs_dist_top_oi_pct: float
    within_em_king: bool
    pin_tier: str


@dataclass(frozen=True)
class MagnetAccuracySummary:
    """Naive closeness of session close to each magnet definition."""

    magnet: MagnetKind
    n: int
    median_abs_dist_pct: float
    mean_abs_dist_pct: float
    within_em_rate: float


@dataclass(frozen=True)
class TimeSlotSummary:
    """Pin IC and stratum test for one intraday clock."""

    time_of_day: str
    n: int
    spearman_ic: float
    high_pin_median_dist_pct: float
    low_pin_median_dist_pct: float
    comparison: StratumComparison


def session_time_to_close_pct(session_date: date, time_of_day: str) -> float:
    """0 at open → 100 at close (matches pin_score time factor)."""
    hrs = hours_to_close(session_date, time_of_day)
    return float(np.clip((1.0 - hrs / SESSION_HOURS) * 100.0, 0.0, 100.0))


def session_close_from_1m(session_date: date) -> float:
    """Last SPX 1m print at or before 16:00 ET."""
    path = spx_price_1m_path(session_date)
    if not path.is_file():
        return float("nan")
    bars = load_parquet(path)
    if bars.empty or "price" not in bars.columns:
        return float("nan")
    ts = pd.to_datetime(bars["timestamp"])
    if ts.dt.tz is None:
        from quant_lab.data.base import MARKET_TZ

        ts = ts.dt.tz_localize(MARKET_TZ)
    else:
        ts = ts.dt.tz_convert("America/New_York")
    bars = bars.assign(timestamp=ts)
    from quant_lab.data.intraday_time import session_datetime

    close_cutoff = session_datetime(session_date, "16:00:00")
    sub = bars[bars["timestamp"] <= close_cutoff]
    if sub.empty:
        return float("nan")
    return float(sub["price"].iloc[-1])


def _abs_dist_pct(close: float, strike: float) -> float:
    if not np.isfinite(close) or close <= 0 or not np.isfinite(strike):
        return float("nan")
    return float(abs(close - strike) / close * 100.0)


def evaluate_intraday_session(
    session_date: date,
    time_of_day: str,
    *,
    option_root: str = DEFAULT_OPTION_ROOT,
    dte_max: int = 1,
    oi_mode: str = "settled",
) -> IntradayPinRow | None:
    """Build one evaluation row; None if chain or close missing."""
    try:
        chain, meta = load_built_intraday_chain(session_date, time_of_day, option_root=option_root)
    except FileNotFoundError:
        return None

    if len(chain) < MIN_CHAIN_ROWS:
        return None

    spot = float("nan")
    if not meta.empty and "spot" in meta.columns:
        spot = float(meta["spot"].iloc[0])
    if not np.isfinite(spot):
        return None

    close = session_close_from_1m(session_date)
    if not np.isfinite(close) or close <= 0:
        return None

    time_pct = session_time_to_close_pct(session_date, time_of_day)
    pin_result = pin_score_from_chain(
        chain,
        spot,
        dte_max=dte_max,
        time_to_close_pct=time_pct,
        oi_mode=oi_mode,
    )
    from quant_lab.factors.effective_oi import chain_for_positioning

    work = chain_for_positioning(chain, oi_mode=oi_mode)
    profile = compute_gex_profile(work, spot, dte_max=dte_max, compute_flip=False)
    mp = max_pain(work, dte_max=dte_max)
    top_oi = top_oi_strike(work, dte_max=dte_max)
    king = profile.king_node
    from quant_lab.factors.positioning import atm_iv_from_chain, expected_move_1sd

    iv = atm_iv_from_chain(chain, spot, dte=dte_max)
    em_dollars = expected_move_1sd(spot, iv, dte=dte_max)

    dist_king = _abs_dist_pct(close, king)
    dist_mp = _abs_dist_pct(close, mp)
    dist_top = _abs_dist_pct(close, top_oi)

    return IntradayPinRow(
        session_date=session_date,
        time_of_day=time_of_day,
        spot=spot,
        close=close,
        pin_score=pin_result.score,
        regime=regime_from_net_gex(profile.net_gex),
        king=king,
        max_pain_strike=mp,
        top_oi_strike=top_oi,
        expected_move_1sd=em_dollars,
        magnet_strike=pin_result.magnet_strike,
        abs_dist_king_pct=dist_king,
        abs_dist_max_pain_pct=dist_mp,
        abs_dist_top_oi_pct=dist_top,
        within_em_king=bool(np.isfinite(em_dollars) and abs(close - king) <= em_dollars),
        pin_tier=pin_tier(pin_result.score),
    )


def build_intraday_pin_frame(
    *,
    times: tuple[str, ...] = PIN_PLAY_TIMES_ET,
    start: date | None = None,
    end: date | None = None,
    option_root: str = DEFAULT_OPTION_ROOT,
    oi_mode: str = "settled",
) -> pd.DataFrame:
    """Evaluate all available session × time slots."""
    rows: list[dict[str, object]] = []
    for iso in list_intraday_chain_dates(option_root=option_root):
        session = date.fromisoformat(iso)
        if start is not None and session < start:
            continue
        if end is not None and session > end:
            continue
        for tod in times:
            row = evaluate_intraday_session(session, tod, option_root=option_root, oi_mode=oi_mode)
            if row is None:
                continue
            rows.append(
                {
                    "date": pd.Timestamp(session),
                    "time_of_day": row.time_of_day,
                    "oi_mode": oi_mode,
                    "spot": row.spot,
                    "close": row.close,
                    "pin_score": row.pin_score,
                    "regime": row.regime,
                    "king": row.king,
                    "max_pain": row.max_pain_strike,
                    "top_oi": row.top_oi_strike,
                    "magnet_strike": row.magnet_strike,
                    "expected_move_1sd": row.expected_move_1sd,
                    "abs_dist_king_pct": row.abs_dist_king_pct,
                    "abs_dist_max_pain_pct": row.abs_dist_max_pain_pct,
                    "abs_dist_top_oi_pct": row.abs_dist_top_oi_pct,
                    "within_em_king": row.within_em_king,
                    "pin_tier": row.pin_tier,
                    "king_eq_max_pain": bool(
                        np.isfinite(row.king)
                        and np.isfinite(row.max_pain_strike)
                        and row.king == row.max_pain_strike
                    ),
                    "king_eq_top_oi": bool(
                        np.isfinite(row.king) and np.isfinite(row.top_oi_strike) and row.king == row.top_oi_strike
                    ),
                }
            )
    return pd.DataFrame(rows)


def summarize_magnet_accuracy(frame: pd.DataFrame) -> pd.DataFrame:
    """Which magnet definition is closest to close (naive hit rate)."""
    mapping: dict[MagnetKind, tuple[str, str]] = {
        "king": ("abs_dist_king_pct", "king"),
        "max_pain": ("abs_dist_max_pain_pct", "max_pain"),
        "top_oi": ("abs_dist_top_oi_pct", "top_oi"),
    }
    rows: list[dict[str, float | str | int]] = []
    em = frame["expected_move_1sd"].astype("float64")
    for magnet, (col, strike_col) in mapping.items():
        dist = frame[col].astype("float64").dropna()
        strike = frame.loc[dist.index, strike_col].astype("float64")
        close = frame.loc[dist.index, "close"].astype("float64")
        within = (close - strike).abs() <= em.loc[dist.index]
        rows.append(
            {
                "magnet": magnet,
                "n": len(dist),
                "median_abs_dist_pct": float(dist.median()) if len(dist) else float("nan"),
                "mean_abs_dist_pct": float(dist.mean()) if len(dist) else float("nan"),
                "within_em_rate": float(within.mean()) if len(within) else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def summarize_by_time_slot(frame: pd.DataFrame) -> list[TimeSlotSummary]:
    """Pin IC and high/low pin strata for each clock time."""
    out: list[TimeSlotSummary] = []
    for tod, grp in frame.groupby("time_of_day", sort=True):
        work = grp.dropna(subset=["pin_score", "abs_dist_king_pct"]).copy()
        if work.empty:
            continue
        ic, _ = spearman_ic(work["pin_score"], -work["abs_dist_king_pct"])
        comp_frame = work.rename(columns={"abs_dist_king_pct": "abs_dist_pct"})
        comp = compare_pin_strata(
            comp_frame,
            mode="same_day",
            valid_only=False,
            regime="long_gamma",
        )
        out.append(
            TimeSlotSummary(
                time_of_day=str(tod),
                n=len(work),
                spearman_ic=float(ic),
                high_pin_median_dist_pct=comp.high_median_abs_dist_pct,
                low_pin_median_dist_pct=comp.low_median_abs_dist_pct,
                comparison=comp,
            )
        )
    return out


def best_magnet_per_row(frame: pd.DataFrame) -> pd.Series:
    """Which magnet was closest to close on each row."""
    cols = {
        "king": "abs_dist_king_pct",
        "max_pain": "abs_dist_max_pain_pct",
        "top_oi": "abs_dist_top_oi_pct",
    }
    dist = frame[list(cols.values())].astype("float64")
    idx = dist.idxmin(axis=1)
    inv = {v: k for k, v in cols.items()}
    return idx.map(inv)
