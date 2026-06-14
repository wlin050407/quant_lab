"""Feature-layer leakage checks (extends ML-P6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from quant_lab.ml.features.schemas import FORBIDDEN_FEATURE_COLUMNS, LABEL_PREFIXES
from quant_lab.ml.leakage import (
    LeakageCheckResult,
    LeakageViolation,
    LeakageViolationType,
    check_label_separate_from_features,
    check_no_final_volume_in_features,
)


def check_no_label_columns_in_features(feature_dict: dict[str, Any]) -> LeakageCheckResult:
    violations: list[LeakageViolation] = []
    for key in feature_dict:
        if key.startswith(LABEL_PREFIXES) or key.startswith("labels."):
            violations.append(
                LeakageViolation(
                    LeakageViolationType.LABEL_IN_FEATURE_SOURCE,
                    f"label column in features: {key}",
                    key,
                )
            )
        if key in FORBIDDEN_FEATURE_COLUMNS:
            violations.append(
                LeakageViolation(
                    LeakageViolationType.LABEL_IN_FEATURE_SOURCE,
                    f"forbidden outcome column in features: {key}",
                    key,
                )
            )
    return LeakageCheckResult(passed=len(violations) == 0, violations=violations)


def check_feature_row_leakage(
    feature_row: dict[str, Any],
    as_of_timestamp: datetime,
    *,
    source_timestamp_max: datetime | None,
    join_keys: dict[str, str] | None = None,
    label_row_keys: dict[str, str] | None = None,
) -> LeakageCheckResult:
    violations: list[LeakageViolation] = []
    feats = {k.replace("features.", ""): v for k, v in feature_row.items() if k.startswith("features.")}
    feats.update({k: v for k, v in feature_row.items() if not k.startswith("features.") and k not in {
        "feature_schema_version", "trade_date", "as_of_timestamp", "feature_cutoff_timestamp",
        "replay_state_hash", "deterministic_bundle_hash", "source_timestamp_max",
        "source_partition_hashes", "feature_warnings", "feature_exclusion_reasons", "split",
    }})

    for result in [
        check_no_label_columns_in_features(feats),
        check_no_final_volume_in_features(feats.keys()),
        check_label_separate_from_features(feats),
    ]:
        violations.extend(result.violations)

    if source_timestamp_max is not None and source_timestamp_max > as_of_timestamp:
        violations.append(
            LeakageViolation(
                LeakageViolationType.FEATURE_AFTER_AS_OF,
                f"source_timestamp_max {source_timestamp_max} > as_of {as_of_timestamp}",
            )
        )

    if join_keys and label_row_keys:
        for k in ("replay_state_hash", "deterministic_bundle_hash", "trade_date", "as_of_timestamp"):
            if join_keys.get(k) != label_row_keys.get(k):
                violations.append(
                    LeakageViolation(
                        LeakageViolationType.ZONE_MISMATCH_FOR_LABEL,
                        f"join key mismatch on {k}",
                        k,
                    )
                )

    forbidden_outcome = {"official_close", "future_index_path", "normalized_close_move"}
    for key in feats:
        if key in forbidden_outcome or key.startswith("labels."):
            violations.append(
                LeakageViolation(
                    LeakageViolationType.LABEL_IN_FEATURE_SOURCE,
                    f"outcome leaked into features: {key}",
                    key,
                )
            )

    return LeakageCheckResult(passed=len(violations) == 0, violations=violations)


def check_adversarial_feature_injection(
    as_of: datetime,
    *,
    quote_ts: datetime | None = None,
    trade_ts: datetime | None = None,
    index_ts: datetime | None = None,
    iv_ts: datetime | None = None,
    feature_dict: dict[str, Any] | None = None,
) -> LeakageCheckResult:
    violations: list[LeakageViolation] = []
    timestamps = [
        (quote_ts, LeakageViolationType.FUTURE_QUOTE_IN_FEATURES),
        (trade_ts, LeakageViolationType.FUTURE_TRADE_IN_FEATURES),
        (index_ts, LeakageViolationType.FUTURE_INDEX_IN_FEATURES),
        (iv_ts, LeakageViolationType.FUTURE_GREEK_IN_FEATURES),
    ]
    for ts, vtype in timestamps:
        if ts is not None and ts > as_of:
            violations.append(LeakageViolation(vtype, f"future timestamp {ts}", str(vtype)))
    if feature_dict:
        violations.extend(check_no_label_columns_in_features(feature_dict).violations)
        violations.extend(check_no_final_volume_in_features(feature_dict.keys()).violations)
    return LeakageCheckResult(passed=len(violations) == 0, violations=violations)
