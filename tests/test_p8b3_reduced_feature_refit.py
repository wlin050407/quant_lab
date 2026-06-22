"""Tests for ML-P8B.3.7 reduced-feature train-only learned refit."""

# ruff: noqa: N803, N806

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from quant_lab.ml.harness.p8b3_7_refit import (
    FEATURE_SET_A,
    FEATURE_SET_B,
    FEATURE_SET_C,
    HARNESS_STAGE_P8B3_7,
    P8B37Config,
    P8B37FitResult,
    build_p8b37_dry_run_plan,
    parse_feature_set_ids,
    resolve_feature_set,
    run_p8b37_refit,
    validate_reduced_manifest,
    validate_selected_features,
)
from quant_lab.ml.harness.p8b3_fit import FIXED_HYPERPARAMETERS, TrainOnlyPreprocessor
from quant_lab.ml.harness.p8b3_plan import P8B31Config
from quant_lab.ml.harness.validators import validate_forbidden_features


def _mini_manifest(*, target_based: bool = False, model_fitting: bool = False) -> dict[str, object]:
    return {
        "feature_set_version": "p8b3_reduced_features_v0_proposal",
        "target_based_selection_used": target_based,
        "model_fitting_performed": model_fitting,
        "candidate_sets": [
            {
                "feature_set_name": FEATURE_SET_A,
                "feature_set_version": "p8b3_reduced_features_v0_proposal",
                "target_based_selection_used": False,
                "selected_features": ["spot_t", "pin_score_t", "net_gex"],
            },
            {
                "feature_set_name": FEATURE_SET_B,
                "feature_set_version": "p8b3_reduced_features_v0_proposal",
                "target_based_selection_used": False,
                "selected_features": ["spot_t", "pin_score_t", "net_gex", "call_gex"],
            },
            {
                "feature_set_name": FEATURE_SET_C,
                "feature_set_version": "p8b3_reduced_features_v0_proposal",
                "target_based_selection_used": False,
                "selected_features": ["spot_t"],
            },
        ],
    }


def test_parse_feature_set_ids_accepts_a_b() -> None:
    assert parse_feature_set_ids("A,B") == ["A", "B"]
    assert parse_feature_set_ids("A|B") == ["A", "B"]


def test_parse_feature_set_ids_rejects_c() -> None:
    with pytest.raises(ValueError, match="FeatureSet_C"):
        parse_feature_set_ids("C")


def test_validate_reduced_manifest_passes_valid() -> None:
    val = validate_reduced_manifest(
        _mini_manifest(), expected_version="p8b3_reduced_features_v0_proposal"
    )
    assert val.passed
    assert val.target_based_selection_used is False
    assert val.model_fitting_performed is False


def test_validate_reduced_manifest_rejects_target_based() -> None:
    val = validate_reduced_manifest(
        _mini_manifest(target_based=True),
        expected_version="p8b3_reduced_features_v0_proposal",
    )
    assert not val.passed
    assert any("target_based" in e for e in val.errors)


def test_validate_reduced_manifest_rejects_model_fitting_performed() -> None:
    val = validate_reduced_manifest(
        _mini_manifest(model_fitting=True),
        expected_version="p8b3_reduced_features_v0_proposal",
    )
    assert not val.passed
    assert any("model_fitting_performed" in e for e in val.errors)


def test_resolve_feature_set_a_b_from_manifest() -> None:
    manifest = _mini_manifest()
    name_a, feats_a = resolve_feature_set(manifest, "A")
    assert name_a == FEATURE_SET_A
    assert "spot_t" in feats_a
    name_b, _ = resolve_feature_set(manifest, "B")
    assert name_b == FEATURE_SET_B


def test_resolve_feature_set_rejects_c() -> None:
    with pytest.raises(ValueError, match="FeatureSet_C"):
        resolve_feature_set(_mini_manifest(), "C")


def test_validate_selected_features_missing() -> None:
    missing = validate_selected_features(["spot_t", "missing_col"], ["spot_t", "pin_score_t"])
    assert missing == ["missing_col"]


def test_forbidden_columns_fail_before_fitting() -> None:
    forb = validate_forbidden_features(["spot_t", "labels.close_distance_to_primary_pin_em"])
    assert not forb.passed


