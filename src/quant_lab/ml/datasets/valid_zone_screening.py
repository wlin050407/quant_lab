"""Regular-5min valid-zone candidate screening (ML-P7.6.7, no feature build)."""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.data.point_in_time_replay import (
    compute_deterministic_bundle,
    deterministic_input_to_factor_chain,
    replay_state,
    to_deterministic_input_frame,
)
from quant_lab.factors.pin_cluster import detect_pin_cluster
from quant_lab.factors.positioning import pin_magnet_ranking
from quant_lab.factors.regime import pin_reliability, regime_from_net_gex
from quant_lab.ml.datasets.pin_zone_diagnosis import classify_merge_reason
from quant_lab.ml.datasets.point_in_time import (
    PilotIndexOutcomeProvider,
    _build_heatmap_rows,
    generate_anchors,
)
from quant_lab.ml.datasets.reporting import load_completed_checkpoint_dates
from quant_lab.ml.datasets.sample_builder import (
    DateEntry,
    SampleBuildConfig,
    _anchor_config_for_date,
    missing_partitions_for_date,
)
from quant_lab.ml.labels import compute_all_labels
from quant_lab.ml.schemas import AsOfContext

log = logging.getLogger(__name__)

SESSION_METADATA_GLOB = re.compile(r"trade_date=(\d{4}-\d{2}-\d{2})")
KNOWN_NEGATIVE_CONTROLS: frozenset[str] = frozenset({"2024-05-03", "2024-06-07"})
DEFAULT_REPORT_ROOT = Path("artifacts/reports/valid_zone_candidate_screening_v1")

FAILURE_BUCKETS: frozenset[str] = frozenset(
    {
        "short_gamma_regime_gate",
        "secondary_strength_too_low",
        "pin_distance_too_wide",
        "low_pin_reliability_gate",
    }
)


@dataclass(frozen=True)
class LakeDateInventory:
    complete_dates: tuple[str, ...]
    incomplete_dates: tuple[str, ...]
    skipped_dates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "complete_dates": list(self.complete_dates),
            "incomplete_dates": list(self.incomplete_dates),
            "skipped_dates": list(self.skipped_dates),
        }


@dataclass(frozen=True)
class AnchorScreenResult:
    has_valid_zone: bool
    included: bool
    close_location: str | None
    primary_pin_nonnull: bool
    secondary_pin_nonnull: bool
    zone_low_nonnull: bool
    zone_high_nonnull: bool
    pin_score: float | None
    net_gex_positive: bool
    regime: str
    zone_failure_reason: str
    replay_quality: float


@dataclass
class DateScreenMetrics:
    trade_date: date
    day_type: str
    lake_status: str
    anchor_count: int
    valid_zone_count: int
    valid_zone_ratio: float
    included_count: int
    excluded_count: int
    inside_count: int
    below_count: int
    above_count: int
    primary_pin_nonnull_ratio: float
    secondary_pin_nonnull_ratio: float
    zone_low_nonnull_ratio: float
    zone_high_nonnull_ratio: float
    mean_pin_score: float | None
    net_gex_positive_ratio: float
    short_gamma_regime_ratio: float
    secondary_strength_too_low_ratio: float
    pin_distance_too_wide_ratio: float
    low_pin_reliability_ratio: float
    mean_replay_quality: float
    runtime_seconds: float
    label_diversity_score: int = field(init=False)
    status: str = "completed"
    scan_error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "label_diversity_score",
            sum(
                1
                for c in (self.inside_count, self.below_count, self.above_count)
                if c > 0
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trade_date": self.trade_date.isoformat(),
            "day_type": self.day_type,
            "lake_status": self.lake_status,
            "anchor_count": self.anchor_count,
            "valid_zone_count": self.valid_zone_count,
            "valid_zone_ratio": self.valid_zone_ratio,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "inside_count": self.inside_count,
            "below_count": self.below_count,
            "above_count": self.above_count,
            "label_diversity_score": self.label_diversity_score,
            "primary_pin_nonnull_ratio": self.primary_pin_nonnull_ratio,
            "secondary_pin_nonnull_ratio": self.secondary_pin_nonnull_ratio,
            "zone_low_nonnull_ratio": self.zone_low_nonnull_ratio,
            "zone_high_nonnull_ratio": self.zone_high_nonnull_ratio,
            "mean_pin_score": self.mean_pin_score,
            "net_gex_positive_ratio": self.net_gex_positive_ratio,
            "short_gamma_regime_ratio": self.short_gamma_regime_ratio,
            "secondary_strength_too_low_ratio": self.secondary_strength_too_low_ratio,
            "pin_distance_too_wide_ratio": self.pin_distance_too_wide_ratio,
            "low_pin_reliability_ratio": self.low_pin_reliability_ratio,
            "mean_replay_quality": self.mean_replay_quality,
            "runtime_seconds": self.runtime_seconds,
            "scan_error": self.scan_error,
        }


