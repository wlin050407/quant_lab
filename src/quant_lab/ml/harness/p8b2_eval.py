"""ML-P8B.2 model-free baseline evaluation orchestration."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml

from quant_lab.ml.datasets.join import strict_join_batches
from quant_lab.ml.features.p8b1_build import load_label_dicts
from quant_lab.ml.features.p8b1_validation import extract_feature_value_columns
from quant_lab.ml.harness.baselines import (
    ClassPriorBaseline,
    ConstantNotNearBaseline,
    MajorityClassBaseline,
    ModelFreeBaseline,
    TrainMeanBaseline,
    TrainMedianBaseline,
    TrainPriorProbabilityBaseline,
    ZeroEmBaseline,
)
from quant_lab.ml.harness.manifests import HARNESS_STAGE_P8B2, RunManifest, validate_run_manifest
from quant_lab.ml.harness.metrics import (
    compute_p0_regression_metrics,
    compute_p1_binary_metrics,
    compute_p2_multiclass_metrics,
)
from quant_lab.ml.harness.splits import (
    detect_row_level_random_split,
    validate_session_split,
)
from quant_lab.ml.harness.validators import validate_forbidden_features
from quant_lab.ml.schemas import BASELINE_LABEL_SCHEMA_VERSION, LABEL_SCHEMA_VERSION

log = logging.getLogger(__name__)

SplitMode = Literal["chronological", "configured"]

LABEL_P0 = "labels.close_distance_to_primary_pin_em"
LABEL_P1_050 = "labels.close_near_primary_pin_050"
LABEL_P1_025 = "labels.close_near_primary_pin_025"
LABEL_P2_050 = "labels.close_above_below_primary_pin_050"
LABEL_P2_025 = "labels.close_above_below_primary_pin_025"
LABEL_BASELINE_ELIGIBLE = "labels.baseline_target_eligible"
LABEL_ZONE_LOC = "labels.close_location_vs_current_zone"
LABEL_ZONE_INSIDE = "labels.close_inside_current_zone"


@dataclass
class P8B2EvalConfig:
    version: str
    dataset_root: Path
    feature_root: Path
    input_reports: Path
    output_reports: Path
    baseline_label_schema_version: str
    split_protocol: str
    train_sessions_count: int
    validation_sessions_count: int
    test_sessions_count: int
    preferred_binary_target: str
    sensitivity_binary_target: str
    model_fitting_allowed: bool
    configured_train_sessions: list[str] = field(default_factory=list)
    configured_validation_sessions: list[str] = field(default_factory=list)
    configured_test_sessions: list[str] = field(default_factory=list)


@dataclass
class SessionSplitManifest:
    train_sessions: list[str]
    validation_sessions: list[str]
    test_sessions: list[str]
    split_mode: SplitMode

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_sessions": self.train_sessions,
            "validation_sessions": self.validation_sessions,
            "test_sessions": self.test_sessions,
            "split_mode": self.split_mode,
        }


@dataclass
class P8B2EvalResult:
    dry_run: bool = False
    p8b2_pass: bool = False
    split_validation: dict[str, Any] = field(default_factory=dict)
    forbidden_validation: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    run_manifest_path: Path | None = None
    report_path: Path | None = None
    model_fitting_occurred: bool = False


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _hash_manifest_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_p8b2_config(path: Path) -> P8B2EvalConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    split = raw.get("split") or {}
    return P8B2EvalConfig(
        version=str(raw.get("version", "p8b2-model-free")),
        dataset_root=Path(raw["input_dataset"]),
        feature_root=Path(raw["input_features"]),
        input_reports=Path(raw.get("input_reports", "artifacts/reports/pit_features_baseline_v1_1_validation")),
        output_reports=Path(raw["output_reports"]),
        baseline_label_schema_version=str(raw.get("baseline_label_schema_version", BASELINE_LABEL_SCHEMA_VERSION)),
        split_protocol=str(raw.get("split_protocol", "session_grouped")),
        train_sessions_count=int(split.get("train_sessions", 11)),
        validation_sessions_count=int(split.get("validation_sessions", 3)),
        test_sessions_count=int(split.get("test_sessions", 5)),
        preferred_binary_target=str(raw.get("preferred_binary_target", "close_near_primary_pin_050")),
        sensitivity_binary_target=str(raw.get("sensitivity_binary_target", "close_near_primary_pin_025")),
        model_fitting_allowed=bool(raw.get("model_fitting_allowed", False)),
        configured_train_sessions=[str(d) for d in split.get("configured_train_sessions") or []],
        configured_validation_sessions=[str(d) for d in split.get("configured_validation_sessions") or []],
        configured_test_sessions=[str(d) for d in split.get("configured_test_sessions") or []],
    )


def load_feature_dicts(feature_root: Path) -> list[dict[str, Any]]:
    path = feature_root / "features.parquet"
    if not path.is_file():
        shard_dir = feature_root / "per_date"
        rows: list[dict[str, Any]] = []
        for p in sorted(shard_dir.glob("*.parquet")):
            rows.extend(pd.read_parquet(p).to_dict(orient="records"))
        return rows
    return pd.read_parquet(path).to_dict(orient="records")


def load_joined_rows(dataset_root: Path, feature_root: Path) -> list[dict[str, Any]]:
    labels = load_label_dicts(dataset_root)
    features = load_feature_dicts(feature_root)
    joined = strict_join_batches(labels, features)
    return [j.to_dict() for j in joined]


def build_chronological_split(
    sessions: list[str],
    *,
    train_n: int,
    val_n: int,
    test_n: int,
) -> SessionSplitManifest:
    unique = sorted(set(sessions))
    if len(unique) != train_n + val_n + test_n:
        raise ValueError(
            f"session count {len(unique)} != train+val+test ({train_n}+{val_n}+{test_n})"
        )
    return SessionSplitManifest(
        train_sessions=unique[:train_n],
        validation_sessions=unique[train_n : train_n + val_n],
        test_sessions=unique[train_n + val_n :],
        split_mode="chronological",
    )


def build_configured_split(config: P8B2EvalConfig) -> SessionSplitManifest:
    return SessionSplitManifest(
        train_sessions=list(config.configured_train_sessions),
        validation_sessions=list(config.configured_validation_sessions),
        test_sessions=list(config.configured_test_sessions),
        split_mode="configured",
    )


def assign_split(rows: list[dict[str, Any]], split: SessionSplitManifest) -> list[dict[str, Any]]:
    train = set(split.train_sessions)
    val = set(split.validation_sessions)
    test = set(split.test_sessions)
    out: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        sid = str(r.get("trade_date", r.get("session_id")))
        if sid in train:
            r["split"] = "train"
        elif sid in val:
            r["split"] = "validation"
        elif sid in test:
            r["split"] = "test"
        else:
            r["split"] = "unassigned"
        out.append(r)
    return out


def _is_true(val: Any) -> bool:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return False
    return bool(val)


def _is_non_null(val: Any) -> bool:
    if val is None:
        return False
    return not (isinstance(val, float) and np.isnan(val))


def filter_baseline_eligible(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if _is_true(r.get(LABEL_BASELINE_ELIGIBLE))]


def filter_zone_eligible(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if _is_non_null(r.get(LABEL_ZONE_LOC))]


def _rows_for_split(rows: list[dict[str, Any]], split_name: str) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("split") == split_name]


def _extract_y(rows: list[dict[str, Any]], key: str) -> list[Any]:
    return [r.get(key) for r in rows]


def evaluate_p0_baselines(
    rows: list[dict[str, Any]],
    *,
    baselines: list[ModelFreeBaseline],
) -> dict[str, Any]:
    train_rows = _rows_for_split(rows, "train")
    y_train = _extract_y(train_rows, LABEL_P0)
    for b in baselines:
        b.fit_from_train(y_train)

    result: dict[str, Any] = {}
    for split_name in ("train", "validation", "test"):
        split_rows = _rows_for_split(rows, split_name)
        y_true = np.asarray(_extract_y(split_rows, LABEL_P0), dtype=float)
        result[split_name] = {}
        for b in baselines:
            y_pred = b.predict(len(split_rows))
            result[split_name][b.name] = compute_p0_regression_metrics(y_true, y_pred)
    train_stats = {}
    for b in baselines:
        if hasattr(b, "compute_train_priors"):
            train_stats[b.name] = b.compute_train_priors()  # type: ignore[attr-defined]
        elif isinstance(b, TrainMedianBaseline):
            train_stats[b.name] = {"median_em": b._median}
        elif isinstance(b, TrainMeanBaseline):
            train_stats[b.name] = {"mean_em": b._mean}
    result["train_priors"] = train_stats
    return result


def evaluate_p1_baselines(
    rows: list[dict[str, Any]],
    *,
    label_key: str,
    baselines: list[ModelFreeBaseline],
) -> dict[str, Any]:
    train_rows = _rows_for_split(rows, "train")
    y_train = _extract_y(train_rows, label_key)
    for b in baselines:
        b.fit_from_train(y_train)

    result: dict[str, Any] = {"label_key": label_key}
    priors: dict[str, Any] = {}
    for b in baselines:
        if isinstance(b, TrainPriorProbabilityBaseline):
            priors[b.name] = b.compute_train_priors()
        elif isinstance(b, MajorityClassBaseline):
            priors[b.name] = {"majority": b._majority}
        elif isinstance(b, ConstantNotNearBaseline):
            priors[b.name] = {"constant": False}

    result["train_priors"] = priors
    for split_name in ("train", "validation", "test"):
        split_rows = _rows_for_split(rows, split_name)
        y_true = np.asarray(_extract_y(split_rows, label_key), dtype=bool)
        result[split_name] = {}
        for b in baselines:
            y_pred = b.predict(len(split_rows))
            y_score = None
            if isinstance(b, TrainPriorProbabilityBaseline):
                y_score = b.predict_proba_near(len(split_rows))
            result[split_name][b.name] = compute_p1_binary_metrics(y_true, y_pred, y_score)
    return result


def evaluate_p2_baselines(
    rows: list[dict[str, Any]],
    *,
    label_key: str,
    baselines: list[ModelFreeBaseline],
) -> dict[str, Any]:
    train_rows = _rows_for_split(rows, "train")
    y_train = _extract_y(train_rows, label_key)
    for b in baselines:
        b.fit_from_train(y_train)

    result: dict[str, Any] = {"label_key": label_key}
    priors: dict[str, Any] = {}
    for b in baselines:
        if isinstance(b, ClassPriorBaseline):
            priors[b.name] = b.compute_train_priors()
        elif isinstance(b, MajorityClassBaseline):
            priors[b.name] = {"majority": str(b._majority)}

    result["train_priors"] = priors
    for split_name in ("train", "validation", "test"):
        split_rows = _rows_for_split(rows, split_name)
        y_true = _extract_y(split_rows, label_key)
        result[split_name] = {}
        for b in baselines:
            y_pred = b.predict(len(split_rows))
            result[split_name][b.name] = compute_p2_multiclass_metrics(y_true, y_pred)
    return result


def evaluate_zone_secondary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    zone_rows = filter_zone_eligible(rows)
    result: dict[str, Any] = {
        "zone_eligible_row_count": len(zone_rows),
        "total_row_count": len(rows),
    }
    if not zone_rows:
        result["skipped_reason"] = "no_zone_eligible_rows"
        return result

    loc_counts = Counter(str(r.get(LABEL_ZONE_LOC)) for r in zone_rows)
    result["close_location_distribution"] = dict(loc_counts)

    train_zone = _rows_for_split(zone_rows, "train")
    majority = MajorityClassBaseline()
    majority.fit_from_train(_extract_y(train_zone, LABEL_ZONE_LOC))

    for split_name in ("train", "validation", "test"):
        split_zone = _rows_for_split(zone_rows, split_name)
        if not split_zone:
            result[f"{split_name}_zone"] = {"row_count": 0}
            continue
        y_loc = _extract_y(split_zone, LABEL_ZONE_LOC)
        y_pred = majority.predict(len(split_zone))
        result[f"{split_name}_zone"] = {
            "row_count": len(split_zone),
            "majority_class_baseline_train_prior": compute_p2_multiclass_metrics(y_loc, y_pred),
        }
    return result


def validate_joined_forbidden_features(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate feature matrix columns only (labels are targets, not inputs)."""
    all_feature_cols: set[str] = set()
    for row in rows:
        all_feature_cols.update(extract_feature_value_columns(row))
    result = validate_forbidden_features(sorted(all_feature_cols))
    return {
        "forbidden_input_pass": result.passed,
        "forbidden_columns": result.forbidden_columns,
        "warning_columns": result.warning_columns,
        "feature_column_count": len(all_feature_cols),
    }


