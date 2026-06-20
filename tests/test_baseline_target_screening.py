"""Tests for ML-P7.8 baseline target coverage screening."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quant_lab.data.base import MARKET_TZ
from quant_lab.ml.datasets.baseline_target_screening import (
    P78_MIN_ELIGIBLE_ROWS,
    AnchorBaselineResult,
    BaselineScreeningOptions,
    DateBaselineMetrics,
    aggregate_date_baseline_metrics,
    aggregate_p0_distribution,
    aggregate_p1_stats,
    aggregate_p2_stats,
    build_baseline_summary,
    check_baseline_leakage,
    compute_close_distance_to_primary_pin_em,
    compute_p1_near,
    compute_p2_directional,
    evaluate_p0_eligibility,
    evaluate_p78_gates,
    evaluate_session_split_readiness,
    metrics_from_dict,
    screen_baseline_targets,
    write_per_date_report,
)
from quant_lab.ml.datasets.sample_builder import DateEntry, SampleBuildConfig
from quant_lab.ml.datasets.valid_zone_screening import LakeDateInventory


def _minimal_config(tmp_path: Path) -> SampleBuildConfig:
    return SampleBuildConfig(
        version="test",
        root="SPXW",
        index_symbol="SPX",
        strike_range=60,
        strike_range_fallback=30,
        anchor_type="regular_5min",
        anchor_start_offset_minutes=5,
        anchor_end_offset_minutes=5,
        session_rth_start="09:30:00",
        session_rth_end="16:00:00",
        lake_root=tmp_path / "lake",
        dataset_root=tmp_path / "dataset",
        feature_root=tmp_path / "features",
        report_root=tmp_path / "reports",
        joined_root=tmp_path / "joined",
        ingest_enabled=False,
        ingest_full_rth=True,
        ingest_max_retries=2,
        ingest_request_budget_per_date=8,
        ingest_write_raw_lake=True,
        ingest_idempotent_skip_existing=True,
        quote_resolution="tick_or_1s",
        index_resolution="tick_or_1s",
        stage_a_dates=(),
        seed_from_pilot_lake=None,
        dates=(),
    )


def test_p0_distance_formula() -> None:
    d = compute_close_distance_to_primary_pin_em(5010.0, 5000.0, 20.0)
    assert d == pytest.approx(0.5)


def test_p0_eligibility_success() -> None:
    as_of = datetime(2024, 1, 19, 10, 0, tzinfo=MARKET_TZ)
    label_ts = datetime(2024, 1, 19, 16, 0, tzinfo=MARKET_TZ)
    ok, reasons = evaluate_p0_eligibility(
        primary_pin_t=5000.0,
        remaining_expected_move_t=25.0,
        official_close=5010.0,
        label_source_timestamp=label_ts,
        as_of_timestamp=as_of,
    )
    assert ok is True
    assert reasons == []


def test_remaining_em_non_positive_exclusion() -> None:
    as_of = datetime(2024, 1, 19, 10, 0, tzinfo=MARKET_TZ)
    label_ts = datetime(2024, 1, 19, 16, 0, tzinfo=MARKET_TZ)
    ok, reasons = evaluate_p0_eligibility(
        primary_pin_t=5000.0,
        remaining_expected_move_t=0.0,
        official_close=5010.0,
        label_source_timestamp=label_ts,
        as_of_timestamp=as_of,
    )
    assert ok is False
    assert "remaining_em_non_positive" in reasons


def test_missing_primary_pin_exclusion() -> None:
    as_of = datetime(2024, 1, 19, 10, 0, tzinfo=MARKET_TZ)
    label_ts = datetime(2024, 1, 19, 16, 0, tzinfo=MARKET_TZ)
    ok, reasons = evaluate_p0_eligibility(
        primary_pin_t=None,
        remaining_expected_move_t=25.0,
        official_close=5010.0,
        label_source_timestamp=label_ts,
        as_of_timestamp=as_of,
    )
    assert ok is False
    assert "primary_pin_missing_at_as_of" in reasons


def test_label_timestamp_not_after_as_of_exclusion() -> None:
    ts = datetime(2024, 1, 19, 10, 0, tzinfo=MARKET_TZ)
    ok, reasons = evaluate_p0_eligibility(
        primary_pin_t=5000.0,
        remaining_expected_move_t=25.0,
        official_close=5010.0,
        label_source_timestamp=ts,
        as_of_timestamp=ts,
    )
    assert ok is False
    assert "label_timestamp_not_after_as_of" in reasons


def test_p1_threshold_025_and_050() -> None:
    assert compute_p1_near(0.1, 0.25) is True
    assert compute_p1_near(0.1, 0.50) is True
    assert compute_p1_near(0.4, 0.25) is False
    assert compute_p1_near(0.4, 0.50) is True


def test_p2_directional_classification() -> None:
    assert compute_p2_directional(-0.5, 0.25) == "below"
    assert compute_p2_directional(0.1, 0.25) == "near"
    assert compute_p2_directional(0.5, 0.25) == "above"


def test_p0_distribution_aggregation() -> None:
    stats = aggregate_p0_distribution([-1.0, 0.0, 1.0, 2.0])
    assert stats["count"] == 4
    assert stats["positive_count"] == 2
    assert stats["negative_count"] == 1
    assert stats["near_zero_count"] == 1


def test_p1_class_balance_aggregation() -> None:
    stats = aggregate_p1_stats([True, False, False], threshold_em=0.25, eligible_count=3)
    assert stats["near_count"] == 1
    assert stats["not_near_count"] == 2
    assert stats["both_classes_present"] is True


def test_p2_class_distribution() -> None:
    stats = aggregate_p2_stats(["below", "near", "above"], threshold_em=0.25)
    assert stats["class_count_nonzero"] == 3
    assert stats["below_count"] == 1


def test_leakage_violation_detection() -> None:
    as_of = datetime(2024, 1, 19, 12, 0, tzinfo=MARKET_TZ)
    ok, violations = check_baseline_leakage(as_of, as_of)
    assert ok is False
    assert violations


def test_leakage_pass() -> None:
    as_of = datetime(2024, 1, 19, 10, 0, tzinfo=MARKET_TZ)
    label_ts = datetime(2024, 1, 19, 16, 0, tzinfo=MARKET_TZ)
    ok, violations = check_baseline_leakage(as_of, label_ts)
    assert ok is True
    assert violations == []


def test_session_grouped_readiness() -> None:
    metrics = [
        DateBaselineMetrics(
            trade_date=date(2024, 1, 19),
            day_type="normal",
            anchor_count=77,
            eligible_count=50,
            eligible_ratio=0.65,
            zone_included_count=48,
            p0={"count": 50},
            p1={"0.25": {"near_count": 10, "not_near_count": 40}},
            p2={"0.25": {"below_count": 5, "near_count": 10, "above_count": 35}},
            null_reason_distribution={},
            leakage_pass=True,
            leakage_violation_count=0,
            leakage_violation_examples=[],
            runtime_seconds=1.0,
        )
    ]
    readiness = evaluate_session_split_readiness(metrics)
    assert readiness["both_classes_present"] is True
    assert readiness["eligible_sessions"] == 1


def test_p78_gates_fail_small_sample() -> None:
    summary = {
        "eligible_rows_total": 50,
        "leakage_validation": {"leakage_pass": True},
        "session_split_readiness": {
            "eligible_sessions": 2,
            "both_classes_present": True,
            "can_create_session_grouped_split": False,
        },
    }
    gates = evaluate_p78_gates(summary)
    assert gates["p78_pass"] is False
    assert gates["ml_p8b_blocked"] is True


def test_p78_gates_pass_mock() -> None:
    summary = {
        "eligible_rows_total": P78_MIN_ELIGIBLE_ROWS,
        "leakage_validation": {"leakage_pass": True},
        "session_split_readiness": {
            "eligible_sessions": 10,
            "both_classes_present": True,
            "can_create_session_grouped_split": True,
        },
    }
    gates = evaluate_p78_gates(summary)
    assert gates["p78_pass"] is True


def test_aggregate_date_baseline_metrics() -> None:
    anchors = [
        AnchorBaselineResult(
            eligible=True,
            null_reasons=(),
            d_em=0.1,
            p1_near={"0.25": True, "0.50": True},
            p2_class={"0.25": "near", "0.50": "near"},
            zone_included=True,
            zone_close_location="inside",
            leakage_ok=True,
            leakage_violations=(),
        ),
        AnchorBaselineResult(
            eligible=True,
            null_reasons=(),
            d_em=1.0,
            p1_near={"0.25": False, "0.50": False},
            p2_class={"0.25": "above", "0.50": "above"},
            zone_included=False,
            zone_close_location=None,
            leakage_ok=True,
            leakage_violations=(),
        ),
        AnchorBaselineResult(
            eligible=False,
            null_reasons=("remaining_em_non_positive",),
            d_em=None,
            p1_near={"0.25": None, "0.50": None},
            p2_class={"0.25": None, "0.50": None},
            zone_included=False,
            zone_close_location=None,
            leakage_ok=True,
            leakage_violations=(),
        ),
    ]
    m = aggregate_date_baseline_metrics(
        DateEntry(trade_date=date(2024, 1, 19), day_type="normal"),
        anchors,
        runtime_seconds=2.0,
    )
    assert m.eligible_count == 2
    assert m.p1["0.25"]["both_classes_present"] is True
    assert m.zone_included_count == 1


def test_resume_skip_completed_date(tmp_path: Path) -> None:
    report_root = tmp_path / "baseline_reports"
    m = DateBaselineMetrics(
        trade_date=date(2024, 1, 19),
        day_type="normal",
        anchor_count=77,
        eligible_count=70,
        eligible_ratio=0.9,
        zone_included_count=48,
        p0={"count": 70, "mean": 0.1},
        p1={"0.25": {"near_count": 10, "not_near_count": 60}},
        p2={},
        null_reason_distribution={},
        leakage_pass=True,
        leakage_violation_count=0,
        leakage_violation_examples=[],
        runtime_seconds=1.0,
    )
    write_per_date_report(report_root, m)
    payload = json.loads((report_root / "per_date/2024-01-19.json").read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    restored = metrics_from_dict(payload)
    assert restored.eligible_count == 70


@patch("quant_lab.ml.features.builder.build_feature_dataset")
@patch("quant_lab.ml.datasets.baseline_target_screening.screen_baseline_anchor_at")
@patch("quant_lab.ml.datasets.baseline_target_screening.generate_anchors")
@patch("quant_lab.ml.datasets.baseline_target_screening.PilotIndexOutcomeProvider")
def test_no_feature_builder_called(
    mock_provider: MagicMock,
    mock_generate: MagicMock,
    mock_screen: MagicMock,
    mock_feature: MagicMock,
    tmp_path: Path,
) -> None:
    cfg = _minimal_config(tmp_path)
    with patch(
        "quant_lab.ml.datasets.baseline_target_screening.inventory_raw_lake",
        return_value=LakeDateInventory(
            complete_dates=("2024-01-19",),
            incomplete_dates=(),
            skipped_dates=(),
        ),
    ), patch(
        "quant_lab.ml.datasets.baseline_target_screening.load_completed_checkpoint_dates",
        return_value=set(),
    ):
        mock_generate.return_value = [
            (datetime(2024, 1, 19, 10, 0, tzinfo=MARKET_TZ), "regular_5min")
        ]
        mock_screen.return_value = AnchorBaselineResult(
            eligible=True,
            null_reasons=(),
            d_em=0.2,
            p1_near={"0.25": True, "0.50": True},
            p2_class={"0.25": "near", "0.50": "near"},
            zone_included=True,
            zone_close_location="above",
            leakage_ok=True,
            leakage_violations=(),
        )
        screen_baseline_targets(
            cfg,
            {"2024-01-19": "monthly_opex"},
            options=BaselineScreeningOptions(
                resume=False,
                progress_every=0,
                report_root=tmp_path / "out",
            ),
        )
    mock_feature.assert_not_called()


def test_no_model_training_imports() -> None:
    import quant_lab.ml.datasets.baseline_target_screening as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("torch", "lightgbm", "xgboost", "sklearn", ".fit("):
        assert forbidden not in src


def test_build_summary_zone_comparison() -> None:
    m = DateBaselineMetrics(
        trade_date=date(2024, 1, 19),
        day_type="normal",
        anchor_count=77,
        eligible_count=77,
        eligible_ratio=1.0,
        zone_included_count=48,
        p0={"count": 77, "mean": 0.0, "positive_count": 40, "negative_count": 37},
        p1={"0.25": {"near_count": 20, "not_near_count": 57}},
        p2={"0.25": {"below_count": 10, "near_count": 20, "above_count": 47}},
        null_reason_distribution={},
        leakage_pass=True,
        leakage_violation_count=0,
        leakage_violation_examples=[],
        runtime_seconds=1.0,
    )
    summary = build_baseline_summary(
        screened_dates=["2024-01-19"],
        skipped_dates=["2026-06-10"],
        metrics=[m],
        zone_baseline={"zone_included_total_reference": 89},
    )
    assert summary["eligible_rows_total"] == 77
    assert summary["zone_comparison"]["zone_included_total_reference"] == 89


def test_no_official_label_spec_mutation() -> None:
    spec = Path("docs/ml/label_spec.md").read_text(encoding="utf-8")
    assert "label_schema_version" in spec
    assert "1.0.0" in spec
