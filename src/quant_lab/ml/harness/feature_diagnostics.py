"""ML-P8B.3.5 feature stability diagnostics (unsupervised, train-only selection)."""

from __future__ import annotations

import json
import logging
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from quant_lab.ml.features.p8b1_validation import (
    extract_feature_value_columns,
    validate_feature_matrix_forbidden,
    validate_feature_timestamp_leakage,
)
from quant_lab.ml.features.schemas import FEATURE_CATALOG_BY_NAME
from quant_lab.ml.harness.p8b2_eval import (
    SessionSplitManifest,
    assign_split,
    filter_baseline_eligible,
    load_joined_rows,
)
from quant_lab.ml.harness.splits import detect_row_level_random_split, validate_session_split
from quant_lab.ml.harness.validators import validate_forbidden_features

log = logging.getLogger(__name__)

HARNESS_STAGE_P8B3_5 = "ML-P8B.3.5"


def feature_group(name: str) -> str:
    spec = FEATURE_CATALOG_BY_NAME.get(name)
    return spec.group if spec else "unknown"


def is_zone_dependent(name: str) -> bool:
    if name in {"zone_low_t", "zone_high_t", "zone_center_t"}:
        return True
    return any(
        name.startswith(p)
        for p in ("distance_spot_to_zone_", "zone_width_", "spot_position_in_zone")
    )


def _is_numeric_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)):
        return not (isinstance(val, float) and (np.isnan(val) or np.isinf(val)))
    return False


def select_numeric_columns(
    train_rows: list[dict[str, Any]],
    feat_cols: list[str],
) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    non_numeric: list[str] = []
    for col in feat_cols:
        vals = [row.get(f"features.{col}") for row in train_rows]
        if all(_is_numeric_value(v) or v is None for v in vals):
            numeric.append(col)
        else:
            non_numeric.append(col)
    return numeric, non_numeric


@dataclass
class DiagnosticThresholds:
    train_missingness_drop_threshold: float = 0.80
    near_constant_same_value_threshold: float = 0.99
    correlation_prune_threshold: float = 0.95


@dataclass
class P8B35Config:
    version: str
    feature_root: Path
    label_root: Path
    input_reports: Path
    output_reports: Path
    feature_set_version: str
    baseline_label_schema_version: str
    split_protocol: str
    selection_scope: str
    target_based_selection_allowed: bool
    model_fitting_allowed: bool
    thresholds: DiagnosticThresholds
    configured_train_sessions: list[str] = field(default_factory=list)
    configured_validation_sessions: list[str] = field(default_factory=list)
    configured_test_sessions: list[str] = field(default_factory=list)