def build_dry_run_plan(config: P8B2EvalConfig) -> dict[str, Any]:
    ds_ok = config.dataset_root.is_dir()
    feat_ok = (config.feature_root / "features.parquet").is_file() or (
        config.feature_root / "per_date"
    ).is_dir()
    label_count = len(load_label_dicts(config.dataset_root)) if ds_ok else 0
    feat_count = len(load_feature_dicts(config.feature_root)) if feat_ok else 0
    sessions = sorted({str(r.get("trade_date")) for r in load_label_dicts(config.dataset_root)}) if ds_ok else []
    return {
        "dry_run": True,
        "dataset_root": str(config.dataset_root),
        "feature_root": str(config.feature_root),
        "dataset_exists": ds_ok,
        "feature_exists": feat_ok,
        "label_row_count": label_count,
        "feature_row_count": feat_count,
        "sessions": len(sessions),
        "output_reports": str(config.output_reports),
        "model_fitting_allowed": config.model_fitting_allowed,
    }


def evaluate_p8b2_gates(
    *,
    split_pass: bool,
    forbidden_pass: bool,
    p0_done: bool,
    p1_done: bool,
    model_fitting: bool,
) -> bool:
    return split_pass and forbidden_pass and p0_done and p1_done and not model_fitting


def run_p8b2_evaluation(
    config: P8B2EvalConfig,
    *,
    split_mode: SplitMode = "chronological",
    dry_run: bool = False,
) -> P8B2EvalResult:
    result = P8B2EvalResult(dry_run=dry_run)
    if dry_run:
        return result

    if config.model_fitting_allowed:
        raise ValueError("model_fitting_allowed must be false for P8B.2")

    joined = load_joined_rows(config.dataset_root, config.feature_root)
    sessions = sorted({str(r.get("trade_date")) for r in joined})

    if split_mode == "configured" and config.configured_train_sessions:
        split_manifest = build_configured_split(config)
    else:
        split_manifest = build_chronological_split(
            sessions,
            train_n=config.train_sessions_count,
            val_n=config.validation_sessions_count,
            test_n=config.test_sessions_count,
        )

    rows = assign_split(joined, split_manifest)
    split_val = validate_session_split(
        rows,
        train_sessions=split_manifest.train_sessions,
        validation_sessions=split_manifest.validation_sessions,
        test_sessions=split_manifest.test_sessions,
        target_key=LABEL_P1_050,
    )
    row_level_errors = detect_row_level_random_split(rows)
    result.split_validation = {
        **split_val.to_dict(),
        **split_manifest.to_dict(),
        "row_level_random_split_errors": row_level_errors,
        "row_level_random_split_pass": len(row_level_errors) == 0,
    }
    if not split_val.passed or row_level_errors:
        log.error("split validation FAIL: %s", split_val.errors + row_level_errors)
        return result

    forb = validate_joined_forbidden_features(joined)
    result.forbidden_validation = forb
    if not forb.get("forbidden_input_pass"):
        log.error("forbidden input FAIL: %s", forb.get("forbidden_columns"))
        return result

    eligible = filter_baseline_eligible(rows)
    log.info("baseline eligible rows: %d / %d", len(eligible), len(rows))

    p0_baselines: list[ModelFreeBaseline] = [
        ZeroEmBaseline(),
        TrainMedianBaseline(),
        TrainMeanBaseline(),
    ]
    p1_baselines: list[ModelFreeBaseline] = [
        MajorityClassBaseline(),
        ConstantNotNearBaseline(),
        TrainPriorProbabilityBaseline(),
    ]
    p2_baselines: list[ModelFreeBaseline] = [
        MajorityClassBaseline(),
        ClassPriorBaseline(),
    ]

    metrics: dict[str, Any] = {
        "input_summary": {
            "joined_row_count": len(joined),
            "baseline_eligible_count": len(eligible),
            "feature_column_count": len(extract_feature_value_columns(joined[0])) if joined else 0,
            "sessions": len(sessions),
        },
        "p0_close_distance_to_primary_pin_em": evaluate_p0_baselines(eligible, baselines=p0_baselines),
        "p1_close_near_primary_pin_050": evaluate_p1_baselines(
            eligible, label_key=LABEL_P1_050, baselines=p1_baselines
        ),
        "p1_close_near_primary_pin_025_sensitivity": evaluate_p1_baselines(
            eligible, label_key=LABEL_P1_025, baselines=p1_baselines
        ),
        "p2_close_above_below_primary_pin_050": evaluate_p2_baselines(
            eligible, label_key=LABEL_P2_050, baselines=p2_baselines
        ),
        "p2_close_above_below_primary_pin_025": evaluate_p2_baselines(
            eligible, label_key=LABEL_P2_025, baselines=p2_baselines
        ),
        "zone_secondary": evaluate_zone_secondary(rows),
        "model_fitting_occurred": False,
        "sklearn_fit_called": False,
    }
    result.metrics = metrics

    ds_hash = _hash_manifest_file(config.dataset_root / "manifest.json")
    feat_hash = _hash_manifest_file(config.feature_root / "manifest.json")
    run_manifest = RunManifest(
        run_id=hashlib.sha256(f"p8b2-{datetime.now(tz=UTC).isoformat()}".encode()).hexdigest()[:32],
        stage=HARNESS_STAGE_P8B2,
        created_at=datetime.now(tz=UTC).isoformat(),
        code_commit=_git_commit(),
        dataset_manifest_hash=ds_hash,
        feature_manifest_hash=feat_hash,
        label_schema_version=LABEL_SCHEMA_VERSION,
        baseline_label_schema_version=config.baseline_label_schema_version,
        target_name=config.preferred_binary_target,
        split_protocol=config.split_protocol,
        train_sessions=split_manifest.train_sessions,
        validation_sessions=split_manifest.validation_sessions,
        test_sessions=split_manifest.test_sessions,
        metrics_version="p8b0-v1",
        leakage_validation_status="PASS",
        forbidden_input_validation_status="PASS",
        model_type="model_free_baseline",
        model_fitting_allowed=False,
        artifacts_written=[str(config.output_reports)],
        notes="ML-P8B.2 model-free baseline evaluation — no learned model fitting",
    )
    validate_run_manifest(run_manifest)

    config.output_reports.mkdir(parents=True, exist_ok=True)
    manifest_path = config.output_reports / "p8b2_run_manifest.json"
    manifest_path.write_text(run_manifest.to_json(), encoding="utf-8")
    result.run_manifest_path = manifest_path

    eval_report = {
        "phase": HARNESS_STAGE_P8B2,
        "split": split_manifest.to_dict(),
        "split_validation": result.split_validation,
        "forbidden_validation": result.forbidden_validation,
        "metrics": metrics,
        "p8b2_pass": False,
        "artifacts_not_committed": True,
    }
    report_json = config.output_reports / "p8b2_evaluation_report.json"
    report_json.write_text(json.dumps(eval_report, indent=2), encoding="utf-8")
    result.report_path = report_json

    result.model_fitting_occurred = False
    result.p8b2_pass = evaluate_p8b2_gates(
        split_pass=split_val.passed and not row_level_errors,
        forbidden_pass=bool(forb.get("forbidden_input_pass")),
        p0_done=bool(metrics.get("p0_close_distance_to_primary_pin_em")),
        p1_done=bool(metrics.get("p1_close_near_primary_pin_050")),
        model_fitting=False,
    )
    eval_report["p8b2_pass"] = result.p8b2_pass
    report_json.write_text(json.dumps(eval_report, indent=2), encoding="utf-8")
    return result


