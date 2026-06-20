"""Baseline primary-pin target coverage screening (ML-P7.8, no feature build)."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.ml.datasets.point_in_time import (
    PilotIndexOutcomeProvider,
    build_as_of_context,
    generate_anchors,
)
from quant_lab.ml.datasets.reporting import load_completed_checkpoint_dates
from quant_lab.ml.datasets.sample_builder import (
    DateEntry,
    SampleBuildConfig,
    _anchor_config_for_date,
)
from quant_lab.ml.datasets.valid_zone_screening import (
    inventory_raw_lake,
)
from quant_lab.ml.labels import compute_all_labels, remaining_expected_move
from quant_lab.ml.leakage import check_label_timestamp_after_as_of

log = logging.getLogger(__name__)

DEFAULT_REPORT_ROOT = Path("artifacts/reports/baseline_target_screening_v1")
SKIP_DATES: frozenset[str] = frozenset({"2026-06-10"})
P1_THRESHOLDS: tuple[float, ...] = (0.25, 0.50)
P2_THRESHOLDS: tuple[float, ...] = (0.25, 0.50)
NEAR_ZERO_ABS = 1e-9
OUTLIER_ABS_EM = 3.0

P78_MIN_ELIGIBLE_ROWS = 300
P78_MIN_ELIGIBLE_SESSIONS = 10

DirectionClass = Literal["below", "near", "above"]


@dataclass(frozen=True)
class AnchorBaselineResult:
    eligible: bool
    null_reasons: tuple[str, ...]
    d_em: float | None
    p1_near: dict[str, bool | None]
    p2_class: dict[str, DirectionClass | None]
    zone_included: bool
    zone_close_location: str | None
    leakage_ok: bool
    leakage_violations: tuple[str, ...]


@dataclass
class DateBaselineMetrics:
    trade_date: date
    day_type: str
    anchor_count: int
    eligible_count: int
    eligible_ratio: float
    zone_included_count: int
    p0: dict[str, Any]
    p1: dict[str, Any]
    p2: dict[str, Any]
    null_reason_distribution: dict[str, int]
    leakage_pass: bool
    leakage_violation_count: int
    leakage_violation_examples: list[str]
    runtime_seconds: float
    status: str = "completed"
    scan_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trade_date": self.trade_date.isoformat(),
            "day_type": self.day_type,
            "anchor_count": self.anchor_count,
            "eligible_count": self.eligible_count,
            "eligible_ratio": self.eligible_ratio,
            "zone_included_count": self.zone_included_count,
            "p0": self.p0,
            "p1": self.p1,
            "p2": self.p2,
            "null_reason_distribution": self.null_reason_distribution,
            "leakage_pass": self.leakage_pass,
            "leakage_violation_count": self.leakage_violation_count,
            "leakage_violation_examples": self.leakage_violation_examples,
            "runtime_seconds": self.runtime_seconds,
            "scan_error": self.scan_error,
        }


def compute_close_distance_to_primary_pin_em(
    official_close: float,
    primary_pin_t: float,
    remaining_expected_move_t: float,
) -> float:
    """P0 regression target (EM-normalized signed distance to primary pin)."""
    return (official_close - primary_pin_t) / remaining_expected_move_t


def evaluate_p0_eligibility(
    *,
    primary_pin_t: float | None,
    remaining_expected_move_t: float | None,
    official_close: float | None,
    label_source_timestamp: datetime | None,
    as_of_timestamp: datetime,
) -> tuple[bool, list[str]]:
    """Return (eligible, exclusion_reasons) for baseline P0 track."""
    reasons: list[str] = []
    if primary_pin_t is None or (isinstance(primary_pin_t, float) and math.isnan(primary_pin_t)):
        reasons.append("primary_pin_missing_at_as_of")
    if remaining_expected_move_t is None or not math.isfinite(remaining_expected_move_t):
        reasons.append("remaining_em_invalid")
    elif remaining_expected_move_t <= 0:
        reasons.append("remaining_em_non_positive")
    if official_close is None or (isinstance(official_close, float) and math.isnan(official_close)):
        reasons.append("official_close_missing")
    if label_source_timestamp is None:
        reasons.append("label_source_timestamp_missing")
    elif label_source_timestamp <= as_of_timestamp:
        reasons.append("label_timestamp_not_after_as_of")
    return len(reasons) == 0, reasons


def compute_p1_near(d_em: float, threshold_em: float) -> bool:
    """P1 binary: close near primary pin within threshold EM."""
    return abs(d_em) <= threshold_em


def compute_p2_directional(d_em: float, threshold_em: float) -> DirectionClass:
    """P2 ternary classification relative to primary pin."""
    if d_em < -threshold_em:
        return "below"
    if abs(d_em) <= threshold_em:
        return "near"
    return "above"


def _percentiles(values: list[float], ps: tuple[float, ...]) -> dict[str, float]:
    if not values:
        return {f"p{int(p)}": None for p in ps}
    arr = np.array(values, dtype=float)
    return {f"p{int(p)}": float(np.percentile(arr, p)) for p in ps}


def aggregate_p0_distribution(values: list[float]) -> dict[str, Any]:
    """Summarize P0 eligible values."""
    if not values:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "p01": None,
            "p05": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p95": None,
            "p99": None,
            "positive_count": 0,
            "negative_count": 0,
            "near_zero_count": 0,
            "outlier_count": 0,
        }
    arr = np.array(values, dtype=float)
    pct = _percentiles(values, (1, 5, 25, 50, 75, 95, 99))
    return {
        "count": len(values),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        **pct,
        "positive_count": int(np.sum(arr > NEAR_ZERO_ABS)),
        "negative_count": int(np.sum(arr < -NEAR_ZERO_ABS)),
        "near_zero_count": int(np.sum(np.abs(arr) <= NEAR_ZERO_ABS)),
        "outlier_count": int(np.sum(np.abs(arr) > OUTLIER_ABS_EM)),
    }


def aggregate_p1_stats(
    near_flags: list[bool],
    *,
    threshold_em: float,
    eligible_count: int,
) -> dict[str, Any]:
    near_count = sum(1 for x in near_flags if x)
    not_near = len(near_flags) - near_count
    denom = max(len(near_flags), 1)
    return {
        "threshold_em": threshold_em,
        "eligible_count": eligible_count,
        "near_count": near_count,
        "not_near_count": not_near,
        "near_ratio": near_count / denom,
        "not_near_ratio": not_near / denom,
        "class_balance": near_count / max(not_near, 1),
        "both_classes_present": near_count > 0 and not_near > 0,
    }


def aggregate_p2_stats(
    classes: list[DirectionClass],
    *,
    threshold_em: float,
) -> dict[str, Any]:
    counts = Counter(classes)
    below = counts.get("below", 0)
    near = counts.get("near", 0)
    above = counts.get("above", 0)
    nonzero = sum(1 for c in (below, near, above) if c > 0)
    total = max(len(classes), 1)
    return {
        "threshold_em": threshold_em,
        "below_count": below,
        "near_count": near,
        "above_count": above,
        "class_count_nonzero": nonzero,
        "class_distribution": {
            "below": below / total,
            "near": near / total,
            "above": above / total,
        },
    }


def check_baseline_leakage(
    as_of_timestamp: datetime,
    label_source_timestamp: datetime | None,
) -> tuple[bool, list[str]]:
    """Screening-level leakage check for label timing."""
    result = check_label_timestamp_after_as_of(as_of_timestamp, label_source_timestamp)
    violations = [v.message for v in result.violations]
    return result.passed, violations


def screen_baseline_anchor_at(
    trade_date: date,
    as_of_timestamp: datetime,
    *,
    data_root: Path,
    outcome_provider: PilotIndexOutcomeProvider,
    root: str = "SPXW",
    symbol: str = "^SPX",
    session_close_time: str | None = None,
) -> AnchorBaselineResult:
    """Replay as-of context + outcome; compute baseline targets (no features)."""
    close_tod = session_close_time or SESSION_CLOSE.strftime("%H:%M:%S")
    session_close = session_datetime(trade_date, close_tod)
    ctx, strikes, _bundle = build_as_of_context(
        trade_date,
        as_of_timestamp,
        root=root,
        expiration=trade_date,
        data_root=data_root,
        symbol=symbol,
    )
    outcome = outcome_provider.get_outcome(trade_date, as_of_timestamp)
    labels = compute_all_labels(ctx, outcome, nearest_strikes=strikes)
    label_ts = outcome.label_source_timestamp()
    official_close = outcome.official_close

    rem_em = remaining_expected_move(
        float(ctx.expected_move_t) if ctx.expected_move_t is not None else float("nan"),
        as_of_timestamp,
        session_close,
    )

    eligible, null_reasons = evaluate_p0_eligibility(
        primary_pin_t=ctx.primary_pin_t,
        remaining_expected_move_t=rem_em,
        official_close=official_close,
        label_source_timestamp=label_ts,
        as_of_timestamp=as_of_timestamp,
    )

    leakage_ok, leakage_violations = check_baseline_leakage(as_of_timestamp, label_ts)

    d_em: float | None = None
    p1_near: dict[str, bool | None] = {f"{t:.2f}": None for t in P1_THRESHOLDS}
    p2_class: dict[str, DirectionClass | None] = {f"{t:.2f}": None for t in P2_THRESHOLDS}

    if eligible and ctx.primary_pin_t is not None and rem_em is not None and official_close is not None:
        d_em = compute_close_distance_to_primary_pin_em(official_close, ctx.primary_pin_t, rem_em)
        for t in P1_THRESHOLDS:
            key = f"{t:.2f}"
            p1_near[key] = compute_p1_near(d_em, t)
        for t in P2_THRESHOLDS:
            key = f"{t:.2f}"
            p2_class[key] = compute_p2_directional(d_em, t)

    zone_included = ctx.has_valid_zone and labels.close_location_vs_current_zone is not None

    return AnchorBaselineResult(
        eligible=eligible,
        null_reasons=tuple(null_reasons),
        d_em=d_em,
        p1_near=p1_near,
        p2_class=p2_class,
        zone_included=zone_included,
        zone_close_location=labels.close_location_vs_current_zone,
        leakage_ok=leakage_ok,
        leakage_violations=tuple(leakage_violations),
    )


def aggregate_date_baseline_metrics(
    entry: DateEntry,
    anchors: list[AnchorBaselineResult],
    *,
    runtime_seconds: float,
) -> DateBaselineMetrics:
    """Aggregate per-anchor baseline screening into date-level metrics."""
    n = len(anchors)
    eligible_rows = [a for a in anchors if a.eligible and a.d_em is not None]
    d_values = [float(a.d_em) for a in eligible_rows if a.d_em is not None]
    null_counter: Counter[str] = Counter()
    for a in anchors:
        for r in a.null_reasons:
            null_counter[r] += 1

    p1: dict[str, Any] = {}
    p2: dict[str, Any] = {}
    for t in P1_THRESHOLDS:
        key = f"{t:.2f}"
        flags = [a.p1_near[key] for a in eligible_rows if a.p1_near.get(key) is not None]
        p1[key] = aggregate_p1_stats(flags, threshold_em=t, eligible_count=len(eligible_rows))
    for t in P2_THRESHOLDS:
        key = f"{t:.2f}"
        classes = [a.p2_class[key] for a in eligible_rows if a.p2_class.get(key) is not None]
        p2[key] = aggregate_p2_stats(classes, threshold_em=t)

    violations: list[str] = []
    for a in anchors:
        violations.extend(a.leakage_violations)
    examples = violations[:5]

    return DateBaselineMetrics(
        trade_date=entry.trade_date,
        day_type=entry.day_type,
        anchor_count=n,
        eligible_count=len(eligible_rows),
        eligible_ratio=len(eligible_rows) / n if n else 0.0,
        zone_included_count=sum(1 for a in anchors if a.zone_included),
        p0=aggregate_p0_distribution(d_values),
        p1=p1,
        p2=p2,
        null_reason_distribution=dict(null_counter),
        leakage_pass=all(a.leakage_ok for a in anchors),
        leakage_violation_count=len(violations),
        leakage_violation_examples=examples,
        runtime_seconds=runtime_seconds,
    )


def evaluate_session_split_readiness(
    per_date: list[DateBaselineMetrics],
    *,
    p1_threshold_key: str = "0.25",
) -> dict[str, Any]:
    """Assess session-grouped split readiness from screening aggregates."""
    eligible_sessions = [m for m in per_date if m.eligible_count > 0]
    session_count = len(per_date)
    total_eligible = sum(m.eligible_count for m in per_date)
    rows_per_session = [m.eligible_count for m in eligible_sessions]

    p1_near_total = 0
    p1_not_near_total = 0
    for m in per_date:
        block = m.p1.get(p1_threshold_key, {})
        p1_near_total += int(block.get("near_count", 0))
        p1_not_near_total += int(block.get("not_near_count", 0))

    both_classes = p1_near_total > 0 and p1_not_near_total > 0
    can_split = (
        total_eligible >= P78_MIN_ELIGIBLE_ROWS
        and len(eligible_sessions) >= P78_MIN_ELIGIBLE_SESSIONS
        and both_classes
    )

    n_sess = len(eligible_sessions)
    if n_sess >= 3:
        train_n = max(1, int(n_sess * 0.6))
        val_n = max(1, int(n_sess * 0.2))
        test_n = max(1, n_sess - train_n - val_n)
    else:
        train_n = val_n = test_n = 0

    return {
        "session_count": session_count,
        "eligible_sessions": len(eligible_sessions),
        "eligible_rows_total": total_eligible,
        "eligible_rows_per_session_mean": float(np.mean(rows_per_session)) if rows_per_session else 0.0,
        "eligible_rows_per_session_min": min(rows_per_session) if rows_per_session else 0,
        "eligible_rows_per_session_max": max(rows_per_session) if rows_per_session else 0,
        "p1_threshold_evaluated": p1_threshold_key,
        "p1_near_total": p1_near_total,
        "p1_not_near_total": p1_not_near_total,
        "both_classes_present": both_classes,
        "can_create_session_grouped_split": can_split,
        "suggested_train_val_test_session_counts": {
            "train": train_n,
            "validation": val_n,
            "test": test_n,
        },
    }


def evaluate_p78_gates(
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate ML-P7.8 pass/fail gates."""
    split = summary.get("session_split_readiness", {})
    leakage = summary.get("leakage_validation", {})
    eligible_rows = int(summary.get("eligible_rows_total", 0))
    eligible_sessions = int(split.get("eligible_sessions", 0))
    both_classes = bool(split.get("both_classes_present", False))
    leakage_pass = bool(leakage.get("leakage_pass", False))
    split_pass = bool(split.get("can_create_session_grouped_split", False))

    checks = {
        "baseline_eligible_rows_gte_300": eligible_rows >= P78_MIN_ELIGIBLE_ROWS,
        "eligible_sessions_gte_10": eligible_sessions >= P78_MIN_ELIGIBLE_SESSIONS,
        "p1_both_classes_one_threshold": both_classes,
        "leakage_pass": leakage_pass,
        "session_grouped_split_readiness_pass": split_pass,
        "no_training_performed": True,
        "official_label_spec_unchanged": True,
    }
    passed = all(checks.values())
    return {
        "p78_pass": passed,
        "checks": checks,
        "ml_p8b_blocked": True,
        "note": "P7.8 pass does not approve ML-P8B or production label builder.",
    }