def discover_lake_dates(lake_root: Path, *, root: str = "SPXW") -> list[str]:
    """List trade dates with session_metadata partitions under raw lake."""
    sm_root = lake_root / f"dataset=session_metadata/root={root}"
    if not sm_root.is_dir():
        return []
    dates: list[str] = []
    for path in sm_root.iterdir():
        if not path.is_dir():
            continue
        match = SESSION_METADATA_GLOB.fullmatch(path.name)
        if match:
            dates.append(match.group(1))
    return sorted(dates)


def inventory_raw_lake(
    config: SampleBuildConfig,
    *,
    candidate_dates: list[str] | None = None,
) -> LakeDateInventory:
    """Classify raw lake dates as complete or incomplete (no ingest)."""
    all_dates = candidate_dates or discover_lake_dates(config.lake_root, root=config.root)
    complete: list[str] = []
    incomplete: list[str] = []
    for date_str in all_dates:
        td = date.fromisoformat(date_str)
        missing = missing_partitions_for_date(config, td)
        if missing:
            incomplete.append(date_str)
        else:
            complete.append(date_str)
    return LakeDateInventory(
        complete_dates=tuple(complete),
        incomplete_dates=tuple(incomplete),
        skipped_dates=tuple(incomplete),
    )


def label_diversity_score(metrics: DateScreenMetrics) -> int:
    """Count non-zero close_location classes among inside/below/above."""
    return metrics.label_diversity_score


def rare_label_bonus(metrics: DateScreenMetrics) -> int:
    """Prefer dates contributing inside and/or below labels."""
    bonus = 0
    if metrics.inside_count > 0:
        bonus += 2
    if metrics.below_count > 0:
        bonus += 3
    return bonus


def ranking_sort_key(metrics: DateScreenMetrics) -> tuple[Any, ...]:
    """Sort key for valid-zone candidate ranking (ML-P7.6.7)."""
    return (
        metrics.included_count,
        metrics.valid_zone_ratio,
        metrics.label_diversity_score,
        rare_label_bonus(metrics),
        metrics.mean_replay_quality,
        -metrics.runtime_seconds,
    )


def rank_screened_dates(metrics: list[DateScreenMetrics]) -> list[DateScreenMetrics]:
    """Rank completed date metrics by valid-zone screening rules."""
    scannable = [m for m in metrics if m.status == "completed" and m.scan_error is None]
    return sorted(scannable, key=ranking_sort_key, reverse=True)


