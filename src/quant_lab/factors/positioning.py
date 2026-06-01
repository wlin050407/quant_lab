"""Positioning factors from a single EoD option-chain snapshot.

These complement `factors/gex.py`: GEX tells you *how* dealer hedging behaves;
positioning factors tell you *where* OI is concentrated and what the crowd
is betting.

All functions are stateless: chain DataFrame in, scalar or small DataFrame out.
No I/O, no network (per module boundary in AGENTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_lab.factors.gex import (
    add_bs_gamma_column,
    compute_dealer_gamma_exposure,
    compute_gex_profile,
    filter_chain_by_dte,
    max_abs_net_gex_bn,
    net_gex_at_strike,
    net_gex_bn_per_1pct,
    pct_dte_cohort_of_total,
)
from quant_lab.data.intraday_time import (
    SESSION_HOURS,
    TRADING_DAYS_PER_YEAR,
    pin_time_remaining_score,
)
from quant_lab.factors.effective_oi import chain_for_positioning

# Bump when pin inputs / weighting change materially (surfaced in terminal ``meta``).
PIN_SCORE_MODEL_VERSION = "v2"

# FlashAlpha pin-risk weights (https://flashalpha.com/concepts/pin-risk)
PIN_WEIGHT_OI = 0.30
PIN_WEIGHT_PROXIMITY = 0.25
PIN_WEIGHT_TIME = 0.25
PIN_WEIGHT_GAMMA = 0.20

# Sub-score saturation (calibrated on SPY dte≤1 history; revisit with FlashAlpha API)
PIN_OI_SATURATION = 0.45
PIN_GAMMA_REF_BN = 2.0
PIN_PROXIMITY_FALLBACK_PCT = 0.015
PIN_PROXIMITY_EM_HALF_WIDTH = 0.5
PIN_TIME_CURVE_EXPONENT = 0.65
PIN_MAGNET_DIVERGE_SAT_PCT = 0.015
PIN_MAGNET_DIVERGE_MAX_PENALTY = 0.20
PIN_COHORT_PCT_REF = 40.0
PIN_COHORT_FLOOR_MULT = 0.40


@dataclass(frozen=True)
class PinScoreResult:
    """Pin / magnet prediction bundle (FlashAlpha-aligned semantics)."""

    score: float
    magnet_strike: float
    max_pain_strike: float
    distance_to_magnet_pct: float
    magnet_gex_bn: float
    components: dict[str, float]
    adjustments: dict[str, float]


def oi_by_strike(chain: pd.DataFrame) -> pd.DataFrame:
    """Open interest aggregated by strike, calls and puts split.

    Returns:
        DataFrame indexed by strike with columns
        `call_oi`, `put_oi`, `total_oi` (int64).
    """
    required = {"strike", "right", "open_interest"}
    missing = required - set(chain.columns)
    if missing:
        raise ValueError(f"chain missing columns: {sorted(missing)}")

    if chain.empty:
        out = pd.DataFrame(columns=["call_oi", "put_oi", "total_oi"])
        out.index.name = "strike"
        return out

    work = chain[["strike", "right", "open_interest"]].copy()
    work["open_interest"] = pd.to_numeric(work["open_interest"], errors="coerce").fillna(0).astype("float64")
    pivot = work.pivot_table(
        index="strike",
        columns="right",
        values="open_interest",
        aggfunc="sum",
        fill_value=0.0,
    )
    call_oi = pivot.get("C", pd.Series(0.0, index=pivot.index))
    put_oi = pivot.get("P", pd.Series(0.0, index=pivot.index))
    out = pd.DataFrame(
        {
            "call_oi": call_oi.round().astype("int64"),
            "put_oi": put_oi.round().astype("int64"),
        },
        index=pivot.index,
    )
    out["total_oi"] = out["call_oi"] + out["put_oi"]
    return out.sort_index()


def put_call_ratio(
    chain: pd.DataFrame,
    *,
    kind: str = "open_interest",
) -> float:
    """Put / call ratio for volume or open interest.

    Args:
        chain: option chain with `right` and the chosen column.
        kind: ``"open_interest"`` or ``"volume"``.

    Returns:
        puts / calls. NaN if call side is zero.
    """
    if kind not in ("open_interest", "volume"):
        raise ValueError(f"kind must be 'open_interest' or 'volume', got {kind!r}")
    if kind not in chain.columns:
        raise ValueError(f"chain missing column {kind!r}")

    calls = chain.loc[chain["right"] == "C", kind].sum()
    puts = chain.loc[chain["right"] == "P", kind].sum()
    if calls == 0:
        return float("nan")
    return float(puts / calls)


def max_pain(
    chain: pd.DataFrame,
    *,
    dte_max: int | None = None,
) -> float:
    """Strike that minimizes total option-holder ITM payout at expiry.

    For each candidate settlement price ``S``, we sum dollar payout across
    all contracts:

        calls: max(S - K, 0) × OI × 100
        puts:  max(K - S, 0) × OI × 100

    The strike (from the set of listed strikes) with the minimum total payout
    is max pain. This is the classic "pin" level dealers prefer because it
    minimizes their hedging obligation at expiry.

    Args:
        chain: full chain; needs `strike`, `right`, `open_interest`.
        dte_max: if set, only include rows with ``dte <= dte_max`` (e.g. 1
            for near-expiry / 0DTE cohort).

    Returns:
        Max-pain strike (float), or NaN if the chain is empty after filtering.
    """
    required = {"strike", "right", "open_interest"}
    missing = required - set(chain.columns)
    if missing:
        raise ValueError(f"chain missing columns: {sorted(missing)}")

    work = chain.copy()
    if dte_max is not None:
        if "dte" not in work.columns:
            raise ValueError("dte_max filter requires a 'dte' column")
        work = work[work["dte"] <= dte_max]
    if work.empty:
        return float("nan")

    strikes = np.sort(work["strike"].unique())
    if len(strikes) == 0:
        return float("nan")

    calls = work[work["right"] == "C"][["strike", "open_interest"]]
    puts = work[work["right"] == "P"][["strike", "open_interest"]]

    call_k = calls["strike"].to_numpy(dtype="float64")
    call_oi = calls["open_interest"].to_numpy(dtype="float64")
    put_k = puts["strike"].to_numpy(dtype="float64")
    put_oi = puts["open_interest"].to_numpy(dtype="float64")

    min_payout = float("inf")
    best_strike = float("nan")
    for s in strikes:
        call_pay = np.maximum(s - call_k, 0.0) * call_oi
        put_pay = np.maximum(put_k - s, 0.0) * put_oi
        total = float((call_pay.sum() + put_pay.sum()) * 100)
        if total < min_payout:
            min_payout = total
            best_strike = float(s)

    return best_strike


def oi_concentration(
    chain: pd.DataFrame,
    *,
    top_n: int = 5,
    dte_max: int | None = None,
) -> float:
    """Fraction of total OI held in the top-N strikes by combined OI.

    High concentration → pinning risk is localized; low concentration → OI
    is spread out and max-pain / flip signals are noisier.

    Args:
        chain: option chain.
        top_n: number of largest-OI strikes to include in the numerator.
        dte_max: optional filter (e.g. 1 for next-day 0DTE cohort).

    Returns:
        Ratio in [0, 1], or NaN if total OI is zero.
    """
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    work = chain.copy()
    if dte_max is not None:
        if "dte" not in work.columns:
            raise ValueError("dte_max filter requires a 'dte' column")
        work = work[work["dte"] <= dte_max]
    if work.empty:
        return float("nan")

    by_strike = oi_by_strike(work)
    total = int(by_strike["total_oi"].sum())
    if total == 0:
        return float("nan")

    top = int(by_strike["total_oi"].nlargest(min(top_n, len(by_strike))).sum())
    return float(top / total)


def top_oi_strike(
    chain: pd.DataFrame,
    *,
    dte_max: int | None = None,
) -> float:
    """Strike with the highest combined call + put open interest."""
    work = chain.copy()
    if dte_max is not None:
        if "dte" not in work.columns:
            raise ValueError("dte_max filter requires a 'dte' column")
        work = work[work["dte"] <= dte_max]
    if work.empty:
        return float("nan")
    by_strike = oi_by_strike(work)
    if by_strike.empty or int(by_strike["total_oi"].sum()) == 0:
        return float("nan")
    return float(by_strike["total_oi"].idxmax())


def resolve_cohort_time_years(
    chain: pd.DataFrame,
    *,
    dte_max: int | None = 1,
    hours_to_close: float | None = None,
    trading_days_per_year: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Year fraction for EM / IV on a 0DTE cohort (``dte <= dte_max``).

    Prefers per-row ``time_to_expiry_years`` (ThetaData intraday). Falls back to
    remaining session hours, then calendar ``dte`` (EoD ``dte=0`` uses ~1 trading
    hour, aligned with ``gex.effective_time_to_expiry_years``).
    """
    if chain.empty:
        return float("nan")

    work = chain
    if dte_max is not None and "dte" in chain.columns:
        filtered = chain[chain["dte"] <= dte_max]
        if not filtered.empty:
            work = filtered

    if "time_to_expiry_years" in work.columns:
        t = pd.to_numeric(work["time_to_expiry_years"], errors="coerce")
        positive = t[t > 0]
        if not positive.empty:
            return float(positive.median())

    if hours_to_close is not None and np.isfinite(hours_to_close) and hours_to_close > 0:
        return float(hours_to_close / (trading_days_per_year * SESSION_HOURS))

    if "dte" not in work.columns:
        return float("nan")

    dte_min = int(pd.to_numeric(work["dte"], errors="coerce").min())
    if dte_min <= 0:
        return float(1.0 / (trading_days_per_year * SESSION_HOURS))
    return float(max(dte_min, 1) / trading_days_per_year)


