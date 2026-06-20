"""Tests for ML-P7.8.3 baseline dataset validation reporting."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from quant_lab.ml.datasets.reporting import (
    BASELINE_LABEL_FIELDS,
    build_baseline_dataset_manifest,
    build_baseline_dataset_validation_report,
    build_baseline_session_split_readiness,
    compare_baseline_to_screening,
    evaluate_p783_gates,
    validate_label_dataset_leakage,
)
from quant_lab.ml.datasets.sample_builder import (
    SampleBuildOptions,
    build_dry_run_plan,
    load_sample_config,
)
from quant_lab.ml.schemas import BASELINE_LABEL_SCHEMA_VERSION, LABEL_SCHEMA_VERSION


def _label_row(
    *,
    trade_date: str = "2024-01-19",
    as_of: str = "2024-01-19T10:00:00-05:00",
    label_ts: str = "2024-01-19T16:00:00-05:00",
    eligible: bool = True,
    d_em: float = 0.1,
    near_025: bool = True,
    near_050: bool = True,
    p2_050: str = "near",
    zone: str | None = "inside",
) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "session_id": trade_date,
        "as_of_timestamp": as_of,
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "labels.label_source_timestamp": label_ts,
        "labels.baseline_target_eligible": eligible,
        "labels.baseline_target_exclusion_reasons": [] if eligible else ["remaining_em_invalid"],
        "labels.baseline_label_schema_version": BASELINE_LABEL_SCHEMA_VERSION,
        "labels.close_distance_to_primary_pin_points": d_em * 10.0,
        "labels.close_distance_to_primary_pin_em": d_em if eligible else None,
        "labels.close_near_primary_pin_025": near_025 if eligible else None,
        "labels.close_near_primary_pin_050": near_050 if eligible else None,
        "labels.close_above_below_primary_pin_025": "near" if eligible else None,
        "labels.close_above_below_primary_pin_050": p2_050 if eligible else None,
        "labels.close_location_vs_current_zone": zone,
        "labels.close_inside_current_zone": zone == "inside" if zone else None,
        "labels.first_zone_exit_direction": "up" if zone else None,
        "labels.valid_upside_exit_15m": True if zone else None,
        "labels.valid_upside_exit_30m": True if zone else None,
        "labels.valid_downside_exit_15m": False if zone else None,
        "labels.valid_downside_exit_30m": False if zone else None,
    }


def test_dataset_row_contains_v1_1_baseline_fields() -> None:
    row = _label_row()
    for field in BASELINE_LABEL_FIELDS:
        assert field in row


def test_dataset_row_preserves_zone_fields() -> None:
    row = _label_row(zone="inside")
    assert row["labels.close_location_vs_current_zone"] == "inside"
    assert row["labels.close_inside_current_zone"] is True


def test_baseline_coverage_aggregation() -> None:
    rows = [_label_row(), _label_row(eligible=False, zone=None)]
    report = build_baseline_dataset_validation_report(
        label_rows=rows,
        failed_dates=[],
        successful_dates=["2024-01-19"],
        skipped_dates=["2026-06-10"],
    )
    cov = report["coverage_summary"]
    assert cov["row_count"] == 2
    assert cov["baseline_eligible_rows"] == 1
    assert cov["zone_included_total"] == 1


def test_p1_025_and_050_aggregation() -> None:
    rows = [
        _label_row(near_025=True, near_050=True),
        _label_row(near_025=False, near_050=False, d_em=2.0, p2_050="above"),
    ]
    cov = build_baseline_dataset_validation_report(
        label_rows=rows,
        failed_dates=[],
        successful_dates=["2024-01-19"],
        skipped_dates=[],
    )["coverage_summary"]
    assert cov["p1_025"]["near_count"] == 1
    assert cov["p1_050"]["near_count"] == 1
    assert cov["p1_050"]["both_classes_present"] is True


def test_p2_aggregation() -> None:
    rows = [
        _label_row(p2_050="below", d_em=-1.0, near_050=False),
        _label_row(p2_050="near"),
        _label_row(p2_050="above", d_em=1.0, near_050=False),
    ]
    cov = build_baseline_dataset_validation_report(
        label_rows=rows,
        failed_dates=[],
        successful_dates=["2024-01-19"],
        skipped_dates=[],
    )["coverage_summary"]
    assert cov["p2_050"]["below_count"] == 1
    assert cov["p2_050"]["near_count"] == 1
    assert cov["p2_050"]["above_count"] == 1


def test_screening_consistency_tolerance_pass() -> None:
    rebuilt = {
        "baseline_eligible_rows": 1390,
        "p1_025": {"near_count": 152},
        "p1_050": {"near_count": 317},
        "zone_included_total": 89,
    }
    result = compare_baseline_to_screening(rebuilt)
    assert result["consistency_pass"] is True


def test_screening_consistency_tolerance_fail() -> None:
    rebuilt = {
        "baseline_eligible_rows": 1200,
        "p1_025": {"near_count": 100},
        "p1_050": {"near_count": 200},
        "zone_included_total": 50,
    }
    result = compare_baseline_to_screening(rebuilt)
    assert result["consistency_pass"] is False


def test_leakage_violation_detection() -> None:
    bad = _label_row(label_ts="2024-01-19T10:00:00-05:00")
    result = validate_label_dataset_leakage([bad])
    assert result.passed is False
    assert result.violations


def test_session_grouped_readiness() -> None:
    metrics = {
        "eligible_sessions": 19,
        "baseline_eligible_rows": 1390,
        "p1_050": {"both_classes_present": True},
    }
    split = build_baseline_session_split_readiness(metrics)
    assert split["can_create_session_grouped_split"] is True
    assert split["no_row_level_random_split"] is True


def test_manifest_contains_baseline_schema_version() -> None:
    provider = MagicMock()
    provider.outcome_source_hash.return_value = "test-hash"
    manifest = build_baseline_dataset_manifest(
        [_label_row()],
        outcome_provider=provider,
        anchor_config={"anchor_type": "regular_5min"},
        label_schema_version="1.1.0-draft",
        baseline_label_schema_version="1.1.0-draft",
    )
    assert manifest["label_schema_version"] == "1.1.0-draft"
    assert manifest["baseline_label_schema_version"] == "1.1.0-draft"
    assert manifest["dataset_only"] is True


def test_old_v1_row_compatibility_missing_baseline_fields() -> None:
    legacy = {
        "trade_date": "2024-01-19",
        "as_of_timestamp": "2024-01-19T10:00:00-05:00",
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "labels.close_location_vs_current_zone": "inside",
    }
    cov = build_baseline_dataset_validation_report(
        label_rows=[legacy],
        failed_dates=[],
        successful_dates=["2024-01-19"],
        skipped_dates=[],
    )["coverage_summary"]
    assert cov["baseline_eligible_rows"] == 0
    assert cov["zone_included_total"] == 1


def test_p783_gates_pass_on_reference_metrics() -> None:
    report = build_baseline_dataset_validation_report(
        label_rows=[_label_row(trade_date=f"2024-01-{d:02d}") for d in range(5, 24)],
        failed_dates=[],
        successful_dates=[f"2024-01-{d:02d}" for d in range(5, 24)],
        skipped_dates=["2026-06-10"],
    )
    # Override coverage to screening-like values
    report["coverage_summary"]["baseline_eligible_rows"] = 1390
    report["coverage_summary"]["eligible_sessions"] = 19
    report["coverage_summary"]["p1_025"] = {
        "near_count": 152,
        "not_near_count": 1238,
        "both_classes_present": True,
    }
    report["coverage_summary"]["p1_050"] = {
        "near_count": 317,
        "not_near_count": 1073,
        "both_classes_present": True,
    }
    report["coverage_summary"]["zone_included_total"] = 89
    report["screening_consistency"] = compare_baseline_to_screening(report["coverage_summary"])
    report["session_split_readiness"] = build_baseline_session_split_readiness(
        report["coverage_summary"]
    )
    gates = evaluate_p783_gates(report)
    assert gates["p783_pass"] is True


def test_dry_run_respects_dataset_only_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        """
version: test
lake_root: artifacts/raw_lake_sample
dataset_root: artifacts/datasets/test
feature_root: artifacts/features/test
report_root: artifacts/reports/test
joined_root: artifacts/datasets/test/joined
ingest:
  enabled: false
build:
  dataset_only: true
dates:
  - date: "2024-01-19"
    day_type: normal
""",
        encoding="utf-8",
    )
    with patch(
        "quant_lab.ml.datasets.sample_builder.missing_partitions_for_date",
        return_value=[],
    ):
        config = load_sample_config(cfg_path)
        plan = build_dry_run_plan(config, dates_filter=(date(2024, 1, 19),))
    assert config.dataset_only is True
    assert plan.total_anchors > 0


def test_sample_build_options_dataset_only_flag() -> None:
    opts = SampleBuildOptions(dataset_only=True)
    assert opts.dataset_only is True
