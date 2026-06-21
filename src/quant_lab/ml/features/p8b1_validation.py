"""ML-P8B.1 feature dataset validation — strict join, leakage, coverage."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from quant_lab.ml.datasets.join import (
    JoinKeyMismatchError,
    extract_join_keys,
    strict_join_label_feature,
)
from quant_lab.ml.features.leakage import check_feature_row_leakage
from quant_lab.ml.features.schemas import FEATURE_CATALOG_BY_NAME
from quant_lab.ml.harness.validators import validate_forbidden_features


@dataclass
class StrictJoinValidationResult:
    input_dataset_rows: int
    feature_rows: int
    joined_rows: int
    missing_feature_rows: list[dict[str, Any]] = field(default_factory=list)
    duplicate_feature_keys: list[dict[str, Any]] = field(default_factory=list)
    join_pass: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_dataset_rows": self.input_dataset_rows,
            "feature_rows": self.feature_rows,
            "joined_rows": self.joined_rows,
            "missing_feature_rows": len(self.missing_feature_rows),
            "duplicate_feature_keys": len(self.duplicate_feature_keys),
            "join_pass": self.join_pass,
            "errors": list(self.errors),
            "missing_feature_examples": self.missing_feature_rows[:5],
            "duplicate_key_examples": self.duplicate_feature_keys[:5],
        }


@dataclass
class TimestampLeakageValidationResult:
    timestamp_leakage_pass: bool
    violation_count: int
    violation_examples: list[str] = field(default_factory=list)
    max_source_timestamp_delta_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_leakage_pass": self.timestamp_leakage_pass,
            "violation_count": self.violation_count,
            "violation_examples": self.violation_examples[:10],
            "max_source_timestamp_delta": self.max_source_timestamp_delta_seconds,
        }


@dataclass
class FeatureCoverageResult:
    feature_row_count: int
    feature_column_count: int
    feature_groups_present: dict[str, int]
    missingness_by_feature: dict[str, float]
    missingness_by_group: dict[str, float]
    high_missingness_features: list[str]
    constant_features: list[str]
    nan_inf_counts: dict[str, int]
    feature_quality_score_summary: dict[str, float]
    rows_per_session: dict[str, int]
    features_per_session: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_row_count": self.feature_row_count,
            "feature_column_count": self.feature_column_count,
            "feature_groups_present": self.feature_groups_present,
            "missingness_by_feature": self.missingness_by_feature,
            "missingness_by_group": self.missingness_by_group,
            "high_missingness_features": self.high_missingness_features,
            "constant_features": self.constant_features,
            "nan_inf_counts": self.nan_inf_counts,
            "feature_quality_score_summary": self.feature_quality_score_summary,
            "rows_per_session": self.rows_per_session,
            "features_per_session": self.features_per_session,
        }


def _join_key_tuple(row: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(extract_join_keys(row).items())


def validate_strict_hash_join(
    label_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
) -> StrictJoinValidationResult:
    """Validate four-key strict join between label and feature rows."""
    feature_index: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = defaultdict(list)
    for fr in feature_rows:
        feature_index[_join_key_tuple(fr)].append(fr)

    duplicate_keys: list[dict[str, Any]] = []
    for key, rows in feature_index.items():
        if len(rows) > 1:
            duplicate_keys.append({"join_key": dict(key), "count": len(rows)})

    missing: list[dict[str, Any]] = []
    joined_count = 0
    errors: list[str] = []

    for lr in label_rows:
        key = _join_key_tuple(lr)
        matches = feature_index.get(key, [])
        if not matches:
            missing.append({"join_key": dict(key), "trade_date": lr.get("trade_date")})
            continue
        if len(matches) > 1:
            errors.append(f"duplicate feature key {dict(key)}")
            continue
        try:
            strict_join_label_feature(lr, matches[0])
            joined_count += 1
        except JoinKeyMismatchError as exc:
            errors.append(str(exc))

    join_pass = (
        joined_count == len(label_rows)
        and len(missing) == 0
        and len(duplicate_keys) == 0
        and len(errors) == 0
    )
    return StrictJoinValidationResult(
        input_dataset_rows=len(label_rows),
        feature_rows=len(feature_rows),
        joined_rows=joined_count,
        missing_feature_rows=missing,
        duplicate_feature_keys=duplicate_keys,
        join_pass=join_pass,
        errors=errors,
    )


def extract_feature_value_columns(row: dict[str, Any]) -> list[str]:
    """Feature matrix column names (without ``features.`` prefix)."""
    return [k.replace("features.", "", 1) for k in row if k.startswith("features.")]


def validate_feature_matrix_forbidden(row: dict[str, Any]) -> dict[str, Any]:
    """Run forbidden-input validator on feature columns only."""
    feat_cols = extract_feature_value_columns(row)
    all_cols = list(row.keys())
    label_cols = [c for c in all_cols if c.startswith("labels.")]
    result = validate_forbidden_features(feat_cols)
    forbidden = list(result.forbidden_columns)
    if label_cols:
        forbidden.extend(label_cols)
    passed = len(forbidden) == 0
    return {
        "forbidden_input_pass": passed,
        "forbidden_columns": sorted(set(forbidden)),
        "warning_columns": result.warning_columns,
    }


def validate_feature_timestamp_leakage(
    feature_rows: list[dict[str, Any]],
) -> TimestampLeakageValidationResult:
    """Verify source_timestamp_max <= as_of for all feature rows."""
    violations: list[str] = []
    max_delta = 0.0
    for i, row in enumerate(feature_rows):
        as_of_raw = row.get("as_of_timestamp")
        if not as_of_raw:
            violations.append(f"row {i}: missing as_of_timestamp")
            continue
        as_of = datetime.fromisoformat(str(as_of_raw))
        src_raw = row.get("source_timestamp_max")
        src_max = datetime.fromisoformat(str(src_raw)) if src_raw else None
        leak = check_feature_row_leakage(row, as_of, source_timestamp_max=src_max)
        if not leak.passed:
            violations.extend(f"row {i}: {v.message}" for v in leak.violations[:3])
        if src_max is not None:
            delta = (src_max - as_of).total_seconds()
            if delta > max_delta:
                max_delta = delta
            if delta > 0:
                violations.append(
                    f"row {i}: source_timestamp_max {src_max.isoformat()} > as_of {as_of.isoformat()}"
                )
    return TimestampLeakageValidationResult(
        timestamp_leakage_pass=len(violations) == 0,
        violation_count=len(violations),
        violation_examples=violations[:20],
        max_source_timestamp_delta_seconds=max_delta if max_delta > 0 else None,
    )


def _feature_group(name: str) -> str:
    spec = FEATURE_CATALOG_BY_NAME.get(name)
    return spec.group if spec else "unknown"


def compute_feature_coverage(feature_rows: list[dict[str, Any]]) -> FeatureCoverageResult:
    """Aggregate missingness and quality stats over feature rows."""
    if not feature_rows:
        return FeatureCoverageResult(
            feature_row_count=0,
            feature_column_count=0,
            feature_groups_present={},
            missingness_by_feature={},
            missingness_by_group={},
            high_missingness_features=[],
            constant_features=[],
            nan_inf_counts={"nan": 0, "inf": 0},
            feature_quality_score_summary={},
            rows_per_session={},
            features_per_session={},
        )

    all_names: set[str] = set()
    for row in feature_rows:
        all_names.update(extract_feature_value_columns(row))

    null_counts: Counter[str] = Counter()
    value_sets: dict[str, set[Any]] = defaultdict(set)
    nan_count = 0
    inf_count = 0
    quality_scores: list[float] = []
    rows_per_session: Counter[str] = Counter()
    features_per_session: Counter[str] = Counter()

    for row in feature_rows:
        session = str(row.get("trade_date", row.get("session_id", "unknown")))
        rows_per_session[session] += 1
        features_per_session[session] += len(extract_feature_value_columns(row))
        q = row.get("features.feature_quality_score")
        if q is not None and isinstance(q, (int, float)) and math.isfinite(float(q)):
            quality_scores.append(float(q))
        for name in all_names:
            key = f"features.{name}"
            val = row.get(key)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                null_counts[name] += 1
            else:
                value_sets[name].add(val)
            if isinstance(val, float):
                if math.isnan(val):
                    nan_count += 1
                elif math.isinf(val):
                    inf_count += 1

    n = len(feature_rows)
    missingness = {name: null_counts[name] / n for name in sorted(all_names)}
    group_null: dict[str, list[float]] = defaultdict(list)
    for name, rate in missingness.items():
        group_null[_feature_group(name)].append(rate)
    missingness_by_group = {
        g: float(np.mean(rates)) if rates else 0.0 for g, rates in sorted(group_null.items())
    }
    high_missing = [k for k, v in missingness.items() if v > 0.5]
    constant = [k for k, vals in value_sets.items() if len(vals) <= 1]

    groups_present: Counter[str] = Counter()
    for name in all_names:
        if missingness.get(name, 1.0) < 1.0:
            groups_present[_feature_group(name)] += 1

    quality_summary: dict[str, float] = {}
    if quality_scores:
        quality_summary = {
            "mean": float(np.mean(quality_scores)),
            "min": float(np.min(quality_scores)),
            "max": float(np.max(quality_scores)),
        }

    return FeatureCoverageResult(
        feature_row_count=n,
        feature_column_count=len(all_names),
        feature_groups_present=dict(groups_present),
        missingness_by_feature=missingness,
        missingness_by_group=missingness_by_group,
        high_missingness_features=sorted(high_missing)[:50],
        constant_features=sorted(constant)[:50],
        nan_inf_counts={"nan": nan_count, "inf": inf_count},
        feature_quality_score_summary=quality_summary,
        rows_per_session=dict(rows_per_session),
        features_per_session=dict(features_per_session),
    )


def validate_all_feature_rows_forbidden(feature_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Batch forbidden-input validation across all feature rows."""
    all_forbidden: set[str] = set()
    all_warnings: set[str] = set()
    failing_rows = 0
    for row in feature_rows:
        res = validate_feature_matrix_forbidden(row)
        if not res["forbidden_input_pass"]:
            failing_rows += 1
        all_forbidden.update(res["forbidden_columns"])
        all_warnings.update(res["warning_columns"])
    return {
        "forbidden_input_pass": failing_rows == 0,
        "forbidden_columns": sorted(all_forbidden),
        "warning_columns": sorted(all_warnings),
        "failing_row_count": failing_rows,
    }