def expected_move_1sd(
    spot: float,
    atm_iv: float,
    *,
    dte: int | None = 1,
    time_years: float | None = None,
    trading_days_per_year: int = 365,
) -> float:
    """One standard-deviation expected move in dollars (straddle-implied proxy).

    ``EM = spot × IV × sqrt(T)``. Prefer ``time_years`` (intraday 0DTE); else
    ``dte / trading_days_per_year`` for EoD snapshots.
    """
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(atm_iv) or atm_iv <= 0:
        return float("nan")
    if time_years is not None and np.isfinite(time_years) and time_years > 0:
        t = float(time_years)
    elif dte is not None and dte > 0:
        t = dte / trading_days_per_year
    else:
        return float("nan")
    return float(spot * atm_iv * np.sqrt(t))


def _iv_cohort(
    chain: pd.DataFrame,
    *,
    dte: int | None = None,
    dte_max: int | None = None,
) -> pd.DataFrame:
    """Rows used for ATM IV (0DTE bucket ``dte<=1`` when ``dte`` is 0 or 1)."""
    if dte_max is not None:
        if "dte" not in chain.columns:
            raise ValueError("dte_max filter requires a 'dte' column")
        out = chain[chain["dte"] <= dte_max]
        return out.copy() if not out.empty else chain.copy()
    if dte is not None:
        if "dte" not in chain.columns:
            raise ValueError("dte filter requires a 'dte' column")
        if dte <= 1:
            out = chain[chain["dte"] <= 1]
            if not out.empty:
                return out.copy()
        return chain[chain["dte"] == dte].copy()
    return chain.copy()


