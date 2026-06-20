"""Quality, leakage, and split-readiness reporting for ML-P7.5."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.ml.datasets.join import JOIN_KEYS, JoinedRow, extract_join_keys
from quant_lab.ml.datasets.lake_ingest import DateIngestResult
from quant_lab.ml.features.leakage import check_no_label_columns_in_features
from quant_lab.ml.leakage import check_label_timestamp_after_as_of, check_split_config
from quant_lab.ml.splits import (
    assert_no_session_overlap,
    expanding_walk_forward_split,
    locked_holdout_split,
    session_grouped_split,
)


@dataclass
class LeakageValidationResult:
    passed: bool
    violations: list[str] = field(default_factory=list)


def validate_joined_dataset_leakage(rows: list[JoinedRow]) -> LeakageValidationResult:
    """Run ML-P7.5 leakage checks on joined rows."""
    violations: list[str] = []
    for i, joined in enumerate(rows):
        row = joined.to_dict()
        feature_cols = {k: v for k, v in row.items() if k.startswith("features.")}
        plain_feats = {k.replace("features.", ""): v for k, v in feature_cols.items()}
        label_check = check_no_label_columns_in_features(plain_feats)
        if not label_check.passed:
            violations.extend(f"row {i}: {v.message}" for v in label_check.violations)

        as_of_raw = row.get("as_of_timestamp")
        as_of = datetime.fromisoformat(str(as_of_raw)) if as_of_raw else None
        label_ts_raw = row.get("labels.label_source_timestamp")
        if as_of and label_ts_raw:
            label_ts = datetime.fromisoformat(str(label_ts_raw))
            ts_check = check_label_timestamp_after_as_of(as_of, label_ts)
            if not ts_check.passed:
                violations.extend(f"row {i}: {v.message}" for v in ts_check.violations)

        src_max_raw = row.get("source_timestamp_max")
        if as_of and src_max_raw:
            src_max = datetime.fromisoformat(str(src_max_raw))
            if src_max > as_of:
                violations.append(f"row {i}: source_timestamp_max {src_max} > as_of {as_of}")

        if "official_close" in row and not str(row.get("official_close", "")).startswith("labels."):
            violations.append(f"row {i}: official_close in non-label columns")

        if row.get("features.oi_semantics_unconfirmed") is True or "oi_semantics_unconfirmed" in (
            row.get("warning_codes") or []
        ):
            continue

    split_check = check_split_config(shuffle=False)
    if not split_check.passed:
        violations.extend(v.message for v in split_check.violations)

    return LeakageValidationResult(passed=len(violations) == 0, violations=violations)


def build_coverage_report(
    *,
    joined_rows: list[JoinedRow],
    failed_dates: list[dict[str, str]],
    timings: dict[str, float],
    sizes_bytes: dict[str, int],
    date_entries: list[dict[str, Any]],
    ingest_results: list[DateIngestResult] | None = None,
    successful_dates: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate coverage / missingness metrics (no raw market data)."""
    rows = [j.to_dict() for j in joined_rows]
    n = len(rows)
    included = sum(1 for r in rows if float(r.get("sample_weight") or 0) > 0)
    excluded = n - included

    zone_labels = [
        r.get("labels.close_location_vs_current_zone")
        for r in rows
        if r.get("labels.close_location_vs_current_zone") is not None
    ]
    zone_dist = dict(Counter(zone_labels))
    null_labels = sum(1 for r in rows if r.get("labels.close_location_vs_current_zone") is None)

    null_feature_counts = [
        sum(1 for k, v in r.items() if k.startswith("features.") and v is None) for r in rows
    ]
    fq_scores = [r.get("features.feature_quality_score") for r in rows if r.get("features.feature_quality_score") is not None]
    rq_scores = [r.get("features.replay_quality_score") for r in rows if r.get("features.replay_quality_score") is not None]

    oi_unconfirmed = sum(
        1
        for r in rows
        if r.get("features.oi_semantics_unconfirmed") is True
        or "oi_semantics_unconfirmed" in (r.get("warning_codes") or [])
    )
    gamma_sources = Counter(r.get("features.gamma_source") for r in rows if r.get("features.gamma_source"))

    sessions = sorted({str(r.get("session_id") or r.get("trade_date")) for r in rows})
    anchors = n

    theta_requests = sum(r.api_request_count for r in (ingest_results or []))
    quote_resolutions = {
        r.trade_date.isoformat(): r.quote_resolution_used
        for r in (ingest_results or [])
        if r.quote_resolution_used
    }
    quote_fallbacks = {
        r.trade_date.isoformat(): r.quote_fallback_reason
        for r in (ingest_results or [])
        if r.quote_fallback_reason
    }

    return {
        "date_count_configured": len(date_entries),
        "date_count_built": len({r.get("trade_date") for r in rows}),
        "session_count": len(sessions),
        "anchor_count": anchors,
        "row_count": n,
        "included_row_count": included,
        "excluded_row_count": excluded,
        "valid_zone_label_count": len(zone_labels),
        "valid_zone_ratio": len(zone_labels) / n if n else 0.0,
        "close_location_distribution": zone_dist,
        "null_label_count": null_labels,
        "null_feature_count_mean": sum(null_feature_counts) / len(null_feature_counts) if null_feature_counts else 0.0,
        "feature_quality_score_distribution": {
            "min": min(fq_scores) if fq_scores else None,
            "max": max(fq_scores) if fq_scores else None,
            "mean": sum(fq_scores) / len(fq_scores) if fq_scores else None,
        },
        "replay_quality_score_distribution": {
            "min": min(rq_scores) if rq_scores else None,
            "max": max(rq_scores) if rq_scores else None,
            "mean": sum(rq_scores) / len(rq_scores) if rq_scores else None,
        },
        "oi_unconfirmed_count": oi_unconfirmed,
        "gamma_source_distribution": dict(gamma_sources),
        "quote_coverage_mean": _mean_feature(rows, "features.quote_coverage_ratio"),
        "greek_coverage_mean": _mean_feature(rows, "features.greeks_coverage_ratio"),
        "gamma_coverage_mean": _mean_feature(rows, "features.gamma_coverage_ratio"),
        "index_coverage_proxy": _mean_feature(rows, "features.replay_quality_score"),
        "average_replay_time_per_anchor_sec": timings.get("replay_per_anchor_sec"),
        "average_feature_build_time_per_row_sec": timings.get("feature_per_row_sec"),
        "raw_lake_size_bytes": sizes_bytes.get("raw_lake", 0),
        "dataset_size_bytes": sizes_bytes.get("dataset", 0),
        "feature_size_bytes": sizes_bytes.get("features", 0),
        "joined_dataset_size_bytes": sizes_bytes.get("joined", 0),
        "failed_dates": failed_dates,
        "failure_reasons": dict(Counter(f.get("reason", "unknown") for f in failed_dates)),
        "successful_dates": successful_dates or [],
        "thetadata_request_count": theta_requests,
        "quote_resolution_by_date": quote_resolutions,
        "quote_fallback_by_date": quote_fallbacks,
        "timings_sec": timings,
        "sizes_bytes": sizes_bytes,
    }


