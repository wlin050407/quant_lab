"""Tests for ML-P7 feature schema and catalog."""

from __future__ import annotations

from quant_lab.ml.features.schemas import (
    FEATURE_CATALOG,
    FEATURE_CATALOG_BY_NAME,
    FEATURE_MANIFEST_VERSION,
    FEATURE_SCHEMA_VERSION,
    FORBIDDEN_FEATURE_COLUMNS,
    FeatureConfig,
)


def test_version_constants() -> None:
    assert FEATURE_MANIFEST_VERSION == "pit-features-v1"
    assert FEATURE_SCHEMA_VERSION == "1.0.0"


def test_required_feature_groups_present() -> None:
    groups = {s.group for s in FEATURE_CATALOG}
    for g in (
        "context",
        "deterministic",
        "chain_summary",
        "quote_microstructure",
        "trade_flow_proxy",
        "greeks_iv",
        "index_path",
        "quality",
        "multiresolution",
    ):
        assert g in groups


def test_catalog_entries_have_metadata() -> None:
    spec = FEATURE_CATALOG_BY_NAME["spot_t"]
    assert spec.group == "deterministic"
    assert spec.timestamp_rule == "source_timestamp <= as_of_timestamp"


def test_nullable_zone_features() -> None:
    spec = FEATURE_CATALOG_BY_NAME["zone_low_t"]
    assert spec.nullable is True


def test_strict_unknown_rejection() -> None:
    cfg = FeatureConfig(strict_unknown_features=True)
    assert cfg.strict_unknown_features is True


def test_forbidden_columns_include_labels() -> None:
    assert "official_close" in FORBIDDEN_FEATURE_COLUMNS
    assert "labels.close_location_vs_current_zone" in FORBIDDEN_FEATURE_COLUMNS
