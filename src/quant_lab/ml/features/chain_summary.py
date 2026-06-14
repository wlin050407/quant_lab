"""Option chain summary features (OI-based model-implied GEX)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_lab.data.point_in_time_replay import PointInTimeState
from quant_lab.factors.gex import compute_dealer_gamma_exposure, filter_chain_by_dte


def compute_chain_summary_features(
    state: PointInTimeState,
    *,
    factor_chain: pd.DataFrame | None = None,
    spot: float | None = None,
    expected_move: float | None = None,
) -> tuple[dict[str, Any], float | None, float | None]:
    """Return chain summary features plus call/put gex for deterministic group."""
    chain = state.option_chain
    spot_val = spot
    if spot_val is None and state.index_state and state.index_state.price is not None:
        spot_val = float(state.index_state.price)
    if spot_val is None or not np.isfinite(spot_val):
        return _empty_chain_features(len(chain)), None, None

    work = factor_chain if factor_chain is not None else chain
    if "bs_gamma" not in work.columns and "gamma" in work.columns:
        work = work.assign(bs_gamma=work["gamma"])
    if "bs_gamma" not in work.columns:
        return _empty_chain_features(len(chain)), None, None

    cohort = filter_chain_by_dte(work, dte_max=1)
    per = compute_dealer_gamma_exposure(cohort, spot_val, gamma_col="bs_gamma")

    call_gex = float(per["call_gex"].sum()) if not per.empty else None
    put_gex = float(per["put_gex"].sum()) if not per.empty else None

    q = state.quality
    rights = chain["right"].astype(str).str.upper()
    call_mask = rights.isin(["C", "CALL"])
    put_mask = rights.isin(["P", "PUT"])

    oi = pd.to_numeric(chain["open_interest"], errors="coerce").fillna(0.0)
    call_oi = float(oi[call_mask].sum())
    put_oi = float(oi[put_mask].sum())
    total_oi = call_oi + put_oi

    gamma_col = chain["gamma"] if "gamma" in chain.columns else pd.Series([np.nan] * len(chain))
    abs_gamma_oi = pd.to_numeric(gamma_col, errors="coerce").abs() * oi

    gex_hhi, top1, top3, w_strike, w_dist_em = _gex_concentration(per, spot_val, expected_move)

    return (
        {
            "contract_count": int(len(chain)),
            "active_contract_count": int(q.active_contract_count),
            "call_contract_count": int(call_mask.sum()),
            "put_contract_count": int(put_mask.sum()),
            "quote_coverage_ratio": q.quote_coverage_ratio,
            "greeks_coverage_ratio": q.greeks_coverage_ratio,
            "gamma_coverage_ratio": q.gamma_coverage_ratio,
            "oi_coverage_ratio": q.oi_coverage_ratio,
            "total_open_interest": total_oi,
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "call_put_oi_ratio": call_oi / put_oi if put_oi > 0 else None,
            "total_abs_gamma_oi": float(abs_gamma_oi.sum()),
            "call_abs_gamma_oi": float(abs_gamma_oi[call_mask].sum()),
            "put_abs_gamma_oi": float(abs_gamma_oi[put_mask].sum()),
            "gex_hhi": gex_hhi,
            "top_1_gex_share": top1,
            "top_3_gex_share": top3,
            "gex_weighted_strike": w_strike,
            "gex_weighted_distance_em": w_dist_em,
        },
        call_gex,
        put_gex,
    )


def _empty_chain_features(n: int) -> dict[str, Any]:
    return {
        "contract_count": n,
        "active_contract_count": n,
        "call_contract_count": None,
        "put_contract_count": None,
        "quote_coverage_ratio": 0.0,
        "greeks_coverage_ratio": 0.0,
        "gamma_coverage_ratio": 0.0,
        "oi_coverage_ratio": 0.0,
        "total_open_interest": None,
        "call_open_interest": None,
        "put_open_interest": None,
        "call_put_oi_ratio": None,
        "total_abs_gamma_oi": None,
        "call_abs_gamma_oi": None,
        "put_abs_gamma_oi": None,
        "gex_hhi": None,
        "top_1_gex_share": None,
        "top_3_gex_share": None,
        "gex_weighted_strike": None,
        "gex_weighted_distance_em": None,
    }


def _gex_concentration(
    per: pd.DataFrame,
    spot: float,
    expected_move: float | None,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    if per.empty:
        return None, None, None, None, None
    abs_net = per["net_gex"].abs()
    total = float(abs_net.sum())
    if total <= 0:
        return None, None, None, None, None
    shares = abs_net / total
    hhi = float((shares**2).sum())
    sorted_shares = shares.sort_values(ascending=False)
    top1 = float(sorted_shares.iloc[0])
    top3 = float(sorted_shares.head(3).sum())
    w_strike = float((per.index.to_numpy(dtype=float) * shares.to_numpy()).sum())
    if expected_move and expected_move > 0:
        w_dist = float((abs(per.index.to_numpy(dtype=float) - spot) / expected_move * shares.to_numpy()).sum())
    else:
        w_dist = None
    return hhi, top1, top3, w_strike, w_dist