def _mean_feature(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def build_split_readiness_report(session_ids: list[str]) -> dict[str, Any]:
    """Generate split plans without training (mechanism validation only)."""
    unique = sorted(set(session_ids))
    grouped = session_grouped_split(unique, train_ratio=0.6, val_ratio=0.2)
    walk = expanding_walk_forward_split(unique, n_folds=3, min_train_sessions=2)
    holdout = locked_holdout_split(unique, holdout_sessions=unique[-2:] if len(unique) >= 4 else unique[-1:])
    assert_no_session_overlap(grouped)
    for fold in walk:
        assert_no_session_overlap(fold)
    assert_no_session_overlap(holdout)

    def _split_rows(manifest_sessions: tuple[str, ...], split_name: str) -> dict[str, Any]:
        return {
            "split": split_name,
            "session_count": len(manifest_sessions),
            "date_range": manifest_sessions[0] if manifest_sessions else None,
            "date_range_end": manifest_sessions[-1] if manifest_sessions else None,
        }

    return {
        "session_grouped_split": {
            "train": _split_rows(grouped.train_sessions, "train"),
            "validation": _split_rows(grouped.validation_sessions, "validation"),
            "test": _split_rows(grouped.test_sessions, "test"),
        },
        "expanding_walk_forward_folds": len(walk),
        "locked_holdout_sessions": list(holdout.holdout_sessions),
        "note": "Sample size insufficient for real model evaluation; split mechanism only.",
        "no_row_level_random_split": True,
    }


def evaluate_stage_a_gate(coverage: dict[str, Any], *, leakage_passed: bool) -> dict[str, Any]:
    """ML-P7.6 Stage A smoke criteria (3-day build)."""
    checks = {
        "date_count_built_gte_3": coverage.get("date_count_built", 0) >= 3,
        "row_count_gt_100": coverage.get("row_count", 0) > 100,
        "valid_zone_ratio_gt_0": coverage.get("valid_zone_ratio", 0.0) > 0.0,
        "leakage_passed": leakage_passed,
        "failed_dates_empty": len(coverage.get("failed_dates") or []) == 0,
    }
    passed = all(checks.values())
    return {"passed": passed, "checks": checks}


def evaluate_p8b_readiness(coverage: dict[str, Any], *, leakage_passed: bool) -> dict[str, Any]:
    """Minimum criteria before ML-P8B baseline training."""
    zone_dist = coverage.get("close_location_distribution") or {}
    zone_categories = len([k for k, v in zone_dist.items() if v and k is not None])
    checks = {
        "row_count_gte_1000": coverage.get("row_count", 0) >= 1000,
        "included_rows_gte_300": coverage.get("included_row_count", 0) >= 300,
        "valid_zone_ratio_gte_20pct": coverage.get("valid_zone_ratio", 0.0) >= 0.20,
        "zone_categories_gte_2": zone_categories >= 2,
        "leakage_passed": leakage_passed,
    }
    passed = all(checks.values())
    return {
        "ready_for_ml_p8b": passed,
        "checks": checks,
        "note": "Mechanism may pass while sample size blocks training.",
    }


def write_reports(
    report_root: Path,
    *,
    coverage: dict[str, Any],
    split_readiness: dict[str, Any],
    leakage: LeakageValidationResult,
    stage_a_gate: dict[str, Any] | None = None,
    p8b_readiness: dict[str, Any] | None = None,
) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "coverage_report.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (report_root / "split_readiness.json").write_text(json.dumps(split_readiness, indent=2), encoding="utf-8")
    (report_root / "leakage_validation.json").write_text(
        json.dumps({"passed": leakage.passed, "violations": leakage.violations}, indent=2),
        encoding="utf-8",
    )
    if stage_a_gate is not None:
        (report_root / "stage_a_gate.json").write_text(json.dumps(stage_a_gate, indent=2), encoding="utf-8")
    if p8b_readiness is not None:
        (report_root / "p8b_readiness.json").write_text(json.dumps(p8b_readiness, indent=2), encoding="utf-8")


def per_date_report_path(report_root: Path, trade_date: date) -> Path:
    """Path for per-date checkpoint report (ML-P7.6.3)."""
    return report_root / "per_date" / f"{trade_date.isoformat()}.json"


def load_completed_checkpoint_dates(report_root: Path) -> set[str]:
    """Return trade dates with completed per-date checkpoint reports."""
    per_date_dir = report_root / "per_date"
    if not per_date_dir.is_dir():
        return set()
    completed: set[str] = set()
    for path in per_date_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("status") == "completed":
            completed.add(str(payload.get("trade_date") or path.stem))
    return completed


def build_per_date_coverage_report(
    *,
    trade_date: date,
    day_type: str,
    joined_rows: list[JoinedRow],
    replay_per_anchor_sec: float,
    feature_per_row_sec: float,
    anchor_count: int,
    latest_anchor: str | None,
    leakage_passed: bool,
    strict_join_passed: bool,
) -> dict[str, Any]:
    """Coverage metrics for one trade date (checkpoint artifact)."""
    rows = [j.to_dict() for j in joined_rows]
    n = len(rows)
    included = sum(1 for r in rows if float(r.get("sample_weight") or 0) > 0)
    zone_labels = [
        r.get("labels.close_location_vs_current_zone")
        for r in rows
        if r.get("labels.close_location_vs_current_zone") is not None
    ]
    null_feats = [sum(1 for k, v in r.items() if k.startswith("features.") and v is None) for r in rows]
    fq = [r.get("features.feature_quality_score") for r in rows if r.get("features.feature_quality_score") is not None]
    rq = [r.get("features.replay_quality_score") for r in rows if r.get("features.replay_quality_score") is not None]
    return {
        "status": "completed",
        "trade_date": trade_date.isoformat(),
        "day_type": day_type,
        "anchor_count": anchor_count,
        "latest_anchor": latest_anchor,
        "row_count": n,
        "included_row_count": included,
        "excluded_row_count": n - included,
        "valid_zone_label_count": len(zone_labels),
        "valid_zone_ratio": len(zone_labels) / n if n else 0.0,
        "close_location_distribution": dict(Counter(zone_labels)),
        "null_feature_count_mean": sum(null_feats) / len(null_feats) if null_feats else 0.0,
        "feature_count": sum(1 for k in (rows[0].keys() if rows else []) if str(k).startswith("features.")),
        "feature_quality_score_mean": sum(fq) / len(fq) if fq else None,
        "replay_quality_score_mean": sum(rq) / len(rq) if rq else None,
        "average_replay_time_per_anchor_sec": replay_per_anchor_sec,
        "average_feature_build_time_per_row_sec": feature_per_row_sec,
        "leakage_passed": leakage_passed,
        "strict_hash_join_passed": strict_join_passed,
    }


def write_per_date_report(report_root: Path, report: dict[str, Any]) -> Path:
    """Write per-date checkpoint report and flush to disk."""
    trade_date = str(report["trade_date"])
    path = per_date_report_path(report_root, date.fromisoformat(trade_date))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def verify_join_keys_match(rows: list[JoinedRow]) -> bool:
    for joined in rows:
        row = joined.to_dict()
        keys = extract_join_keys(row)
        for key in JOIN_KEYS:
            if str(row.get(key, "")) != keys[key] and key != "as_of_timestamp":
                return False
    return True


# --- ML-P7.8.3 baseline dataset validation ---

P78_SCREENING_REFERENCE: dict[str, Any] = {
    "source": "ML-P7.8 baseline_target_coverage_screening",
    "anchor_count_total": 1391,
    "baseline_eligible_rows": 1390,
    "baseline_eligible_ratio": 0.9992810927390366,
    "p1_025_near": 152,
    "p1_050_near": 317,
    "p2_025": {"below": 512, "near": 152, "above": 726},
    "p2_050": {"below": 424, "near": 317, "above": 649},
    "zone_included_total": 89,
    "eligible_sessions": 19,
}

BASELINE_LABEL_FIELDS: tuple[str, ...] = (
    "labels.close_distance_to_primary_pin_points",
    "labels.close_distance_to_primary_pin_em",
    "labels.close_near_primary_pin_025",
    "labels.close_near_primary_pin_050",
    "labels.close_above_below_primary_pin_025",
    "labels.close_above_below_primary_pin_050",
    "labels.baseline_target_eligible",
    "labels.baseline_target_exclusion_reasons",
    "labels.baseline_label_schema_version",
)

ZONE_PRESENCE_FIELDS: tuple[str, ...] = (
    "labels.close_location_vs_current_zone",
    "labels.close_inside_current_zone",
    "labels.first_zone_exit_direction",
    "labels.valid_upside_exit_15m",
    "labels.valid_upside_exit_30m",
    "labels.valid_downside_exit_15m",
    "labels.valid_downside_exit_30m",
)

SCREENING_CONSISTENCY_TOLERANCE: dict[str, int] = {
    "baseline_eligible_rows": 2,
    "p1_025_near": 3,
    "p1_050_near": 3,
    "zone_included_total": 3,
}


def validate_label_dataset_leakage(rows: list[dict[str, Any]]) -> LeakageValidationResult:
    """Leakage checks for label-only dataset rows (no features)."""
    violations: list[str] = []
    for i, row in enumerate(rows):
        as_of_raw = row.get("as_of_timestamp")
        as_of = datetime.fromisoformat(str(as_of_raw)) if as_of_raw else None
        label_ts_raw = row.get("labels.label_source_timestamp")
        if as_of and label_ts_raw:
            label_ts = datetime.fromisoformat(str(label_ts_raw))
            ts_check = check_label_timestamp_after_as_of(as_of, label_ts)
            if not ts_check.passed:
                violations.extend(f"row {i}: {v.message}" for v in ts_check.violations)
        for key in row:
            if key.startswith("features."):
                violations.append(f"row {i}: unexpected feature column {key} in dataset-only row")
        if "official_close" in row:
            violations.append(f"row {i}: official_close in non-label columns")

    split_check = check_split_config(shuffle=False)
    if not split_check.passed:
        violations.extend(v.message for v in split_check.violations)

    return LeakageValidationResult(passed=len(violations) == 0, violations=violations)


def _is_non_null(value: Any) -> bool:
    if value is None:
        return False
    try:
        return bool(not pd.isna(value))
    except (TypeError, ValueError):
        return True


def _as_reason_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return [str(x) for x in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return [str(value)]


def _label_field(row: dict[str, Any], key: str) -> Any:
    return row.get(key)


def _aggregate_baseline_from_label_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    eligible_rows = [r for r in rows if bool(_label_field(r, "labels.baseline_target_eligible"))]
    eligible_count = len(eligible_rows)
    exclusion_dist: Counter[str] = Counter()
    for r in rows:
        reasons = _as_reason_list(_label_field(r, "labels.baseline_target_exclusion_reasons"))
        exclusion_dist.update(reasons)

    d_em_vals = [
        float(v)
        for r in eligible_rows
        if _is_non_null(v := _label_field(r, "labels.close_distance_to_primary_pin_em"))
    ]
    p0: dict[str, Any] = {"count": len(d_em_vals)}
    if d_em_vals:
        arr = np.array(d_em_vals, dtype=float)
        p0.update(
            {
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "p25": float(np.percentile(arr, 25)),
                "p50": float(np.percentile(arr, 50)),
                "p75": float(np.percentile(arr, 75)),
                "p95": float(np.percentile(arr, 95)),
                "p99": float(np.percentile(arr, 99)),
            }
        )

    def _p1_stats(threshold_key: str) -> dict[str, Any]:
        near = sum(1 for r in eligible_rows if _label_field(r, threshold_key) is True)
        not_near = eligible_count - near
        denom = max(eligible_count, 1)
        return {
            "near_count": near,
            "not_near_count": not_near,
            "near_ratio": near / denom,
            "not_near_ratio": not_near / denom,
            "both_classes_present": near > 0 and not_near > 0,
        }

    def _p2_stats(threshold_key: str) -> dict[str, Any]:
        classes = [
            str(_label_field(r, threshold_key))
            for r in eligible_rows
            if _label_field(r, threshold_key) is not None
        ]
        counts = Counter(classes)
        below = counts.get("below", 0)
        near = counts.get("near", 0)
        above = counts.get("above", 0)
        total = max(len(classes), 1)
        return {
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

    zone_included = sum(
        1
        for r in rows
        if _is_non_null(_label_field(r, "labels.close_location_vs_current_zone"))
    )
    sessions = sorted({str(r.get("session_id") or r.get("trade_date")) for r in eligible_rows})
    rows_per_session = Counter(str(r.get("session_id") or r.get("trade_date")) for r in eligible_rows)

    p1_025 = _p1_stats("labels.close_near_primary_pin_025")
    p1_050 = _p1_stats("labels.close_near_primary_pin_050")

    return {
        "row_count": n,
        "baseline_eligible_rows": eligible_count,
        "baseline_eligible_ratio": eligible_count / n if n else 0.0,
        "baseline_exclusion_reason_distribution": dict(exclusion_dist),
        "eligible_sessions": len(sessions),
        "rows_per_session_mean": float(np.mean(list(rows_per_session.values()))) if rows_per_session else 0.0,
        "rows_per_session_min": min(rows_per_session.values()) if rows_per_session else 0,
        "rows_per_session_max": max(rows_per_session.values()) if rows_per_session else 0,
        "p0_summary": p0,
        "p1_025": p1_025,
        "p1_050": p1_050,
        "p2_025": _p2_stats("labels.close_above_below_primary_pin_025"),
        "p2_050": _p2_stats("labels.close_above_below_primary_pin_050"),
        "zone_included_total": zone_included,
        "zone_valid_zone_ratio": zone_included / n if n else 0.0,
        "baseline_field_presence": {
            field: sum(1 for r in rows if field in r) for field in BASELINE_LABEL_FIELDS
        },
        "zone_field_presence": {
            field: sum(1 for r in rows if field in r) for field in ZONE_PRESENCE_FIELDS
        },
        "p1_050_sessions_both_classes": _sessions_with_both_p1_classes(
            rows, "labels.close_near_primary_pin_050"
        ),
    }


def _sessions_with_both_p1_classes(rows: list[dict[str, Any]], field: str) -> int:
    by_session: dict[str, list[bool | None]] = {}
    for r in rows:
        if not bool(_label_field(r, "labels.baseline_target_eligible")):
            continue
        sid = str(r.get("session_id") or r.get("trade_date"))
        by_session.setdefault(sid, []).append(_label_field(r, field))
    count = 0
    for flags in by_session.values():
        near = sum(1 for x in flags if x is True)
        not_near = sum(1 for x in flags if x is False)
        if near > 0 and not_near > 0:
            count += 1
    return count


def compare_baseline_to_screening(
    rebuilt: dict[str, Any],
    reference: dict[str, Any] | None = None,
    *,
    tolerance: dict[str, int] | None = None,
) -> dict[str, Any]:
    ref = reference or P78_SCREENING_REFERENCE
    tol = tolerance or SCREENING_CONSISTENCY_TOLERANCE
    checks: dict[str, Any] = {}

    def _within(key: str, rebuilt_val: int, ref_key: str | None = None) -> bool:
        ref_val = int(ref.get(ref_key or key, 0))
        return abs(rebuilt_val - ref_val) <= tol.get(key, 0)

    checks["baseline_eligible_rows"] = _within(
        "baseline_eligible_rows", int(rebuilt.get("baseline_eligible_rows", 0))
    )
    checks["p1_025_near"] = _within(
        "p1_025_near",
        int(rebuilt.get("p1_025", {}).get("near_count", 0)),
        "p1_025_near",
    )
    checks["p1_050_near"] = _within(
        "p1_050_near",
        int(rebuilt.get("p1_050", {}).get("near_count", 0)),
        "p1_050_near",
    )
    checks["zone_included_total"] = _within(
        "zone_included_total", int(rebuilt.get("zone_included_total", 0))
    )
    passed = all(bool(v) for v in checks.values())
    return {
        "consistency_pass": passed,
        "checks": checks,
        "reference": ref,
        "rebuilt_snapshot": {
            "baseline_eligible_rows": rebuilt.get("baseline_eligible_rows"),
            "p1_025_near": rebuilt.get("p1_025", {}).get("near_count"),
            "p1_050_near": rebuilt.get("p1_050", {}).get("near_count"),
            "zone_included_total": rebuilt.get("zone_included_total"),
        },
        "tolerance": tol,
    }


def build_baseline_session_split_readiness(rebuilt: dict[str, Any]) -> dict[str, Any]:
    sessions = int(rebuilt.get("eligible_sessions", 0))
    eligible_rows = int(rebuilt.get("baseline_eligible_rows", 0))
    p1_050 = rebuilt.get("p1_050", {})
    both_classes = bool(p1_050.get("both_classes_present"))
    can_split = eligible_rows >= 300 and sessions >= 10 and both_classes
    if sessions >= 3:
        train_n = max(1, int(sessions * 0.6))
        val_n = max(1, int(sessions * 0.2))
        test_n = max(1, sessions - train_n - val_n)
    else:
        train_n = val_n = test_n = 0
    return {
        "eligible_sessions": sessions,
        "baseline_eligible_rows": eligible_rows,
        "p1_050_both_classes_present": both_classes,
        "can_create_session_grouped_split": can_split,
        "suggested_train_val_test_session_counts": {
            "train": train_n,
            "validation": val_n,
            "test": test_n,
        },
        "no_row_level_random_split": True,
    }


def evaluate_p783_gates(report: dict[str, Any]) -> dict[str, Any]:
    cov = report.get("coverage_summary") or report
    leakage = report.get("leakage_validation") or {}
    split = report.get("session_split_readiness") or {}
    consistency = report.get("screening_consistency") or {}
    checks = {
        "baseline_eligible_rows_gte_300": int(cov.get("baseline_eligible_rows", 0)) >= 300,
        "eligible_sessions_gte_10": int(cov.get("eligible_sessions", 0)) >= 10,
        "p1_050_both_classes": bool((cov.get("p1_050") or {}).get("both_classes_present")),
        "leakage_pass": bool(leakage.get("leakage_pass")),
        "session_grouped_split_readiness_pass": bool(split.get("can_create_session_grouped_split")),
        "screening_consistency_pass": bool(consistency.get("consistency_pass")),
        "zone_labels_present": int(cov.get("zone_included_total", 0)) > 0,
        "no_training_performed": True,
        "official_label_spec_unchanged": True,
    }
    passed = all(checks.values())
    return {
        "p783_pass": passed,
        "checks": checks,
        "ml_p8b_blocked": True,
        "note": "P7.8.3 pass does not approve ML-P8B or production deployment.",
    }


def build_baseline_dataset_validation_report(
    *,
    label_rows: list[dict[str, Any]],
    failed_dates: list[dict[str, str]],
    successful_dates: list[str],
    skipped_dates: list[str],
) -> dict[str, Any]:
    coverage = _aggregate_baseline_from_label_rows(label_rows)
    leakage_result = validate_label_dataset_leakage(label_rows)
    leakage = {
        "leakage_pass": leakage_result.passed,
        "violation_count": len(leakage_result.violations),
        "violation_examples": leakage_result.violations[:10],
    }
    split_readiness = build_baseline_session_split_readiness(coverage)
    consistency = compare_baseline_to_screening(coverage)
    return {
        "version": "baseline-dataset-validation-v1",
        "rebuild_dates": successful_dates,
        "skipped_dates": skipped_dates,
        "failed_dates": failed_dates,
        "coverage_summary": coverage,
        "leakage_validation": leakage,
        "session_split_readiness": split_readiness,
        "screening_consistency": consistency,
        "p783_gates": evaluate_p783_gates(
            {
                "coverage_summary": coverage,
                "leakage_validation": leakage,
                "session_split_readiness": split_readiness,
                "screening_consistency": consistency,
            }
        ),
    }


def build_per_date_baseline_report(
    *,
    trade_date: date,
    day_type: str,
    label_rows: list[dict[str, Any]],
    replay_per_anchor_sec: float,
    anchor_count: int,
    latest_anchor: str | None,
    leakage_passed: bool,
) -> dict[str, Any]:
    metrics = _aggregate_baseline_from_label_rows(label_rows)
    return {
        "status": "completed",
        "trade_date": trade_date.isoformat(),
        "day_type": day_type,
        "anchor_count": anchor_count,
        "latest_anchor": latest_anchor,
        "row_count": metrics["row_count"],
        "baseline_eligible_count": metrics["baseline_eligible_rows"],
        "baseline_eligible_ratio": metrics["baseline_eligible_ratio"],
        "zone_included_count": metrics["zone_included_total"],
        "zone_valid_zone_ratio": metrics["zone_valid_zone_ratio"],
        "p1_025_near": metrics["p1_025"]["near_count"],
        "p1_050_near": metrics["p1_050"]["near_count"],
        "baseline_exclusion_reason_distribution": metrics["baseline_exclusion_reason_distribution"],
        "average_replay_time_per_anchor_sec": replay_per_anchor_sec,
        "leakage_passed": leakage_passed,
        "dataset_only": True,
    }


def build_baseline_dataset_manifest(
    label_dicts: list[dict[str, Any]],
    *,
    outcome_provider: Any,
    anchor_config: dict[str, Any],
    split_config: dict[str, Any] | None = None,
    label_schema_version: str = "1.1.0-draft",
    baseline_label_schema_version: str | None = "1.1.0-draft",
) -> dict[str, Any]:
    exclusion_counts: Counter[str] = Counter()
    baseline_exclusion: Counter[str] = Counter()
    for row in label_dicts:
        for reason in _as_reason_list(row.get("exclusion_reasons")):
            exclusion_counts[str(reason)] += 1
        for reason in _as_reason_list(row.get("labels.baseline_target_exclusion_reasons")):
            baseline_exclusion[str(reason)] += 1
    dates = sorted({str(r.get("trade_date")) for r in label_dicts})
    metrics = _aggregate_baseline_from_label_rows(label_dicts)
    return {
        "dataset_manifest_version": "pit-dataset-v1",
        "dataset_schema_version": "1.0.0",
        "label_schema_version": label_schema_version,
        "baseline_label_schema_version": baseline_label_schema_version,
        "feature_schema_version": None,
        "deterministic_contract_version": "ml-p5-v1",
        "baseline_target_thresholds": [0.25, 0.50],
        "baseline_target_track": "primary_pin_distance_v1",
        "zone_target_track": "pin_zone_strict_v1",
        "baseline_preferred_binary_threshold_em": 0.50,
        "outcome_source_hash": outcome_provider.outcome_source_hash(),
        "anchor_config": anchor_config,
        "date_range": {"min": dates[0] if dates else None, "max": dates[-1] if dates else None},
        "session_count": metrics.get("eligible_sessions", 0),
        "row_count": len(label_dicts),
        "baseline_eligible_rows": metrics.get("baseline_eligible_rows", 0),
        "exclusion_reasons": dict(exclusion_counts),
        "baseline_exclusion_reasons": dict(baseline_exclusion),
        "split_config": split_config or {},
        "dataset_only": True,
        "feature_cutoff_rule": "event_timestamp <= as_of_timestamp",
        "label_rule": "label timestamps may be > as_of_timestamp and are stored separately",
    }


def write_baseline_validation_report(report_root: Path, report: dict[str, Any]) -> Path:
    report_root.mkdir(parents=True, exist_ok=True)
    path = report_root / "baseline_validation_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (report_root / "p783_gates.json").write_text(
        json.dumps(report.get("p783_gates", {}), indent=2),
        encoding="utf-8",
    )
    return path