def atm_iv_from_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    dte: int | None = 1,
    dte_max: int | None = None,
    min_iv: float = 0.05,
    max_iv: float = 3.0,
) -> float:
    """Nearest-strike ATM implied vol for a cohort (``dte_max`` or ``dte`` bucket)."""
    if chain.empty or "implied_volatility" not in chain.columns:
        return float("nan")
    cohort = _iv_cohort(chain, dte=dte, dte_max=dte_max)
    if cohort.empty:
        return float("nan")
    cohort = cohort.assign(dist=(cohort["strike"].astype("float64") - spot).abs())
    row = cohort.loc[cohort["dist"].idxmin()]
    iv = float(row["implied_volatility"])
    if not np.isfinite(iv) or iv < min_iv or iv > max_iv:
        return float("nan")
    return iv


def oi_concentration_near_magnet(
    chain: pd.DataFrame,
    magnet_strike: float,
    spot: float,
    *,
    dte_max: int | None = None,
    band_pct: float = 0.005,
) -> float:
    """Fraction of cohort OI within ``band_pct × spot`` dollars of the magnet strike."""
    if not np.isfinite(magnet_strike) or not np.isfinite(spot) or spot <= 0:
        return float("nan")
    work = chain.copy()
    if dte_max is not None:
        if "dte" not in work.columns:
            raise ValueError("dte_max filter requires a 'dte' column")
        work = work[work["dte"] <= dte_max]
    if work.empty:
        return float("nan")
    band = max(spot * band_pct, 0.5)
    near = work[work["strike"].astype("float64").sub(magnet_strike).abs() <= band]
    total_oi = pd.to_numeric(work["open_interest"], errors="coerce").fillna(0).sum()
    if total_oi <= 0:
        return float("nan")
    near_oi = pd.to_numeric(near["open_interest"], errors="coerce").fillna(0).sum()
    return float(near_oi / total_oi)


