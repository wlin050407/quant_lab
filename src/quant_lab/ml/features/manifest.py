"""Feature dataset manifest generation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from quant_lab.ml.features.schemas import (
    FEATURE_CATALOG,
    FEATURE_MANIFEST_VERSION,
    FEATURE_SCHEMA_VERSION,
    MAX_SOURCE_TIMESTAMP_RULE,
    FeatureRow,
)


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def hash_dataset_manifest(manifest: dict[str, Any] | None) -> str:
    if not manifest:
        return ""
    payload = json.dumps(
        {
            "dataset_manifest_version": manifest.get("dataset_manifest_version"),
            "row_count": manifest.get("row_count"),
            "outcome_source_hash": manifest.get("outcome_source_hash"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def build_feature_manifest(
    rows: list[FeatureRow],
    *,
    feature_config: dict[str, Any],
    dataset_manifest: dict[str, Any] | None = None,
    raw_lake_manifest_hashes: list[str] | None = None,
) -> dict[str, Any]:
    groups = Counter()
    for spec in FEATURE_CATALOG:
        groups[spec.group] += 1

    nullable_counts: list[int] = []
    missing_counts: list[int] = []
    excluded = 0
    for row in rows:
        nulls = sum(1 for v in row.features.values() if v is None)
        nullable_counts.append(nulls)
        missing_counts.append(len(row.feature_exclusion_reasons))
        if row.feature_exclusion_reasons:
            excluded += 1

    feature_names = {s.name for s in FEATURE_CATALOG}
    populated = set()
    for row in rows:
        populated.update(row.features.keys())

    return {
        "feature_manifest_version": FEATURE_MANIFEST_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_manifest_hash": hash_dataset_manifest(dataset_manifest),
        "raw_lake_manifest_hashes": raw_lake_manifest_hashes or [],
        "feature_config": feature_config,
        "row_count": len(rows),
        "excluded_row_count": excluded,
        "feature_count": len(feature_names),
        "populated_feature_count": len(populated & feature_names),
        "feature_groups": dict(groups),
        "nullable_feature_count_mean": (
            sum(nullable_counts) / len(nullable_counts) if nullable_counts else 0
        ),
        "missing_feature_count_mean": (
            sum(missing_counts) / len(missing_counts) if missing_counts else 0
        ),
        "max_source_timestamp_rule": MAX_SOURCE_TIMESTAMP_RULE,
        "known_open_questions": [
            "OI semantics not officially confirmed",
            "Pin score internal gamma recomputation",
        ],
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "code_commit": _git_commit(),
    }
