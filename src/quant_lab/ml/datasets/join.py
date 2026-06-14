"""Strict feature+label join for ML-P7.5 sample datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

JOIN_KEYS: tuple[str, ...] = (
    "trade_date",
    "as_of_timestamp",
    "replay_state_hash",
    "deterministic_bundle_hash",
)

METADATA_COLUMNS: tuple[str, ...] = (
    "dataset_schema_version",
    "label_schema_version",
    "feature_schema_version",
    "deterministic_contract_version",
    "trade_date",
    "as_of_timestamp",
    "feature_cutoff_timestamp",
    "session_id",
    "anchor_type",
    "replay_state_hash",
    "deterministic_bundle_hash",
    "source_partition_hashes",
    "source_timestamp_max",
    "sample_weight",
    "exclusion_reasons",
    "warning_codes",
    "split_group",
)


class JoinKeyMismatchError(ValueError):
    """Raised when label and feature rows cannot be joined on strict hash keys."""


@dataclass
class JoinedRow:
    """One joined supervised sample (features + labels, no training)."""

    row: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.row)


def _normalize_join_value(key: str, value: Any) -> str:
    if value is None:
        return ""
    if key == "as_of_timestamp" and isinstance(value, datetime):
        return value.isoformat()
    if key == "as_of_timestamp":
        return str(value)
    return str(value)


def extract_join_keys(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in JOIN_KEYS:
        if key not in row:
            raise JoinKeyMismatchError(f"missing join key {key} in row")
        out[key] = _normalize_join_value(key, row[key])
    return out


def strict_join_label_feature(
    label_row: dict[str, Any],
    feature_row: dict[str, Any],
) -> JoinedRow:
    """Join one label row with one feature row using exact hash keys only."""
    label_keys = extract_join_keys(label_row)
    feature_keys = extract_join_keys(feature_row)
    mismatches = [k for k in JOIN_KEYS if label_keys[k] != feature_keys[k]]
    if mismatches:
        raise JoinKeyMismatchError(
            f"join key mismatch on {mismatches}: label={label_keys} feature={feature_keys}"
        )

    merged: dict[str, Any] = {}
    for col in METADATA_COLUMNS:
        if col in label_row:
            merged[col] = label_row[col]
        elif col in feature_row:
            merged[col] = feature_row[col]

    for key, value in label_row.items():
        if key.startswith("labels."):
            merged[key] = value
    for key, value in feature_row.items():
        if key.startswith("features."):
            if key in merged:
                raise JoinKeyMismatchError(f"duplicate feature column after join: {key}")
            merged[key] = value

    merged["join_keys_verified"] = True
    merged["join_method"] = "strict_hash_keys"
    return JoinedRow(row=merged)


def strict_join_batches(
    label_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
) -> list[JoinedRow]:
    """Join batches by hash key index — no nearest merge, order-independent."""
    feature_index = {tuple(extract_join_keys(r).items()): r for r in feature_rows}
    joined: list[JoinedRow] = []
    for label in label_rows:
        key = tuple(extract_join_keys(label).items())
        if key not in feature_index:
            raise JoinKeyMismatchError(f"no feature row for join key {dict(key)}")
        joined.append(strict_join_label_feature(label, feature_index[key]))
    return joined
