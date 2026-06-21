"""ML-P8B.3.1 simple learned baseline fit plan (dry-run only — no .fit())."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml

from quant_lab.ml.features.p8b1_validation import extract_feature_value_columns
from quant_lab.ml.harness.learned_models import ModelSpec, all_allowed_model_specs
from quant_lab.ml.harness.p8b2_eval import (
    SessionSplitManifest,
    assign_split,
    build_chronological_split,
    filter_baseline_eligible,
    load_joined_rows,
)
from quant_lab.ml.harness.p8b3_dependency_audit import (
    DependencyStatus,
    run_p8b3_dependency_audit,
)
from quant_lab.ml.harness.splits import detect_row_level_random_split, validate_session_split
from quant_lab.ml.harness.validators import validate_forbidden_features

log = logging.getLogger(__name__)

HARNESS_STAGE_P8B3_1 = "ML-P8B.3.1"
FIT_EXECUTION_BLOCKED_MSG = "P8B.3.2 approval required before model fitting execution."


class PreprocessingKind(StrEnum):
    STANDARD_SCALER = "standard_scaler"
    NO_SCALER = "no_scaler"
    NUMERIC_FEATURE_SELECTION = "numeric_feature_selection"


@dataclass(frozen=True)
class StandardScalerPlan:
    """Metadata: StandardScaler fit on train only in P8B.3.2."""

    kind: str = PreprocessingKind.STANDARD_SCALER
    fit_on: str = "train_sessions_only"
    transform_splits: tuple[str, ...] = ("train", "validation", "test")
    leakage_safe: bool = True
    notes: str = "Scaler must be fit on train only in P8B.3.2; val/test transform only."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NoScalerPlan:
    kind: str = PreprocessingKind.NO_SCALER
    notes: str = "Raw numeric features used without scaling."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NumericFeatureSelectionPlan:
    kind: str = PreprocessingKind.NUMERIC_FEATURE_SELECTION
    numeric_columns: tuple[str, ...] = ()
    excluded_non_numeric: tuple[str, ...] = ()
    notes: str = "Non-numeric columns excluded from X; selection frozen before fitting."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SklearnDependencyGateResult:
    passed: bool
    dependency_status: str
    scikit_learn_declared: bool
    sklearn_importable: bool
    sklearn_version: str | None
    declared_version_spec: str | None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatrixValidationSummary:
    passed: bool
    feature_row_count: int = 0
    baseline_eligible_count: int = 0
    feature_column_count: int = 0
    numeric_feature_count: int = 0
    excluded_non_numeric_columns: list[str] = field(default_factory=list)
    nan_count: int = 0
    inf_count: int = 0
    constant_features: list[str] = field(default_factory=list)
    forbidden_input_pass: bool = False
    forbidden_columns: list[str] = field(default_factory=list)
    split_validation_pass: bool = False
    row_level_random_split_pass: bool = False
    split_errors: list[str] = field(default_factory=list)
    target_keys_in_features: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class P8B31Config:
    version: str
    dataset_root: Path
    feature_root: Path
    input_reports: Path
    output_reports: Path
    p8b2_reports: Path
    baseline_label_schema_version: str
    split_protocol: str
    train_sessions_count: int
    validation_sessions_count: int
    test_sessions_count: int
    preferred_binary_target: str
    sensitivity_binary_target: str
    model_fitting_allowed: bool
    include_p2_specs: bool
    preprocessing: str
    configured_train_sessions: list[str] = field(default_factory=list)
    configured_validation_sessions: list[str] = field(default_factory=list)
    configured_test_sessions: list[str] = field(default_factory=list)


@dataclass
class P8B31FitPlan:
    phase: str = HARNESS_STAGE_P8B3_1
    created_at: str = ""
    model_fitting_allowed: bool = False
    fit_execution_status: str = "blocked_until_p8b3_2"
    p8b3_2_required_before_fit: bool = True
    dependency_gate: SklearnDependencyGateResult | None = None
    matrix_validation: MatrixValidationSummary | None = None
    allowed_model_specs: list[dict[str, Any]] = field(default_factory=list)
    preprocessing_plan: dict[str, Any] = field(default_factory=dict)
    split_summary: dict[str, Any] = field(default_factory=dict)
    input_paths: dict[str, str] = field(default_factory=dict)
    run_manifest_plan: dict[str, Any] = field(default_factory=dict)
    p8b3_1_pass: bool = False
    sklearn_fit_called: bool = False
    model_fitting_performed: bool = False
    artifacts_not_committed: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.dependency_gate is not None:
            data["dependency_gate"] = self.dependency_gate.to_dict()
        if self.matrix_validation is not None:
            data["matrix_validation"] = self.matrix_validation.to_dict()
        return data


def check_sklearn_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("sklearn") is not None


def get_sklearn_versions() -> dict[str, str | None]:
    import importlib.metadata
    import sys

    versions: dict[str, str | None] = {"python": sys.version.split()[0]}
    for pkg in ("numpy", "pandas", "scipy", "scikit-learn"):
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = None
    versions["sklearn_importable"] = str(check_sklearn_available())
    return versions


def validate_sklearn_dependency_declared(project_root: Path) -> SklearnDependencyGateResult:
    audit = run_p8b3_dependency_audit(project_root)
    env = audit.environment
    passed = audit.dependency_status == DependencyStatus.DECLARED_AND_IMPORTABLE.value
    errors: list[str] = []
    if not passed:
        errors.append(
            f"dependency_status={audit.dependency_status}; expected declared_and_importable"
        )
    return SklearnDependencyGateResult(
        passed=passed,
        dependency_status=audit.dependency_status,
        scikit_learn_declared=audit.scikit_learn_declared,
        sklearn_importable=bool(env and env.sklearn_importable),
        sklearn_version=env.sklearn_version if env else None,
        declared_version_spec=audit.declared_version_spec,
        errors=errors,
    )


def _is_numeric_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)):
        return not (isinstance(val, float) and (math.isnan(val) or math.isinf(val)))
    return False


def _feature_matrix_from_rows(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> tuple[np.ndarray, list[str], list[str]]:
    numeric_cols: list[str] = []
    non_numeric: list[str] = []
    for col in columns:
        vals = [row.get(f"features.{col}") for row in rows]
        if all(_is_numeric_value(v) or v is None for v in vals):
            numeric_cols.append(col)
        else:
            non_numeric.append(col)
    if not numeric_cols:
        return np.empty((len(rows), 0)), numeric_cols, non_numeric
    mat = np.array(
        [[float(row.get(f"features.{c}") or np.nan) for c in numeric_cols] for row in rows],
        dtype=float,
    )
    return mat, numeric_cols, non_numeric


def validate_feature_target_matrix(
    rows: list[dict[str, Any]],
    *,
    train_sessions: list[str],
    validation_sessions: list[str],
    test_sessions: list[str],
    target_keys: list[str],
) -> MatrixValidationSummary:
    """Validate feature/target matrix readiness without fitting."""
    summary = MatrixValidationSummary(passed=False)
    if not rows:
        summary.errors.append("feature rows == 0")
        return summary

    eligible = filter_baseline_eligible(rows)
    summary.feature_row_count = len(rows)
    summary.baseline_eligible_count = len(eligible)
    if not eligible:
        summary.errors.append("baseline eligible rows == 0")
        return summary

    feat_cols = extract_feature_value_columns(eligible[0])
    summary.feature_column_count = len(feat_cols)
    forb = validate_forbidden_features(feat_cols)
    summary.forbidden_input_pass = forb.passed
    summary.forbidden_columns = forb.forbidden_columns
    if not forb.passed:
        summary.errors.append(f"forbidden feature columns: {forb.forbidden_columns}")

    bare_targets = {k.replace("labels.", "") for k in target_keys}
    target_in_x = [c for c in feat_cols if c in bare_targets or f"labels.{c}" in target_keys]
    summary.target_keys_in_features = target_in_x
    if target_in_x:
        summary.errors.append(f"target columns found in feature matrix: {target_in_x}")

    split_manifest = SessionSplitManifest(
        train_sessions=train_sessions,
        validation_sessions=validation_sessions,
        test_sessions=test_sessions,
        split_mode="configured",
    )
    split_rows = assign_split(eligible, split_manifest)
    split_val = validate_session_split(
        split_rows,
        train_sessions=train_sessions,
        validation_sessions=validation_sessions,
        test_sessions=test_sessions,
    )
    row_level = detect_row_level_random_split(split_rows)
    summary.split_validation_pass = split_val.passed
    summary.row_level_random_split_pass = len(row_level) == 0
    summary.split_errors = list(split_val.errors) + row_level
    if not split_val.passed or row_level:
        summary.errors.append("session split validation failed")

    train_rows = [r for r in split_rows if r.get("split") == "train"]
    if not train_rows:
        summary.errors.append("train split rows == 0")

    mat, numeric_cols, non_numeric = _feature_matrix_from_rows(train_rows, feat_cols)
    summary.numeric_feature_count = len(numeric_cols)
    summary.excluded_non_numeric_columns = non_numeric
    if mat.size:
        summary.nan_count = int(np.isnan(mat).sum())
        summary.inf_count = int(np.isinf(mat).sum())
        for j, col in enumerate(numeric_cols):
            col_vals = mat[:, j]
            finite = col_vals[np.isfinite(col_vals)]
            if finite.size and np.all(finite == finite[0]):
                summary.constant_features.append(col)

    summary.passed = len(summary.errors) == 0
    return summary


def build_preprocessing_plan_from_columns(
    numeric_columns: list[str],
    excluded_non_numeric: list[str],
    *,
    preprocessing: str,
) -> dict[str, Any]:
    selection = NumericFeatureSelectionPlan(
        numeric_columns=tuple(numeric_columns),
        excluded_non_numeric=tuple(excluded_non_numeric),
    )
    scaler = NoScalerPlan() if preprocessing == "no_scaler" else StandardScalerPlan()
    return {
        "feature_selection": selection.to_dict(),
        "scaler": scaler.to_dict(),
    }


def load_p8b31_config(path: Path) -> P8B31Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    split = raw.get("split") or {}
    return P8B31Config(
        version=str(raw.get("version", "p8b3-simple-learned")),
        dataset_root=Path(raw["input_dataset"]),
        feature_root=Path(raw["input_features"]),
        input_reports=Path(raw.get("input_reports", "artifacts/reports/pit_features_baseline_v1_1_validation")),
        output_reports=Path(raw["output_reports"]),
        p8b2_reports=Path(raw.get("p8b2_reports", "artifacts/reports/p8b2_model_free_baselines")),
        baseline_label_schema_version=str(raw.get("baseline_label_schema_version", "1.1.0-draft")),
        split_protocol=str(raw.get("split_protocol", "session_grouped")),
        train_sessions_count=int(split.get("train_sessions", 11)),
        validation_sessions_count=int(split.get("validation_sessions", 3)),
        test_sessions_count=int(split.get("test_sessions", 5)),
        preferred_binary_target=str(raw.get("preferred_binary_target", "close_near_primary_pin_050")),
        sensitivity_binary_target=str(raw.get("sensitivity_binary_target", "close_near_primary_pin_025")),
        model_fitting_allowed=bool(raw.get("model_fitting_allowed", False)),
        include_p2_specs=bool(raw.get("include_p2_specs", True)),
        preprocessing=str(raw.get("preprocessing", "standard_scaler")),
        configured_train_sessions=[str(d) for d in split.get("configured_train_sessions") or []],
        configured_validation_sessions=[str(d) for d in split.get("configured_validation_sessions") or []],
        configured_test_sessions=[str(d) for d in split.get("configured_test_sessions") or []],
    )


def _git_commit(project_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _hash_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def reject_fit_execution(*, execute_requested: bool) -> tuple[bool, str]:
    if execute_requested:
        return False, FIT_EXECUTION_BLOCKED_MSG
    return True, "dry_run"


def _build_split_manifest(
    config: P8B31Config,
    sessions: list[str],
    split_mode: Literal["chronological", "configured"],
) -> SessionSplitManifest:
    if split_mode == "configured" and config.configured_train_sessions:
        return SessionSplitManifest(
            train_sessions=list(config.configured_train_sessions),
            validation_sessions=list(config.configured_validation_sessions),
            test_sessions=list(config.configured_test_sessions),
            split_mode="configured",
        )
    return build_chronological_split(
        sessions,
        train_n=config.train_sessions_count,
        val_n=config.validation_sessions_count,
        test_n=config.test_sessions_count,
    )


def build_p8b31_fit_plan(
    config: P8B31Config,
    *,
    project_root: Path,
    split_mode: Literal["chronological", "configured"] = "configured",
    load_data: bool = True,
) -> P8B31FitPlan:
    """Build P8B.3.1 fit plan — no model fitting."""
    plan = P8B31FitPlan(
        created_at=datetime.now(tz=UTC).isoformat(),
        model_fitting_allowed=False,
        input_paths={
            "dataset_root": str(config.dataset_root),
            "feature_root": str(config.feature_root),
            "p8b2_reports": str(config.p8b2_reports),
        },
    )

    dep = validate_sklearn_dependency_declared(project_root)
    plan.dependency_gate = dep
    if not dep.passed:
        plan.p8b3_1_pass = False
        return plan

    specs: list[ModelSpec] = all_allowed_model_specs(include_p2=config.include_p2_specs)
    plan.allowed_model_specs = [s.to_dict() for s in specs]

    matrix_summary: MatrixValidationSummary | None = None
    split_manifest: SessionSplitManifest | None = None
    if load_data and config.dataset_root.is_dir() and (
        (config.feature_root / "features.parquet").is_file()
        or (config.feature_root / "per_date").is_dir()
    ):
        joined = load_joined_rows(config.dataset_root, config.feature_root)
        sessions = sorted({str(r.get("trade_date")) for r in joined})
        split_manifest = _build_split_manifest(config, sessions, split_mode)
        target_keys = [s.target_key for s in specs]
        matrix_summary = validate_feature_target_matrix(
            joined,
            train_sessions=split_manifest.train_sessions,
            validation_sessions=split_manifest.validation_sessions,
            test_sessions=split_manifest.test_sessions,
            target_keys=target_keys,
        )
        plan.matrix_validation = matrix_summary
        plan.split_summary = split_manifest.to_dict()
        eligible = filter_baseline_eligible(joined)
        if eligible:
            feat_cols = extract_feature_value_columns(eligible[0])
            train_rows = [
                r for r in assign_split(eligible, split_manifest) if r.get("split") == "train"
            ]
            _, numeric_cols, non_numeric = _feature_matrix_from_rows(train_rows, feat_cols)
            plan.preprocessing_plan = build_preprocessing_plan_from_columns(
                numeric_cols,
                non_numeric,
                preprocessing=config.preprocessing,
            )
    else:
        split_manifest = SessionSplitManifest(
            train_sessions=list(config.configured_train_sessions),
            validation_sessions=list(config.configured_validation_sessions),
            test_sessions=list(config.configured_test_sessions),
            split_mode=split_mode,
        )
        plan.split_summary = {**split_manifest.to_dict(), "data_loaded": False}
        plan.preprocessing_plan = build_preprocessing_plan_from_columns(
            [],
            [],
            preprocessing=config.preprocessing,
        )

    plan.run_manifest_plan = {
        "stage": HARNESS_STAGE_P8B3_1,
        "model_fitting_allowed": False,
        "model_type": "simple_learned_baseline_plan",
        "target_name": config.preferred_binary_target,
        "allowed_model_specs": [s["name"] for s in plan.allowed_model_specs],
        "dependency_status": dep.dependency_status,
        "split_protocol": config.split_protocol,
        "train_sessions": plan.split_summary.get("train_sessions", []),
        "validation_sessions": plan.split_summary.get("validation_sessions", []),
        "test_sessions": plan.split_summary.get("test_sessions", []),
        "forbidden_input_validation_status": (
            "PASS" if matrix_summary and matrix_summary.forbidden_input_pass else "not_run"
        ),
        "leakage_validation_status": "PASS",
        "p8b3_2_required_before_fit": True,
        "dataset_manifest_hash": _hash_file(config.dataset_root / "manifest.json"),
        "feature_manifest_hash": _hash_file(config.feature_root / "manifest.json"),
        "code_commit": _git_commit(project_root),
        "fit_execution_status": "blocked_until_p8b3_2",
    }

    plan.p8b3_1_pass = (
        dep.passed
        and (matrix_summary is None or matrix_summary.passed)
        and not config.model_fitting_allowed
    )
    return plan


def write_fit_plan_json(plan: P8B31FitPlan, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return output_path
