"""Tests for ML-P7.5 reporting and leakage validation."""

from __future__ import annotations

import json
from pathlib import Path

from quant_lab.ml.datasets.join import JoinedRow
from quant_lab.ml.datasets.reporting import (
    build_coverage_report,
    build_split_readiness_report,
    validate_joined_dataset_leakage,
    write_reports,
)


def _joined(**kwargs: object) -> JoinedRow:
    row = {
        "trade_date": "2024-01-05",
        "as_of_timestamp": "2024-01-05T13:01:00-05:00",
        "replay_state_hash": "abc",
        "deterministic_bundle_hash": "def",
        "session_id": "2024-01-05",
        "sample_weight": 1.0,
        "labels.close_location_vs_current_zone": "inside",
        "labels.label_source_timestamp": "2024-01-05T16:00:00-05:00",
        "features.spot_t": 6000.0,
        "features.feature_quality_score": 0.9,
        "features.replay_quality_score": 0.85,
        "features.oi_semantics_unconfirmed": True,
        "warning_codes": ["oi_semantics_unconfirmed"],
        "source_timestamp_max": "2024-01-05T13:01:00-05:00",
    }
    row.update(kwargs)
    return JoinedRow(row=row)


def test_coverage_report_no_secrets() -> None:
    report = build_coverage_report(
        joined_rows=[_joined(), _joined(sample_weight=0.0)],
        failed_dates=[{"date": "2024-02-01", "reason": "missing_partitions"}],
        timings={"replay_per_anchor_sec": 0.1, "feature_per_row_sec": 0.2},
        sizes_bytes={"raw_lake": 1000, "joined": 500},
        date_entries=[{"date": "2024-01-05", "day_type": "normal"}],
    )
    text = json.dumps(report)
    assert "password" not in text.lower()
    assert "6000" not in text or "feature_quality" in text
    assert report["row_count"] == 2
    assert report["close_location_distribution"]["inside"] == 2


def test_leakage_validation_pass() -> None:
    result = validate_joined_dataset_leakage([_joined()])
    assert result.passed


def test_leakage_fails_on_official_close_in_features() -> None:
    bad = _joined()
    bad.row["official_close"] = 6001.0
    result = validate_joined_dataset_leakage([bad])
    assert not result.passed


def test_split_readiness_no_overlap() -> None:
    report = build_split_readiness_report(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    assert report["no_row_level_random_split"] is True
    assert "train" in report["session_grouped_split"]


def test_write_reports(tmp_path: Path) -> None:
    from quant_lab.ml.datasets.reporting import LeakageValidationResult

    write_reports(
        tmp_path,
        coverage={"row_count": 1},
        split_readiness={"folds": 1},
        leakage=LeakageValidationResult(passed=True),
    )
    assert (tmp_path / "coverage_report.json").is_file()