@dataclass
class P8B35Result:
    dry_run: bool = True
    p8b3_5_pass: bool = False
    model_fitting_performed: bool = False
    target_based_selection_used: bool = False
    diagnostics_path: Path | None = None
    proposal_manifest_path: Path | None = None
    run_manifest_path: Path | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("diagnostics_path", "proposal_manifest_path", "run_manifest_path"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        return data


def load_p8b35_config(path: Path) -> P8B35Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    split = raw.get("split") or {}
    thr = raw.get("thresholds") or {}
    return P8B35Config(
        version=str(raw.get("version", "p8b3-feature-stability-diagnostics")),
        feature_root=Path(raw["input_features"]),
        label_root=Path(raw["input_labels"]),
        input_reports=Path(raw.get("input_reports", "")),
        output_reports=Path(raw["output_reports"]),
        feature_set_version=str(raw.get("feature_set_version", "p8b3_reduced_features_v0_proposal")),
        baseline_label_schema_version=str(raw.get("baseline_label_schema_version", "1.1.0-draft")),
        split_protocol=str(raw.get("split_protocol", "chronological_11_3_5")),
        selection_scope=str(raw.get("selection_scope", "train_only_unsupervised")),
        target_based_selection_allowed=bool(raw.get("target_based_selection_allowed", False)),
        model_fitting_allowed=bool(raw.get("model_fitting_allowed", False)),
        thresholds=DiagnosticThresholds(
            train_missingness_drop_threshold=float(thr.get("train_missingness_drop_threshold", 0.80)),
            near_constant_same_value_threshold=float(thr.get("near_constant_same_value_threshold", 0.99)),
            correlation_prune_threshold=float(thr.get("correlation_prune_threshold", 0.95)),
        ),
        configured_train_sessions=[str(d) for d in split.get("configured_train_sessions") or []],
        configured_validation_sessions=[str(d) for d in split.get("configured_validation_sessions") or []],
        configured_test_sessions=[str(d) for d in split.get("configured_test_sessions") or []],
    )


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


def _hash_file(path: Path) -> str:
    if not path.is_file():
        return ""
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _matrix_for_columns(rows: list[dict[str, Any]], columns: list[str]) -> np.ndarray:
    if not columns:
        return np.empty((len(rows), 0))
    return np.array(
        [[_to_float(row.get(f"features.{c}")) for c in columns] for row in rows],
        dtype=float,
    )


def _to_float(val: Any) -> float:
    if val is None:
        return np.nan
    if isinstance(val, bool):
        return float(val)
    if isinstance(val, (int, float)):
        v = float(val)
        return np.nan if (np.isnan(v) or np.isinf(v)) else v
    return np.nan


def compute_missingness_by_feature(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, float]:
    if not rows:
        return {c: 1.0 for c in columns}
    mat = _matrix_for_columns(rows, columns)
    return {col: float(np.isnan(mat[:, j]).mean()) for j, col in enumerate(columns)}


def compute_missingness_by_group(
    missingness: dict[str, float],
) -> dict[str, float]:
    group_vals: dict[str, list[float]] = defaultdict(list)
    for name, rate in missingness.items():
        group_vals[feature_group(name)].append(rate)
    return {g: float(np.mean(v)) if v else 1.0 for g, v in sorted(group_vals.items())}


def compute_train_constant_stats(
    train_rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for col in columns:
        vals = [_to_float(r.get(f"features.{col}")) for r in train_rows]
        finite = [v for v in vals if np.isfinite(v)]
        n = len(vals)
        if n == 0:
            stats[col] = {
                "all_nan_train": True,
                "constant_train": True,
                "near_constant_train": True,
                "top_value_ratio_train": 1.0,
                "unique_count_train": 0,
            }
            continue
        nan_rate = 1.0 - len(finite) / n
        if not finite:
            stats[col] = {
                "all_nan_train": True,
                "constant_train": True,
                "near_constant_train": True,
                "top_value_ratio_train": 1.0,
                "unique_count_train": 0,
            }
            continue
        counts = Counter(finite)
        top_ratio = counts.most_common(1)[0][1] / len(finite)
        unique = len(set(finite))
        stats[col] = {
            "all_nan_train": nan_rate >= 1.0,
            "constant_train": unique <= 1,
            "near_constant_train": top_ratio >= 0.99,
            "top_value_ratio_train": float(top_ratio),
            "unique_count_train": unique,
        }
    return stats


def compute_nan_inf_summary(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    split_name: str,
) -> dict[str, Any]:
    mat = _matrix_for_columns(rows, columns)
    if mat.size == 0:
        return {"split": split_name, "nan_count": 0, "inf_count": 0, "finite_ratio": 0.0}
    nan_count = int(np.isnan(mat).sum())
    inf_count = int(np.isinf(mat).sum())
    total = mat.size
    finite_ratio = float(np.isfinite(mat).sum() / total) if total else 0.0
    return {
        "split": split_name,
        "nan_count": nan_count,
        "inf_count": inf_count,
        "finite_ratio": finite_ratio,
    }


def _impute_median_train(mat: np.ndarray) -> np.ndarray:
    """Column median imputation using train statistics only (no sklearn .fit())."""
    out = mat.copy()
    for j in range(out.shape[1]):
        col = out[:, j]
        finite = col[np.isfinite(col)]
        fill = float(np.median(finite)) if finite.size else 0.0
        col[~np.isfinite(col)] = fill
        out[:, j] = col
    return out


def compute_correlation_diagnostics(
    train_rows: list[dict[str, Any]],
    columns: list[str],
    *,
    threshold: float,
) -> dict[str, Any]:
    if len(columns) < 2:
        return {
            "threshold": threshold,
            "high_correlation_pairs": [],
            "correlation_clusters": [],
        }
    mat = _matrix_for_columns(train_rows, columns)
    imp = _impute_median_train(mat)
    if imp.shape[0] < 2:
        return {"threshold": threshold, "high_correlation_pairs": [], "correlation_clusters": []}
    corr = np.corrcoef(imp, rowvar=False)
    pairs: list[dict[str, Any]] = []
    n = len(columns)
    adj: dict[int, set[int]] = defaultdict(set)
    for i in range(n):
        for j in range(i + 1, n):
            if not np.isfinite(corr[i, j]):
                continue
            if abs(float(corr[i, j])) >= threshold:
                pairs.append(
                    {
                        "feature_a": columns[i],
                        "feature_b": columns[j],
                        "correlation": float(corr[i, j]),
                    }
                )
                adj[i].add(j)
                adj[j].add(i)

    visited: set[int] = set()
    clusters: list[list[str]] = []
    for i in range(n):
        if i in visited:
            continue
        stack = [i]
        component: list[int] = []
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            stack.extend(adj[node] - visited)
        if len(component) > 1:
            clusters.append([columns[k] for k in sorted(component)])

    return {
        "threshold": threshold,
        "high_correlation_pairs": pairs,
        "correlation_clusters": clusters,
        "train_rows_used": len(train_rows),
    }


def compute_distribution_monitoring(
    train_rows: list[dict[str, Any]],
    val_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, Any]:
    monitoring: dict[str, Any] = {"selection_basis": "monitoring_only", "features": {}}
    for col in columns:
        per_split: dict[str, Any] = {}
        train_std: float | None = None
        for split_name, rows in (
            ("train", train_rows),
            ("validation", val_rows),
            ("test", test_rows),
        ):
            vals = np.array([_to_float(r.get(f"features.{col}")) for r in rows], dtype=float)
            finite = vals[np.isfinite(vals)]
            if finite.size:
                per_split[split_name] = {
                    "mean": float(np.mean(finite)),
                    "std": float(np.std(finite)),
                    "median": float(np.median(finite)),
                    "p25": float(np.percentile(finite, 25)),
                    "p75": float(np.percentile(finite, 75)),
                    "missingness": float(np.isnan(vals).mean()),
                }
                if split_name == "train":
                    train_std = per_split[split_name]["std"]
            else:
                per_split[split_name] = {
                    "mean": None,
                    "std": None,
                    "median": None,
                    "p25": None,
                    "p75": None,
                    "missingness": 1.0,
                }
        if train_std and train_std > 0:
            for other in ("validation", "test"):
                tm = per_split.get("train", {}).get("mean")
                om = per_split.get(other, {}).get("mean")
                if tm is not None and om is not None:
                    per_split[f"mean_diff_over_train_std_{other}"] = float((om - tm) / train_std)
        monitoring["features"][col] = per_split
    return monitoring


def compute_session_stability(
    train_rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, Any]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in train_rows:
        by_session[str(row.get("trade_date"))].append(row)

    feature_session_missing: dict[str, list[float]] = {c: [] for c in columns}
    group_session_missing: dict[str, list[float]] = defaultdict(list)

    for _sid, sess_rows in sorted(by_session.items()):
        miss = compute_missingness_by_feature(sess_rows, columns)
        for col, rate in miss.items():
            feature_session_missing[col].append(rate)
        group_miss = compute_missingness_by_group(miss)
        for g, rate in group_miss.items():
            group_session_missing[g].append(rate)

    unstable_features: list[dict[str, Any]] = []
    for col, rates in feature_session_missing.items():
        if len(rates) < 2:
            continue
        std = float(np.std(rates))
        if std > 0.25:
            unstable_features.append(
                {"feature": col, "missingness_std_across_train_sessions": std}
            )

    return {
        "train_session_count": len(by_session),
        "feature_group_stability_by_session": {
            g: {"missingness_mean": float(np.mean(r)), "missingness_std": float(np.std(r))}
            for g, r in sorted(group_session_missing.items())
            if r
        },
        "unstable_train_features": unstable_features[:50],
    }


def compute_timestamp_freshness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    margins: list[float] = []
    has_metadata = False
    for row in rows:
        as_of_raw = row.get("as_of_timestamp")
        src_raw = row.get("source_timestamp_max")
        if not as_of_raw or not src_raw:
            continue
        has_metadata = True
        try:
            as_of = datetime.fromisoformat(str(as_of_raw))
            src = datetime.fromisoformat(str(src_raw))
            margins.append((as_of - src).total_seconds())
        except ValueError:
            continue
    if not has_metadata:
        return {
            "status": "source timestamp freshness unavailable in current artifact format",
            "rows_with_metadata": 0,
        }
    arr = np.array(margins, dtype=float)
    return {
        "status": "available",
        "rows_with_metadata": len(margins),
        "margin_seconds_mean": float(np.mean(arr)) if arr.size else None,
        "margin_seconds_median": float(np.median(arr)) if arr.size else None,
        "margin_seconds_min": float(np.min(arr)) if arr.size else None,
        "max_source_timestamp_delta_seconds": float(-np.min(margins)) if arr.size else None,
    }


def build_diagnostics_payload(
    *,
    config: P8B35Config,
    split_manifest: SessionSplitManifest,
    all_columns: list[str],
    numeric_columns: list[str],
    train_rows: list[dict[str, Any]],
    val_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    eligibility_summary: dict[str, Any],
) -> dict[str, Any]:
    thr = config.thresholds
    miss_train = compute_missingness_by_feature(train_rows, numeric_columns)
    miss_val = compute_missingness_by_feature(val_rows, numeric_columns)
    miss_test = compute_missingness_by_feature(test_rows, numeric_columns)
    constant_stats = compute_train_constant_stats(train_rows, numeric_columns)

    return {
        "stage": HARNESS_STAGE_P8B3_5,
        "feature_set_version": config.feature_set_version,
        "selection_scope": config.selection_scope,
        "target_based_selection_used": False,
        "model_fitting_performed": False,
        "eligibility_summary": eligibility_summary,
        "feature_column_count_raw": len(all_columns),
        "numeric_feature_count": len(numeric_columns),
        "missingness_by_feature": {
            "train": miss_train,
            "validation_monitoring_only": miss_val,
            "test_monitoring_only": miss_test,
        },
        "missingness_by_feature_group": {
            "train": compute_missingness_by_group(miss_train),
            "validation_monitoring_only": compute_missingness_by_group(miss_val),
            "test_monitoring_only": compute_missingness_by_group(miss_test),
        },
        "missingness_by_split": {
            "train": float(np.mean(list(miss_train.values()))) if miss_train else 1.0,
            "validation_monitoring_only": float(np.mean(list(miss_val.values()))) if miss_val else 1.0,
            "test_monitoring_only": float(np.mean(list(miss_test.values()))) if miss_test else 1.0,
        },
        "missingness_by_session": {
            sid: compute_missingness_by_feature(
                [r for r in train_rows if str(r.get("trade_date")) == sid],
                numeric_columns,
            )
            for sid in split_manifest.train_sessions
        },
        "constant_near_constant_train": constant_stats,
        "nan_inf_summary": [
            compute_nan_inf_summary(train_rows, numeric_columns, split_name="train"),
            compute_nan_inf_summary(val_rows, numeric_columns, split_name="validation_monitoring_only"),
            compute_nan_inf_summary(test_rows, numeric_columns, split_name="test_monitoring_only"),
        ],
        "correlation_diagnostics": compute_correlation_diagnostics(
            train_rows,
            numeric_columns,
            threshold=thr.correlation_prune_threshold,
        ),
        "split_drift_monitoring": compute_distribution_monitoring(
            train_rows, val_rows, test_rows, numeric_columns
        ),
        "session_stability_train": compute_session_stability(train_rows, numeric_columns),
        "timestamp_freshness": compute_timestamp_freshness(train_rows + val_rows + test_rows),
        "zone_dependent_features": [c for c in numeric_columns if is_zone_dependent(c)],
        "thresholds": asdict(thr),
        "split_manifest": split_manifest.to_dict(),
    }


def run_p8b35_diagnostics(
    config: P8B35Config,
    *,
    project_root: Path,
    dry_run: bool = False,
) -> P8B35Result:
    result = P8B35Result(dry_run=dry_run)
    result.target_based_selection_used = False
    result.model_fitting_performed = False

    if not config.feature_root.is_dir():
        log.error("feature root missing: %s", config.feature_root)
        return result
    if not config.label_root.is_dir():
        log.error("label root missing: %s", config.label_root)
        return result

    joined = load_joined_rows(config.label_root, config.feature_root)
    eligible = filter_baseline_eligible(joined)
    eligibility_summary = {
        "joined_rows": len(joined),
        "baseline_eligible_rows": len(eligible),
        "labels_used_for": "row_alignment_and_eligibility_counts_only",
    }

    split_manifest = SessionSplitManifest(
        train_sessions=list(config.configured_train_sessions),
        validation_sessions=list(config.configured_validation_sessions),
        test_sessions=list(config.configured_test_sessions),
        split_mode="configured",
    )
    split_rows = assign_split(eligible, split_manifest)
    split_val = validate_session_split(
        split_rows,
        train_sessions=split_manifest.train_sessions,
        validation_sessions=split_manifest.validation_sessions,
        test_sessions=split_manifest.test_sessions,
    )
    row_level = detect_row_level_random_split(split_rows)
    feat_cols = extract_feature_value_columns(eligible[0]) if eligible else []
    forb = validate_forbidden_features(feat_cols)

    result.summary = {
        "joined_rows": len(joined),
        "baseline_eligible_rows": len(eligible),
        "feature_columns": len(feat_cols),
        "split_validation_pass": split_val.passed and not row_level,
        "forbidden_input_pass": forb.passed,
        "train_sessions": split_manifest.train_sessions,
        "validation_sessions": split_manifest.validation_sessions,
        "test_sessions": split_manifest.test_sessions,
    }

    if not split_val.passed or row_level or not forb.passed:
        log.error("preflight failed: split=%s forbidden=%s", split_val.errors, forb.forbidden_columns)
        return result

    if dry_run:
        result.p8b3_5_pass = True
        result.summary["dry_run"] = True
        result.summary["output_reports"] = str(config.output_reports)
        return result

    train_rows = [r for r in split_rows if r.get("split") == "train"]
    val_rows = [r for r in split_rows if r.get("split") == "validation"]
    test_rows = [r for r in split_rows if r.get("split") == "test"]
    numeric_columns, non_numeric = select_numeric_columns(train_rows, feat_cols)

    from quant_lab.ml.harness.p8b3_feature_selection import build_all_proposals  # noqa: PLC0415

    diagnostics = build_diagnostics_payload(
        config=config,
        split_manifest=split_manifest,
        all_columns=feat_cols,
        numeric_columns=numeric_columns,
        train_rows=train_rows,
        val_rows=val_rows,
        test_rows=test_rows,
        eligibility_summary=eligibility_summary,
    )

    proposals = build_all_proposals(
        numeric_columns=numeric_columns,
        non_numeric_columns=non_numeric,
        train_rows=train_rows,
        thresholds=config.thresholds,
        feature_set_version=config.feature_set_version,
        split_manifest=split_manifest,
    )
    diagnostics["reduced_feature_set_proposals"] = proposals

    config.output_reports.mkdir(parents=True, exist_ok=True)
    diag_path = config.output_reports / "p8b3_5_feature_diagnostics.json"
    diag_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
    result.diagnostics_path = diag_path

    proposal_manifest = {
        "feature_set_version": config.feature_set_version,
        "selection_rules": {
            "selection_scope": config.selection_scope,
            "target_based_selection_allowed": config.target_based_selection_allowed,
            "thresholds": asdict(config.thresholds),
        },
        "thresholds": asdict(config.thresholds),
        "candidate_sets": proposals,
        "excluded_non_numeric_columns": non_numeric,
        "train_sessions_used_for_selection": split_manifest.train_sessions,
        "validation_sessions_monitoring_only": split_manifest.validation_sessions,
        "test_sessions_monitoring_only": split_manifest.test_sessions,
        "code_commit": _git_commit(),
        "input_feature_manifest_hash": _hash_file(config.feature_root / "manifest.json"),
        "input_dataset_manifest_hash": _hash_file(config.label_root / "manifest.json"),
        "target_based_selection_used": False,
        "model_fitting_performed": False,
    }
    prop_path = config.output_reports / "reduced_feature_set_manifest.json"
    prop_path.write_text(json.dumps(proposal_manifest, indent=2, sort_keys=True), encoding="utf-8")
    result.proposal_manifest_path = prop_path

    leakage = validate_feature_timestamp_leakage(
        [r for r in split_rows if r.get("split") in ("train", "validation", "test")]
    )
    forb_row = validate_feature_matrix_forbidden(eligible[0]) if eligible else {"forbidden_input_pass": False}

    run_manifest = {
        "stage": HARNESS_STAGE_P8B3_5,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "model_fitting_allowed": False,
        "model_type": "feature_stability_diagnostics_only",
        "target_name": None,
        "split_protocol": config.split_protocol,
        "train_sessions": split_manifest.train_sessions,
        "validation_sessions": split_manifest.validation_sessions,
        "test_sessions": split_manifest.test_sessions,
        "forbidden_input_validation_status": "PASS" if forb_row.get("forbidden_input_pass") else "FAIL",
        "leakage_validation_status": "PASS" if leakage.timestamp_leakage_pass else "FAIL",
        "target_based_selection_used": False,
        "model_fitting_performed": False,
        "code_commit": _git_commit(),
        "input_feature_manifest_hash": _hash_file(config.feature_root / "manifest.json"),
        "input_dataset_manifest_hash": _hash_file(config.label_root / "manifest.json"),
        "artifacts_written": [str(config.output_reports)],
        "feature_set_version": config.feature_set_version,
    }
    run_path = config.output_reports / "p8b3_5_run_manifest.json"
    run_path.write_text(json.dumps(run_manifest, indent=2, sort_keys=True), encoding="utf-8")
    result.run_manifest_path = run_path

    result.p8b3_5_pass = True
    result.summary.update(
        {
            "numeric_features": len(numeric_columns),
            "proposal_sets": {p["feature_set_name"]: p["selected_feature_count"] for p in proposals},
        }
    )
    return result


__all__ = [
    "HARNESS_STAGE_P8B3_5",
    "DiagnosticThresholds",
    "P8B35Config",
    "P8B35Result",
    "build_diagnostics_payload",
    "compute_correlation_diagnostics",
    "compute_missingness_by_feature",
    "compute_train_constant_stats",
    "feature_group",
    "is_zone_dependent",
    "load_p8b35_config",
    "run_p8b35_diagnostics",
    "select_numeric_columns",
]
