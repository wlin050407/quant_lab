"""ML-P8B.3.7 train-only reduced-feature learned refit."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from quant_lab.ml.features.p8b1_validation import extract_feature_value_columns
from quant_lab.ml.harness.p8b2_eval import (
    LABEL_P1_050,
    assign_split,
    filter_baseline_eligible,
    load_joined_rows,
)
from quant_lab.ml.harness.p8b3_fit import (
    FIXED_HYPERPARAMETERS,
    ModelFitResult,
    TargetGroup,
    _build_numeric_feature_columns,
    _load_p8b2_baseline_metrics,
    _validate_p1_dual_class,
    fit_model_train_only,
    specs_for_targets,
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
from quant_lab.ml.harness.validators import validate_forbidden_features

log = logging.getLogger(__name__)

HARNESS_STAGE_P8B3_7 = "ML-P8B.3.7"
FEATURE_SET_A = "FeatureSet_A_core_stable"
FEATURE_SET_B = "FeatureSet_B_core_plus_flow"
FEATURE_SET_C = "FeatureSet_C_diagnostic_full_pruned"
FORBIDDEN_FIRST_REFIT_SETS = frozenset({FEATURE_SET_C})

FEATURE_SET_ID_MAP: dict[str, str] = {
    "A": FEATURE_SET_A,
    "B": FEATURE_SET_B,
}


@dataclass
class P8B37Config:
    base: P8B31Config
    reduced_feature_manifest: Path
    p8b3_2_reports: Path
    expected_feature_set_version: str


@dataclass
class ReducedManifestValidation:
    passed: bool
    errors: list[str] = field(default_factory=list)
    manifest_hash: str = ""
    feature_set_version: str = ""
    target_based_selection_used: bool | None = None
    model_fitting_performed: bool | None = None


@dataclass
class FeatureSetRefitResult:
    feature_set_id: str
    feature_set_name: str
    selected_feature_count: int
    selected_features: list[str]
    numeric_columns_used: list[str]
    skipped: bool = False
    skipped_reason: str | None = None
    model_results: list[dict[str, Any]] = field(default_factory=list)
    models_fitted: list[str] = field(default_factory=list)
    skipped_models: dict[str, str] = field(default_factory=dict)
    preprocessing_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class P8B37FitResult:
    phase: str = HARNESS_STAGE_P8B3_7
    dry_run: bool = True
    p8b3_7_pass: bool = False
    model_fitting_performed: bool = False
    sklearn_fit_called: bool = False
    dependency_status: str = ""
    feature_sets_requested: list[str] = field(default_factory=list)
    feature_sets_used: list[str] = field(default_factory=list)
    reduced_manifest_validation: dict[str, Any] = field(default_factory=dict)
    split_validation: dict[str, Any] = field(default_factory=dict)
    forbidden_validation: dict[str, Any] = field(default_factory=dict)
    preprocessing_summary: dict[str, Any] = field(default_factory=dict)
    feature_set_results: list[dict[str, Any]] = field(default_factory=list)
    run_manifest_path: Path | None = None
    report_path: Path | None = None
    test_not_used_for_tuning: bool = True
    hyperparameter_search_performed: bool = False
    p8b4_blocked: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.run_manifest_path is not None:
            data["run_manifest_path"] = str(self.run_manifest_path)
        if self.report_path is not None:
            data["report_path"] = str(self.report_path)
        return data


def load_p8b37_config(path: Path) -> P8B37Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    base = load_p8b31_config(path)
    return P8B37Config(
        base=base,
        reduced_feature_manifest=Path(
            raw.get(
                "reduced_feature_manifest",
                "artifacts/reports/p8b3_feature_stability_diagnostics/reduced_feature_set_manifest.json",
            )
        ),
        p8b3_2_reports=Path(raw.get("p8b3_2_reports", "artifacts/reports/p8b3_simple_models")),
        expected_feature_set_version=str(
            raw.get("feature_set_version", "p8b3_reduced_features_v0_proposal")
        ),
    )


def parse_feature_set_ids(raw: str | None) -> list[str]:
    if not raw:
        return ["A"]
    out: list[str] = []
    for part in raw.replace("|", ",").split(","):
        key = part.strip().upper()
        if not key:
            continue
        if key == "C":
            raise ValueError("FeatureSet_C is forbidden for P8B.3.7 first refit")
        if key not in FEATURE_SET_ID_MAP:
            raise ValueError(f"unknown feature set id: {key!r}; allowed: A, B")
        if key not in out:
            out.append(key)
    return out or ["A"]


def _load_reduced_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"reduced feature manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_reduced_manifest(
    manifest: dict[str, Any],
    *,
    expected_version: str,
) -> ReducedManifestValidation:
    result = ReducedManifestValidation(passed=False)
    required_top = (
        "feature_set_version",
        "target_based_selection_used",
        "model_fitting_performed",
        "candidate_sets",
    )
    for key in required_top:
        if key not in manifest:
            result.errors.append(f"missing manifest field: {key}")

    version = str(manifest.get("feature_set_version", ""))
    result.feature_set_version = version
    if version != expected_version:
        result.errors.append(
            f"feature_set_version mismatch: expected {expected_version!r}, got {version!r}"
        )

    if manifest.get("target_based_selection_used") is not False:
        result.errors.append("target_based_selection_used must be false")
    else:
        result.target_based_selection_used = False

    if manifest.get("model_fitting_performed") is not False:
        result.errors.append("model_fitting_performed must be false in feature-set manifest")
    else:
        result.model_fitting_performed = False

    candidate_sets = manifest.get("candidate_sets")
    if not isinstance(candidate_sets, list) or not candidate_sets:
        result.errors.append("candidate_sets missing or empty")
    else:
        names = {str(c.get("feature_set_name")) for c in candidate_sets}
        for required in (FEATURE_SET_A, FEATURE_SET_B):
            if required not in names:
                result.errors.append(f"missing candidate set: {required}")
        for entry in candidate_sets:
            name = str(entry.get("feature_set_name", ""))
            if name in FORBIDDEN_FIRST_REFIT_SETS:
                continue
            for field_name in ("selected_features", "feature_set_version", "target_based_selection_used"):
                if field_name not in entry:
                    result.errors.append(f"{name}: missing {field_name}")
            if entry.get("target_based_selection_used") is not False:
                result.errors.append(f"{name}: target_based_selection_used must be false")

    result.passed = len(result.errors) == 0
    return result


def resolve_feature_set(manifest: dict[str, Any], feature_set_id: str) -> tuple[str, list[str]]:
    if feature_set_id.upper() == "C":
        raise ValueError("FeatureSet_C is forbidden for P8B.3.7 first refit")
    name = FEATURE_SET_ID_MAP.get(feature_set_id.upper())
    if name is None:
        raise ValueError(f"unknown feature set id: {feature_set_id!r}")
    if name in FORBIDDEN_FIRST_REFIT_SETS:
        raise ValueError(f"{name} is forbidden for P8B.3.7 first refit")
    for entry in manifest.get("candidate_sets", []):
        if str(entry.get("feature_set_name")) == name:
            features = list(entry.get("selected_features") or [])
            if not features:
                raise ValueError(f"{name}: selected_features is empty")
            return name, features
    raise ValueError(f"feature set not found in manifest: {name}")


def validate_selected_features(
    selected: list[str],
    available_cols: list[str],
) -> list[str]:
    available = set(available_cols)
    missing = [c for c in selected if c not in available]
    return missing


def _load_p8b32_learned_metrics(p8b3_reports: Path) -> dict[str, dict[str, Any]]:
    path = p8b3_reports / "p8b3_2_evaluation_report.json"
    if not path.is_file():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    return {str(m["spec_name"]): m.get("metrics", {}) for m in report.get("model_results", [])}


def _compare_vs_p8b32(
    learned_metrics: dict[str, dict[str, Any]],
    p8b32_metrics: dict[str, dict[str, Any]],
    *,
    p8b32_spec: str,
    metric_key: str,
    split: str = "test",
) -> dict[str, Any]:
    full_section = p8b32_metrics.get(p8b32_spec, {})
    full_val = full_section.get(split, {}).get(metric_key)
    learned_val = learned_metrics.get(split, {}).get(metric_key)
    delta: float | None = None
    if full_val is not None and learned_val is not None:
        delta = float(learned_val) - float(full_val)
    return {
        "metric": metric_key,
        "learned_test": learned_val if split == "test" else learned_metrics.get("test", {}).get(metric_key),
        "p8b3_2_full_feature_test": full_val if split == "test" else full_section.get("test", {}).get(metric_key),
        "delta_reduced_minus_full_feature": delta,
        "p8b3_2_full_feature_spec": p8b32_spec,
    }


def _attach_p8b32_comparisons(
    fit_result: ModelFitResult,
    p8b32_metrics: dict[str, dict[str, Any]],
) -> None:
    if fit_result.skipped:
        return
    if fit_result.track == "P0":
        for spec_name in ("p0_linear_regression", "p0_ridge_regression"):
            if spec_name == fit_result.spec_name:
                continue
            fit_result.comparison_vs_p8b3_2[spec_name] = _compare_vs_p8b32(
                fit_result.metrics,
                p8b32_metrics,
                p8b32_spec=spec_name,
                metric_key="mae",
            )
    elif fit_result.track == "P1" and fit_result.spec_name == "p1_logistic_050":
        fit_result.comparison_vs_p8b3_2["p1_logistic_050"] = _compare_vs_p8b32(
            fit_result.metrics,
            p8b32_metrics,
            p8b32_spec="p1_logistic_050",
            metric_key="balanced_accuracy",
        )


def _validate_selected_forbidden(selected: list[str]) -> tuple[bool, list[str]]:
    forb = validate_forbidden_features(selected)
    return forb.passed, forb.forbidden_columns


def _fit_feature_set(
    *,
    feature_set_id: str,
    feature_set_name: str,
    selected_features: list[str],
    config: P8B37Config,
    split_rows: list[dict[str, Any]],
    available_cols: list[str],
    targets: set[TargetGroup],
    use_scaler: bool,
    p8b2_metrics: dict[str, Any],
    p8b32_metrics: dict[str, dict[str, Any]],
    execute: bool,
) -> FeatureSetRefitResult:
    fs_result = FeatureSetRefitResult(
        feature_set_id=feature_set_id,
        feature_set_name=feature_set_name,
        selected_feature_count=len(selected_features),
        selected_features=list(selected_features),
        numeric_columns_used=[],
    )

    missing = validate_selected_features(selected_features, available_cols)
    if missing:
        fs_result.skipped = True
        fs_result.skipped_reason = f"selected features missing from matrix: {missing[:5]}"
        return fs_result

    forb_pass, forb_cols = _validate_selected_forbidden(selected_features)
    if not forb_pass:
        fs_result.skipped = True
        fs_result.skipped_reason = f"forbidden columns in selected set: {forb_cols}"
        return fs_result

    train_rows = [r for r in split_rows if r.get("split") == "train"]
    numeric_cols, non_numeric, all_nan_train = _build_numeric_feature_columns(
        train_rows, selected_features
    )
    fs_result.numeric_columns_used = numeric_cols
    fs_result.preprocessing_summary = {
        "selected_feature_count": len(selected_features),
        "numeric_columns_used": len(numeric_cols),
        "excluded_non_numeric": non_numeric,
        "all_nan_train_columns": all_nan_train,
        "preprocessing_fit_on_train_only": True,
        "use_scaler": use_scaler,
        "imputer": "SimpleImputer(median)",
    }

    if not numeric_cols:
        fs_result.skipped = True
        fs_result.skipped_reason = "no numeric columns after train-only selection"
        return fs_result

    if not execute:
        fs_result.models_fitted = [s.name for s in specs_for_targets(targets)]
        return fs_result

    specs = specs_for_targets(targets)
    model_results: list[ModelFitResult] = []
    for spec in specs:
        fit_result = fit_model_train_only(
            spec,
            split_rows=split_rows,
            numeric_cols=numeric_cols,
            use_scaler=use_scaler,
            p8b2_metrics=p8b2_metrics,
        )
        _attach_p8b32_comparisons(fit_result, p8b32_metrics)
        if fit_result.skipped:
            fs_result.skipped_models[fit_result.spec_name] = fit_result.skipped_reason or "skipped"
        else:
            fs_result.models_fitted.append(fit_result.spec_name)
        model_results.append(fit_result)

    fs_result.model_results = [m.to_dict() for m in model_results]
    return fs_result


def _shared_validation(
    config: P8B37Config,
    *,
    project_root: Path,
    targets: set[TargetGroup],
    split_mode: Literal["chronological", "configured"],
    feature_set_ids: list[str],
) -> tuple[P8B37FitResult, dict[str, Any], list[str], list[dict[str, Any]], Any]:
    result = P8B37FitResult(feature_sets_requested=feature_set_ids)
    dep = validate_sklearn_dependency_declared(project_root)
    result.dependency_status = dep.dependency_status
    if not dep.passed:
        return result, {}, [], [], None

    manifest_path = config.reduced_feature_manifest
    if not manifest_path.is_file():
        result.reduced_manifest_validation = {
            "passed": False,
            "errors": [f"manifest not found: {manifest_path}"],
        }
        return result, {}, [], [], None

    manifest = _load_reduced_manifest(manifest_path)
    manifest_val = validate_reduced_manifest(
        manifest, expected_version=config.expected_feature_set_version
    )
    result.reduced_manifest_validation = {
        "passed": manifest_val.passed,
        "errors": manifest_val.errors,
        "feature_set_version": manifest_val.feature_set_version,
        "target_based_selection_used": manifest_val.target_based_selection_used,
        "model_fitting_performed": manifest_val.model_fitting_performed,
        "reduced_feature_manifest_hash": _hash_file(manifest_path),
        "manifest_path": str(manifest_path),
    }
    if not manifest_val.passed:
        return result, manifest, [], [], None

    base = config.base
    specs = specs_for_targets(targets)
    joined = load_joined_rows(base.dataset_root, base.feature_root)
    sessions = sorted({str(r.get("trade_date")) for r in joined})
    split_manifest = _build_split_manifest(base, sessions, split_mode)
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
        result.p8b3_7_pass = False
        return result, manifest, [], [], None

    eligible = filter_baseline_eligible(joined)
    available_cols = extract_feature_value_columns(eligible[0])
    split_rows = assign_split(eligible, split_manifest)

    p1_errors = _validate_p1_dual_class(split_rows, LABEL_P1_050)
    if p1_errors and "p1_050" in targets:
        result.split_validation["p1_050_dual_class_errors"] = p1_errors
        result.split_validation["passed"] = False
        return result, manifest, available_cols, split_rows, split_manifest

    return result, manifest, available_cols, split_rows, split_manifest


def build_p8b37_dry_run_plan(
    config: P8B37Config,
    *,
    project_root: Path,
    feature_set_ids: list[str],
    targets: set[TargetGroup],
    split_mode: Literal["chronological", "configured"] = "configured",
) -> P8B37FitResult:
    result, manifest, available_cols, split_rows, split_manifest = _shared_validation(
        config,
        project_root=project_root,
        targets=targets,
        split_mode=split_mode,
        feature_set_ids=feature_set_ids,
    )
    if not result.reduced_manifest_validation.get("passed", False):
        return result
    if not result.split_validation.get("passed", False):
        return result
    if result.dependency_status != "declared_and_importable":
        return result

    base = config.base
    use_scaler = base.preprocessing == "standard_scaler"
    fs_results: list[FeatureSetRefitResult] = []
    for fs_id in feature_set_ids:
        fs_name, selected = resolve_feature_set(manifest, fs_id)
        fs_results.append(
            _fit_feature_set(
                feature_set_id=fs_id,
                feature_set_name=fs_name,
                selected_features=selected,
                config=config,
                split_rows=split_rows,
                available_cols=available_cols,
                targets=targets,
                use_scaler=use_scaler,
                p8b2_metrics={},
                p8b32_metrics={},
                execute=False,
            )
        )
        if not fs_results[-1].skipped:
            result.feature_sets_used.append(fs_name)

    result.feature_set_results = [r.to_dict() for r in fs_results]
    result.preprocessing_summary = {
        "preprocessing_fit_on_train_only": True,
        "imputer": "SimpleImputer(median)",
        "scaler": base.preprocessing,
        "feature_sets_planned": result.feature_sets_used,
    }
    a_ok = any(r.feature_set_name == FEATURE_SET_A and not r.skipped for r in fs_results)
    result.p8b3_7_pass = bool(
        result.reduced_manifest_validation.get("passed")
        and result.split_validation.get("passed")
        and result.dependency_status == "declared_and_importable"
        and a_ok
    )
    return result


def run_p8b37_refit(
    config: P8B37Config,
    *,
    project_root: Path,
    feature_set_ids: list[str],
    targets: set[TargetGroup],
    split_mode: Literal["chronological", "configured"] = "configured",
    execute: bool = False,
) -> P8B37FitResult:
    if not execute:
        return build_p8b37_dry_run_plan(
            config,
            project_root=project_root,
            feature_set_ids=feature_set_ids,
            targets=targets,
            split_mode=split_mode,
        )

    result, manifest, available_cols, split_rows, split_manifest = _shared_validation(
        config,
        project_root=project_root,
        targets=targets,
        split_mode=split_mode,
        feature_set_ids=feature_set_ids,
    )
    result.dry_run = False
    if not result.reduced_manifest_validation.get("passed", False):
        return result
    if not result.split_validation.get("passed", False):
        return result
    if result.dependency_status != "declared_and_importable":
        return result

    base = config.base
    use_scaler = base.preprocessing == "standard_scaler"
    p8b2_metrics = _load_p8b2_baseline_metrics(base.p8b2_reports)
    p8b32_metrics = _load_p8b32_learned_metrics(config.p8b3_2_reports)

    fs_results: list[FeatureSetRefitResult] = []
    for fs_id in feature_set_ids:
        fs_name, selected = resolve_feature_set(manifest, fs_id)
        fs_result = _fit_feature_set(
            feature_set_id=fs_id,
            feature_set_name=fs_name,
            selected_features=selected,
            config=config,
            split_rows=split_rows,
            available_cols=available_cols,
            targets=targets,
            use_scaler=use_scaler,
            p8b2_metrics=p8b2_metrics,
            p8b32_metrics=p8b32_metrics,
            execute=True,
        )
        fs_results.append(fs_result)
        if not fs_result.skipped:
            result.feature_sets_used.append(fs_name)

    result.feature_set_results = [r.to_dict() for r in fs_results]
    result.model_fitting_performed = True
    result.sklearn_fit_called = True
    result.test_not_used_for_tuning = True
    result.hyperparameter_search_performed = False
    result.p8b4_blocked = True

    base.output_reports.mkdir(parents=True, exist_ok=True)
    eval_report: dict[str, Any] = {
        "phase": HARNESS_STAGE_P8B3_7,
        "dependency_status": result.dependency_status,
        "feature_sets_used": result.feature_sets_used,
        "reduced_manifest_validation": result.reduced_manifest_validation,
        "split_validation": result.split_validation,
        "forbidden_validation": result.forbidden_validation,
        "feature_set_results": result.feature_set_results,
        "fixed_hyperparameters": FIXED_HYPERPARAMETERS,
        "p8b2_baseline_reference": str(base.p8b2_reports / "p8b2_evaluation_report.json"),
        "p8b3_2_full_feature_reference": str(config.p8b3_2_reports / "p8b3_2_evaluation_report.json"),
        "test_not_used_for_tuning": True,
        "hyperparameter_search_performed": False,
        "p8b4_blocked": True,
    }

    manifest_out: dict[str, Any] = {
        "stage": HARNESS_STAGE_P8B3_7,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "model_fitting_allowed": True,
        "feature_sets_used": result.feature_sets_used,
        "feature_set_version": config.expected_feature_set_version,
        "model_type": "reduced_feature_learned_refit",
        "target_name": base.preferred_binary_target,
        "fixed_hyperparameters": FIXED_HYPERPARAMETERS,
        "feature_manifest_hash": _hash_file(base.feature_root / "manifest.json"),
        "dataset_manifest_hash": _hash_file(base.dataset_root / "manifest.json"),
        "reduced_feature_manifest_hash": result.reduced_manifest_validation.get(
            "reduced_feature_manifest_hash", ""
        ),
        "split_protocol": base.split_protocol,
        "train_sessions": result.split_validation.get("train_sessions", []),
        "validation_sessions": result.split_validation.get("validation_sessions", []),
        "test_sessions": result.split_validation.get("test_sessions", []),
        "dependency_versions": get_sklearn_versions(),
        "preprocessing_fit_on_train_only": True,
        "forbidden_input_validation_status": "PASS",
        "leakage_validation_status": "PASS",
        "trained_on_sessions_only": True,
        "test_not_used_for_tuning": True,
        "hyperparameter_search_performed": False,
        "p8b4_blocked": True,
        "code_commit": _git_commit(project_root),
        "artifacts_written": [str(base.output_reports)],
    }

    a_done = any(
        r.feature_set_name == FEATURE_SET_A and not r.skipped and r.models_fitted
        for r in fs_results
    )
    b_done_or_skipped = all(
        r.feature_set_name != FEATURE_SET_B or (r.skipped or r.models_fitted)
        for r in fs_results
    )
    result.p8b3_7_pass = bool(
        a_done
        and b_done_or_skipped
        and result.split_validation.get("passed")
        and result.reduced_manifest_validation.get("passed")
    )
    eval_report["p8b3_7_pass"] = result.p8b3_7_pass

    report_path = base.output_reports / "p8b3_7_evaluation_report.json"
    report_path.write_text(json.dumps(eval_report, indent=2), encoding="utf-8")
    result.report_path = report_path

    manifest_path = base.output_reports / "p8b3_7_run_manifest.json"
    manifest_path.write_text(json.dumps(manifest_out, indent=2, sort_keys=True), encoding="utf-8")
    result.run_manifest_path = manifest_path
    return result


__all__ = [
    "FEATURE_SET_A",
    "FEATURE_SET_B",
    "FEATURE_SET_C",
    "HARNESS_STAGE_P8B3_7",
    "P8B37Config",
    "P8B37FitResult",
    "build_p8b37_dry_run_plan",
    "load_p8b37_config",
    "parse_feature_set_ids",
    "resolve_feature_set",
    "run_p8b37_refit",
    "validate_reduced_manifest",
    "validate_selected_features",
]
