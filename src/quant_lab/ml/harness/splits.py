"""Session-grouped split validation for ML-P8B harness."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from quant_lab.ml.splits import SplitManifest, assert_no_session_overlap


@dataclass
class SplitValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    train_session_count: int = 0
    validation_session_count: int = 0
    test_session_count: int = 0
    train_row_count: int = 0
    validation_row_count: int = 0
    test_row_count: int = 0
    target_class_distribution: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "train_session_count": self.train_session_count,
            "validation_session_count": self.validation_session_count,
            "test_session_count": self.test_session_count,
            "train_row_count": self.train_row_count,
            "validation_row_count": self.validation_row_count,
            "test_row_count": self.test_row_count,
            "target_class_distribution": self.target_class_distribution,
        }


def _session_key(row: dict[str, Any], key: str) -> str:
    val = row.get(key)
    if val is None:
        val = row.get("trade_date")
    if val is None:
        raise ValueError(f"row missing session key {key!r} and trade_date")
    return str(val)


def _split_name_for_session(
    session: str,
    *,
    train_sessions: set[str],
    validation_sessions: set[str],
    test_sessions: set[str],
) -> str | None:
    hits: list[str] = []
    if session in train_sessions:
        hits.append("train")
    if session in validation_sessions:
        hits.append("validation")
    if session in test_sessions:
        hits.append("test")
    if len(hits) > 1:
        return "|".join(hits)
    return hits[0] if hits else None


def detect_row_level_random_split(
    rows: list[dict[str, Any]],
    *,
    session_key: str = "trade_date",
    split_key: str = "split",
) -> list[str]:
    """Detect rows from same session assigned to different splits (row-level leak)."""
    by_session: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if split_key not in row:
            continue
        sid = _session_key(row, session_key)
        by_session[sid].add(str(row[split_key]))
    errors: list[str] = []
    for sid, splits in by_session.items():
        if len(splits) > 1:
            errors.append(f"session {sid} appears in multiple splits: {sorted(splits)}")
    return errors


def validate_session_split(
    rows: list[dict[str, Any]],
    *,
    train_sessions: set[str] | list[str],
    validation_sessions: set[str] | list[str],
    test_sessions: set[str] | list[str],
    session_key: str = "trade_date",
    target_key: str | None = None,
    require_non_empty_validation: bool = True,
) -> SplitValidationResult:
    """Validate session-grouped split assignment and row coverage."""
    train = set(train_sessions)
    val = set(validation_sessions)
    test = set(test_sessions)
    errors: list[str] = []
    warnings: list[str] = []

    overlap_train_val = train & val
    overlap_train_test = train & test
    overlap_val_test = val & test
    if overlap_train_val:
        errors.append(f"duplicate trade_date in train and validation: {sorted(overlap_train_val)}")
    if overlap_train_test:
        errors.append(f"duplicate trade_date in train and test: {sorted(overlap_train_test)}")
    if overlap_val_test:
        errors.append(f"duplicate trade_date in validation and test: {sorted(overlap_val_test)}")

    if not train:
        errors.append("train_sessions is empty")
    if require_non_empty_validation and not val:
        errors.append("validation_sessions is empty")
    if not test:
        warnings.append("test_sessions is empty")

    manifest = SplitManifest(
        split_config={"method": "harness_validate"},
        train_sessions=tuple(sorted(train)),
        validation_sessions=tuple(sorted(val)),
        test_sessions=tuple(sorted(test)),
    )
    try:
        assert_no_session_overlap(manifest)
    except ValueError as exc:
        errors.append(str(exc))

    row_split_counts = {"train": 0, "validation": 0, "test": 0, "unassigned": 0}
    session_split_map: dict[str, str | None] = {}
    for row in rows:
        sid = _session_key(row, session_key)
        split = _split_name_for_session(
            sid,
            train_sessions=train,
            validation_sessions=val,
            test_sessions=test,
        )
        session_split_map[sid] = split
        if split is None:
            row_split_counts["unassigned"] += 1
        elif "|" in split:
            errors.append(f"same trade_date in multiple splits: {sid} -> {split}")
            row_split_counts["unassigned"] += 1
        else:
            row_split_counts[split] += 1

    random_split_errors = detect_row_level_random_split(rows, session_key=session_key)
    errors.extend(random_split_errors)

    target_dist: dict[str, dict[str, int]] = {}
    if target_key is not None:
        for split_name in ("train", "validation", "test"):
            split_sessions = {"train": train, "validation": val, "test": test}[split_name]
            values: list[Any] = []
            for row in rows:
                sid = _session_key(row, session_key)
                if sid not in split_sessions:
                    continue
                val_raw = row.get(target_key)
                if val_raw is not None and not (isinstance(val_raw, float) and np.isnan(val_raw)):
                    values.append(val_raw)
            if values:
                if isinstance(values[0], bool):
                    target_dist[split_name] = {
                        "near": sum(1 for v in values if v),
                        "not_near": sum(1 for v in values if not v),
                    }
                else:
                    target_dist[split_name] = dict(Counter(str(v) for v in values))

    passed = len(errors) == 0
    return SplitValidationResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        train_session_count=len(train),
        validation_session_count=len(val),
        test_session_count=len(test),
        train_row_count=row_split_counts["train"],
        validation_row_count=row_split_counts["validation"],
        test_row_count=row_split_counts["test"],
        target_class_distribution=target_dist,
    )
