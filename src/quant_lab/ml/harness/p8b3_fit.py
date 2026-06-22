"""ML-P8B.3.2 train-only simple learned baseline fitting."""

# ruff: noqa: N803, N806

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from quant_lab.ml.features.p8b1_validation import extract_feature_value_columns
from quant_lab.ml.harness.learned_models import (
    ModelSpec,
    P1LogisticRegressionSpec,
    default_p0_specs,
    default_p2_specs,
)
from quant_lab.ml.harness.metrics import (
    compute_p0_regression_metrics,
    compute_p1_binary_metrics,
    compute_p2_multiclass_metrics,
)
from quant_lab.ml.harness.p8b2_eval import (
    LABEL_P1_050,
    assign_split,
    filter_baseline_eligible,
    load_joined_rows,
)
from quant_lab.ml.harness.p8b3_plan import (
    P8B31Config,
    _build_split_manifest,
    _git_commit,
    _hash_file,
    get_sklearn_versions,
    load_p8b31_config,
    validate_feature_target_matrix,
    validate_sklearn_dependency_declared,
)

log = logging.getLogger(__name__)

HARNESS_STAGE_P8B3_2 = "ML-P8B.3.2"
TargetGroup = Literal["p0", "p1_050", "p1_025", "p2_optional"]

FIXED_HYPERPARAMETERS: dict[str, dict[str, Any]] = {
    "p0_linear_regression": {},
    "p0_ridge_regression": {"alpha": 1.0},
    "p1_logistic_050": {"C": 1.0, "max_iter": 1000, "class_weight": None, "threshold": 0.5},
    "p1_logistic_025": {"C": 1.0, "max_iter": 1000, "class_weight": None, "threshold": 0.5},
    "p2_multinomial_050": {"C": 1.0, "max_iter": 1000, "solver": "lbfgs", "sklearn_multinomial_note": "sklearn>=1.9: multi_class param removed; lbfgs handles multiclass"},
    "p2_multinomial_025": {"C": 1.0, "max_iter": 1000, "solver": "lbfgs", "sklearn_multinomial_note": "sklearn>=1.9: multi_class param removed; lbfgs handles multiclass"},
}


@dataclass
class TrainOnlyPreprocessor:
    """SimpleImputer + optional StandardScaler fit on train only."""

    imputer: SimpleImputer
    scaler: StandardScaler | None
    fit_n_samples: int = 0

    @classmethod
    def fit_on_train(cls, X_train: np.ndarray, *, use_scaler: bool) -> TrainOnlyPreprocessor:
        imputer = SimpleImputer(strategy="median")
        X_imp = imputer.fit_transform(X_train)
        scaler: StandardScaler | None = None
        if use_scaler:
            scaler = StandardScaler()
            X_imp = scaler.fit_transform(X_imp)
        return cls(imputer=imputer, scaler=scaler, fit_n_samples=int(X_train.shape[0]))

    def transform(self, X: np.ndarray) -> np.ndarray:
        X_imp = self.imputer.transform(X)
        if self.scaler is not None:
            return np.asarray(self.scaler.transform(X_imp), dtype=float)
        return np.asarray(X_imp, dtype=float)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fit_n_samples": self.fit_n_samples,
            "imputer_strategy": self.imputer.strategy,
            "scaler_used": self.scaler is not None,
            "preprocessing_fit_on_train_only": True,
        }


@dataclass
class ModelFitResult:
    spec_name: str
    track: str
    target_key: str
    skipped: bool = False
    skipped_reason: str | None = None
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    comparison_vs_p8b2: dict[str, Any] = field(default_factory=dict)
    comparison_vs_p8b3_2: dict[str, Any] = field(default_factory=dict)
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    preprocessing: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class P8B32FitResult:
    phase: str = HARNESS_STAGE_P8B3_2
    dry_run: bool = True
    p8b3_2_pass: bool = False
    model_fitting_performed: bool = False
    sklearn_fit_called: bool = False
    dependency_status: str = ""
    split_validation: dict[str, Any] = field(default_factory=dict)
    forbidden_validation: dict[str, Any] = field(default_factory=dict)
    preprocessing_summary: dict[str, Any] = field(default_factory=dict)
    models_fitted: list[str] = field(default_factory=list)
    model_results: list[dict[str, Any]] = field(default_factory=list)
    skipped_models: dict[str, str] = field(default_factory=dict)
    run_manifest_path: Path | None = None
    report_path: Path | None = None
    test_not_used_for_tuning: bool = True
    hyperparameter_search_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.run_manifest_path is not None:
            data["run_manifest_path"] = str(self.run_manifest_path)
        if self.report_path is not None:
            data["report_path"] = str(self.report_path)
        return data


