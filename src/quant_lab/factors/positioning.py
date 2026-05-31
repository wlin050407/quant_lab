"""Positioning factors from a single EoD option-chain snapshot.

These complement `factors/gex.py`: GEX tells you *how* dealer hedging behaves;
positioning factors tell you *where* OI is concentrated and what the crowd
is betting.

All functions are stateless: chain DataFrame in, scalar or small DataFrame out.
No I/O, no network (per module boundary in AGENTS.md).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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


def expected_move_1sd(
    spot: float,
    atm_iv: float,
    *,
    dte: int = 1,
    trading_days_per_year: int = 365,
) -> float:
    """One standard-deviation expected move in dollars (straddle-implied proxy).

    ``EM = spot × IV × sqrt(T)`` with ``T = dte / trading_days_per_year``.
    Matches FlashAlpha / SpotGamma expected-move headline units at EoD.
    """
    if not np.isfinite(spot) or spot <= 0 or not np.isfinite(atm_iv) or atm_iv <= 0:
        return float("nan")
    if dte <= 0:
        return float("nan")
    t = dte / trading_days_per_year
    return float(spot * atm_iv * np.sqrt(t))


def atm_iv_from_chain(
    chain: pd.DataFrame,
    spot: float,
    *,
    dte: int = 1,
    min_iv: float = 0.05,
    max_iv: float = 3.0,
) -> float:
    """Nearest-strike ATM implied vol for a ``dte`` cohort."""
    if chain.empty or "dte" not in chain.columns or "implied_volatility" not in chain.columns:
        return float("nan")
    cohort = chain[chain["dte"] == dte].copy()
    if cohort.empty:
        return float("nan")
    cohort = cohort.assign(dist=(cohort["strike"] - spot).abs())
    row = cohort.loc[cohort["dist"].idxmin()]
    iv = float(row["implied_volatility"])
    if not np.isfinite(iv) or iv < min_iv or iv > max_iv:
        return float("nan")
    return iv


def pin_score_components(
    *,
    spot: float,
    magnet_strike: float,
    oi_concentration_top3: float,
    net_gex_bn_per_1pct: float,
    time_to_close_pct: float = 100.0,
) -> dict[str, float]:
    """Sub-scores (0–100) for each ``pin_score`` term."""
    if not np.isfinite(spot) or spot <= 0:
        return {
            "oi_concentration": float("nan"),
            "magnet_proximity": float("nan"),
            "time_remaining": float("nan"),
            "gamma_magnitude": float("nan"),
        }

    conc = oi_concentration_top3 if np.isfinite(oi_concentration_top3) else 0.0
    conc_score = float(np.clip(conc / 0.45, 0.0, 1.0) * 100.0)

    if np.isfinite(magnet_strike):
        dist_pct = abs(spot - magnet_strike) / spot
        prox_score = float(np.clip(1.0 - dist_pct / 0.015, 0.0, 1.0) * 100.0)
    else:
        prox_score = 0.0

    time_score = float(np.clip(time_to_close_pct, 0.0, 100.0))

    if np.isfinite(net_gex_bn_per_1pct):
        mag_score = float(np.clip(abs(net_gex_bn_per_1pct) / 3.0, 0.0, 1.0) * 100.0)
    else:
        mag_score = 0.0

    return {
        "oi_concentration": conc_score,
        "magnet_proximity": prox_score,
        "time_remaining": time_score,
        "gamma_magnitude": mag_score,
    }


def pin_score(
    *,
    spot: float,
    magnet_strike: float,
    oi_concentration_top3: float,
    net_gex_bn_per_1pct: float,
    time_to_close_pct: float = 100.0,
) -> float:
    """Composite pin-risk score 0–100 (EoD approximation of FlashAlpha ``pin_score``).

    Weights (FlashAlpha convention, time term defaulted for EoD close):
        OI concentration (top-3)  30%
        magnet proximity          25%
        time remaining            25%  (``time_to_close_pct`` → 100 at EoD)
        gamma magnitude           20%

    Args:
        spot: underlying price.
        magnet_strike: King node or max-pain strike.
        oi_concentration_top3: fraction in [0, 1] from ``oi_concentration(top_n=3)``.
        net_gex_bn_per_1pct: ``|net_gex|`` in SpotGamma Bn/1% units.
        time_to_close_pct: 0=open, 100=close; EoD snapshots use 100.
    """
    parts = pin_score_components(
        spot=spot,
        magnet_strike=magnet_strike,
        oi_concentration_top3=oi_concentration_top3,
        net_gex_bn_per_1pct=net_gex_bn_per_1pct,
        time_to_close_pct=time_to_close_pct,
    )
    if not np.isfinite(parts["oi_concentration"]):
        return float("nan")
    raw = (
        0.30 * parts["oi_concentration"]
        + 0.25 * parts["magnet_proximity"]
        + 0.25 * parts["time_remaining"]
        + 0.20 * parts["gamma_magnitude"]
    )
    return float(np.clip(raw, 0.0, 100.0))


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