def _time_remaining_score(
    time_to_close_pct: float | None = None,
    *,
    hours_to_close: float | None = None,
) -> float:
    """0 at open → 100 at close; prefers ``hours_to_close`` when provided."""
    if hours_to_close is not None and np.isfinite(hours_to_close):
        return pin_time_remaining_score(float(hours_to_close))
    pct = 100.0 if time_to_close_pct is None else float(time_to_close_pct)
    hrs = SESSION_HOURS * (1.0 - np.clip(pct, 0.0, 100.0) / 100.0)
    return pin_time_remaining_score(hrs)


def _proximity_score(
    spot: float,
    magnet_strike: float,
    *,
    expected_move_1sd: float | None,
) -> tuple[float, float]:
    """Return (proximity sub-score 0–100, distance_to_magnet_pct)."""
    if not np.isfinite(magnet_strike):
        return 0.0, float("nan")
    dist_pct = abs(spot - magnet_strike) / spot * 100.0
    dist_frac = dist_pct / 100.0
    if expected_move_1sd is not None and np.isfinite(expected_move_1sd) and expected_move_1sd > 0:
        em_frac = expected_move_1sd / spot
        denom = max(PIN_PROXIMITY_EM_HALF_WIDTH * em_frac, 1e-6)
        prox = float(np.clip(1.0 - dist_frac / denom, 0.0, 1.0) * 100.0)
    else:
        prox = float(np.clip(1.0 - dist_frac / PIN_PROXIMITY_FALLBACK_PCT, 0.0, 1.0) * 100.0)
    return prox, dist_pct


def _gamma_magnitude_score(
    magnet_gex_bn: float,
    *,
    max_gex_bn_reference: float | None,
) -> float:
    if not np.isfinite(magnet_gex_bn):
        return 0.0
    ref = (
        max_gex_bn_reference
        if max_gex_bn_reference is not None and np.isfinite(max_gex_bn_reference) and max_gex_bn_reference > 0
        else PIN_GAMMA_REF_BN
    )
    return float(np.clip(abs(magnet_gex_bn) / ref, 0.0, 1.0) * 100.0)


def _oi_concentration_score(
    oi_concentration_top3: float,
    oi_near_magnet: float | None,
) -> float:
    conc = oi_concentration_top3 if np.isfinite(oi_concentration_top3) else 0.0
    top3_score = float(np.clip(conc / PIN_OI_SATURATION, 0.0, 1.0) * 100.0)
    if oi_near_magnet is not None and np.isfinite(oi_near_magnet):
        band_score = float(np.clip(oi_near_magnet / 0.35, 0.0, 1.0) * 100.0)
        return 0.85 * top3_score + 0.15 * band_score
    return top3_score


def _magnet_agreement_multiplier(
    magnet_strike: float,
    max_pain_strike: float | None,
    spot: float,
) -> float:
    if max_pain_strike is None or not np.isfinite(max_pain_strike) or not np.isfinite(magnet_strike):
        return 1.0
    diverge_frac = abs(magnet_strike - max_pain_strike) / spot
    penalty = float(np.clip(diverge_frac / PIN_MAGNET_DIVERGE_SAT_PCT, 0.0, 1.0) * PIN_MAGNET_DIVERGE_MAX_PENALTY)
    return 1.0 - penalty


def _cohort_multiplier(pct_gex_dte1: float | None) -> float:
    if pct_gex_dte1 is None or not np.isfinite(pct_gex_dte1):
        return 1.0
    share = float(np.clip(pct_gex_dte1 / PIN_COHORT_PCT_REF, 0.0, 1.0))
    return PIN_COHORT_FLOOR_MULT + (1.0 - PIN_COHORT_FLOOR_MULT) * share


