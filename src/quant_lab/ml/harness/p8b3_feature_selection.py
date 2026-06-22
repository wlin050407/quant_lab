"""ML-P8B.3.5 train-only reduced feature set proposal builders."""

from __future__ import annotations

from typing import Any

from quant_lab.ml.harness.feature_diagnostics import (
    DiagnosticThresholds,
    compute_correlation_diagnostics,
    compute_missingness_by_feature,
    compute_train_constant_stats,
    feature_group,
    is_zone_dependent,
)
from quant_lab.ml.harness.p8b2_eval import SessionSplitManifest

GROUP_PRIORITY: dict[str, int] = {
    "quality": 1,
    "context": 2,
    "deterministic": 3,
    "index_path": 4,
    "greeks_iv": 5,
    "quote_microstructure": 6,
    "trade_flow_proxy": 7,
    "chain_summary": 8,
    "multiresolution": 9,
    "unknown": 10,
}


def _train_exclusion_reason(
    name: str,
    *,
    miss: float,
    stats: dict[str, Any],
    thresholds: DiagnosticThresholds,
) -> str | None:
    if stats.get("all_nan_train"):
        return "train_all_nan"
    if stats.get("constant_train"):
        return "train_constant"
    if stats.get("top_value_ratio_train", 0) >= thresholds.near_constant_same_value_threshold:
        return "train_near_constant"
    if miss > thresholds.train_missingness_drop_threshold:
        return "train_missingness_exceeded"
    return None


def _priority(name: str) -> int:
    base = GROUP_PRIORITY.get(feature_group(name), 99)
    if is_zone_dependent(name):
        return base + 50
    return base


def apply_correlation_prune(
    selected: list[str],
    train_rows: list[dict[str, Any]],
    *,
    thresholds: DiagnosticThresholds,
) -> tuple[list[str], dict[str, str]]:
    if len(selected) < 2:
        return selected, {}
    corr_info = compute_correlation_diagnostics(
        train_rows,
        selected,
        threshold=thresholds.correlation_prune_threshold,
    )
    excluded: dict[str, str] = {}
    keep = set(selected)
    for cluster in corr_info.get("correlation_clusters", []):
        in_cluster = [f for f in cluster if f in keep]
        if len(in_cluster) < 2:
            continue
        in_cluster.sort(key=lambda n: (_priority(n), compute_missingness_by_feature(train_rows, [n])[n]))
        for drop in in_cluster[1:]:
            if drop in keep:
                keep.remove(drop)
                excluded[drop] = "train_correlation_redundant"
    return sorted(keep), excluded


def _build_set_manifest(
    *,
    feature_set_name: str,
    feature_set_version: str,
    selected: list[str],
    all_numeric: list[str],
    exclusion_reasons: dict[str, str],
    groups_included: set[str],
    groups_excluded: set[str],
    split_manifest: SessionSplitManifest,
) -> dict[str, Any]:
    excluded = sorted(set(all_numeric) - set(selected))
    for name in exclusion_reasons:
        if name not in selected:
            excluded.append(name)
    excluded = sorted(set(excluded))
    full_reasons = {name: exclusion_reasons.get(name, "group_rule_excluded") for name in excluded}
    return {
        "feature_set_name": feature_set_name,
        "feature_set_version": feature_set_version,
        "selected_features": selected,
        "excluded_features": excluded,
        "exclusion_reasons": full_reasons,
        "selected_feature_count": len(selected),
        "excluded_feature_count": len(excluded),
        "groups_included": sorted(groups_included),
        "groups_excluded": sorted(groups_excluded),
        "train_sessions_used_for_selection": list(split_manifest.train_sessions),
        "validation_sessions_monitoring_only": list(split_manifest.validation_sessions),
        "test_sessions_monitoring_only": list(split_manifest.test_sessions),
        "target_based_selection_used": False,
    }


def propose_feature_set_a(
    numeric_columns: list[str],
    train_rows: list[dict[str, Any]],
    *,
    thresholds: DiagnosticThresholds,
    feature_set_version: str,
    split_manifest: SessionSplitManifest,
) -> dict[str, Any]:
    miss = compute_missingness_by_feature(train_rows, numeric_columns)
    stats = compute_train_constant_stats(train_rows, numeric_columns)
    allowed_groups = {"context", "deterministic", "quality", "index_path"}
    selected: list[str] = []
    exclusion_reasons: dict[str, str] = {}
    groups_included: set[str] = set()
    groups_excluded: set[str] = set()

    for name in numeric_columns:
        grp = feature_group(name)
        groups_excluded.add(grp)
        if grp not in allowed_groups:
            exclusion_reasons[name] = "group_rule_excluded"
            continue
        if is_zone_dependent(name):
            exclusion_reasons[name] = "group_rule_excluded"
            continue
        reason = _train_exclusion_reason(
            name, miss=miss[name], stats=stats[name], thresholds=thresholds
        )
        if reason:
            exclusion_reasons[name] = reason
            continue
        selected.append(name)
        groups_included.add(grp)
        groups_excluded.discard(grp)

    selected, corr_excl = apply_correlation_prune(selected, train_rows, thresholds=thresholds)
    exclusion_reasons.update(corr_excl)

    return _build_set_manifest(
        feature_set_name="FeatureSet_A_core_stable",
        feature_set_version=feature_set_version,
        selected=selected,
        all_numeric=numeric_columns,
        exclusion_reasons=exclusion_reasons,
        groups_included=groups_included,
        groups_excluded=groups_excluded,
        split_manifest=split_manifest,
    )