def screen_anchor_at(
    trade_date: date,
    as_of_timestamp: datetime,
    *,
    data_root: Path,
    root: str = "SPXW",
    symbol: str = "^SPX",
    outcome_provider: PilotIndexOutcomeProvider,
    session_close_time: str | None = None,
) -> AnchorScreenResult:
    """Replay + deterministic bundle + labels at one anchor (no features)."""
    close_tod = session_close_time or SESSION_CLOSE.strftime("%H:%M:%S")
    state = replay_state(
        trade_date,
        as_of_timestamp,
        root=root,
        expiration=trade_date,
        data_root=data_root,
    )
    spot = float(state.index_state.price) if state.index_state and state.index_state.price else float("nan")
    input_df = to_deterministic_input_frame(state.option_chain, spot=spot)
    hours = (
        session_datetime(trade_date, close_tod) - as_of_timestamp
    ).total_seconds() / 3600.0
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
    regime = regime_from_net_gex(bundle.net_gex)
    pin_score_val = float(bundle.pin_score) if bundle.pin_score is not None else float("nan")
    reliability_tier, _ = pin_reliability(pin_score_val, regime)
    cluster = detect_pin_cluster(
        rankings,
        spot,
        symbol=symbol.replace("^", ""),
        regime=regime,
        pin_reliability=reliability_tier,
    )
    has_valid = bool(cluster.is_cluster)
    z_low = float(cluster.lower) if has_valid else None
    z_high = float(cluster.upper) if has_valid else None
    primary = float(cluster.primary_strike) if has_valid else (
        float(rankings[0]["strike"]) if rankings else bundle.king_node
    )
    secondary = (
        float(cluster.secondary_strike)
        if has_valid and cluster.secondary_strike is not None
        else (float(rankings[1]["strike"]) if len(rankings) > 1 else None)
    )
    zone_failure = (
        "valid_cluster"
        if has_valid
        else classify_merge_reason(str(cluster.merge_reason))
    )

    ctx = AsOfContext(
        trade_date=trade_date,
        as_of_timestamp=as_of_timestamp,
        spot_t=spot,
        primary_pin_t=primary,
        secondary_pin_t=secondary,
        zone_low_t=z_low,
        zone_high_t=z_high,
        zone_center_t=float(cluster.center) if has_valid else None,
        zone_break_up=float(cluster.zone_break.up_break_level) if cluster.zone_break else None,
        zone_break_down=float(cluster.zone_break.down_break_level) if cluster.zone_break else None,
        pin_score_t=bundle.pin_score,
        expected_move_t=bundle.expected_move_1sd,
        gamma_source=bundle.gamma_source,
        oi_semantics_status=bundle.oi_semantics_status,
        spot_zone_state_at_as_of=str(cluster.spot_zone_state),
        has_valid_zone=has_valid,
        quality_score=float(state.quality.quality_score),
        replay_state_hash=state.state_hash,
        deterministic_bundle_hash="screen",
        source_partition_hashes=tuple(p.file_sha256 for p in state.source_partitions if p.file_sha256),
        warning_codes=tuple(state.warnings),
    )
    strikes = [float(r["strike"]) for r in rankings]
    outcome = outcome_provider.get_outcome(trade_date, as_of_timestamp)
    labels = compute_all_labels(ctx, outcome, nearest_strikes=strikes)
    included = ctx.has_valid_zone and labels.close_location_vs_current_zone is not None
    net_gex = bundle.net_gex
    net_pos = net_gex is not None and np.isfinite(net_gex) and float(net_gex) > 0
    pin_score = float(bundle.pin_score) if bundle.pin_score is not None and np.isfinite(bundle.pin_score) else None
    return AnchorScreenResult(
        has_valid_zone=has_valid,
        included=included,
        close_location=labels.close_location_vs_current_zone,
        primary_pin_nonnull=primary is not None and np.isfinite(primary),
        secondary_pin_nonnull=secondary is not None and np.isfinite(secondary),
        zone_low_nonnull=z_low is not None,
        zone_high_nonnull=z_high is not None,
        pin_score=pin_score,
        net_gex_positive=net_pos,
        regime=regime,
        zone_failure_reason=zone_failure,
        replay_quality=float(state.quality.quality_score),
    )