def pin_score_components(
    *,
    spot: float,
    magnet_strike: float,
    oi_concentration_top3: float,
    magnet_gex_bn_per_1pct: float,
    time_to_close_pct: float | None = None,
    hours_to_close: float | None = None,
    expected_move_1sd: float | None = None,
    max_gex_bn_reference: float | None = None,
    max_pain_strike: float | None = None,
    pct_gex_dte1: float | None = None,
    oi_near_magnet: float | None = None,
    net_gex_bn_per_1pct: float | None = None,
) -> dict[str, float]:
    """Sub-scores (0–100) for each ``pin_score`` term (FlashAlpha field semantics).

    ``magnet_gex_bn_per_1pct`` is **|net GEX at the magnet strike|**, not whole-book net.
    ``net_gex_bn_per_1pct`` is accepted only as a legacy fallback when magnet GEX is missing.
    """
    if not np.isfinite(spot) or spot <= 0:
        return {
            "oi_concentration": float("nan"),
            "magnet_proximity": float("nan"),
            "time_remaining": float("nan"),
            "gamma_magnitude": float("nan"),
            "distance_to_magnet_pct": float("nan"),
        }

    magnet_bn = magnet_gex_bn_per_1pct
    if not np.isfinite(magnet_bn) and net_gex_bn_per_1pct is not None:
        magnet_bn = net_gex_bn_per_1pct

    prox_score, dist_pct = _proximity_score(
        spot, magnet_strike, expected_move_1sd=expected_move_1sd
    )

    parts: dict[str, float] = {
        "oi_concentration": _oi_concentration_score(oi_concentration_top3, oi_near_magnet),
        "magnet_proximity": prox_score,
        "time_remaining": _time_remaining_score(time_to_close_pct, hours_to_close=hours_to_close),
        "gamma_magnitude": _gamma_magnitude_score(
            magnet_bn if np.isfinite(magnet_bn) else float("nan"),
            max_gex_bn_reference=max_gex_bn_reference,
        ),
        "distance_to_magnet_pct": dist_pct,
        "magnet_agreement_mult": _magnet_agreement_multiplier(magnet_strike, max_pain_strike, spot),
        "cohort_mult": _cohort_multiplier(pct_gex_dte1),
    }
    return parts


def pin_score(
    *,
    spot: float,
    magnet_strike: float,
    oi_concentration_top3: float,
    magnet_gex_bn_per_1pct: float | None = None,
    time_to_close_pct: float | None = None,
    hours_to_close: float | None = None,
    expected_move_1sd: float | None = None,
    max_gex_bn_reference: float | None = None,
    max_pain_strike: float | None = None,
    pct_gex_dte1: float | None = None,
    oi_near_magnet: float | None = None,
    net_gex_bn_per_1pct: float | None = None,
) -> float:
    """Composite pin-risk score 0–100 (FlashAlpha ``pin_score`` alignment).

    Weights:
        OI concentration (top-3 + magnet band)  30%
        magnet proximity (EM-relative)        25%
        time remaining (nonlinear to close)   25%
        gamma magnitude at magnet strike      20%

    Post-composite adjustments (not in FlashAlpha API breakdown):
        magnet agreement (King vs max pain)   up to −20%
        0DTE GEX cohort share                 floor 0.4× when pct→0
    """
    if magnet_gex_bn_per_1pct is None and net_gex_bn_per_1pct is None:
        raise ValueError("pin_score requires magnet_gex_bn_per_1pct (or legacy net_gex_bn_per_1pct)")

    parts = pin_score_components(
        spot=spot,
        magnet_strike=magnet_strike,
        oi_concentration_top3=oi_concentration_top3,
        magnet_gex_bn_per_1pct=magnet_gex_bn_per_1pct if magnet_gex_bn_per_1pct is not None else float("nan"),
        time_to_close_pct=time_to_close_pct,
        hours_to_close=hours_to_close,
        expected_move_1sd=expected_move_1sd,
        max_gex_bn_reference=max_gex_bn_reference,
        max_pain_strike=max_pain_strike,
        pct_gex_dte1=pct_gex_dte1,
        oi_near_magnet=oi_near_magnet,
        net_gex_bn_per_1pct=net_gex_bn_per_1pct,
    )
    if not np.isfinite(parts["oi_concentration"]):
        return float("nan")
    raw = (
        PIN_WEIGHT_OI * parts["oi_concentration"]
        + PIN_WEIGHT_PROXIMITY * parts["magnet_proximity"]
        + PIN_WEIGHT_TIME * parts["time_remaining"]
        + PIN_WEIGHT_GAMMA * parts["gamma_magnitude"]
    )
    adjusted = raw * parts["magnet_agreement_mult"] * parts["cohort_mult"]
    return float(np.clip(adjusted, 0.0, 100.0))


