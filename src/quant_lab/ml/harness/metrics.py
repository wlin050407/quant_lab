"""Metric calculators for ML-P8B harness (synthetic / eval only — no model fitting)."""

from __future__ import annotations

from typing import Any

import numpy as np

P2_CLASSES: tuple[str, ...] = ("below", "near", "above")
METRICS_VERSION = "p8b0-v1"


def _trapz(y: np.ndarray, x: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def _as_float_array(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("expected 1-D array input")
    return arr


def _valid_mask(*arrays: np.ndarray) -> np.ndarray:
    mask = np.ones(arrays[0].shape[0], dtype=bool)
    for arr in arrays:
        mask &= np.isfinite(arr)
    return mask


def _empty_metric_dict(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {"valid_count": 0}
    if extra:
        base.update(extra)
    return base


def compute_p0_regression_metrics(
    y_true: Any,
    y_pred: Any,
    *,
    outlier_threshold_em: float = 3.0,
) -> dict[str, Any]:
    """P0 regression metrics for ``close_distance_to_primary_pin_em``."""
    yt = _as_float_array(y_true)
    yp = _as_float_array(y_pred)
    if yt.shape != yp.shape:
        raise ValueError("y_true and y_pred must have the same shape")
    mask = _valid_mask(yt, yp)
    valid_count = int(mask.sum())
    if valid_count == 0:
        return _empty_metric_dict(
            {
                "mae": None,
                "rmse": None,
                "median_absolute_error": None,
                "sign_accuracy": None,
                "within_0.25_EM_accuracy": None,
                "within_0.50_EM_accuracy": None,
                "outlier_rate": None,
            }
        )
    yt_v = yt[mask]
    yp_v = yp[mask]
    abs_err = np.abs(yt_v - yp_v)
    nonzero = yt_v != 0.0
    sign_acc: float | None
    if nonzero.any():
        sign_acc = float(np.mean(np.sign(yt_v[nonzero]) == np.sign(yp_v[nonzero])))
    else:
        sign_acc = None
    return {
        "valid_count": valid_count,
        "mae": float(np.mean(abs_err)),
        "rmse": float(np.sqrt(np.mean((yt_v - yp_v) ** 2))),
        "median_absolute_error": float(np.median(abs_err)),
        "sign_accuracy": sign_acc,
        "within_0.25_EM_accuracy": float(np.mean(abs_err <= 0.25)),
        "within_0.50_EM_accuracy": float(np.mean(abs_err <= 0.50)),
        "outlier_rate": float(np.mean(abs_err > outlier_threshold_em)),
    }


def _confusion_matrix_binary(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, int]:
    yt = y_true.astype(bool)
    yp = y_pred.astype(bool)
    tn = int(np.sum(~yt & ~yp))
    fp = int(np.sum(~yt & yp))
    fn = int(np.sum(yt & ~yp))
    tp = int(np.sum(yt & yp))
    return {"tn": tn, "fp": fp, "fn": fn, "tp": tp}


def _roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> tuple[float | None, str | None]:
    classes = np.unique(y_true.astype(bool))
    if classes.size < 2:
        return None, "both_classes_required"
    order = np.argsort(-y_score)
    yt = y_true.astype(bool)[order]
    n_pos = int(yt.sum())
    n_neg = int((~yt).sum())
    if n_pos == 0 or n_neg == 0:
        return None, "both_classes_required"
    tps = np.cumsum(yt)
    fps = np.cumsum(~yt)
    tpr = tps / n_pos
    fpr = fps / n_neg
    tpr = np.concatenate([[0.0], tpr, [1.0]])
    fpr = np.concatenate([[0.0], fpr, [1.0]])
    auc = _trapz(tpr, fpr)
    return auc, None


def _pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> tuple[float | None, str | None]:
    classes = np.unique(y_true.astype(bool))
    if classes.size < 2:
        return None, "both_classes_required"
    order = np.argsort(-y_score)
    yt = y_true.astype(bool)[order]
    n_pos = int(yt.sum())
    if n_pos == 0:
        return None, "both_classes_required"
    precision = np.cumsum(yt) / np.arange(1, len(yt) + 1)
    recall = np.cumsum(yt) / n_pos
    recall = np.concatenate([[0.0], recall, [1.0]])
    precision = np.concatenate([[1.0], precision, [precision[-1] if len(precision) else 0.0]])
    auc = _trapz(precision, recall)
    return auc, None


def compute_p1_binary_metrics(
    y_true: Any,
    y_pred_label: Any,
    y_score: Any | None = None,
    *,
    positive_label: bool = True,
) -> dict[str, Any]:
    """P1 binary metrics for near / not_near targets."""
    yt_raw = np.asarray(y_true)
    yp_raw = np.asarray(y_pred_label)
    if yt_raw.shape != yp_raw.shape:
        raise ValueError("y_true and y_pred_label must have the same shape")
    yt = yt_raw.astype(bool)
    yp = yp_raw.astype(bool)
    mask = np.ones(yt.shape[0], dtype=bool)
    for arr in (yt_raw, yp_raw):
        if arr.dtype == object:
            mask &= np.array([v is not None for v in arr], dtype=bool)
        else:
            mask &= np.isfinite(arr.astype(float)) if np.issubdtype(arr.dtype, np.floating) else mask
    valid_count = int(mask.sum())
    if valid_count == 0:
        return _empty_metric_dict(
            {
                "class_distribution": {"near": 0, "not_near": 0, "near_ratio": None},
                "majority_baseline_accuracy": None,
                "balanced_accuracy": None,
                "precision": None,
                "recall": None,
                "f1": None,
                "brier_score": None,
                "roc_auc": None,
                "roc_auc_skipped_reason": "no_valid_rows",
                "pr_auc": None,
                "pr_auc_skipped_reason": "no_valid_rows",
                "confusion_matrix": {"tn": 0, "fp": 0, "fn": 0, "tp": 0},
            }
        )
    yt_v = yt[mask]
    yp_v = yp[mask]
    near_count = int(yt_v.sum())
    not_near_count = int((~yt_v).sum())
    majority = near_count >= not_near_count
    majority_acc = float(np.mean(yp_v == majority))
    cm = _confusion_matrix_binary(yt_v, yp_v)
    tp, fp, fn, tn = cm["tp"], cm["fp"], cm["fn"], cm["tn"]
    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else None
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = float(2 * precision * recall / (precision + recall))
    else:
        f1 = None
    sens = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    spec = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0
    balanced_acc = float((sens + spec) / 2.0)
    brier: float | None = None
    roc_auc: float | None = None
    roc_skip: str | None = None
    pr_auc: float | None = None
    pr_skip: str | None = None
    if y_score is not None:
        ys = _as_float_array(y_score)[mask]
        if np.isfinite(ys).all():
            brier = float(np.mean((ys - yt_v.astype(float)) ** 2))
            roc_auc, roc_skip = _roc_auc(yt_v, ys)
            pr_auc, pr_skip = _pr_auc(yt_v, ys)
    else:
        roc_skip = "scores_not_provided"
        pr_skip = "scores_not_provided"
    return {
        "valid_count": valid_count,
        "class_distribution": {
            "near": near_count,
            "not_near": not_near_count,
            "near_ratio": float(near_count / valid_count),
        },
        "majority_baseline_accuracy": majority_acc,
        "balanced_accuracy": balanced_acc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "brier_score": brier,
        "roc_auc": roc_auc,
        "roc_auc_skipped_reason": roc_skip,
        "pr_auc": pr_auc,
        "pr_auc_skipped_reason": pr_skip,
        "confusion_matrix": cm,
        "positive_label": positive_label,
    }


def compute_p2_multiclass_metrics(
    y_true: Any,
    y_pred_label: Any,
    *,
    classes: tuple[str, ...] = P2_CLASSES,
) -> dict[str, Any]:
    """P2 multiclass metrics for below / near / above."""
    yt = np.asarray(y_true, dtype=object)
    yp = np.asarray(y_pred_label, dtype=object)
    if yt.shape != yp.shape:
        raise ValueError("y_true and y_pred_label must have the same shape")
    mask = np.array([t is not None and p is not None for t, p in zip(yt, yp, strict=True)], dtype=bool)
    valid_count = int(mask.sum())
    if valid_count == 0:
        empty_dist = {c: 0 for c in classes}
        return _empty_metric_dict(
            {
                "class_distribution": empty_dist,
                "macro_f1": None,
                "balanced_accuracy": None,
                "per_class_precision": {c: None for c in classes},
                "per_class_recall": {c: None for c in classes},
                "confusion_matrix": {t: {p: 0 for p in classes} for t in classes},
            }
        )
    yt_v = np.asarray([str(v) for v in yt[mask]])
    yp_v = np.asarray([str(v) for v in yp[mask]])
    dist = {c: int(np.sum(yt_v == c)) for c in classes}
    cm: dict[str, dict[str, int]] = {t: {p: 0 for p in classes} for t in classes}
    for t, p in zip(yt_v, yp_v, strict=True):
        if t in cm and p in cm[t]:
            cm[t][p] += 1
    per_prec: dict[str, float | None] = {}
    per_rec: dict[str, float | None] = {}
    f1s: list[float] = []
    recalls: list[float] = []
    for c in classes:
        tp = cm[c][c]
        fp = sum(cm[t][c] for t in classes if t != c)
        fn = sum(cm[c][p] for p in classes if p != c)
        prec = float(tp / (tp + fp)) if (tp + fp) > 0 else None
        rec = float(tp / (tp + fn)) if (tp + fn) > 0 else None
        per_prec[c] = prec
        per_rec[c] = rec
        if prec is not None and rec is not None and (prec + rec) > 0:
            f1s.append(2 * prec * rec / (prec + rec))
            recalls.append(rec)
        elif rec is not None and (tp + fn) == 0:
            recalls.append(0.0)
    macro_f1 = float(np.mean(f1s)) if f1s else None
    balanced_acc = float(np.mean(recalls)) if recalls else None
    return {
        "valid_count": valid_count,
        "class_distribution": dist,
        "macro_f1": macro_f1,
        "balanced_accuracy": balanced_acc,
        "per_class_precision": per_prec,
        "per_class_recall": per_rec,
        "confusion_matrix": cm,
    }
