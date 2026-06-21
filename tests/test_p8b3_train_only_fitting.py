"""Tests for ML-P8B.3.2 train-only simple learned baseline fitting."""

# ruff: noqa: N803, N806

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from sklearn.linear_model import LinearRegression, LogisticRegression

from quant_lab.ml.harness.learned_models import (
    P0LinearRegressionSpec,
    P1LogisticRegressionSpec,
    P2MultinomialLogisticRegressionSpec,
)
from quant_lab.ml.harness.p8b2_eval import LABEL_P0, LABEL_P1_025, LABEL_P1_050
from quant_lab.ml.harness.p8b3_fit import (
    FIXED_HYPERPARAMETERS,
    HARNESS_STAGE_P8B3_2,
    TrainOnlyPreprocessor,
    create_estimator,
    fit_model_train_only,
    parse_target_groups,
    run_p8b32_fitting,
    specs_for_targets,
)
from quant_lab.ml.harness.p8b3_plan import P8B31Config, validate_feature_target_matrix
from quant_lab.ml.harness.validators import validate_forbidden_features


def _synthetic_row(
    trade_date: str,
    *,
    d_em: float = 0.1,
    near: bool = False,
    near_025: bool = False,
    abc: str = "above",
) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "split": None,
        "features.spot_t": 5000.0 + d_em,
        "features.pin_score_t": 0.5,
        "features.official_close": 5000.0,
        LABEL_P0: d_em,
        LABEL_P1_050: near,
        LABEL_P1_025: near_025,
        "labels.close_above_below_primary_pin_050": abc,
        "labels.baseline_target_eligible": True,
    }