def aggregate_anchor_results(
    entry: DateEntry,
    anchors: list[AnchorScreenResult],
    *,
    lake_status: str,
    runtime_seconds: float,
) -> DateScreenMetrics:
    """Aggregate per-anchor screening into date-level metrics."""
    n = len(anchors)
    if n == 0:
        return DateScreenMetrics(
            trade_date=entry.trade_date,
            day_type=entry.day_type,
            lake_status=lake_status,
            anchor_count=0,
            valid_zone_count=0,
            valid_zone_ratio=0.0,
            included_count=0,
            excluded_count=0,
            inside_count=0,
            below_count=0,
            above_count=0,
            primary_pin_nonnull_ratio=0.0,
            secondary_pin_nonnull_ratio=0.0,
            zone_low_nonnull_ratio=0.0,
            zone_high_nonnull_ratio=0.0,
            mean_pin_score=None,
            net_gex_positive_ratio=0.0,
            short_gamma_regime_ratio=0.0,
            secondary_strength_too_low_ratio=0.0,
            pin_distance_too_wide_ratio=0.0,
            low_pin_reliability_ratio=0.0,
            mean_replay_quality=0.0,
            runtime_seconds=runtime_seconds,
            status="completed",
            scan_error="no_anchors",
        )

    valid_zone = sum(1 for a in anchors if a.has_valid_zone)
    included = sum(1 for a in anchors if a.included)
    inside = sum(1 for a in anchors if a.close_location == "inside")
    below = sum(1 for a in anchors if a.close_location == "below")
    above = sum(1 for a in anchors if a.close_location == "above")
    pin_scores = [a.pin_score for a in anchors if a.pin_score is not None]
    failures: Counter[str] = Counter(a.zone_failure_reason for a in anchors if not a.has_valid_zone)

    def _ratio(bucket: str) -> float:
        return failures.get(bucket, 0) / n

    return DateScreenMetrics(
        trade_date=entry.trade_date,
        day_type=entry.day_type,
        lake_status=lake_status,
        anchor_count=n,
        valid_zone_count=valid_zone,
        valid_zone_ratio=valid_zone / n,
        included_count=included,
        excluded_count=n - included,
        inside_count=inside,
        below_count=below,
        above_count=above,
        primary_pin_nonnull_ratio=sum(1 for a in anchors if a.primary_pin_nonnull) / n,
        secondary_pin_nonnull_ratio=sum(1 for a in anchors if a.secondary_pin_nonnull) / n,
        zone_low_nonnull_ratio=sum(1 for a in anchors if a.zone_low_nonnull) / n,
        zone_high_nonnull_ratio=sum(1 for a in anchors if a.zone_high_nonnull) / n,
        mean_pin_score=float(sum(pin_scores) / len(pin_scores)) if pin_scores else None,
        net_gex_positive_ratio=sum(1 for a in anchors if a.net_gex_positive) / n,
        short_gamma_regime_ratio=sum(1 for a in anchors if a.regime == "short_gamma") / n,
        secondary_strength_too_low_ratio=_ratio("secondary_strength_too_low"),
        pin_distance_too_wide_ratio=_ratio("pin_distance_too_wide"),
        low_pin_reliability_ratio=_ratio("low_pin_reliability_gate"),
        mean_replay_quality=float(sum(a.replay_quality for a in anchors) / n),
        runtime_seconds=runtime_seconds,
    )


def write_per_date_screen_report(report_root: Path, metrics: DateScreenMetrics) -> Path:
    """Write per-date screening JSON checkpoint."""
    out_dir = report_root / "per_date"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{metrics.trade_date.isoformat()}.json"
    path.write_text(json.dumps(metrics.to_dict(), indent=2), encoding="utf-8")
    return path