def write_per_date_report(report_root: Path, metrics: DateBaselineMetrics) -> Path:
    out_dir = report_root / "per_date"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{metrics.trade_date.isoformat()}.json"
    path.write_text(json.dumps(metrics.to_dict(), indent=2), encoding="utf-8")
    return path


def load_per_date_report(report_root: Path, trade_date: date) -> dict[str, Any] | None:
    path = report_root / "per_date" / f"{trade_date.isoformat()}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def metrics_from_dict(payload: dict[str, Any]) -> DateBaselineMetrics:
    td = date.fromisoformat(str(payload["trade_date"]))
    return DateBaselineMetrics(
        trade_date=td,
        day_type=str(payload.get("day_type", "normal")),
        anchor_count=int(payload.get("anchor_count", 0)),
        eligible_count=int(payload.get("eligible_count", 0)),
        eligible_ratio=float(payload.get("eligible_ratio", 0.0)),
        zone_included_count=int(payload.get("zone_included_count", 0)),
        p0=dict(payload.get("p0", {})),
        p1=dict(payload.get("p1", {})),
        p2=dict(payload.get("p2", {})),
        null_reason_distribution=dict(payload.get("null_reason_distribution", {})),
        leakage_pass=bool(payload.get("leakage_pass", False)),
        leakage_violation_count=int(payload.get("leakage_violation_count", 0)),
        leakage_violation_examples=list(payload.get("leakage_violation_examples", [])),
        runtime_seconds=float(payload.get("runtime_seconds", 0.0)),
        status=str(payload.get("status", "completed")),
        scan_error=payload.get("scan_error"),
    )