def test_fixed_hyperparameters_no_search() -> None:
    for hp in FIXED_HYPERPARAMETERS.values():
        assert "grid" not in str(hp).lower()
        assert "search" not in str(hp).lower()
    assert FIXED_HYPERPARAMETERS["p0_ridge_regression"]["alpha"] == 1.0
    assert FIXED_HYPERPARAMETERS["p1_logistic_050"]["class_weight"] is None


def _p8b37_config(tmp_path: Path) -> P8B37Config:
    base = P8B31Config(
        version="test",
        dataset_root=tmp_path / "dataset",
        feature_root=tmp_path / "features",
        input_reports=tmp_path / "reports",
        output_reports=tmp_path / "out",
        p8b2_reports=tmp_path / "p8b2",
        baseline_label_schema_version="1.1.0-draft",
        split_protocol="session_grouped",
        train_sessions_count=11,
        validation_sessions_count=3,
        test_sessions_count=5,
        preferred_binary_target="close_near_primary_pin_050",
        sensitivity_binary_target="close_near_primary_pin_025",
        model_fitting_allowed=False,
        include_p2_specs=True,
        preprocessing="standard_scaler",
        configured_train_sessions=["2024-01-05"],
        configured_validation_sessions=["2024-11-01"],
        configured_test_sessions=["2025-01-03"],
    )
    manifest_path = tmp_path / "reduced_manifest.json"
    manifest_path.write_text(json.dumps(_mini_manifest()), encoding="utf-8")
    return P8B37Config(
        base=base,
        reduced_feature_manifest=manifest_path,
        p8b3_2_reports=tmp_path / "p8b3_2",
        expected_feature_set_version="p8b3_reduced_features_v0_proposal",
    )


def test_dry_run_rejects_missing_manifest(tmp_path: Path) -> None:
    config = _p8b37_config(tmp_path)
    config.reduced_feature_manifest = tmp_path / "missing.json"
    result = build_p8b37_dry_run_plan(
        config,
        project_root=tmp_path,
        feature_set_ids=["A"],
        targets={"p0", "p1_050"},
    )
    assert not result.p8b3_7_pass
    assert not result.reduced_manifest_validation.get("passed")


@patch("quant_lab.ml.harness.p8b3_7_refit.validate_sklearn_dependency_declared")
@patch("quant_lab.ml.harness.p8b3_7_refit.load_joined_rows")
@patch("quant_lab.ml.harness.p8b3_7_refit.validate_feature_target_matrix")
def test_dry_run_loads_feature_set_a_from_manifest(
    mock_matrix: MagicMock,
    mock_joined: MagicMock,
    mock_dep: MagicMock,
    tmp_path: Path,
) -> None:
    mock_dep.return_value = MagicMock(passed=True, dependency_status="declared_and_importable")
    mock_joined.return_value = [
        {
            "trade_date": "2024-01-05",
            "labels.baseline_target_eligible": True,
            "features.spot_t": 1.0,
            "features.pin_score_t": 0.5,
            "features.net_gex": 0.1,
            "features.call_gex": 0.2,
        }
    ]
    mock_matrix.return_value = MagicMock(
        passed=True,
        forbidden_input_pass=True,
        forbidden_columns=[],
        split_validation_pass=True,
        row_level_random_split_pass=True,
        split_errors=[],
    )
    config = _p8b37_config(tmp_path)
    result = build_p8b37_dry_run_plan(
        config,
        project_root=tmp_path,
        feature_set_ids=["A"],
        targets={"p0"},
    )
    assert result.reduced_manifest_validation.get("passed")
    assert FEATURE_SET_A in result.feature_sets_used