def load_per_date_screen_report(report_root: Path, trade_date: date) -> dict[str, Any] | None:
    path = report_root / "per_date" / f"{trade_date.isoformat()}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def metrics_from_dict(payload: dict[str, Any]) -> DateScreenMetrics:
    """Rehydrate DateScreenMetrics from JSON (resume)."""
    td = date.fromisoformat(str(payload["trade_date"]))
    m = DateScreenMetrics(
        trade_date=td,
        day_type=str(payload.get("day_type", "normal")),
        lake_status=str(payload.get("lake_status", "raw_lake_complete")),
        anchor_count=int(payload.get("anchor_count", 0)),
        valid_zone_count=int(payload.get("valid_zone_count", 0)),
        valid_zone_ratio=float(payload.get("valid_zone_ratio", 0.0)),
        included_count=int(payload.get("included_count", 0)),
        excluded_count=int(payload.get("excluded_count", 0)),
        inside_count=int(payload.get("inside_count", 0)),
        below_count=int(payload.get("below_count", 0)),
        above_count=int(payload.get("above_count", 0)),
        primary_pin_nonnull_ratio=float(payload.get("primary_pin_nonnull_ratio", 0.0)),
        secondary_pin_nonnull_ratio=float(payload.get("secondary_pin_nonnull_ratio", 0.0)),
        zone_low_nonnull_ratio=float(payload.get("zone_low_nonnull_ratio", 0.0)),
        zone_high_nonnull_ratio=float(payload.get("zone_high_nonnull_ratio", 0.0)),
        mean_pin_score=payload.get("mean_pin_score"),
        net_gex_positive_ratio=float(payload.get("net_gex_positive_ratio", 0.0)),
        short_gamma_regime_ratio=float(payload.get("short_gamma_regime_ratio", 0.0)),
        secondary_strength_too_low_ratio=float(payload.get("secondary_strength_too_low_ratio", 0.0)),
        pin_distance_too_wide_ratio=float(payload.get("pin_distance_too_wide_ratio", 0.0)),
        low_pin_reliability_ratio=float(payload.get("low_pin_reliability_ratio", 0.0)),
        mean_replay_quality=float(payload.get("mean_replay_quality", 0.0)),
        runtime_seconds=float(payload.get("runtime_seconds", 0.0)),
        status=str(payload.get("status", "completed")),
        scan_error=payload.get("scan_error"),
    )
    return m


def recommend_full_build_dates(
    ranked: list[DateScreenMetrics],
    *,
    already_full_built: frozenset[str] | None = None,
    negative_controls: frozenset[str] = KNOWN_NEGATIVE_CONTROLS,
    min_count: int = 2,
    max_count: int = 4,
) -> list[str]:
    """Pick 2–4 dates for next full build pass."""
    built = already_full_built or frozenset()
    picks: list[str] = []
    for m in ranked:
        key = m.trade_date.isoformat()
        if key in built:
            continue
        if key in negative_controls and m.included_count == 0:
            continue
        if m.included_count <= 0:
            continue
        picks.append(key)
        if len(picks) >= max_count:
            break
    if len(picks) < min_count:
        for m in ranked:
            key = m.trade_date.isoformat()
            if key in picks or key in built:
                continue
            if key in negative_controls and m.included_count == 0:
                continue
            if m.valid_zone_ratio <= 0:
                continue
            picks.append(key)
            if len(picks) >= min_count:
                break
    return picks[:max_count]