def parse_target_groups(raw: str | None) -> set[TargetGroup]:
    if not raw:
        return {"p0", "p1_050", "p1_025", "p2_optional"}
    mapping: dict[str, TargetGroup] = {
        "p0": "p0",
        "p1_050": "p1_050",
        "p1_025": "p1_025",
        "p2_optional": "p2_optional",
        "p2": "p2_optional",
    }
    out: set[TargetGroup] = set()
    for part in raw.split(","):
        key = part.strip().lower()
        if key in mapping:
            out.add(mapping[key])
    return out or {"p0", "p1_050", "p1_025", "p2_optional"}


def specs_for_targets(targets: set[TargetGroup]) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    if "p0" in targets:
        specs.extend(default_p0_specs())
    if "p1_050" in targets:
        specs.append(
            P1LogisticRegressionSpec(
                name="p1_logistic_050",
                target_key="labels.close_near_primary_pin_050",
            )
        )
    if "p1_025" in targets:
        specs.append(
            P1LogisticRegressionSpec(
                name="p1_logistic_025",
                target_key="labels.close_near_primary_pin_025",
            )
        )
    if "p2_optional" in targets:
        specs.extend(default_p2_specs())
    return specs


def create_estimator(spec: ModelSpec) -> Any:
    hp = FIXED_HYPERPARAMETERS.get(spec.name, dict(spec.hyperparameters))
    if spec.name == "p0_linear_regression":
        return LinearRegression()
    if spec.name == "p0_ridge_regression":
        return Ridge(alpha=float(hp.get("alpha", 1.0)))
    if spec.name in ("p1_logistic_050", "p1_logistic_025"):
        return LogisticRegression(
            C=float(hp.get("C", 1.0)),
            max_iter=int(hp.get("max_iter", 1000)),
            class_weight=hp.get("class_weight"),
        )
    if spec.name.startswith("p2_multinomial"):
        return LogisticRegression(
            C=float(hp.get("C", 1.0)),
            max_iter=int(hp.get("max_iter", 1000)),
            solver=str(hp.get("solver", "lbfgs")),
        )
    raise ValueError(f"unsupported spec: {spec.name}")