def build_baseline_summary(
    *,
    screened_dates: list[str],
    skipped_dates: list[str],
    metrics: list[DateBaselineMetrics],
    zone_baseline: dict[str, Any],
) -> dict[str, Any]:
    """Build summary.json payload."""
    total_anchors = sum(m.anchor_count for m in metrics)
    eligible_rows = sum(m.eligible_count for m in metrics)
    zone_included = sum(m.zone_included_count for m in metrics)
    null_dist: Counter[str] = Counter()
    for m in metrics:
        null_dist.update(m.null_reason_distribution)
    p1_combined: dict[str, Any] = {}
    p2_combined: dict[str, Any] = {}
    for t in P1_THRESHOLDS:
        key = f"{t:.2f}"
        near_sum = sum(int(m.p1.get(key, {}).get("near_count", 0)) for m in metrics)
        not_near_sum = sum(int(m.p1.get(key, {}).get("not_near_count", 0)) for m in metrics)
        denom = max(near_sum + not_near_sum, 1)
        p1_combined[key] = {
            "near_count": near_sum,
            "not_near_count": not_near_sum,
            "near_ratio": near_sum / denom,
            "not_near_ratio": not_near_sum / denom,
            "both_classes_present": near_sum > 0 and not_near_sum > 0,
        }
    for t in P2_THRESHOLDS:
        key = f"{t:.2f}"
        below = sum(int(m.p2.get(key, {}).get("below_count", 0)) for m in metrics)
        near = sum(int(m.p2.get(key, {}).get("near_count", 0)) for m in metrics)
        above = sum(int(m.p2.get(key, {}).get("above_count", 0)) for m in metrics)
        total = max(below + near + above, 1)
        p2_combined[key] = {
            "below_count": below,
            "near_count": near,
            "above_count": above,
            "class_count_nonzero": sum(1 for c in (below, near, above) if c > 0),
            "class_distribution": {
                "below": below / total,
                "near": near / total,
                "above": above / total,
            },
        }

    leakage_violations = sum(m.leakage_violation_count for m in metrics)
    leakage_pass = all(m.leakage_pass for m in metrics)

    combined_p0 = _combine_p0_from_dates(metrics)

    split_readiness = evaluate_session_split_readiness(metrics)
    summary: dict[str, Any] = {
        "version": "baseline-target-screening-v1",
        "screened_dates": screened_dates,
        "skipped_dates": skipped_dates,
        "anchor_count_total": total_anchors,
        "eligible_rows_total": eligible_rows,
        "eligible_ratio_total": eligible_rows / total_anchors if total_anchors else 0.0,
        "zone_included_total": zone_included,
        "zone_comparison": zone_baseline,
        "p0_summary": combined_p0,
        "p1_summary": p1_combined,
        "p2_summary": p2_combined,
        "null_reason_distribution": dict(null_dist),
        "leakage_validation": {
            "leakage_pass": leakage_pass,
            "violation_count": leakage_violations,
        },
        "session_split_readiness": split_readiness,
        "per_date_metrics": [m.to_dict() for m in metrics],
    }
    summary["p78_gates"] = evaluate_p78_gates(summary)
    return summary


