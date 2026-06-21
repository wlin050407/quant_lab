"""Forbidden feature / label column validation for ML-P8B harness."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FORBIDDEN_EXACT: frozenset[str] = frozenset(
    {
        "official_close",
        "future_return",
        "future_high",
        "future_low",
        "post_as_of_volume",
        "final_daily_volume",
        "label_source_timestamp",
        "close_distance_to_primary_pin_em",
        "close_near_primary_pin_050",
        "close_near_primary_pin_025",
        "close_above_below_primary_pin_050",
        "close_above_below_primary_pin_025",
        "baseline_target_eligible",
        "baseline_target_exclusion_reasons",
        "baseline_label_schema_version",
        "close_location_vs_current_zone",
        "close_inside_current_zone",
        "normalized_close_move",
    }
)

FORBIDDEN_PREFIXES: tuple[str, ...] = ("labels.",)

FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "official_close",
    "future_return",
    "future_high",
    "future_low",
)

FORBIDDEN_REGEX: tuple[re.Pattern[str], ...] = (
    re.compile(r"^labels\.", re.IGNORECASE),
    re.compile(r"future", re.IGNORECASE),
)

ALLOWLIST_EXACT: frozenset[str] = frozenset(
    {
        "as_of_timestamp",
        "trade_date",
        "session_id",
        "replay_state_hash",
        "deterministic_bundle_hash",
        "feature_cutoff_timestamp",
        "dataset_schema_version",
        "label_schema_version",
        "feature_schema_version",
        "deterministic_contract_version",
        "anchor_type",
        "expiration",
        "root",
        "split",
        "split_group",
        "sample_weight",
    }
)


@dataclass
class ForbiddenInputResult:
    passed: bool
    forbidden_columns: list[str] = field(default_factory=list)
    warning_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "forbidden_columns": list(self.forbidden_columns),
            "warning_columns": list(self.warning_columns),
        }


def _normalize_column(name: str) -> str:
    if name.startswith("labels."):
        return name
    return name.split(".")[-1] if "." in name and name.count(".") == 1 else name


def _is_allowlisted(column: str) -> bool:
    if column in ALLOWLIST_EXACT:
        return True
    base = _normalize_column(column)
    return base in ALLOWLIST_EXACT


def _check_column(column: str) -> tuple[bool, str | None]:
    if _is_allowlisted(column):
        return False, None
    base = _normalize_column(column)
    if column in FORBIDDEN_EXACT or base in FORBIDDEN_EXACT:
        return True, "exact_forbidden"
    for prefix in FORBIDDEN_PREFIXES:
        if column.startswith(prefix):
            return True, "labels_prefix"
    for sub in FORBIDDEN_SUBSTRINGS:
        if sub in column.lower():
            return True, "forbidden_substring"
    for pattern in FORBIDDEN_REGEX:
        if (
            pattern.search(column)
            and not _is_allowlisted(column)
            and not ("future" in pattern.pattern.lower() and column in ALLOWLIST_EXACT)
        ):
            return True, "pattern_match"
    return False, None


def validate_forbidden_features(columns: list[str]) -> ForbiddenInputResult:
    """Return pass/fail and lists of forbidden / warning columns."""
    forbidden: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for col in columns:
        if col in seen:
            continue
        seen.add(col)
        is_forbidden, reason = _check_column(col)
        if is_forbidden:
            forbidden.append(col)
        elif reason == "pattern_match" and "future" in col.lower() and col not in ALLOWLIST_EXACT:
            warnings.append(col)
    return ForbiddenInputResult(
        passed=len(forbidden) == 0,
        forbidden_columns=sorted(forbidden),
        warning_columns=sorted(warnings),
    )
