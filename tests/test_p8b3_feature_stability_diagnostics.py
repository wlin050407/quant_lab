"""Tests for ML-P8B.3.5 feature stability diagnostics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quant_lab.ml.harness.feature_diagnostics import (
    DiagnosticThresholds,
    compute_correlation_diagnostics,
    compute_missingness_by_feature,
    compute_missingness_by_group,
    compute_nan_inf_summary,
    compute_train_constant_stats,
    load_p8b35_config,
    run_p8b35_diagnostics,
    select_numeric_columns,
)
from quant_lab.ml.harness.p8b2_eval import SessionSplitManifest
from quant_lab.ml.harness.p8b3_feature_selection import (
    build_all_proposals,
    propose_feature_set_a,
)
from quant_lab.ml.harness.validators import validate_forbidden_features

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _row(
    trade_date: str,
    *,
    spot: float = 5000.0,
    pin: float = 0.5,
    extra: dict[str, float | None] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "trade_date": trade_date,
        "split": None,
        "features.spot_t": spot,
        "features.pin_score_t": pin,
        "labels.baseline_target_eligible": True,
    }
    if extra:
        for k, v in extra.items():
            data[f"features.{k}"] = v
    return data


def _train_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sid in ("2024-01-05", "2024-01-19", "2024-02-13"):
        for j in range(5):
            rows.append(_row(sid, spot=5000.0 + j, pin=0.1 * j))
    return rows


def test_missingness_by_feature() -> None:
    rows = _train_rows()
    cols = ["spot_t", "pin_score_t", "missing_col"]
    for r in rows:
        r["features.missing_col"] = None
    miss = compute_missingness_by_feature(rows, cols)
    assert miss["spot_t"] == 0.0
    assert miss["missing_col"] == 1.0


def test_group_missingness_aggregation() -> None:
    miss = {"spot_t": 0.1, "pin_score_t": 0.3}
    groups = compute_missingness_by_group(miss)
    assert "deterministic" in groups or "unknown" in groups


def test_constant_and_near_constant_detection() -> None:
    rows = _train_rows()
    for r in rows:
        r["features.const_col"] = 1.0
        r["features.near_const"] = 1.0 if hash(str(r)) % 20 else 2.0
    stats = compute_train_constant_stats(rows, ["const_col", "near_const", "spot_t"])
    assert stats["const_col"]["constant_train"] is True
    assert stats["spot_t"]["constant_train"] is False


def test_nan_inf_summary() -> None:
    rows = _train_rows()
    rows[0]["features.spot_t"] = None
    summary = compute_nan_inf_summary(rows, ["spot_t", "pin_score_t"], split_name="train")
    assert summary["nan_count"] >= 1


def test_correlation_cluster_detection_train_only() -> None:
    rows = _train_rows()
    for i, r in enumerate(rows):
        r["features.corr_a"] = float(i)
        r["features.corr_b"] = float(i) * 1.001
    diag = compute_correlation_diagnostics(rows, ["corr_a", "corr_b"], threshold=0.95)
    assert diag["high_correlation_pairs"]


def test_train_only_missingness_selection() -> None:
    train = _train_rows()
    val = [_row("2024-11-01", extra={"sparse_feat": 1.0}) for _ in range(3)]
    for r in train:
        r["features.sparse_feat"] = None
    for r in val:
        r.setdefault("features.sparse_feat", 1.0)
    miss_train = compute_missingness_by_feature(train, ["sparse_feat"])
    assert miss_train["sparse_feat"] == 1.0
    miss_val = compute_missingness_by_feature(val, ["sparse_feat"])
    assert miss_val["sparse_feat"] == 0.0


def test_forbidden_target_column_rejected() -> None:
    result = validate_forbidden_features(["spot_t", "labels.close_distance_to_primary_pin_em"])
    assert not result.passed


def test_feature_set_manifest_creation() -> None:
    rows = _train_rows()
    cols, _ = select_numeric_columns(rows, ["spot_t", "pin_score_t"])
    split = SessionSplitManifest(
        train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03"],
        split_mode="configured",
    )
    thr = DiagnosticThresholds(
        train_missingness_drop_threshold=0.80,
        near_constant_same_value_threshold=0.99,
        correlation_prune_threshold=0.95,
    )
    manifest = propose_feature_set_a(
        cols,
        rows,
        thresholds=thr,
        feature_set_version="p8b3_reduced_features_v0_proposal",
        split_manifest=split,
    )
    assert manifest["feature_set_name"] == "FeatureSet_A_core_stable"
    assert manifest["target_based_selection_used"] is False
    assert manifest["exclusion_reasons"] is not None
    assert manifest["train_sessions_used_for_selection"] == split.train_sessions


def test_build_all_three_sets() -> None:
    rows = _train_rows()
    cols, non_num = select_numeric_columns(rows, ["spot_t", "pin_score_t"])
    split = SessionSplitManifest(
        train_sessions=["2024-01-05", "2024-01-19", "2024-02-13"],
        validation_sessions=["2024-11-01"],
        test_sessions=["2025-01-03"],
        split_mode="configured",
    )
    proposals = build_all_proposals(
        numeric_columns=cols,
        non_numeric_columns=non_num,
        train_rows=rows,
        thresholds=DiagnosticThresholds(),
        feature_set_version="p8b3_reduced_features_v0_proposal",
        split_manifest=split,
    )
    assert len(proposals) == 3
    names = {p["feature_set_name"] for p in proposals}
    assert "FeatureSet_A_core_stable" in names
    assert "FeatureSet_C_diagnostic_full_pruned" in names


def test_no_sklearn_fit_in_modules() -> None:
    for mod_path in (
        _PROJECT_ROOT / "src/quant_lab/ml/harness/feature_diagnostics.py",
        _PROJECT_ROOT / "src/quant_lab/ml/harness/p8b3_feature_selection.py",
    ):
        text = mod_path.read_text(encoding="utf-8")
        assert "import sklearn" not in text
        assert "GridSearchCV" not in text
        assert "RandomizedSearchCV" not in text
        assert "def fit(" not in text


def test_dry_run_cli() -> None:
    cfg = _PROJECT_ROOT / "config/ml/p8b3_feature_stability_diagnostics.yaml"
    if not (_PROJECT_ROOT / "artifacts/features/pit_features_baseline_v1_1_validation").is_dir():
        pytest.skip("feature artifacts not present")
    proc = subprocess.run(
        [
            sys.executable,
            str(_PROJECT_ROOT / "scripts/run_feature_stability_diagnostics.py"),
            "--config",
            str(cfg),
            "--dry-run",
        ],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_run_manifest_flags(tmp_path: Path) -> None:
    cfg_path = _PROJECT_ROOT / "config/ml/p8b3_feature_stability_diagnostics.yaml"
    if not (_PROJECT_ROOT / "artifacts/features/pit_features_baseline_v1_1_validation").is_dir():
        pytest.skip("feature artifacts not present")
    config = load_p8b35_config(cfg_path)
    config.output_reports = tmp_path / "out"
    result = run_p8b35_diagnostics(config, project_root=_PROJECT_ROOT, dry_run=False)
    assert result.p8b3_5_pass
    assert not result.model_fitting_performed
    assert not result.target_based_selection_used
    manifest = json.loads((config.output_reports / "reduced_feature_set_manifest.json").read_text())
    assert manifest["target_based_selection_used"] is False
    assert manifest["model_fitting_performed"] is False
