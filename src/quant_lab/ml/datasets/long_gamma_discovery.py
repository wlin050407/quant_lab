"""Long-gamma candidate discovery for ML-P7.6.2 (diagnostic-only, no training)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.data.point_in_time_replay import (
    compute_deterministic_bundle,
    replay_state,
    to_deterministic_input_frame,
)
from quant_lab.factors.pin_cluster import CLUSTER_MIN_STRENGTH_RATIO
from quant_lab.ml.datasets.pin_zone_diagnosis import (
    classify_merge_reason,
    diagnose_anchor_pin_zone,
)
from quant_lab.ml.datasets.sample_builder import (
    DateEntry,
    SampleBuildConfig,
    load_sample_config,
    missing_partitions_for_date,
    try_ingest_date,
)

SCAN_ANCHOR_TIMES_NORMAL: tuple[str, ...] = (
    "10:00:00",
    "11:00:00",
    "12:00:00",
    "13:00:00",
    "14:00:00",
    "15:00:00",
)
SCAN_ANCHOR_TIMES_EARLY_CLOSE: tuple[str, ...] = (
    "10:00:00",
    "11:00:00",
    "12:00:00",
)


@dataclass(frozen=True)
class AnchorScanResult:
    trade_date: date
    as_of_timestamp: str
    net_gex: float | None
    regime: str
    pin_reliability: str
    primary_pin_t: float | None
    secondary_pin_t: float | None
    pin_score_t: float | None
    zone_low_t: float | None
    zone_high_t: float | None
    strength_ratio: float | None
    is_valid_zone: bool
    zone_failure_reason: str


@dataclass(frozen=True)
class DateCandidateMetrics:
    trade_date: date
    day_type: str
    lake_status: str
    anchor_count: int
    long_gamma_anchor_ratio: float
    valid_zone_anchor_ratio: float
    net_gex_positive_ratio: float
    secondary_pin_nonnull_ratio: float
    secondary_strength_pass_ratio: float
    pin_reliability_mean: float | None
    zone_failure_reason_distribution: dict[str, int]
    composite_score: float
    scan_error: str | None = None


def scan_anchor_times_for_day_type(day_type: str) -> tuple[str, ...]:
    """Return hourly scan anchors; early-close days stop before 13:00 session close."""
    if day_type == "early_close":
        return SCAN_ANCHOR_TIMES_EARLY_CLOSE
    return SCAN_ANCHOR_TIMES_NORMAL


def scan_anchors_for_date(
    entry: DateEntry,
    *,
    config: SampleBuildConfig,
    data_root: Path | None = None,
) -> list[AnchorScanResult]:
    """Lightweight per-anchor scan (no full dataset build)."""
    lake = data_root or config.lake_root
    symbol = f"^{config.index_symbol}"
    results: list[AnchorScanResult] = []
    for time_str in scan_anchor_times_for_day_type(entry.day_type):
        as_of = session_datetime(entry.trade_date, time_str)
        diag = diagnose_anchor_pin_zone(
            entry.trade_date,
            as_of,
            data_root=lake,
            root=config.root,
            symbol=symbol,
            path="terminal_parity",
        )
        state = replay_state(
            entry.trade_date,
            as_of,
            root=config.root,
            expiration=entry.trade_date,
            data_root=lake,
        )
        spot = float(state.index_state.price) if state.index_state and state.index_state.price else float("nan")
        close_time = "13:00:00" if entry.day_type == "early_close" else SESSION_CLOSE
        input_frame = to_deterministic_input_frame(state.option_chain, spot=spot)
        hours = (session_datetime(entry.trade_date, close_time) - as_of).total_seconds() / 3600.0
        bundle = compute_deterministic_bundle(
            input_frame,
            spot,
            symbol=symbol,
            asof=entry.trade_date,
            hours_to_close=max(hours, 0.0),
            use_precomputed_gamma=True,
        )
        net_gex = float(bundle.net_gex) if bundle.net_gex is not None and np.isfinite(bundle.net_gex) else None
        results.append(
            AnchorScanResult(
                trade_date=entry.trade_date,
                as_of_timestamp=as_of.isoformat(),
                net_gex=net_gex,
                regime=diag.regime,
                pin_reliability=diag.pin_reliability,
                primary_pin_t=diag.primary_strike,
                secondary_pin_t=diag.secondary_strike,
                pin_score_t=diag.pin_score_t,
                zone_low_t=diag.zone_low_t,
                zone_high_t=diag.zone_high_t,
                strength_ratio=diag.strength_ratio,
                is_valid_zone=diag.is_cluster,
                zone_failure_reason=classify_merge_reason(diag.merge_reason),
            )
        )
    return results


def aggregate_anchor_metrics(
    entry: DateEntry,
    anchors: list[AnchorScanResult],
    *,
    lake_status: str,
) -> DateCandidateMetrics:
    """Aggregate scan anchors into date-level ranking metrics."""
    n = len(anchors)
    if n == 0:
        return DateCandidateMetrics(
            trade_date=entry.trade_date,
            day_type=entry.day_type,
            lake_status=lake_status,
            anchor_count=0,
            long_gamma_anchor_ratio=0.0,
            valid_zone_anchor_ratio=0.0,
            net_gex_positive_ratio=0.0,
            secondary_pin_nonnull_ratio=0.0,
            secondary_strength_pass_ratio=0.0,
            pin_reliability_mean=None,
            zone_failure_reason_distribution={},
            composite_score=0.0,
            scan_error="no_anchors_scanned",
        )

    long_gamma = sum(1 for a in anchors if a.regime == "long_gamma")
    valid_zone = sum(1 for a in anchors if a.is_valid_zone)
    net_pos = sum(1 for a in anchors if a.net_gex is not None and a.net_gex > 0)
    sec_nonnull = sum(1 for a in anchors if a.secondary_pin_t is not None)
    strength_pass = sum(
        1
        for a in anchors
        if a.strength_ratio is not None and a.strength_ratio >= CLUSTER_MIN_STRENGTH_RATIO
    )
    rel_map = {"high": 4, "moderate": 3, "caution": 2, "low": 1, "unknown": 0}
    rel_scores = [rel_map.get(a.pin_reliability, 0) for a in anchors]
    rel_mean = float(sum(rel_scores) / len(rel_scores)) if rel_scores else None

    failures: Counter[str] = Counter()
    for a in anchors:
        if not a.is_valid_zone:
            failures[a.zone_failure_reason] += 1

    long_gamma_ratio = long_gamma / n
    valid_zone_ratio = valid_zone / n
    composite = (
        valid_zone_ratio * 100.0
        + long_gamma_ratio * 50.0
        + (net_pos / n) * 25.0
        + (strength_pass / n) * 15.0
        + (rel_mean or 0.0) * 5.0
    )

    return DateCandidateMetrics(
        trade_date=entry.trade_date,
        day_type=entry.day_type,
        lake_status=lake_status,
        anchor_count=n,
        long_gamma_anchor_ratio=long_gamma_ratio,
        valid_zone_anchor_ratio=valid_zone_ratio,
        net_gex_positive_ratio=net_pos / n,
        secondary_pin_nonnull_ratio=sec_nonnull / n,
        secondary_strength_pass_ratio=strength_pass / n,
        pin_reliability_mean=rel_mean,
        zone_failure_reason_distribution=dict(failures),
        composite_score=composite,
    )


def rank_candidates(
    metrics: list[DateCandidateMetrics],
    *,
    top_n: int = 10,
) -> list[DateCandidateMetrics]:
    """Rank dates by composite score (valid zone first, then long-gamma)."""
    scannable = [m for m in metrics if m.scan_error is None and m.lake_status != "failed"]
    ranked = sorted(
        scannable,
        key=lambda m: (
            m.valid_zone_anchor_ratio,
            m.long_gamma_anchor_ratio,
            m.net_gex_positive_ratio,
            m.composite_score,
        ),
        reverse=True,
    )
    return ranked[:top_n]


def _lake_status_for_date(config: SampleBuildConfig, trade_date: date) -> str:
    missing = missing_partitions_for_date(config, trade_date)
    if not missing:
        return "raw_lake_exists"
    return "missing_partitions"


def discover_long_gamma_candidates(
    config: SampleBuildConfig,
    *,
    max_dates: int = 30,
    top_n: int = 10,
    ingest_missing: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scan candidate dates and rank for long-gamma / valid-zone potential."""
    entries = list(config.dates[:max_dates])
    date_metrics: list[DateCandidateMetrics] = []
    ingest_log: list[dict[str, Any]] = []

    for entry in entries:
        status = _lake_status_for_date(config, entry.trade_date)
        if status == "missing_partitions":
            if ingest_missing and config.ingest_enabled and not dry_run:
                ok, reason, ingest_result = try_ingest_date(config, entry, dry_run=False)
                ingest_log.append(
                    {
                        "date": entry.trade_date.isoformat(),
                        "ingested": ok,
                        "reason": reason,
                        "api_requests": ingest_result.api_request_count if ingest_result else 0,
                    }
                )
                status = _lake_status_for_date(config, entry.trade_date)
                if status == "missing_partitions":
                    date_metrics.append(
                        DateCandidateMetrics(
                            trade_date=entry.trade_date,
                            day_type=entry.day_type,
                            lake_status="failed",
                            anchor_count=0,
                            long_gamma_anchor_ratio=0.0,
                            valid_zone_anchor_ratio=0.0,
                            net_gex_positive_ratio=0.0,
                            secondary_pin_nonnull_ratio=0.0,
                            secondary_strength_pass_ratio=0.0,
                            pin_reliability_mean=None,
                            zone_failure_reason_distribution={},
                            composite_score=0.0,
                            scan_error=f"ingest_failed:{reason}",
                        )
                    )
                    continue
                status = "newly_ingested"
            elif dry_run:
                date_metrics.append(
                    DateCandidateMetrics(
                        trade_date=entry.trade_date,
                        day_type=entry.day_type,
                        lake_status="missing_partitions",
                        anchor_count=0,
                        long_gamma_anchor_ratio=0.0,
                        valid_zone_anchor_ratio=0.0,
                        net_gex_positive_ratio=0.0,
                        secondary_pin_nonnull_ratio=0.0,
                        secondary_strength_pass_ratio=0.0,
                        pin_reliability_mean=None,
                        zone_failure_reason_distribution={},
                        composite_score=0.0,
                        scan_error="dry_run_missing_lake",
                    )
                )
                continue
            else:
                date_metrics.append(
                    DateCandidateMetrics(
                        trade_date=entry.trade_date,
                        day_type=entry.day_type,
                        lake_status="failed",
                        anchor_count=0,
                        long_gamma_anchor_ratio=0.0,
                        valid_zone_anchor_ratio=0.0,
                        net_gex_positive_ratio=0.0,
                        secondary_pin_nonnull_ratio=0.0,
                        secondary_strength_pass_ratio=0.0,
                        pin_reliability_mean=None,
                        zone_failure_reason_distribution={},
                        composite_score=0.0,
                        scan_error="missing_partitions_ingest_disabled",
                    )
                )
                continue
        elif status == "raw_lake_exists":
            pass

        try:
            anchors = scan_anchors_for_date(entry, config=config)
            date_metrics.append(
                aggregate_anchor_metrics(entry, anchors, lake_status=status)
            )
        except Exception as exc:
            date_metrics.append(
                DateCandidateMetrics(
                    trade_date=entry.trade_date,
                    day_type=entry.day_type,
                    lake_status=status,
                    anchor_count=0,
                    long_gamma_anchor_ratio=0.0,
                    valid_zone_anchor_ratio=0.0,
                    net_gex_positive_ratio=0.0,
                    secondary_pin_nonnull_ratio=0.0,
                    secondary_strength_pass_ratio=0.0,
                    pin_reliability_mean=None,
                    zone_failure_reason_distribution={},
                    composite_score=0.0,
                    scan_error=str(exc),
                )
            )

    top = rank_candidates(date_metrics, top_n=top_n)
    return {
        "version": config.version,
        "max_dates": max_dates,
        "top_n": top_n,
        "ingest_enabled": config.ingest_enabled,
        "ingest_missing": ingest_missing,
        "dry_run": dry_run,
        "dates_scanned": len(entries),
        "dates_with_lake": sum(
            1 for m in date_metrics if m.lake_status in {"raw_lake_exists", "newly_ingested"}
        ),
        "dates_newly_ingested": sum(1 for m in date_metrics if m.lake_status == "newly_ingested"),
        "dates_failed": sum(1 for m in date_metrics if m.lake_status == "failed" or m.scan_error),
        "ingest_log": ingest_log,
        "per_date_metrics": [_metrics_to_dict(m) for m in date_metrics],
        "top_candidate_dates": [m.trade_date.isoformat() for m in top],
        "top_candidates": [_metrics_to_dict(m) for m in top],
        "aggregate": _aggregate_scan_summary(date_metrics),
    }


