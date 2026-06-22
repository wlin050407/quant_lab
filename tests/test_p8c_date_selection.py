"""Tests for ML-P8C.1 candidate date selection."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from quant_lab.ml.datasets.p8c_date_selection import (
    HARNESS_STAGE_P8C1,
    AvailabilityRecord,
    CandidateRecord,
    assign_primary_bucket,
    estimate_build_cost,
    load_existing_sessions,
    load_p8c_selection_config,
    run_p8c1_selection,
    select_stage1_dates,
    validate_selection_rules_flags,
)


def _write_sample_config(tmp_path: Path, dates: list[str]) -> Path:
    cfg = {
        "version": "test",
        "dates": [{"date": d, "day_type": "normal"} for d in dates],
    }
    path = tmp_path / "sample.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def test_load_existing_sessions(tmp_path: Path) -> None:
    p = _write_sample_config(tmp_path, ["2024-01-05", "2024-01-19"])
    sessions = load_existing_sessions([p], tmp_path)
    assert sessions == ["2024-01-05", "2024-01-19"]


def test_validate_selection_rules_flags_rejects_disabled() -> None:
    errors = validate_selection_rules_flags({"no_model_performance_selection": False})
    assert errors


def test_validate_selection_rules_flags_passes() -> None:
    rules = {
        "no_model_performance_selection": True,
        "no_target_based_selection": True,
        "no_pnl_selection": True,
        "no_manual_cherry_pick": True,
        "deterministic_with_seed": True,
    }
    assert not validate_selection_rules_flags(rules)


def test_assign_primary_bucket_priority() -> None:
    assert assign_primary_bucket(["normal_range", "high_vol"]) == "high_vol"
    assert assign_primary_bucket(["early_close", "monthly_opex"]) == "early_close"


def test_select_stage1_dates_deterministic_with_seed() -> None:
    candidates = [
        CandidateRecord(
            trade_date=f"2023-01-{10 + i:02d}",
            year=2023,
            quarter=1,
            primary_bucket="normal_range",
            secondary_buckets=[],
            bucket_reason="test",
            selection_source="test",
            selection_seed=20260621,
            index_stats_available=False,
        )
        for i in range(12)
    ]
    quotas = {"normal_range": 5}
    a, _ = select_stage1_dates(candidates, quotas, seed=20260621)
    b, _ = select_stage1_dates(candidates, quotas, seed=20260621)
    assert [x.trade_date for x in a] == [x.trade_date for x in b]
    assert len(a) == 5


def test_select_stage1_dates_target_count_with_spill() -> None:
    candidates: list[CandidateRecord] = []
    for i in range(30):
        bucket = "high_vol" if i < 3 else "normal_range"
        candidates.append(
            CandidateRecord(
                trade_date=f"2023-02-{i + 1:02d}",
                year=2023,
                quarter=1,
                primary_bucket=bucket,
                secondary_buckets=[],
                bucket_reason="test",
                selection_source="test",
                selection_seed=1,
                index_stats_available=False,
            )
        )
    quotas = {"high_vol": 5, "normal_range": 3}
    selected, summaries = select_stage1_dates(candidates, quotas, seed=99)
    assert len(selected) == 8
    high_summary = next(s for s in summaries if s.bucket == "high_vol")
    assert high_summary.underfilled_reason is not None


def test_estimate_build_cost() -> None:
    availability = [
        AvailabilityRecord(
            date="2023-01-05",
            raw_lake_status="missing",
            dataset_status="missing",
            feature_status="missing",
            missing_partitions=[],
            estimated_ingest_needed=True,
            estimated_build_needed=True,
        )
    ]
    cost = estimate_build_cost(
        availability,
        {
            "ingest_minutes_per_date_low": 10.0,
            "ingest_minutes_per_date_base": 20.0,
            "ingest_minutes_per_date_high": 30.0,
            "dataset_build_minutes_per_date_low": 5.0,
            "dataset_build_minutes_per_date_base": 10.0,
            "dataset_build_minutes_per_date_high": 15.0,
            "feature_build_minutes_per_date_low": 5.0,
            "feature_build_minutes_per_date_base": 10.0,
            "feature_build_minutes_per_date_high": 15.0,
            "storage_gb_per_date_low": 1.0,
            "storage_gb_per_date_base": 2.0,
            "storage_gb_per_date_high": 3.0,
        },
    )
    assert cost["estimated_new_raw_lake_days"] == 1
    assert "estimated_runtime_minutes" in cost


def test_run_p8c1_dry_run(tmp_path: Path) -> None:
    baseline = _write_sample_config(
        tmp_path,
        [f"2024-01-{d:02d}" for d in range(1, 20)],
    )
    cfg_path = tmp_path / "p8c.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "stage": HARNESS_STAGE_P8C1,
                "selection_seed": 20260621,
                "current_sample_config": {
                    "existing_sample_configs": [str(baseline)],
                    "baseline_config_primary": str(baseline),
                    "current_session_count": 19,
                },
                "stage1_target": {"target_total_sessions": 40, "new_sessions_required": 21},
                "bucket_quotas": {
                    "normal_range": 8,
                    "high_vol": 5,
                    "trend": 4,
                    "monthly_opex": 2,
                    "early_close": 1,
                    "recent": 1,
                },
                "selection_rules": {
                    "no_model_performance_selection": True,
                    "no_target_based_selection": True,
                    "no_pnl_selection": True,
                    "no_manual_cherry_pick": True,
                    "deterministic_with_seed": True,
                },
                "candidate_pool": {
                    "start_date": "2023-01-01",
                    "end_date": "2023-06-30",
                    "candidate_years": [2023],
                },
                "paths": {
                    "lake_root": str(tmp_path / "lake"),
                    "dataset_root": str(tmp_path / "dataset"),
                    "feature_root": str(tmp_path / "features"),
                },
                "output_reports": {"output_dir": str(tmp_path / "out")},
            }
        ),
        encoding="utf-8",
    )
    config = load_p8c_selection_config(cfg_path)
    result = run_p8c1_selection(config, project_root=tmp_path, execute=False)
    assert result.p8c1_pass
    assert result.candidate_pool_size > 0


def test_run_p8c1_execute_writes_manifest_flags(tmp_path: Path) -> None:
    baseline = _write_sample_config(tmp_path, ["2024-01-05"])
    cfg_path = tmp_path / "p8c.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "stage": HARNESS_STAGE_P8C1,
                "selection_seed": 42,
                "current_sample_config": {
                    "existing_sample_configs": [str(baseline)],
                    "baseline_config_primary": str(baseline),
                    "current_session_count": 1,
                },
                "stage1_target": {"target_total_sessions": 10, "new_sessions_required": 3},
                "bucket_quotas": {"normal_range": 2, "high_vol": 1},
                "selection_rules": {
                    "no_model_performance_selection": True,
                    "no_target_based_selection": True,
                    "no_pnl_selection": True,
                    "no_manual_cherry_pick": True,
                    "deterministic_with_seed": True,
                },
                "candidate_pool": {
                    "start_date": "2023-01-01",
                    "end_date": "2023-03-31",
                    "candidate_years": [2023],
                },
                "temporal_constraints": {},
                "paths": {
                    "lake_root": str(tmp_path / "lake"),
                    "dataset_root": str(tmp_path / "dataset"),
                    "feature_root": str(tmp_path / "features"),
                },
                "output_reports": {"output_dir": str(tmp_path / "out")},
            }
        ),
        encoding="utf-8",
    )
    config = load_p8c_selection_config(cfg_path)
    result = run_p8c1_selection(config, project_root=tmp_path, execute=True)
    assert result.manifest_path is not None
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["model_performance_used"] is False
    assert manifest["target_based_selection_used"] is False
    assert manifest["actual_ingest_performed"] is False
    assert manifest["model_fitting_performed"] is False
    assert manifest["p8b4_authorized"] is False


def test_forbidden_model_performance_flag_rejected() -> None:
    errors = validate_selection_rules_flags({"no_model_performance_selection": False})
    assert errors
    assert any("no_model_performance" in e for e in errors)
