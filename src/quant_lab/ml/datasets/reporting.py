"""Quality, leakage, and split-readiness reporting for ML-P7.5."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from quant_lab.ml.datasets.join import JOIN_KEYS, JoinedRow, extract_join_keys
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


def write_reports(report_root: Path, *, coverage: dict[str, Any], split_readiness: dict[str, Any], leakage: LeakageValidationResult) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "coverage_report.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (report_root / "split_readiness.json").write_text(json.dumps(split_readiness, indent=2), encoding="utf-8")
    (report_root / "leakage_validation.json").write_text(
        json.dumps({"passed": leakage.passed, "violations": leakage.violations}, indent=2),
        encoding="utf-8",
    )


def verify_join_keys_match(rows: list[JoinedRow]) -> bool:
    for joined in rows:
        row = joined.to_dict()
        keys = extract_join_keys(row)
        for key in JOIN_KEYS:
            if str(row.get(key, "")) != keys[key] and key != "as_of_timestamp":
                return False
    return True