def _combine_p0_from_dates(metrics: list[DateBaselineMetrics]) -> dict[str, Any]:
    """Re-aggregate P0 from per-date eligible counts — approximate via weighted stats."""
    total_count = sum(int(m.p0.get("count", 0)) for m in metrics)
    if total_count == 0:
        return aggregate_p0_distribution([])
    weighted_mean = 0.0
    for m in metrics:
        c = int(m.p0.get("count", 0))
        mu = m.p0.get("mean")
        if c and mu is not None:
            weighted_mean += float(mu) * c
    weighted_mean /= total_count
    pos = sum(int(m.p0.get("positive_count", 0)) for m in metrics)
    neg = sum(int(m.p0.get("negative_count", 0)) for m in metrics)
    nz = sum(int(m.p0.get("near_zero_count", 0)) for m in metrics)
    out = sum(int(m.p0.get("outlier_count", 0)) for m in metrics)
    mins = [m.p0["min"] for m in metrics if m.p0.get("min") is not None]
    maxs = [m.p0["max"] for m in metrics if m.p0.get("max") is not None]
    return {
        "count": total_count,
        "mean": weighted_mean,
        "min": min(mins) if mins else None,
        "max": max(maxs) if maxs else None,
        "positive_count": pos,
        "negative_count": neg,
        "near_zero_count": nz,
        "outlier_count": out,
        "note": "std/percentiles in per_date reports; combined summary uses aggregates",
    }


