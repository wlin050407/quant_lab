"""Tests for ML-P8B.3.1 simple learned baseline harness (no .fit())."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quant_lab.ml.harness.learned_models import (
    P0LinearRegressionSpec,
    P0RidgeRegressionSpec,
    P1LogisticRegressionSpec,
    P2MultinomialLogisticRegressionSpec,
    all_allowed_model_specs,
    default_p0_specs,
    default_p1_specs,
    default_p2_specs,
)
from quant_lab.ml.harness.p8b2_eval import LABEL_P0, LABEL_P1_050
from quant_lab.ml.harness.p8b3_plan import (
    FIT_EXECUTION_BLOCKED_MSG,
    HARNESS_STAGE_P8B3_1,
    NoScalerPlan,
    NumericFeatureSelectionPlan,
    P8B31Config,
    StandardScalerPlan,
    build_p8b31_fit_plan,
    build_preprocessing_plan_from_columns,
    check_sklearn_available,
    reject_fit_execution,
    validate_feature_target_matrix,
    validate_sklearn_dependency_declared,
    write_fit_plan_json,
)


def _synthetic_row(
    trade_date: str,
    *,
    d_em: float = 0.1,
    near: bool = False,
) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "features.spot_t": 5000.0,
        "features.pin_score_t": 0.5,
        LABEL_P0: d_em,
        LABEL_P1_050: near,
        "labels.baseline_target_eligible": True,
    }


def _synthetic_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sid in ("2024-01-05", "2024-01-19", "2024-02-13", "2024-11-01", "2025-01-03"):
        for j in range(3):
            rows.append(_synthetic_row(sid, d_em=float(j) * 0.1, near=j % 2 == 0))
    return rows


def _test_config(tmp_path: Path) -> P8B31Config:
    return P8B31Config(
        version="test",
        dataset_root=tmp_path / "ds",
        feature_root=tmp_path / "feat",
        input_reports=tmp_path / "in",
        output_reports=tmp_path / "out",
        p8b2_reports=tmp_path / "p8b2",
        baseline_label_schema_version="1.1.0-draft",
        split_protocol="session_grouped",
        train_sessions_count=3,
        validation_sessions_count=1,
        test_sessions_count=1,
        preferred_binary_target="close_near_primary_pin_050",
        sensitivity_binary_target="close_near_primary_pin_025",
        model_fitting_allowed=False,
        include_p2_specs=True,
        preprocessing="standard_scaler",
        configured_train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        configured_validation_sessions=["2024-11-01"],
        configured_test_sessions=["2025-01-03"],
    )


def test_sklearn_dependency_declared_and_importable_pass() -> None:
    root = Path(__file__).resolve().parents[1]
    gate = validate_sklearn_dependency_declared(root)
    assert gate.scikit_learn_declared is True
    assert gate.sklearn_importable is True
    assert gate.dependency_status == "declared_and_importable"
    assert gate.passed is True


def test_missing_dependency_declaration_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "requirements.txt").write_text("numpy>=1.26\n", encoding="utf-8")

    def _probe_no_sklearn() -> object:
        from quant_lab.ml.harness.p8b3_dependency_audit import EnvironmentVersions

        return EnvironmentVersions(python_version="3.12.0", sklearn_importable=False)

    monkeypatch.setattr(
        "quant_lab.ml.harness.p8b3_dependency_audit.probe_environment",
        _probe_no_sklearn,
    )
    gate = validate_sklearn_dependency_declared(tmp_path)
    assert gate.passed is False
    assert gate.dependency_status == "not_declared_not_importable"


def test_model_specs_p0_p1_p2() -> None:
    assert isinstance(P0LinearRegressionSpec(), P0LinearRegressionSpec)
    assert P0RidgeRegressionSpec().hyperparameters["alpha"] == 1.0
    assert P1LogisticRegressionSpec().hyperparameters["threshold"] == 0.5
    assert P2MultinomialLogisticRegressionSpec().optional is True
    specs = all_allowed_model_specs()
    tracks = {s.track for s in specs}
    assert tracks == {"P0", "P1", "P2"}
    assert len(default_p0_specs()) == 2
    assert len(default_p1_specs()) == 2
    assert len(default_p2_specs()) == 2


def test_dry_run_produces_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _test_config(tmp_path)

    def _mock_gate(*_a: object, **_k: object) -> object:
        from quant_lab.ml.harness.p8b3_plan import SklearnDependencyGateResult

        return SklearnDependencyGateResult(
            passed=True,
            dependency_status="declared_and_importable",
            scikit_learn_declared=True,
            sklearn_importable=True,
            sklearn_version="1.9.0",
            declared_version_spec="scikit-learn>=1.4",
        )

    monkeypatch.setattr("quant_lab.ml.harness.p8b3_plan.validate_sklearn_dependency_declared", _mock_gate)
    plan = build_p8b31_fit_plan(cfg, project_root=tmp_path, load_data=False)
    assert plan.model_fitting_allowed is False
    assert plan.fit_execution_status == "blocked_until_p8b3_2"
    assert len(plan.allowed_model_specs) >= 4
    out = write_fit_plan_json(plan, tmp_path / "plan.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["phase"] == HARNESS_STAGE_P8B3_1


def test_execute_mode_blocked() -> None:
    ok, msg = reject_fit_execution(execute_requested=True)
    assert ok is False
    assert msg == FIT_EXECUTION_BLOCKED_MSG


def test_forbidden_target_in_features_fails() -> None:
    rows = _synthetic_rows()
    bad = dict(rows[0])
    bad["features.close_near_primary_pin_050"] = 1.0
    rows_bad = [bad] + rows[1:]
    summary = validate_feature_target_matrix(
        rows_bad,
        train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03"],
        target_keys=[LABEL_P1_050],
    )
    assert summary.passed is False
    assert not summary.forbidden_input_pass


def test_session_split_validation_required() -> None:
    rows = _synthetic_rows()
    summary = validate_feature_target_matrix(
        rows,
        train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03"],
        target_keys=[LABEL_P0, LABEL_P1_050],
    )
    assert summary.split_validation_pass is True
    assert summary.row_level_random_split_pass is True


def test_numeric_feature_selection_excludes_non_numeric() -> None:
    rows = _synthetic_rows()
    rows[0]["features.cat_col"] = "bad"
    summary = validate_feature_target_matrix(
        rows,
        train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03"],
        target_keys=[LABEL_P0],
    )
    assert "cat_col" in summary.excluded_non_numeric_columns


def test_nan_inf_summary_produced() -> None:
    rows = _synthetic_rows()
    rows[0]["features.spot_t"] = float("nan")
    summary = validate_feature_target_matrix(
        rows,
        train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03"],
        target_keys=[LABEL_P0],
    )
    assert summary.nan_count >= 0


def test_preprocessing_plan_train_only_requirement() -> None:
    plan = build_preprocessing_plan_from_columns(["spot_t"], ["cat_col"], preprocessing="standard_scaler")
    assert plan["scaler"]["fit_on"] == "train_sessions_only"
    assert StandardScalerPlan().leakage_safe is True
    assert NoScalerPlan().kind == "no_scaler"
    assert NumericFeatureSelectionPlan().kind == "numeric_feature_selection"


def test_run_manifest_plan_model_fitting_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _test_config(tmp_path)

    def _mock_gate(*_a: object, **_k: object) -> object:
        from quant_lab.ml.harness.p8b3_plan import SklearnDependencyGateResult

        return SklearnDependencyGateResult(
            passed=True,
            dependency_status="declared_and_importable",
            scikit_learn_declared=True,
            sklearn_importable=True,
            sklearn_version="1.9.0",
            declared_version_spec="scikit-learn>=1.4",
        )

    monkeypatch.setattr("quant_lab.ml.harness.p8b3_plan.validate_sklearn_dependency_declared", _mock_gate)
    plan = build_p8b31_fit_plan(cfg, project_root=tmp_path, load_data=False)
    assert plan.run_manifest_plan["model_fitting_allowed"] is False
    assert plan.run_manifest_plan["p8b3_2_required_before_fit"] is True


def test_no_fit_called_in_plan_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _test_config(tmp_path)

    def _mock_gate(*_a: object, **_k: object) -> object:
        from quant_lab.ml.harness.p8b3_plan import SklearnDependencyGateResult

        return SklearnDependencyGateResult(
            passed=True,
            dependency_status="declared_and_importable",
            scikit_learn_declared=True,
            sklearn_importable=True,
            sklearn_version="1.9.0",
            declared_version_spec="scikit-learn>=1.4",
        )

    monkeypatch.setattr("quant_lab.ml.harness.p8b3_plan.validate_sklearn_dependency_declared", _mock_gate)
    plan = build_p8b31_fit_plan(cfg, project_root=tmp_path, load_data=False)
    assert plan.sklearn_fit_called is False
    assert plan.model_fitting_performed is False


def test_cli_dry_run_exits_zero() -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "scripts/prepare_simple_learned_baselines.py", "--dry-run"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["fit_execution_status"] == "blocked_until_p8b3_2"


def test_cli_execute_exits_nonzero() -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "scripts/prepare_simple_learned_baselines.py", "--execute"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert FIT_EXECUTION_BLOCKED_MSG in proc.stdout


def test_check_sklearn_available() -> None:
    assert check_sklearn_available() is True