def pin_score_from_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    dte_max: int = 1,
    time_to_close_pct: float | None = None,
    hours_to_close: float | None = None,
    pct_gex_dte1: float | None = None,
    oi_mode: str = "settled",
    r: float = 0.05,
    q: float = 0.013,
) -> PinScoreResult:
    """Compute pin score + magnet metadata from a single chain snapshot.

    ``oi_mode='effective'`` uses ``effective_open_interest`` (flow-adjusted) for
    GEX, max pain, and OI concentration — aligned with FlashAlpha flow pin-risk.
    """
    if chain.empty or not np.isfinite(spot) or spot <= 0:
        nan_parts = pin_score_components(
            spot=float("nan"),
            magnet_strike=float("nan"),
            oi_concentration_top3=float("nan"),
            magnet_gex_bn_per_1pct=float("nan"),
        )
        return PinScoreResult(
            score=float("nan"),
            magnet_strike=float("nan"),
            max_pain_strike=float("nan"),
            distance_to_magnet_pct=float("nan"),
            magnet_gex_bn=float("nan"),
            components=nan_parts,
            adjustments={"magnet_agreement_mult": 1.0, "cohort_mult": 1.0},
        )

    work = chain_for_positioning(chain, oi_mode=oi_mode)

    sym = str(work["symbol"].iloc[0]) if "symbol" in work.columns and not work.empty else None
    profile_all = compute_gex_profile(
        work, spot, symbol=sym, dte_max=None, r=r, q=q, compute_flip=False
    )
    profile = compute_gex_profile(
        work, spot, symbol=sym, dte_max=dte_max, r=r, q=q, compute_flip=False
    )

    cohort = filter_chain_by_dte(work, dte_max=dte_max)
    with_gamma = add_bs_gamma_column(cohort, spot, r=r, q=q)
    per_strike = compute_dealer_gamma_exposure(with_gamma, spot)

    mp = max_pain(work, dte_max=dte_max)
    conc = oi_concentration(work, top_n=3, dte_max=dte_max)
    t_years = resolve_cohort_time_years(
        work, dte_max=dte_max, hours_to_close=hours_to_close
    )
    iv = atm_iv_from_chain(work, spot, dte_max=dte_max)
    em = expected_move_1sd(spot, iv, time_years=t_years, dte=1)

    magnet = profile.king_node if np.isfinite(profile.king_node) else mp
    if not np.isfinite(magnet):
        magnet = mp

    magnet_gex = net_gex_at_strike(per_strike, magnet) if np.isfinite(magnet) else float("nan")
    magnet_bn = net_gex_bn_per_1pct(magnet_gex) if np.isfinite(magnet_gex) else float("nan")
    max_ref = max_abs_net_gex_bn(per_strike)
    near_oi = (
        oi_concentration_near_magnet(work, magnet, spot, dte_max=dte_max)
        if np.isfinite(magnet)
        else float("nan")
    )

    if pct_gex_dte1 is None:
        pct_gex_dte1 = pct_dte_cohort_of_total(profile.net_gex, profile_all.net_gex)

    parts = pin_score_components(
        spot=spot,
        magnet_strike=magnet,
        oi_concentration_top3=conc if np.isfinite(conc) else 0.0,
        magnet_gex_bn_per_1pct=magnet_bn,
        time_to_close_pct=time_to_close_pct,
        hours_to_close=hours_to_close,
        expected_move_1sd=em,
        max_gex_bn_reference=max_ref,
        max_pain_strike=mp,
        pct_gex_dte1=pct_gex_dte1,
        oi_near_magnet=near_oi,
    )
    score = pin_score(
        spot=spot,
        magnet_strike=magnet,
        oi_concentration_top3=conc if np.isfinite(conc) else 0.0,
        magnet_gex_bn_per_1pct=magnet_bn,
        time_to_close_pct=time_to_close_pct,
        hours_to_close=hours_to_close,
        expected_move_1sd=em,
        max_gex_bn_reference=max_ref,
        max_pain_strike=mp,
        pct_gex_dte1=pct_gex_dte1,
        oi_near_magnet=near_oi,
    )

    return PinScoreResult(
        score=score,
        magnet_strike=float(magnet),
        max_pain_strike=float(mp),
        distance_to_magnet_pct=float(parts.get("distance_to_magnet_pct", float("nan"))),
        magnet_gex_bn=float(magnet_bn),
        components=parts,
        adjustments={
            "magnet_agreement_mult": float(parts.get("magnet_agreement_mult", 1.0)),
            "cohort_mult": float(parts.get("cohort_mult", 1.0)),
        },
    )