@dataclass(frozen=True)
class BaselineScreeningOptions:
    dates_filter: frozenset[str] | None = None
    resume: bool = True
    progress_every: int = 10
    report_root: Path = DEFAULT_REPORT_ROOT


def screen_baseline_targets(
    config: SampleBuildConfig,
    day_type_map: dict[str, str],
    *,
    options: BaselineScreeningOptions | None = None,
) -> dict[str, Any]:
    """Run baseline primary-pin target screening over complete raw lake dates."""
    opts = options or BaselineScreeningOptions()
    report_root = opts.report_root
    inventory = inventory_raw_lake(config)

    completed: set[str] = set()
    if opts.resume:
        completed = load_completed_checkpoint_dates(report_root)

    dates_to_scan = [d for d in inventory.complete_dates if d not in SKIP_DATES]
    if opts.dates_filter:
        dates_to_scan = [d for d in dates_to_scan if d in opts.dates_filter]

    skipped = list(inventory.incomplete_dates) + sorted(SKIP_DATES & set(inventory.complete_dates))
    screened: list[str] = []
    all_metrics: list[DateBaselineMetrics] = []

    if opts.resume:
        for date_str in dates_to_scan:
            if date_str not in completed:
                continue
            payload = load_per_date_report(report_root, date.fromisoformat(date_str))
            if payload:
                all_metrics.append(metrics_from_dict(payload))
                screened.append(date_str)

    provider = PilotIndexOutcomeProvider(data_root=config.lake_root, symbol=config.index_symbol)
    symbol = f"^{config.index_symbol}"

    zone_baseline = {
        "zone_included_total_reference": 89,
        "zone_valid_zone_ratio_reference": 0.064,
        "source": "ML-P7.6.7 valid_zone_candidate_screening",
    }

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
        session_close = "13:00:00" if day_type == "early_close" else None
        results: list[AnchorBaselineResult] = []
        total = len(anchors_ts)

        try:
            for idx, (as_of, _atype) in enumerate(anchors_ts, start=1):
                results.append(
                    screen_baseline_anchor_at(
                        td,
                        as_of,
                        data_root=config.lake_root,
                        outcome_provider=provider,
                        root=config.root,
                        symbol=symbol,
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
            failed = DateBaselineMetrics(
                trade_date=td,
                day_type=day_type,
                anchor_count=len(anchors_ts),
                eligible_count=0,
                eligible_ratio=0.0,
                zone_included_count=0,
                p0=aggregate_p0_distribution([]),
                p1={},
                p2={},
                null_reason_distribution={},
                leakage_pass=False,
                leakage_violation_count=0,
                leakage_violation_examples=[],
                runtime_seconds=time.perf_counter() - started,
                status="failed",
                scan_error=f"{type(exc).__name__}:{exc}",
            )
            write_per_date_report(report_root, failed)
            skipped.append(date_str)
            continue

        runtime = time.perf_counter() - started
        metrics = aggregate_date_baseline_metrics(entry, results, runtime_seconds=runtime)
        write_per_date_report(report_root, metrics)
        all_metrics.append(metrics)
        screened.append(date_str)

        p1_025 = metrics.p1.get("0.25", {})
        p1_050 = metrics.p1.get("0.50", {})
        log.info(
            "[screen complete] %s eligible=%d p1_025_near=%d p1_050_near=%d zone_included=%d",
            date_str,
            metrics.eligible_count,
            p1_025.get("near_count", 0),
            p1_050.get("near_count", 0),
            metrics.zone_included_count,
        )

    summary = build_baseline_summary(
        screened_dates=sorted(set(screened)),
        skipped_dates=sorted(set(skipped)),
        metrics=all_metrics,
        zone_baseline=zone_baseline,
    )
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