def build_screening_summary(
    *,
    inventory: LakeDateInventory,
    metrics: list[DateScreenMetrics],
    screened_dates: list[str],
    skipped_dates: list[str],
    recommended_dates: list[str],
    already_full_built: list[str],
) -> dict[str, Any]:
    """Build summary.json payload."""
    ranked = rank_screened_dates(metrics)
    by_included = sorted(ranked, key=lambda m: (m.included_count, m.valid_zone_ratio), reverse=True)
    by_valid_zone = sorted(ranked, key=lambda m: (m.valid_zone_ratio, m.included_count), reverse=True)
    by_diversity = sorted(
        ranked,
        key=lambda m: (m.label_diversity_score, m.included_count),
        reverse=True,
    )
    return {
        "version": "valid-zone-candidate-screening-v1",
        "screening_source": "artifacts/raw_lake_sample",
        "anchor_type": "regular_5min",
        "inventory": inventory.to_dict(),
        "screened_dates": screened_dates,
        "skipped_dates": skipped_dates,
        "already_full_built": already_full_built,
        "known_negative_controls": sorted(KNOWN_NEGATIVE_CONTROLS),
        "ranking_rules": [
            "included_count DESC",
            "valid_zone_ratio DESC",
            "label_diversity_score DESC",
            "rare_label_bonus",
            "mean_replay_quality DESC",
            "runtime_seconds ASC",
        ],
        "per_date_metrics": [m.to_dict() for m in metrics],
        "ranked_dates": [m.trade_date.isoformat() for m in ranked],
        "top_by_included_count": [
            {"trade_date": m.trade_date.isoformat(), "included_count": m.included_count}
            for m in by_included[:10]
        ],
        "top_by_valid_zone_ratio": [
            {"trade_date": m.trade_date.isoformat(), "valid_zone_ratio": m.valid_zone_ratio}
            for m in by_valid_zone[:10]
        ],
        "top_by_label_diversity": [
            {
                "trade_date": m.trade_date.isoformat(),
                "label_diversity_score": m.label_diversity_score,
            }
            for m in by_diversity[:10]
        ],
        "dates_with_inside": [m.trade_date.isoformat() for m in metrics if m.inside_count > 0],
        "dates_with_below": [m.trade_date.isoformat() for m in metrics if m.below_count > 0],
        "dates_with_above": [m.trade_date.isoformat() for m in metrics if m.above_count > 0],
        "recommended_next_full_build_dates": recommended_dates,
        "ml_p8b_blocked": True,
    }


@dataclass(frozen=True)
class ScreeningOptions:
    dates_filter: frozenset[str] | None = None
    resume: bool = True
    progress_every: int = 10
    report_root: Path = DEFAULT_REPORT_ROOT
    already_full_built: frozenset[str] = frozenset(
        {
            "2024-01-19",
            "2024-10-04",
            "2025-05-02",
            "2024-05-03",
            "2024-06-07",
        }
    )