def _strike_tags(
    strike: float,
    *,
    king: float | None,
    max_pain: float | None,
    tol: float = 0.51,
) -> list[str]:
    tags: list[str] = []
    if king is not None and np.isfinite(king) and abs(strike - king) <= tol:
        tags.append("king")
    if max_pain is not None and np.isfinite(max_pain) and abs(strike - max_pain) <= tol:
        tags.append("max_pain")
    return tags


def pin_magnet_ranking(
    heatmap_rows: list[dict[str, float | None]],
    spot: float,
    *,
    king: float | None = None,
    max_pain: float | None = None,
    top_n: int = 5,
) -> list[dict[str, float | list[str]]]:
    """Rank strikes by dealer magnet heuristic: ``|net_gex| × open_interest``.

    Returns ``weight_pct`` summing to ~100 across returned rows — a **relative**
    magnet score, not a calibrated close probability. Use King / max pain tags for
    structural anchors.
    """
    if not heatmap_rows or not np.isfinite(spot) or spot <= 0:
        return []

    scored: list[tuple[float, dict[str, float | None]]] = []
    total_oi = 0.0
    for row in heatmap_rows:
        oi = row.get("total_oi")
        if oi is None or not np.isfinite(float(oi)) or float(oi) <= 0:
            continue
        total_oi += float(oi)

    if total_oi <= 0:
        return []

    for row in heatmap_rows:
        strike = row.get("strike")
        net_gex = row.get("net_gex")
        oi = row.get("total_oi")
        if strike is None or net_gex is None or oi is None:
            continue
        strike_f = float(strike)
        oi_f = float(oi)
        if not np.isfinite(strike_f) or not np.isfinite(float(net_gex)) or oi_f <= 0:
            continue
        raw = abs(float(net_gex)) * oi_f
        if raw <= 0:
            continue
        scored.append(
            (
                raw,
                {
                    "strike": strike_f,
                    "net_gex_bn": float(row.get("net_gex_bn") or 0.0),
                    "oi": oi_f,
                },
            )
        )

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    raw_sum = sum(s for s, _ in scored)
    out: list[dict[str, float | list[str]]] = []
    seen: set[float] = set()

    for raw, payload in scored[:top_n]:
        strike_f = float(payload["strike"])
        seen.add(strike_f)
        oi_share = float(payload["oi"]) / total_oi
        dist_pct = abs(strike_f - spot) / spot * 100.0
        out.append(
            {
                "strike": strike_f,
                "weight_pct": float(raw / raw_sum * 100.0),
                "net_gex_bn": float(payload["net_gex_bn"]),
                "oi_share": oi_share,
                "dist_pct": dist_pct,
                "tags": _strike_tags(strike_f, king=king, max_pain=max_pain),
            }
        )

    for extra_strike, tag in ((king, "king"), (max_pain, "max_pain")):
        if extra_strike is None or not np.isfinite(extra_strike):
            continue
        key = float(extra_strike)
        if any(abs(float(r["strike"]) - key) <= 0.51 for r in out):
            continue
        match = next((row for row in heatmap_rows if abs(float(row["strike"]) - key) <= 0.51), None)
        oi_share = 0.0
        net_gex_bn = 0.0
        if match is not None:
            oi = match.get("total_oi")
            if oi is not None and np.isfinite(float(oi)):
                oi_share = float(oi) / total_oi
            bn = match.get("net_gex_bn")
            if bn is not None and np.isfinite(float(bn)):
                net_gex_bn = float(bn)
        out.append(
            {
                "strike": key,
                "weight_pct": 0.0,
                "net_gex_bn": net_gex_bn,
                "oi_share": oi_share,
                "dist_pct": abs(key - spot) / spot * 100.0,
                "tags": [tag],
            }
        )

    out.sort(key=lambda r: float(r["weight_pct"]), reverse=True)
    return out