def _assign_splits(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    train = {"2024-01-05", "2024-01-19", "2024-02-13"}
    val = {"2024-11-01"}
    out: list[dict[str, object]] = []
    for r in rows:
        sid = str(r["trade_date"])
        if sid in train:
            split = "train"
        elif sid in val:
            split = "validation"
        else:
            split = "test"
        out.append({**r, "split": split})
    return out


def _synthetic_split_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sessions = (
        ["2024-01-05", "2024-01-19", "2024-02-13"]
        + ["2024-11-01"]
        + ["2025-01-03", "2025-02-07"]
    )
    for i, sid in enumerate(sessions):
        for j in range(4):
            rows.append(
                _synthetic_row(
                    sid,
                    d_em=float(i + j) * 0.05,
                    near=j % 2 == 0,
                    near_025=j % 3 == 0,
                    abc=["above", "below", "at"][j % 3],
                )
            )
    return _assign_splits(rows)


def test_parse_target_groups_defaults() -> None:
    assert parse_target_groups(None) == {"p0", "p1_050", "p1_025", "p2_optional"}
    assert parse_target_groups("p0,p1_050") == {"p0", "p1_050"}


def test_fixed_hyperparameters_no_search_objects() -> None:
    for hp in FIXED_HYPERPARAMETERS.values():
        assert "grid" not in str(hp).lower()
        assert "search" not in str(hp).lower()
    est = create_estimator(P0LinearRegressionSpec())
    assert isinstance(est, LinearRegression)
    ridge_hp = FIXED_HYPERPARAMETERS["p0_ridge_regression"]
    assert ridge_hp["alpha"] == 1.0


def test_forbidden_columns_fail_before_fitting() -> None:
    rows = _synthetic_split_rows()
    rows[0]["features.labels.close_distance_to_primary_pin_em"] = 1.0
    feat_cols = ["spot_t", "pin_score_t", "labels.close_distance_to_primary_pin_em"]
    forb = validate_forbidden_features(feat_cols)
    assert not forb.passed


def test_target_column_excluded_from_x_validation() -> None:
    rows = _synthetic_split_rows()
    rows_with_bad = [{**r, "features.close_near_primary_pin_050": True} for r in rows]
    summary = validate_feature_target_matrix(
        rows_with_bad,
        train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03", "2025-02-07"],
        target_keys=[LABEL_P1_050],
    )
    assert not summary.passed


def test_imputer_fit_on_train_only() -> None:
    X_train = np.array([[1.0, np.nan], [2.0, 3.0], [np.nan, 4.0]])
    X_val = np.array([[np.nan, 5.0], [10.0, np.nan]])
    prep = TrainOnlyPreprocessor.fit_on_train(X_train, use_scaler=False)
    assert prep.fit_n_samples == 3
    assert prep.imputer.statistics_[0] == pytest.approx(1.5)
    transformed = prep.transform(X_val)
    assert transformed[0, 0] == pytest.approx(1.5)


def test_scaler_fit_on_train_only() -> None:
    X_train = np.array([[0.0], [2.0], [4.0]])
    X_test = np.array([[2.0]])
    prep = TrainOnlyPreprocessor.fit_on_train(X_train, use_scaler=True)
    assert prep.scaler is not None
    assert prep.scaler.n_samples_seen_ == 3
    out = prep.transform(X_test)
    assert out[0, 0] == pytest.approx(0.0)


def test_p0_linear_fits_train_only(monkeypatch: pytest.MonkeyPatch) -> None:
    split_rows = _synthetic_split_rows()
    feat_cols = ["spot_t", "pin_score_t"]
    fit_calls: list[int] = []

    original_fit = LinearRegression.fit

    def tracked_fit(self: LinearRegression, X: np.ndarray, y: np.ndarray, *args: object, **kwargs: object) -> LinearRegression:
        fit_calls.append(X.shape[0])
        return original_fit(self, X, y, *args, **kwargs)

    monkeypatch.setattr(LinearRegression, "fit", tracked_fit)
    result = fit_model_train_only(
        P0LinearRegressionSpec(),
        split_rows=split_rows,
        numeric_cols=feat_cols,
        use_scaler=True,
        p8b2_metrics={},
    )
    assert not result.skipped
    assert fit_calls == [12]
    assert "train" in result.metrics
    assert "test" in result.metrics


def test_p1_logistic_fits_train_only(monkeypatch: pytest.MonkeyPatch) -> None:
    split_rows = _synthetic_split_rows()
    feat_cols = ["spot_t", "pin_score_t"]
    fit_calls: list[int] = []

    original_fit = LogisticRegression.fit

    def tracked_fit(self: LogisticRegression, X: np.ndarray, y: np.ndarray, *args: object, **kwargs: object) -> LogisticRegression:
        fit_calls.append(X.shape[0])
        return original_fit(self, X, y, *args, **kwargs)

    monkeypatch.setattr(LogisticRegression, "fit", tracked_fit)
    result = fit_model_train_only(
        P1LogisticRegressionSpec(name="p1_logistic_050", target_key=LABEL_P1_050),
        split_rows=split_rows,
        numeric_cols=feat_cols,
        use_scaler=True,
        p8b2_metrics={},
    )
    assert not result.skipped
    assert fit_calls == [12]
    assert result.metrics["validation"]["balanced_accuracy"] is not None


def test_p2_skips_insufficient_train_classes() -> None:
    split_rows = _synthetic_split_rows()
    for r in split_rows:
        if r.get("split") == "train":
            r["labels.close_above_below_primary_pin_050"] = "above"
    result = fit_model_train_only(
        P2MultinomialLogisticRegressionSpec(name="p2_multinomial_050"),
        split_rows=split_rows,
        numeric_cols=["spot_t", "pin_score_t"],
        use_scaler=True,
        p8b2_metrics={},
    )
    assert result.skipped
    assert "insufficient" in (result.skipped_reason or "").lower()


def test_no_hyperparameter_search_imports() -> None:
    import quant_lab.ml.harness.p8b3_fit as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "GridSearchCV" not in source
    assert "RandomizedSearchCV" not in source
    assert "xgboost" not in source
    assert "lightgbm" not in source


def test_run_manifest_records_fitting_flags(tmp_path: Path) -> None:
    config = P8B31Config(
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
        test_sessions_count=2,
        preferred_binary_target="close_near_primary_pin_050",
        sensitivity_binary_target="close_near_primary_pin_025",
        model_fitting_allowed=False,
        include_p2_specs=True,
        preprocessing="standard_scaler",
        configured_train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        configured_validation_sessions=["2024-11-01"],
        configured_test_sessions=["2025-01-03", "2025-02-07"],
    )
    (tmp_path / "p8b2").mkdir()
    (tmp_path / "p8b2" / "p8b2_evaluation_report.json").write_text(
        json.dumps({"metrics": {}}), encoding="utf-8"
    )

    split_rows = _synthetic_split_rows()
    feat_cols = ["spot_t", "pin_score_t"]

    with (
        patch(
            "quant_lab.ml.harness.p8b3_fit.validate_sklearn_dependency_declared",
            return_value=MagicMock(passed=True, dependency_status="declared_and_importable"),
        ),
        patch("quant_lab.ml.harness.p8b3_fit.load_joined_rows", return_value=split_rows),
        patch(
            "quant_lab.ml.harness.p8b3_fit.filter_baseline_eligible",
            return_value=[r for r in split_rows if r.get("labels.baseline_target_eligible")],
        ),
        patch(
            "quant_lab.ml.harness.p8b3_fit.extract_feature_value_columns",
            return_value=feat_cols,
        ),
        patch(
            "quant_lab.ml.harness.p8b3_fit.validate_feature_target_matrix",
            return_value=MagicMock(
                passed=True,
                forbidden_input_pass=True,
                forbidden_columns=[],
                split_validation_pass=True,
                row_level_random_split_pass=True,
                split_errors=[],
                numeric_feature_count=2,
                excluded_non_numeric_columns=[],
            ),
        ),
    ):
        result = run_p8b32_fitting(
            config,
            project_root=tmp_path,
            targets={"p0", "p1_050"},
            execute=True,
        )

    assert result.model_fitting_performed
    assert result.test_not_used_for_tuning
    assert not result.hyperparameter_search_performed
    assert result.run_manifest_path is not None
    manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage"] == HARNESS_STAGE_P8B3_2
    assert manifest["model_fitting_allowed"] is True
    assert manifest["test_not_used_for_tuning"] is True
    assert manifest["preprocessing_fit_on_train_only"] is True


def test_dry_run_does_not_fit(tmp_path: Path) -> None:
    config = P8B31Config(
        version="test",
        dataset_root=Path("artifacts/datasets/pit_sample_baseline_v1_1_validation"),
        feature_root=Path("artifacts/features/pit_features_baseline_v1_1_validation"),
        input_reports=tmp_path / "in",
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
        configured_train_sessions=[],
        configured_validation_sessions=[],
        configured_test_sessions=[],
    )
    project_root = Path(__file__).resolve().parents[1]
    if not (project_root / config.dataset_root / "manifest.json").is_file():
        pytest.skip("validation artifacts not present")
    result = run_p8b32_fitting(
        config,
        project_root=project_root,
        targets={"p0", "p1_050"},
        execute=False,
    )
    assert result.dry_run
    assert not result.model_fitting_performed
    assert not result.sklearn_fit_called


def test_specs_for_targets() -> None:
    specs = specs_for_targets({"p0", "p1_050"})
    names = {s.name for s in specs}
    assert "p0_linear_regression" in names
    assert "p1_logistic_050" in names
    assert "p1_logistic_025" not in names