def _fmt_metrics_block(metrics: dict[str, Any] | None, indent: int = 0) -> str:
    if not metrics:
        return "  " * indent + "- (none)\n"
    prefix = "  " * indent
    lines: list[str] = []
    for key, val in metrics.items():
        if isinstance(val, dict):
            lines.append(f"{prefix}- **{key}**:")
            lines.append(_fmt_metrics_block(val, indent + 1))
        elif isinstance(val, float):
            lines.append(f"{prefix}- {key}: {val:.6f}")
        else:
            lines.append(f"{prefix}- {key}: {val}")
    return "\n".join(lines) + "\n"


def render_p8b2_markdown_report(
    report_payload: dict[str, Any],
    config: P8B2EvalConfig,
) -> str:
    """Render human-readable P8B.2 evaluation report."""
    split = report_payload.get("split") or {}
    split_val = report_payload.get("split_validation") or {}
    forb = report_payload.get("forbidden_validation") or {}
    metrics = report_payload.get("metrics") or {}
    input_summary = metrics.get("input_summary") or {}
    p8b2_pass = report_payload.get("p8b2_pass", False)

    lines = [
        "# ML-P8B.2 Model-Free Baseline Evaluation Report",
        "",
        "## Stage",
        "",
        "- Phase: **ML-P8B.2**",
        "- `model_fitting_allowed`: **false**",
        "- `model_type`: **model_free_baseline**",
        "",
        "## Input Summary",
        "",
        f"- Dataset: `{config.dataset_root}`",
        f"- Features: `{config.feature_root}`",
        f"- Joined rows: {input_summary.get('joined_row_count')}",
        f"- Baseline-eligible rows: {input_summary.get('baseline_eligible_count')}",
        f"- Feature columns: {input_summary.get('feature_column_count')}",
        f"- Sessions: {input_summary.get('sessions')}",
        "",
        "## Split Sessions",
        "",
        f"- Mode: `{split.get('split_mode')}`",
        f"- Train ({len(split.get('train_sessions', []))}): {', '.join(split.get('train_sessions', []))}",
        f"- Validation ({len(split.get('validation_sessions', []))}): {', '.join(split.get('validation_sessions', []))}",
        f"- Test ({len(split.get('test_sessions', []))}): {', '.join(split.get('test_sessions', []))}",
        "",
        "## Split Validation",
        "",
        f"- PASS: **{split_val.get('passed')}**",
        f"- Row-level random split PASS: **{split_val.get('row_level_random_split_pass')}**",
        f"- Train rows: {split_val.get('train_row_count')} | Val: {split_val.get('validation_row_count')} | Test: {split_val.get('test_row_count')}",
        "",
        "## Forbidden Input Validation",
        "",
        f"- PASS: **{forb.get('forbidden_input_pass')}**",
        f"- Feature columns checked: {forb.get('feature_column_count')}",
        f"- Forbidden columns found: {forb.get('forbidden_columns') or 'none'}",
        "",
        "## P0 Regression (`close_distance_to_primary_pin_em`)",
        "",
        _fmt_metrics_block(metrics.get("p0_close_distance_to_primary_pin_em")),
        "## P1 Binary Preferred (`close_near_primary_pin_050`)",
        "",
        _fmt_metrics_block(metrics.get("p1_close_near_primary_pin_050")),
        "## P1 Sensitivity (`close_near_primary_pin_025`)",
        "",
        _fmt_metrics_block(metrics.get("p1_close_near_primary_pin_025_sensitivity")),
        "## P2 Optional Directional",
        "",
        "### `close_above_below_primary_pin_050`",
        "",
        _fmt_metrics_block(metrics.get("p2_close_above_below_primary_pin_050")),
        "### `close_above_below_primary_pin_025`",
        "",
        _fmt_metrics_block(metrics.get("p2_close_above_below_primary_pin_025")),
        "## Zone Secondary Metrics",
        "",
        _fmt_metrics_block(metrics.get("zone_secondary")),
        "## Model Fitting Attestation",
        "",
        "- **No learned model fitting was performed.**",
        "- **No sklearn `.fit()` was called.**",
        "- **No trading signal was generated.**",
        "",
        "## Gate Status",
        "",
        f"- P8B.2 PASS: **{p8b2_pass}**",
        "- P8B.3 (learned model fitting): **BLOCKED**",
        "",
        "## Next Stage",
        "",
        "Proceed only to **ML-P8B.3 Approval Review — Learned Model Fitting Gate** after explicit approval.",
        "",
    ]
    return "\n".join(lines)