def propose_feature_set_b(
    numeric_columns: list[str],
    train_rows: list[dict[str, Any]],
    *,
    thresholds: DiagnosticThresholds,
    feature_set_version: str,
    split_manifest: SessionSplitManifest,
) -> dict[str, Any]:
    set_a = propose_feature_set_a(
        numeric_columns,
        train_rows,
        thresholds=thresholds,
        feature_set_version=feature_set_version,
        split_manifest=split_manifest,
    )
    base_selected = set(set_a["selected_features"])
    extra_groups = {"quote_microstructure", "trade_flow_proxy", "greeks_iv"}
    miss = compute_missingness_by_feature(train_rows, numeric_columns)
    stats = compute_train_constant_stats(train_rows, numeric_columns)
    selected = list(base_selected)
    exclusion_reasons = dict(set_a["exclusion_reasons"])
    groups_included = set(set_a["groups_included"])

    for name in numeric_columns:
        if name in base_selected:
            continue
        grp = feature_group(name)
        if grp not in extra_groups:
            continue
        reason = _train_exclusion_reason(
            name, miss=miss[name], stats=stats[name], thresholds=thresholds
        )
        if reason:
            exclusion_reasons[name] = reason
            continue
        selected.append(name)
        groups_included.add(grp)

    selected, corr_excl = apply_correlation_prune(selected, train_rows, thresholds=thresholds)
    exclusion_reasons.update(corr_excl)
    all_groups = {feature_group(n) for n in numeric_columns}
    groups_excluded = all_groups - groups_included

    return _build_set_manifest(
        feature_set_name="FeatureSet_B_core_plus_flow",
        feature_set_version=feature_set_version,
        selected=selected,
        all_numeric=numeric_columns,
        exclusion_reasons=exclusion_reasons,
        groups_included=groups_included,
        groups_excluded=groups_excluded,
        split_manifest=split_manifest,
    )


def propose_feature_set_c(
    numeric_columns: list[str],
    train_rows: list[dict[str, Any]],
    *,
    thresholds: DiagnosticThresholds,
    feature_set_version: str,
    split_manifest: SessionSplitManifest,
) -> dict[str, Any]:
    miss = compute_missingness_by_feature(train_rows, numeric_columns)
    stats = compute_train_constant_stats(train_rows, numeric_columns)
    selected: list[str] = []
    exclusion_reasons: dict[str, str] = {}
    groups_included: set[str] = set()

    for name in numeric_columns:
        grp = feature_group(name)
        if is_zone_dependent(name) and miss[name] > thresholds.train_missingness_drop_threshold:
            exclusion_reasons[name] = "train_missingness_exceeded"
            continue
        reason = _train_exclusion_reason(
            name, miss=miss[name], stats=stats[name], thresholds=thresholds
        )
        if reason:
            exclusion_reasons[name] = reason
            continue
        selected.append(name)
        groups_included.add(grp)

    selected, corr_excl = apply_correlation_prune(selected, train_rows, thresholds=thresholds)
    exclusion_reasons.update(corr_excl)
    all_groups = {feature_group(n) for n in numeric_columns}
    groups_excluded = all_groups - groups_included

    return _build_set_manifest(
        feature_set_name="FeatureSet_C_diagnostic_full_pruned",
        feature_set_version=feature_set_version,
        selected=selected,
        all_numeric=numeric_columns,
        exclusion_reasons=exclusion_reasons,
        groups_included=groups_included,
        groups_excluded=groups_excluded,
        split_manifest=split_manifest,
    )


def build_all_proposals(
    *,
    numeric_columns: list[str],
    non_numeric_columns: list[str],
    train_rows: list[dict[str, Any]],
    thresholds: DiagnosticThresholds,
    feature_set_version: str,
    split_manifest: SessionSplitManifest,
) -> list[dict[str, Any]]:
    _ = non_numeric_columns  # recorded in outer manifest as excluded_non_numeric_columns
    return [
        propose_feature_set_a(
            numeric_columns,
            train_rows,
            thresholds=thresholds,
            feature_set_version=feature_set_version,
            split_manifest=split_manifest,
        ),
        propose_feature_set_b(
            numeric_columns,
            train_rows,
            thresholds=thresholds,
            feature_set_version=feature_set_version,
            split_manifest=split_manifest,
        ),
        propose_feature_set_c(
            numeric_columns,
            train_rows,
            thresholds=thresholds,
            feature_set_version=feature_set_version,
            split_manifest=split_manifest,
        ),
    ]


__all__ = [
    "GROUP_PRIORITY",
    "apply_correlation_prune",
    "build_all_proposals",
    "propose_feature_set_a",
    "propose_feature_set_b",
    "propose_feature_set_c",
]
