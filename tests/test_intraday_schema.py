"""Unit tests for raw event lake schema constants (ML-P3)."""

from __future__ import annotations

import pytest

from quant_lab.data.intraday_schema import (
    DATASET_SCHEMA_VERSION,
    DERIVED_DATASETS,
    GAMMA_METHOD,
    MANIFEST_VERSION,
    NBBO_QUOTE_DATASETS,
    OI_SEMANTICS_DEFAULT,
    SOURCE,
    is_derived_dataset,
    is_nbbo_quote_dataset,
    required_fields,
    validate_required_columns,
)


def test_manifest_version_constant() -> None:
    assert MANIFEST_VERSION == "raw-lake-v1"
    assert SOURCE == "thetadata"


def test_all_p2_data_families_have_schema_version() -> None:
    expected = {
        "option_quote_tick",
        "option_quote_1s",
        "option_trade_tick",
        "option_greeks_1m_first_order",
        "option_open_interest",
        "derived_gamma_black76_1m",
        "index_price_tick",
        "index_price_1s",
        "session_metadata",
        "source_manifests",
    }
    assert expected == set(DATASET_SCHEMA_VERSION)


def test_common_fields_present_on_option_quote() -> None:
    fields = required_fields("option_quote_tick")
    for col in (
        "source",
        "dataset",
        "dataset_schema_version",
        "event_timestamp",
        "root_or_symbol",
    ):
        assert col in fields


def test_option_contract_fields_on_trade() -> None:
    fields = required_fields("option_trade_tick")
    for col in ("root", "expiration", "strike", "right", "contract_identifier"):
        assert col in fields


def test_validate_required_columns_reports_missing() -> None:
    missing = validate_required_columns("option_trade_tick", ["source", "dataset"])
    assert "event_timestamp" in missing
    assert "price" in missing


def test_nullable_extra_columns_allowed() -> None:
    cols = list(required_fields("index_price_tick")) + ["extra_nullable"]
    assert validate_required_columns("index_price_tick", cols) == []


def test_derived_gamma_includes_all_parameters() -> None:
    fields = required_fields("derived_gamma_black76_1m")
    for col in (
        "gamma",
        "gamma_method",
        "gamma_method_version",
        "spot",
        "implied_vol",
        "rate",
        "dividend_yield_or_forward_assumption",
        "time_to_expiry_years",
        "expiry_timestamp",
        "settlement_timestamp",
        "input_source_hash",
    ):
        assert col in fields
    assert GAMMA_METHOD == "black76"


def test_oi_defaults_unconfirmed() -> None:
    fields = required_fields("option_open_interest")
    assert "oi_semantics_status" in fields
    assert "oi_publication_time_confirmed" in fields
    assert OI_SEMANTICS_DEFAULT == "unconfirmed"


def test_nbbo_quote_not_labeled_l2() -> None:
    assert is_nbbo_quote_dataset("option_quote_tick")
    assert is_nbbo_quote_dataset("option_quote_1s")
    for ds in NBBO_QUOTE_DATASETS:
        assert "level2" not in ds
        assert "l2" not in ds


def test_black76_gamma_separate_from_greeks() -> None:
    assert is_derived_dataset("derived_gamma_black76_1m")
    assert "derived_gamma_black76_1m" in DERIVED_DATASETS
    assert "derived_gamma_black76_1m" not in NBBO_QUOTE_DATASETS


@pytest.mark.parametrize("dataset", sorted(DATASET_SCHEMA_VERSION))
def test_required_fields_non_empty(dataset: str) -> None:
    assert len(required_fields(dataset)) > 0
