"""Pin zone coverage diagnosis helpers (ML-P7.6.1, diagnostic-only)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.data.point_in_time_replay import (
    DeterministicBundle,
    PointInTimeState,
    compute_deterministic_bundle,
    deterministic_input_to_factor_chain,
    replay_state,
    to_deterministic_input_frame,
)
from quant_lab.factors.pin_cluster import detect_pin_cluster
from quant_lab.factors.positioning import pin_magnet_ranking
from quant_lab.factors.regime import pin_reliability, regime_from_net_gex
from quant_lab.ml.datasets.point_in_time import _build_heatmap_rows, generate_anchors
from quant_lab.ml.datasets.sample_builder import SampleBuildConfig, _anchor_config_for_date

DiagnosisPath = Literal["replay_default", "terminal_parity"]


@dataclass(frozen=True)
class AnchorPinDiagnosis:
    trade_date: date
    as_of_timestamp: datetime
    path: DiagnosisPath
    is_cluster: bool
    merge_reason: str
    primary_strike: float | None
    secondary_strike: float | None
    strength_ratio: float | None
    dist_pct: float | None
    pin_score_t: float | None
    regime: str
    pin_reliability: str
    contract_count: int
    spot_t: float | None
    expected_move_t: float | None
    zone_low_t: float | None
    zone_high_t: float | None


def _cluster_params(
    *,
    path: DiagnosisPath,
    bundle: DeterministicBundle,
) -> tuple[str, str]:
    regime = regime_from_net_gex(bundle.net_gex)
    pin_score = float(bundle.pin_score) if bundle.pin_score is not None else float("nan")
    if path == "replay_default":
        return "undetermined", "unknown"
    reliability, _ = pin_reliability(pin_score, regime)
    return regime, reliability


def diagnose_anchor_pin_zone(
    trade_date: date,
    as_of_timestamp: datetime,
    *,
    data_root: Path,
    root: str = "SPXW",
    symbol: str = "^SPX",
    path: DiagnosisPath = "terminal_parity",
) -> AnchorPinDiagnosis:
    """Diagnose pin cluster outcome at one anchor without mutating production formulas."""
    state = replay_state(
        trade_date,
        as_of_timestamp,
        root=root,
        expiration=trade_date,
        data_root=data_root,
    )
    spot = float(state.index_state.price) if state.index_state and state.index_state.price else float("nan")
    input_df = to_deterministic_input_frame(state.option_chain, spot=spot)
    hours = (session_datetime(trade_date, SESSION_CLOSE) - as_of_timestamp).total_seconds() / 3600.0
    bundle = compute_deterministic_bundle(
        input_df,
        spot,
        symbol=symbol,
        asof=trade_date,
        hours_to_close=max(hours, 0.0),
        use_precomputed_gamma=True,
    )
    factor_chain = deterministic_input_to_factor_chain(
        input_df,
        spot=spot,
        symbol=symbol,
        dte=0,
        hours_to_close=max(hours, 0.0),
    )
    heatmap = _build_heatmap_rows(factor_chain, spot)
    rankings = pin_magnet_ranking(
        heatmap,
        spot,
        king=bundle.king_node,
        max_pain=bundle.max_pain,
    )
    regime, reliability = _cluster_params(path=path, bundle=bundle)
    cluster = detect_pin_cluster(
        rankings,
        spot,
        symbol=symbol.replace("^", ""),
        regime=regime,
        pin_reliability=reliability,
    )
    dist_pct = None
    strength_ratio = None
    if len(rankings) >= 2 and np.isfinite(spot) and spot > 0:
        w = [
            (float(r["strike"]), float(r["weight_pct"]))
            for r in rankings
            if r.get("strike") is not None and r.get("weight_pct") is not None
        ]
        if len(w) >= 2:
            p_strike, p_w = w[0]
            s_strike, s_w = w[1]
            if p_w > 0:
                strength_ratio = s_w / p_w
                dist_pct = abs(p_strike - s_strike) / spot

    return AnchorPinDiagnosis(
        trade_date=trade_date,
        as_of_timestamp=as_of_timestamp,
        path=path,
        is_cluster=bool(cluster.is_cluster),
        merge_reason=cluster.merge_reason,
        primary_strike=float(cluster.primary_strike) if np.isfinite(cluster.primary_strike) else None,
        secondary_strike=(
            float(cluster.secondary_strike)
            if cluster.secondary_strike is not None and np.isfinite(cluster.secondary_strike)
            else None
        ),
        strength_ratio=float(strength_ratio) if strength_ratio is not None else None,
        dist_pct=float(dist_pct) if dist_pct is not None else None,
        pin_score_t=float(bundle.pin_score) if bundle.pin_score is not None else None,
        regime=regime,
        pin_reliability=reliability,
        contract_count=len(state.option_chain),
        spot_t=spot if np.isfinite(spot) else None,
        expected_move_t=float(bundle.expected_move_1sd) if bundle.expected_move_1sd is not None else None,
        zone_low_t=float(cluster.lower) if cluster.is_cluster else None,
        zone_high_t=float(cluster.upper) if cluster.is_cluster else None,
    )


def classify_merge_reason(merge_reason: str) -> str:
    """Map raw merge_reason to governance-friendly failure bucket."""
    mapping = {
        "low_pin_reliability": "low_pin_reliability_gate",
        "strikes_too_far_apart": "pin_distance_too_wide",
        "secondary_too_weak": "secondary_strength_too_low",
        "insufficient_magnets": "missing_secondary_pin",
        "short_gamma_regime": "short_gamma_regime_gate",
        "macro_event_active": "macro_blocked",
        "no_cluster": "missing_primary_pin",
        "adjacent_gex_peaks": "valid_cluster",
    }
    return mapping.get(merge_reason, "other")


def replay_state_coverage(state: PointInTimeState) -> dict[str, Any]:
    """Summarize replay chain coverage at one anchor."""
    chain = state.option_chain
    if chain.empty:
        return {
            "contract_count": 0,
            "call_contract_count": 0,
            "put_contract_count": 0,
            "quote_coverage_ratio": 0.0,
            "greeks_coverage_ratio": 0.0,
            "gamma_coverage_ratio": 0.0,
            "oi_coverage_ratio": 0.0,
            "spot_available": False,
            "replay_quality_score": float(state.quality.quality_score),
        }
    calls = int((chain["right"].astype(str).str.upper().isin({"C", "CALL"})).sum())
    puts = int((chain["right"].astype(str).str.upper().isin({"P", "PUT"})).sum())
    n = len(chain)
    if "mid" in chain.columns:
        quote_ok = int(chain["mid"].notna().sum())
    elif "latest_bid" in chain.columns and "latest_ask" in chain.columns:
        mid = (chain["latest_bid"] + chain["latest_ask"]) / 2
        quote_ok = int(mid.notna().sum())
    else:
        quote_ok = 0
    greek_ok = int(chain["implied_vol"].notna().sum()) if "implied_vol" in chain.columns else 0
    gamma_ok = int(chain["gamma"].notna().sum()) if "gamma" in chain.columns else 0
    oi_ok = int((chain["open_interest"].fillna(0) > 0).sum()) if "open_interest" in chain.columns else 0
    spot = state.index_state.price if state.index_state else None
    return {
        "contract_count": n,
        "call_contract_count": calls,
        "put_contract_count": puts,
        "quote_coverage_ratio": quote_ok / n,
        "greeks_coverage_ratio": greek_ok / n,
        "gamma_coverage_ratio": gamma_ok / n,
        "oi_coverage_ratio": oi_ok / n,
        "spot_available": spot is not None and np.isfinite(spot),
        "replay_quality_score": float(state.quality.quality_score),
    }


def build_pin_zone_diagnosis_report(
    config: SampleBuildConfig,
    *,
    max_dates: int = 3,
    data_root: Path | None = None,
    sample_every_n: int = 5,
) -> dict[str, Any]:
    """Build aggregate pin zone diagnosis for Stage A dates (no network)."""
    lake = data_root or config.lake_root
    entries = list(config.dates[:max_dates])
    per_date: dict[str, Any] = {}
    failure_buckets: Counter[str] = Counter()
    parity_valid = 0
    default_valid = 0
    total_sampled = 0

    for entry in entries:
        anchor_cfg = _anchor_config_for_date(config, entry)
        anchors = generate_anchors(entry.trade_date, anchor_cfg)
        sampled = anchors[::sample_every_n] if sample_every_n > 1 else anchors
        date_failures: Counter[str] = Counter()
        coverage_rows: list[dict[str, Any]] = []
        bundle_fields: Counter[str] = Counter()
        parity_hits = 0
        default_hits = 0

        for as_of, _ in sampled:
            total_sampled += 1
            state = replay_state(
                entry.trade_date,
                as_of,
                root=config.root,
                expiration=entry.trade_date,
                data_root=lake,
            )
            coverage_rows.append(replay_state_coverage(state))

            for path in ("replay_default", "terminal_parity"):
                diag = diagnose_anchor_pin_zone(
                    entry.trade_date,
                    as_of,
                    data_root=lake,
                    root=config.root,
                    symbol=f"^{config.index_symbol}",
                    path=path,  # type: ignore[arg-type]
                )
                bucket = classify_merge_reason(diag.merge_reason)
                if path == "replay_default":
                    if diag.is_cluster:
                        default_hits += 1
                        default_valid += 1
                    else:
                        date_failures[bucket] += 1
                        failure_buckets[bucket] += 1
                elif diag.is_cluster:
                    parity_hits += 1
                    parity_valid += 1
                else:
                    date_failures[f"parity_{bucket}"] += 1

                if path == "terminal_parity":
                    if diag.primary_strike is not None:
                        bundle_fields["primary_pin_t"] += 1
                    if diag.secondary_strike is not None:
                        bundle_fields["secondary_pin_t"] += 1
                    if diag.pin_score_t is not None:
                        bundle_fields["pin_score_t"] += 1
                    if diag.zone_low_t is not None:
                        bundle_fields["zone_low_t"] += 1
                    if diag.expected_move_t is not None:
                        bundle_fields["expected_move_t"] += 1

        contract_counts = [r["contract_count"] for r in coverage_rows]

        def _mean_from_rows(key: str, rows: list[dict[str, Any]]) -> float | None:
            vals = [r[key] for r in rows if r.get(key) is not None]
            return float(sum(vals) / len(vals)) if vals else None

        per_date[entry.trade_date.isoformat()] = {
            "day_type": entry.day_type,
            "anchor_count": len(anchors),
            "sampled_anchors": len(sampled),
            "latest_anchor": anchors[-1][0].isoformat() if anchors else None,
            "valid_zone_ratio_replay_default": default_hits / len(sampled) if sampled else 0.0,
            "valid_zone_ratio_terminal_parity": parity_hits / len(sampled) if sampled else 0.0,
            "failure_reason_distribution": dict(date_failures),
            "replay_coverage": {
                "contract_count_mean": _mean_from_rows("contract_count", coverage_rows),
                "contract_count_min": min(contract_counts) if contract_counts else None,
                "contract_count_max": max(contract_counts) if contract_counts else None,
                "quote_coverage_ratio_mean": _mean_from_rows("quote_coverage_ratio", coverage_rows),
                "greeks_coverage_ratio_mean": _mean_from_rows("greeks_coverage_ratio", coverage_rows),
                "gamma_coverage_ratio_mean": _mean_from_rows("gamma_coverage_ratio", coverage_rows),
                "oi_coverage_ratio_mean": _mean_from_rows("oi_coverage_ratio", coverage_rows),
                "replay_quality_score_mean": _mean_from_rows("replay_quality_score", coverage_rows),
            },
            "bundle_field_non_null_sampled": dict(bundle_fields),
        }

    return {
        "dates_analyzed": [e.trade_date.isoformat() for e in entries],
        "sample_every_n": sample_every_n,
        "total_anchors_sampled": total_sampled,
        "valid_zone_ratio_replay_default": default_valid / total_sampled if total_sampled else 0.0,
        "valid_zone_ratio_terminal_parity": parity_valid / total_sampled if total_sampled else 0.0,
        "failure_reason_distribution": dict(failure_buckets),
        "per_date": per_date,
        "adapter_bug_suspected": failure_buckets.get("low_pin_reliability_gate", 0) > 0
        and parity_valid > default_valid,
    }