def screen_valid_zone_candidates(
    config: SampleBuildConfig,
    day_type_map: dict[str, str],
    *,
    options: ScreeningOptions | None = None,
) -> dict[str, Any]:
    """Run regular-5min valid-zone screening over complete raw lake dates."""
    opts = options or ScreeningOptions()
    report_root = opts.report_root
    inventory = inventory_raw_lake(config)
    completed: set[str] = set()
    if opts.resume:
        completed = load_completed_checkpoint_dates(report_root)

    dates_to_scan = list(inventory.complete_dates)
    if opts.dates_filter:
        dates_to_scan = [d for d in dates_to_scan if d in opts.dates_filter]

    screened: list[str] = []
    skipped: list[str] = list(inventory.incomplete_dates)
    all_metrics: list[DateScreenMetrics] = []

    if opts.resume:
        for date_str in dates_to_scan:
            if date_str not in completed:
                continue
            payload = load_per_date_screen_report(report_root, date.fromisoformat(date_str))
            if payload:
                all_metrics.append(metrics_from_dict(payload))
                screened.append(date_str)

    provider = PilotIndexOutcomeProvider(data_root=config.lake_root, symbol=config.index_symbol)
    symbol = f"^{config.index_symbol}"

    for date_str in dates_to_scan:
        if opts.resume and date_str in completed:
            log.info("[screen resume skip] %s", date_str)
            continue

        td = date.fromisoformat(date_str)
        day_type = day_type_map.get(date_str, "normal")
        entry = DateEntry(trade_date=td, day_type=day_type)
        anchor_cfg = _anchor_config_for_date(config, entry)
        anchors_ts = generate_anchors(td, anchor_cfg)
        if not anchors_ts:
            skipped.append(date_str)
            continue

        log.info("[screen start] %s anchors=%d", date_str, len(anchors_ts))
        started = time.perf_counter()
        anchor_results: list[AnchorScreenResult] = []
        total = len(anchors_ts)
        session_close = "13:00:00" if day_type == "early_close" else None

        try:
            for idx, (as_of, _atype) in enumerate(anchors_ts, start=1):
                anchor_results.append(
                    screen_anchor_at(
                        td,
                        as_of,
                        data_root=config.lake_root,
                        root=config.root,
                        symbol=symbol,
                        outcome_provider=provider,
                        session_close_time=session_close,
                    )
                )
                if opts.progress_every > 0 and (idx % opts.progress_every == 0 or idx == total):
                    elapsed = time.perf_counter() - started
                    log.info(
                        "[screen progress] %s anchor %d/%d as_of=%s elapsed=%.1fs",
                        date_str,
                        idx,
                        total,
                        as_of.isoformat(),
                        elapsed,
                    )
        except Exception as exc:
            log.exception("[screen failed] %s error=%s", date_str, exc)
            failed = DateScreenMetrics(
                trade_date=td,
                day_type=day_type,
                lake_status="raw_lake_complete",
                anchor_count=len(anchors_ts),
                valid_zone_count=0,
                valid_zone_ratio=0.0,
                included_count=0,
                excluded_count=0,
                inside_count=0,
                below_count=0,
                above_count=0,
                primary_pin_nonnull_ratio=0.0,
                secondary_pin_nonnull_ratio=0.0,
                zone_low_nonnull_ratio=0.0,
                zone_high_nonnull_ratio=0.0,
                mean_pin_score=None,
                net_gex_positive_ratio=0.0,
                short_gamma_regime_ratio=0.0,
                secondary_strength_too_low_ratio=0.0,
                pin_distance_too_wide_ratio=0.0,
                low_pin_reliability_ratio=0.0,
                mean_replay_quality=0.0,
                runtime_seconds=time.perf_counter() - started,
                status="failed",
                scan_error=f"{type(exc).__name__}:{exc}",
            )
            write_per_date_screen_report(report_root, failed)
            skipped.append(date_str)
            continue

        runtime = time.perf_counter() - started
        metrics = aggregate_anchor_results(
            entry,
            anchor_results,
            lake_status="raw_lake_complete",
            runtime_seconds=runtime,
        )
        write_per_date_screen_report(report_root, metrics)
        all_metrics.append(metrics)
        screened.append(date_str)
        classes = {
            k: v
            for k, v in (
                ("inside", metrics.inside_count),
                ("below", metrics.below_count),
                ("above", metrics.above_count),
            )
            if v > 0
        }
        log.info(
            "[screen complete] %s valid_zone=%.3f included=%d classes=%s",
            date_str,
            metrics.valid_zone_ratio,
            metrics.included_count,
            classes,
        )

    ranked = rank_screened_dates(all_metrics)
    recommended = recommend_full_build_dates(
        ranked,
        already_full_built=opts.already_full_built,
    )
    summary = build_screening_summary(
        inventory=inventory,
        metrics=all_metrics,
        screened_dates=sorted(set(screened)),
        skipped_dates=sorted(set(skipped)),
        recommended_dates=recommended,
        already_full_built=sorted(opts.already_full_built),
    )
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def parse_dates_filter(raw: str | None) -> frozenset[str] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return frozenset(parts) if parts else None


def load_day_type_map(config_path: Path | None) -> dict[str, str]:
    """Optional day_type hints from candidate config YAML."""
    if config_path is None or not config_path.is_file():
        return {}
    import yaml

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for item in raw.get("dates") or []:
        if isinstance(item, dict) and item.get("date"):
            out[str(item["date"])] = str(item.get("day_type", "normal"))
    return out
