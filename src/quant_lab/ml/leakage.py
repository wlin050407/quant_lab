"""Leakage detection for ML-P6 point-in-time datasets."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from quant_lab.ml.schemas import AsOfContext


class LeakageViolationType(StrEnum):
    FEATURE_AFTER_AS_OF = "feature_timestamp_after_as_of"
    LABEL_NOT_AFTER_AS_OF = "label_timestamp_not_after_as_of"
    FINAL_VOLUME_IN_FEATURES = "final_volume_in_features"
    FUTURE_QUOTE_IN_FEATURES = "future_quote_in_features"
    FUTURE_TRADE_IN_FEATURES = "future_trade_in_features"
    FUTURE_GREEK_IN_FEATURES = "future_greek_in_features"
    FUTURE_GAMMA_IN_FEATURES = "future_gamma_in_features"
    FUTURE_INDEX_IN_FEATURES = "future_index_in_features"
    FUTURE_OI_IN_FEATURES = "future_oi_in_features"
    POST_CLOSE_ZONE_RECOMPUTE = "post_close_zone_recompute"
    ZONE_MISMATCH_FOR_LABEL = "zone_mismatch_for_label"
    RANDOM_ROW_SPLIT = "random_row_split"
    LABEL_IN_FEATURE_SOURCE = "label_in_feature_source"
    SHUFFLE_SPLIT = "shuffle_split_enabled"


@dataclass
class LeakageViolation:
    violation_type: LeakageViolationType
    message: str
    field: str | None = None


@dataclass
class LeakageCheckResult:
    passed: bool
    violations: list[LeakageViolation] = field(default_factory=list)

    def raise_if_failed(self) -> None:
        if not self.passed:
            msgs = "; ".join(f"{v.violation_type.value}: {v.message}" for v in self.violations)
            raise ValueError(f"Leakage check failed: {msgs}")


def check_feature_timestamp_cutoff(
    as_of_timestamp: datetime,
    feature_timestamps: Iterable[tuple[str, datetime | None]],
) -> LeakageCheckResult:
    violations: list[LeakageViolation] = []
    for field_name, ts in feature_timestamps:
        if ts is None:
            continue
        if ts > as_of_timestamp:
            violations.append(
                LeakageViolation(
                    LeakageViolationType.FEATURE_AFTER_AS_OF,
                    f"{field_name} timestamp {ts} > as_of {as_of_timestamp}",
                    field_name,
                )
            )
    return LeakageCheckResult(passed=len(violations) == 0, violations=violations)


def check_label_timestamp_after_as_of(
    as_of_timestamp: datetime,
    label_source_timestamp: datetime | None,
) -> LeakageCheckResult:
    if label_source_timestamp is None:
        return LeakageCheckResult(passed=True)
    if label_source_timestamp <= as_of_timestamp:
        return LeakageCheckResult(
            passed=False,
            violations=[
                LeakageViolation(
                    LeakageViolationType.LABEL_NOT_AFTER_AS_OF,
                    f"label_source {label_source_timestamp} <= as_of {as_of_timestamp}",
                )
            ],
        )
    return LeakageCheckResult(passed=True)


def check_no_final_volume_in_features(feature_columns: Iterable[str]) -> LeakageCheckResult:
    banned = {"final_volume", "daily_volume", "session_total_volume", "eod_volume"}
    found = [c for c in feature_columns if c.lower() in banned]
    if found:
        return LeakageCheckResult(
            passed=False,
            violations=[
                LeakageViolation(
                    LeakageViolationType.FINAL_VOLUME_IN_FEATURES,
                    f"final volume fields in features: {found}",
                )
            ],
        )
    return LeakageCheckResult(passed=True)


def check_future_market_data_in_features(
    as_of_timestamp: datetime,
    *,
    quote_ts: datetime | None = None,
    trade_ts: datetime | None = None,
    greek_ts: datetime | None = None,
    gamma_ts: datetime | None = None,
    index_ts: datetime | None = None,
    oi_ts: datetime | None = None,
    oi_trade_date: str | None = None,
    feature_trade_date: str | None = None,
) -> LeakageCheckResult:
    violations: list[LeakageViolation] = []
    checks = [
        (quote_ts, LeakageViolationType.FUTURE_QUOTE_IN_FEATURES, "quote"),
        (trade_ts, LeakageViolationType.FUTURE_TRADE_IN_FEATURES, "trade"),
        (greek_ts, LeakageViolationType.FUTURE_GREEK_IN_FEATURES, "greek"),
        (gamma_ts, LeakageViolationType.FUTURE_GAMMA_IN_FEATURES, "gamma"),
        (index_ts, LeakageViolationType.FUTURE_INDEX_IN_FEATURES, "index"),
        (oi_ts, LeakageViolationType.FUTURE_OI_IN_FEATURES, "oi"),
    ]
    for ts, vtype, name in checks:
        if ts is not None and ts > as_of_timestamp:
            violations.append(
                LeakageViolation(vtype, f"future {name} timestamp {ts} > as_of", name)
            )
    if oi_trade_date and feature_trade_date and oi_trade_date > feature_trade_date:
        violations.append(
            LeakageViolation(
                LeakageViolationType.FUTURE_OI_IN_FEATURES,
                f"next-day OI trade_date {oi_trade_date} > feature {feature_trade_date}",
            )
        )
    return LeakageCheckResult(passed=len(violations) == 0, violations=violations)


def check_zone_for_label_matches_as_of(
    label_zone_low: float | None,
    label_zone_high: float | None,
    ctx: AsOfContext,
) -> LeakageCheckResult:
    if label_zone_low != ctx.zone_low_t or label_zone_high != ctx.zone_high_t:
        return LeakageCheckResult(
            passed=False,
            violations=[
                LeakageViolation(
                    LeakageViolationType.ZONE_MISMATCH_FOR_LABEL,
                    "label zone differs from as-of deterministic bundle zone",
                )
            ],
        )
    return LeakageCheckResult(passed=True)


def check_post_close_zone_recompute(
    zone_computed_at: datetime | None,
    session_close: datetime,
) -> LeakageCheckResult:
    if zone_computed_at is not None and zone_computed_at > session_close:
        return LeakageCheckResult(
            passed=False,
            violations=[
                LeakageViolation(
                    LeakageViolationType.POST_CLOSE_ZONE_RECOMPUTE,
                    f"zone computed at {zone_computed_at} after session close",
                )
            ],
        )
    return LeakageCheckResult(passed=True)


def check_split_config(
    *,
    shuffle: bool = False,
    group_key: str | None = None,
    split_method: str = "session_grouped",
) -> LeakageCheckResult:
    violations: list[LeakageViolation] = []
    if shuffle:
        violations.append(
            LeakageViolation(
                LeakageViolationType.SHUFFLE_SPLIT,
                "shuffle=True is not allowed for session-grouped splits",
            )
        )
    if split_method == "random_row":
        violations.append(
            LeakageViolation(
                LeakageViolationType.RANDOM_ROW_SPLIT,
                "row-level random split is forbidden",
            )
        )
    if group_key not in {None, "session_id", "trade_date"}:
        violations.append(
            LeakageViolation(
                LeakageViolationType.RANDOM_ROW_SPLIT,
                f"invalid split group key: {group_key}",
            )
        )
    return LeakageCheckResult(passed=len(violations) == 0, violations=violations)


def check_label_separate_from_features(
    feature_dict: dict[str, Any],
    label_prefix: str = "labels.",
) -> LeakageCheckResult:
    leaked = [k for k in feature_dict if k.startswith(label_prefix) or k == "official_close"]
    if leaked:
        return LeakageCheckResult(
            passed=False,
            violations=[
                LeakageViolation(
                    LeakageViolationType.LABEL_IN_FEATURE_SOURCE,
                    f"label fields found in feature dict: {leaked}",
                )
            ],
        )
    return LeakageCheckResult(passed=True)


def run_full_leakage_checks(
    as_of_timestamp: datetime,
    ctx: AsOfContext,
    *,
    feature_timestamps: Iterable[tuple[str, datetime | None]] | None = None,
    label_source_timestamp: datetime | None = None,
    feature_columns: Iterable[str] | None = None,
    label_zone: tuple[float | None, float | None] | None = None,
    split_shuffle: bool = False,
) -> LeakageCheckResult:
    """Aggregate standard ML-P6 leakage checks."""
    all_violations: list[LeakageViolation] = []

    def merge(result: LeakageCheckResult) -> None:
        all_violations.extend(result.violations)

    if feature_timestamps is not None:
        merge(check_feature_timestamp_cutoff(as_of_timestamp, feature_timestamps))
    merge(check_label_timestamp_after_as_of(as_of_timestamp, label_source_timestamp))
    if feature_columns is not None:
        merge(check_no_final_volume_in_features(feature_columns))
    if label_zone is not None:
        merge(check_zone_for_label_matches_as_of(label_zone[0], label_zone[1], ctx))
    merge(check_split_config(shuffle=split_shuffle))
    merge(check_post_close_zone_recompute(ctx.as_of_timestamp, ctx.as_of_timestamp))

    return LeakageCheckResult(passed=len(all_violations) == 0, violations=all_violations)


def assert_adversarial_injection_rejected(
    injection_type: LeakageViolationType,
    check_fn: Any,
) -> None:
    """Helper for tests: adversarial injection must fail leakage check."""
    result = check_fn()
    if result.passed:
        raise AssertionError(f"Expected rejection for {injection_type.value}")
    types = {v.violation_type for v in result.violations}
    if injection_type not in types:
        raise AssertionError(
            f"Expected {injection_type.value}, got {[t.value for t in types]}"
        )


def validate_dataset_rows_no_feature_leakage(
    rows: list[dict[str, Any]],
) -> LeakageCheckResult:
    """Ensure row dicts keep labels separate and respect cutoff metadata."""
    violations: list[LeakageViolation] = []
    for i, row in enumerate(rows):
        feat_keys = [k for k in row if not k.startswith("labels.")]
        if "official_close" in feat_keys and "labels.official_close_source" not in row:
            violations.append(
                LeakageViolation(
                    LeakageViolationType.LABEL_IN_FEATURE_SOURCE,
                    f"row {i}: official_close in feature columns",
                )
            )
        cutoff = row.get("feature_cutoff_timestamp")
        as_of = row.get("as_of_timestamp")
        if cutoff and as_of and cutoff != as_of:
            violations.append(
                LeakageViolation(
                    LeakageViolationType.FEATURE_AFTER_AS_OF,
                    f"row {i}: feature_cutoff != as_of",
                )
            )
    return LeakageCheckResult(passed=len(violations) == 0, violations=violations)