def _build_numeric_feature_columns(
    train_rows: list[dict[str, Any]],
    feat_cols: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Select numeric columns using train rows only; drop all-NaN train columns."""
    numeric_cols: list[str] = []
    non_numeric: list[str] = []
    for col in feat_cols:
        vals = [row.get(f"features.{col}") for row in train_rows]
        if all(_is_numeric_value(v) or v is None for v in vals):
            numeric_cols.append(col)
        else:
            non_numeric.append(col)
    all_nan: list[str] = []
    kept: list[str] = []
    if numeric_cols:
        mat = _matrix_for_columns(train_rows, numeric_cols)
        for j, col in enumerate(numeric_cols):
            col_vals = mat[:, j]
            if np.all(np.isnan(col_vals)):
                all_nan.append(col)
            else:
                kept.append(col)
    return kept, non_numeric, all_nan


def _is_numeric_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)):
        return not (isinstance(val, float) and (np.isnan(val) or np.isinf(val)))
    return False


def _matrix_for_columns(rows: list[dict[str, Any]], columns: list[str]) -> np.ndarray:
    if not columns:
        return np.empty((len(rows), 0))
    return np.array(
        [[float(row.get(f"features.{c}") or np.nan) for c in columns] for row in rows],
        dtype=float,
    )


def _extract_y(rows: list[dict[str, Any]], target_key: str, track: str) -> Any:
    vals = [r.get(target_key) for r in rows]
    if track == "P0":
        return np.asarray([float(v) if v is not None else np.nan for v in vals], dtype=float)
    if track == "P1":
        return np.asarray([bool(v) for v in vals], dtype=bool)
    return np.asarray([str(v) if v is not None else None for v in vals], dtype=object)


def _positive_class_proba(estimator: LogisticRegression, X: np.ndarray) -> np.ndarray:
    classes = list(estimator.classes_)
    if True in classes:
        idx = classes.index(True)
    elif 1 in classes:
        idx = classes.index(1)
    else:
        idx = 1 if len(classes) > 1 else 0
    return estimator.predict_proba(X)[:, idx]


def _validate_p1_dual_class(split_rows: list[dict[str, Any]], target_key: str) -> list[str]:
    errors: list[str] = []
    for split_name in ("train", "validation"):
        rows = [r for r in split_rows if r.get("split") == split_name]
        vals = [bool(r.get(target_key)) for r in rows if r.get(target_key) is not None]
        if len(set(vals)) < 2:
            errors.append(f"{target_key}: both classes required in {split_name}, got {set(vals)}")
    return errors


def _load_p8b2_baseline_metrics(p8b2_reports: Path) -> dict[str, Any]:
    path = p8b2_reports / "p8b2_evaluation_report.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("metrics", {})


def _compare_test_metric(
    learned: dict[str, Any],
    p8b2_metrics: dict[str, Any],
    *,
    p8b2_section: str,
    p8b2_model: str,
    metric_key: str,
) -> dict[str, Any]:
    section = p8b2_metrics.get(p8b2_section, {})
    test_base = section.get("test", {}).get(p8b2_model, {})
    base_val = test_base.get(metric_key)
    learned_val = learned.get("test", {}).get(metric_key)
    delta: float | None = None
    if base_val is not None and learned_val is not None:
        delta = float(learned_val) - float(base_val)
    return {
        "metric": metric_key,
        "learned_test": learned_val,
        "p8b2_baseline_test": base_val,
        "delta_learned_minus_baseline": delta,
        "p8b2_baseline_model": p8b2_model,
    }


def fit_model_train_only(
    spec: ModelSpec,
    *,
    split_rows: list[dict[str, Any]],
    numeric_cols: list[str],
    use_scaler: bool,
    p8b2_metrics: dict[str, Any],
) -> ModelFitResult:
    result = ModelFitResult(
        spec_name=spec.name,
        track=spec.track,
        target_key=spec.target_key,
        hyperparameters=dict(FIXED_HYPERPARAMETERS.get(spec.name, {})),
    )
    train_rows = [r for r in split_rows if r.get("split") == "train"]
    y_train = _extract_y(train_rows, spec.target_key, spec.track)

    if spec.track == "P1":
        p1_errors = _validate_p1_dual_class(split_rows, spec.target_key)
        if p1_errors:
            if spec.name == "p1_logistic_050":
                result.skipped = True
                result.skipped_reason = "; ".join(p1_errors)
                return result
            result.skipped = True
            result.skipped_reason = "; ".join(p1_errors)
            return result

    if spec.track == "P2":
        classes = {str(v) for v in y_train if v is not None}
        if len(classes) < 2:
            result.skipped = True
            result.skipped_reason = f"train classes insufficient: {sorted(classes)}"
            return result

    X_train_raw = _matrix_for_columns(train_rows, numeric_cols)
    preprocessor = TrainOnlyPreprocessor.fit_on_train(X_train_raw, use_scaler=use_scaler)
    result.preprocessing = preprocessor.to_dict()

    estimator = create_estimator(spec)
    X_train = preprocessor.transform(X_train_raw)
    estimator.fit(X_train, y_train)

    threshold = float(result.hyperparameters.get("threshold", 0.5))
    for split_name in ("train", "validation", "test"):
        rows = [r for r in split_rows if r.get("split") == split_name]
        X_raw = _matrix_for_columns(rows, numeric_cols)
        X = preprocessor.transform(X_raw)
        y_true = _extract_y(rows, spec.target_key, spec.track)
        if spec.track == "P0":
            y_pred = estimator.predict(X)
            result.metrics[split_name] = compute_p0_regression_metrics(y_true, y_pred)
        elif spec.track == "P1":
            y_proba = _positive_class_proba(estimator, X)
            y_pred = y_proba >= threshold
            result.metrics[split_name] = compute_p1_binary_metrics(y_true, y_pred, y_proba)
        else:
            y_pred = estimator.predict(X)
            result.metrics[split_name] = compute_p2_multiclass_metrics(y_true, y_pred)

    if spec.track == "P0":
        for bname in ("zero_em", "train_median_em", "train_mean_em"):
            result.comparison_vs_p8b2[bname] = _compare_test_metric(
                result.metrics,
                p8b2_metrics,
                p8b2_section="p0_close_distance_to_primary_pin_em",
                p8b2_model=bname,
                metric_key="mae",
            )
    elif spec.track == "P1" and spec.name == "p1_logistic_050":
        for bname in ("majority_class", "constant_not_near", "train_prior_probability"):
            result.comparison_vs_p8b2[bname] = _compare_test_metric(
                result.metrics,
                p8b2_metrics,
                p8b2_section="p1_close_near_primary_pin_050",
                p8b2_model=bname,
                metric_key="balanced_accuracy",
            )

    return result


def build_p8b32_dry_run_plan(
    config: P8B31Config,
    *,
    project_root: Path,
    targets: set[TargetGroup],
    split_mode: Literal["chronological", "configured"] = "configured",
) -> P8B32FitResult:
    result = P8B32FitResult(dry_run=True, model_fitting_performed=False, sklearn_fit_called=False)
    dep = validate_sklearn_dependency_declared(project_root)
    result.dependency_status = dep.dependency_status
    if not dep.passed:
        return result

    specs = specs_for_targets(targets)
    joined = load_joined_rows(config.dataset_root, config.feature_root)
    sessions = sorted({str(r.get("trade_date")) for r in joined})
    split_manifest = _build_split_manifest(config, sessions, split_mode)
    matrix_val = validate_feature_target_matrix(
        joined,
        train_sessions=split_manifest.train_sessions,
        validation_sessions=split_manifest.validation_sessions,
        test_sessions=split_manifest.test_sessions,
        target_keys=[s.target_key for s in specs],
    )
    result.forbidden_validation = {
        "forbidden_input_pass": matrix_val.forbidden_input_pass,
        "forbidden_columns": matrix_val.forbidden_columns,
    }
    result.split_validation = {
        "passed": matrix_val.split_validation_pass and matrix_val.row_level_random_split_pass,
        "errors": matrix_val.split_errors,
        "train_sessions": split_manifest.train_sessions,
        "validation_sessions": split_manifest.validation_sessions,
        "test_sessions": split_manifest.test_sessions,
    }
    result.preprocessing_summary = {
        "numeric_feature_count": matrix_val.numeric_feature_count,
        "excluded_non_numeric": matrix_val.excluded_non_numeric_columns,
        "preprocessing_fit_on_train_only": True,
        "imputer": "SimpleImputer(median)",
        "scaler": config.preprocessing,
    }
    result.models_fitted = [s.name for s in specs]
    result.p8b3_2_pass = matrix_val.passed and dep.passed
    return result


def run_p8b32_fitting(
    config: P8B31Config,
    *,
    project_root: Path,
    targets: set[TargetGroup],
    split_mode: Literal["chronological", "configured"] = "configured",
    execute: bool = False,
) -> P8B32FitResult:
    if not execute:
        return build_p8b32_dry_run_plan(
            config, project_root=project_root, targets=targets, split_mode=split_mode
        )

    result = P8B32FitResult(dry_run=False)
    dep = validate_sklearn_dependency_declared(project_root)
    result.dependency_status = dep.dependency_status
    if not dep.passed:
        return result

    specs = specs_for_targets(targets)
    joined = load_joined_rows(config.dataset_root, config.feature_root)
    eligible = filter_baseline_eligible(joined)
    sessions = sorted({str(r.get("trade_date")) for r in joined})
    split_manifest = _build_split_manifest(config, sessions, split_mode)
    matrix_val = validate_feature_target_matrix(
        joined,
        train_sessions=split_manifest.train_sessions,
        validation_sessions=split_manifest.validation_sessions,
        test_sessions=split_manifest.test_sessions,
        target_keys=[s.target_key for s in specs],
    )
    result.forbidden_validation = {
        "forbidden_input_pass": matrix_val.forbidden_input_pass,
        "forbidden_columns": matrix_val.forbidden_columns,
    }
    result.split_validation = {
        "passed": matrix_val.split_validation_pass and matrix_val.row_level_random_split_pass,
        "errors": matrix_val.split_errors,
        "train_sessions": split_manifest.train_sessions,
        "validation_sessions": split_manifest.validation_sessions,
        "test_sessions": split_manifest.test_sessions,
    }
    if not matrix_val.passed:
        log.error("validation failed: %s", matrix_val.errors)
        return result

    split_rows = assign_split(eligible, split_manifest)
    p1_errors = _validate_p1_dual_class(split_rows, LABEL_P1_050)
    if p1_errors and "p1_050" in targets:
        log.error("P1 0.50 dual class gate failed: %s", p1_errors)
        result.split_validation["p1_050_dual_class_errors"] = p1_errors
        return result

    feat_cols = extract_feature_value_columns(eligible[0])
    train_rows = [r for r in split_rows if r.get("split") == "train"]
    numeric_cols, non_numeric, all_nan_train = _build_numeric_feature_columns(train_rows, feat_cols)
    use_scaler = config.preprocessing == "standard_scaler"
    result.preprocessing_summary = {
        "numeric_columns": len(numeric_cols),
        "excluded_non_numeric": non_numeric,
        "all_nan_train_columns": all_nan_train,
        "preprocessing_fit_on_train_only": True,
        "use_scaler": use_scaler,
        "imputer": "SimpleImputer(median)",
    }

    p8b2_metrics = _load_p8b2_baseline_metrics(config.p8b2_reports)
    model_results: list[ModelFitResult] = []
    for spec in specs:
        fit_result = fit_model_train_only(
            spec,
            split_rows=split_rows,
            numeric_cols=numeric_cols,
            use_scaler=use_scaler,
            p8b2_metrics=p8b2_metrics,
        )
        if fit_result.skipped:
            result.skipped_models[fit_result.spec_name] = fit_result.skipped_reason or "skipped"
        else:
            result.models_fitted.append(fit_result.spec_name)
        model_results.append(fit_result)

    result.model_fitting_performed = True
    result.sklearn_fit_called = True
    result.model_results = [m.to_dict() for m in model_results]
    result.test_not_used_for_tuning = True
    result.hyperparameter_search_performed = False

    config.output_reports.mkdir(parents=True, exist_ok=True)
    eval_report: dict[str, Any] = {
        "phase": HARNESS_STAGE_P8B3_2,
        "dependency_status": dep.dependency_status,
        "split_validation": result.split_validation,
        "forbidden_validation": result.forbidden_validation,
        "preprocessing_summary": result.preprocessing_summary,
        "models_fitted": result.models_fitted,
        "skipped_models": result.skipped_models,
        "model_results": result.model_results,
        "fixed_hyperparameters": FIXED_HYPERPARAMETERS,
        "p8b2_baseline_reference": str(config.p8b2_reports / "p8b2_evaluation_report.json"),
        "test_not_used_for_tuning": True,
        "hyperparameter_search_performed": False,
    }

    manifest: dict[str, Any] = {
        "stage": HARNESS_STAGE_P8B3_2,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "model_fitting_allowed": True,
        "model_type": "simple_learned_baseline",
        "target_name": config.preferred_binary_target,
        "model_spec": result.models_fitted,
        "fixed_hyperparameters": FIXED_HYPERPARAMETERS,
        "dataset_manifest_hash": _hash_file(config.dataset_root / "manifest.json"),
        "feature_manifest_hash": _hash_file(config.feature_root / "manifest.json"),
        "split_protocol": config.split_protocol,
        "train_sessions": split_manifest.train_sessions,
        "validation_sessions": split_manifest.validation_sessions,
        "test_sessions": split_manifest.test_sessions,
        "dependency_versions": get_sklearn_versions(),
        "preprocessing_fit_on_train_only": True,
        "forbidden_input_validation_status": "PASS",
        "leakage_validation_status": "PASS",
        "model_free_baseline_reference": str(config.p8b2_reports / "p8b2_run_manifest.json"),
        "trained_on_sessions_only": True,
        "test_not_used_for_tuning": True,
        "hyperparameter_search_performed": False,
        "code_commit": _git_commit(project_root),
        "artifacts_written": [str(config.output_reports)],
    }

    p0_done = any(m.spec_name.startswith("p0_") and not m.skipped for m in model_results)
    p1_done = any(m.spec_name == "p1_logistic_050" and not m.skipped for m in model_results)
    result.p8b3_2_pass = bool(p0_done and p1_done and matrix_val.passed)
    eval_report["p8b3_2_pass"] = result.p8b3_2_pass

    report_path = config.output_reports / "p8b3_2_evaluation_report.json"
    report_path.write_text(json.dumps(eval_report, indent=2), encoding="utf-8")
    result.report_path = report_path

    manifest_path = config.output_reports / "p8b3_2_run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    result.run_manifest_path = manifest_path
    return result


__all__ = [
    "HARNESS_STAGE_P8B3_2",
    "FIXED_HYPERPARAMETERS",
    "P8B32FitResult",
    "TrainOnlyPreprocessor",
    "build_p8b32_dry_run_plan",
    "create_estimator",
    "fit_model_train_only",
    "load_p8b31_config",
    "parse_target_groups",
    "run_p8b32_fitting",
    "specs_for_targets",
]