def _metrics_to_dict(m: DateCandidateMetrics) -> dict[str, Any]:
    return {
        "trade_date": m.trade_date.isoformat(),
        "day_type": m.day_type,
        "lake_status": m.lake_status,
        "anchor_count": m.anchor_count,
        "long_gamma_anchor_ratio": m.long_gamma_anchor_ratio,
        "valid_zone_anchor_ratio": m.valid_zone_anchor_ratio,
        "net_gex_positive_ratio": m.net_gex_positive_ratio,
        "secondary_pin_nonnull_ratio": m.secondary_pin_nonnull_ratio,
        "secondary_strength_pass_ratio": m.secondary_strength_pass_ratio,
        "pin_reliability_mean": m.pin_reliability_mean,
        "zone_failure_reason_distribution": m.zone_failure_reason_distribution,
        "composite_score": m.composite_score,
        "scan_error": m.scan_error,
    }


def _aggregate_scan_summary(metrics: list[DateCandidateMetrics]) -> dict[str, Any]:
    scannable = [m for m in metrics if m.scan_error is None and m.anchor_count > 0]
    if not scannable:
        return {
            "long_gamma_anchor_ratio_mean": 0.0,
            "valid_zone_anchor_ratio_mean": 0.0,
            "dates_with_any_valid_zone": 0,
        }
    return {
        "long_gamma_anchor_ratio_mean": float(
            sum(m.long_gamma_anchor_ratio for m in scannable) / len(scannable)
        ),
        "valid_zone_anchor_ratio_mean": float(
            sum(m.valid_zone_anchor_ratio for m in scannable) / len(scannable)
        ),
        "dates_with_any_valid_zone": sum(1 for m in scannable if m.valid_zone_anchor_ratio > 0),
    }


def load_discovery_config(path: Path) -> SampleBuildConfig:
    """Load candidate discovery config (same schema as sample build config)."""
    return load_sample_config(path)


def stage_a_plus_date_count(top_candidates: list[str], *, min_dates: int = 5, max_dates: int = 10) -> int:
    """Pick Stage A+ date count from ranked candidates."""
    n = len(top_candidates)
    if n == 0:
        return 0
    return max(min_dates, min(n, max_dates))