@patch("quant_lab.ml.harness.p8b3_7_refit.fit_model_train_only")
@patch("quant_lab.ml.harness.p8b3_7_refit.validate_sklearn_dependency_declared")
@patch("quant_lab.ml.harness.p8b3_7_refit.load_joined_rows")
@patch("quant_lab.ml.harness.p8b3_7_refit.validate_feature_target_matrix")
@patch("quant_lab.ml.harness.p8b3_7_refit.filter_baseline_eligible")
@patch("quant_lab.ml.harness.p8b3_7_refit.assign_split")
def test_execute_fit_called_with_comparison_payloads(
    mock_assign: MagicMock,
    mock_filter: MagicMock,
    mock_matrix: MagicMock,
    mock_joined: MagicMock,
    mock_dep: MagicMock,
    mock_fit: MagicMock,
    tmp_path: Path,
) -> None:
    from quant_lab.ml.harness.p8b3_fit import ModelFitResult

    mock_dep.return_value = MagicMock(passed=True, dependency_status="declared_and_importable")
    rows = [
        {
            "trade_date": "2024-01-05",
            "split": "train",
            "labels.baseline_target_eligible": True,
            "features.spot_t": 1.0,
            "features.pin_score_t": 0.5,
            "features.net_gex": 0.1,
            "labels.close_distance_to_primary_pin_em": 0.2,
            "labels.close_near_primary_pin_050": True,
        }
    ]
    mock_joined.return_value = rows
    mock_filter.return_value = rows
    mock_assign.return_value = rows
    mock_matrix.return_value = MagicMock(
        passed=True,
        forbidden_input_pass=True,
        forbidden_columns=[],
        split_validation_pass=True,
        row_level_random_split_pass=True,
        split_errors=[],
    )
    mock_fit.return_value = ModelFitResult(
        spec_name="p0_ridge_regression",
        track="P0",
        target_key="labels.close_distance_to_primary_pin_em",
        metrics={"test": {"mae": 1.0}},
        comparison_vs_p8b2={"zero_em": {"delta_learned_minus_baseline": -0.5}},
        comparison_vs_p8b3_2={"p0_ridge_regression": {"delta_reduced_minus_full_feature": -1.0}},
    )
    p8b2_dir = tmp_path / "p8b2"
    p8b2_dir.mkdir()
    (p8b2_dir / "p8b2_evaluation_report.json").write_text(
        json.dumps({"metrics": {"p0_close_distance_to_primary_pin_em": {"test": {"zero_em": {"mae": 2.0}}}}}),
        encoding="utf-8",
    )
    p8b3_dir = tmp_path / "p8b3_2"
    p8b3_dir.mkdir()
    (p8b3_dir / "p8b3_2_evaluation_report.json").write_text(
        json.dumps(
            {
                "model_results": [
                    {
                        "spec_name": "p0_ridge_regression",
                        "metrics": {"test": {"mae": 3.0}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    config = _p8b37_config(tmp_path)
    config.base.p8b2_reports = p8b2_dir
    config.p8b3_2_reports = p8b3_dir
    result = run_p8b37_refit(
        config,
        project_root=tmp_path,
        feature_set_ids=["A"],
        targets={"p0"},
        execute=True,
    )
    assert mock_fit.called
    assert result.model_fitting_performed
    assert result.hyperparameter_search_performed is False
    assert result.p8b4_blocked is True
    assert result.run_manifest_path is not None
    manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage"] == HARNESS_STAGE_P8B3_7
    assert manifest["feature_set_version"] == "p8b3_reduced_features_v0_proposal"
    assert manifest["test_not_used_for_tuning"] is True
    fs_result = result.feature_set_results[0]
    model = fs_result["model_results"][0]
    assert "comparison_vs_p8b2" in model
    assert "comparison_vs_p8b3_2" in model


def test_run_manifest_records_reduced_feature_set_version() -> None:
    val = validate_reduced_manifest(
        _mini_manifest(), expected_version="p8b3_reduced_features_v0_proposal"
    )
    assert val.feature_set_version == "p8b3_reduced_features_v0_proposal"


def test_p8b4_blocked_in_result_metadata() -> None:
    result = P8B37FitResult()
    assert result.p8b4_blocked is True
    assert result.hyperparameter_search_performed is False


def test_preprocessing_fit_on_train_only() -> None:
    X_train = np.array([[1.0, 2.0], [3.0, 4.0]])
    prep = TrainOnlyPreprocessor.fit_on_train(X_train, use_scaler=True)
    assert prep.fit_n_samples == 2
    assert prep.to_dict()["preprocessing_fit_on_train_only"] is True
