"""Schema constants for ThetaData immutable raw event lake (ML-P3)."""

from __future__ import annotations

from typing import Final, Literal

MANIFEST_VERSION: Final = "raw-lake-v1"
SOURCE: Final = "thetadata"
SOURCE_CLIENT: Final = "thetadata_v3_python"
EVENT_TIMEZONE: Final = "America/New_York"

DatasetName = Literal[
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
]

DERIVED_DATASETS: frozenset[str] = frozenset({"derived_gamma_black76_1m"})
NBBO_QUOTE_DATASETS: frozenset[str] = frozenset({"option_quote_tick", "option_quote_1s"})
INDEX_DATASETS: frozenset[str] = frozenset({"index_price_tick", "index_price_1s"})

DATASET_SCHEMA_VERSION: dict[str, str] = {
    "option_quote_tick": "1.0.0",
    "option_quote_1s": "1.0.0",
    "option_trade_tick": "1.0.0",
    "option_greeks_1m_first_order": "1.0.0",
    "option_open_interest": "1.0.0",
    "derived_gamma_black76_1m": "1.0.0",
    "index_price_tick": "1.0.0",
    "index_price_1s": "1.0.0",
    "session_metadata": "1.0.0",
    "source_manifests": "1.0.0",
}

SOURCE_SCHEMA_VERSION: Final = "thetadata-v3-grpc-1.0"

COMMON_FIELDS: tuple[str, ...] = (
    "source",
    "source_client",
    "source_endpoint",
    "source_request_id",
    "source_schema_version",
    "dataset",
    "dataset_schema_version",
    "ingested_at",
    "trade_date",
    "event_timestamp",
    "event_timezone",
    "root_or_symbol",
)

OPTION_CONTRACT_FIELDS: tuple[str, ...] = (
    "root",
    "expiration",
    "strike",
    "right",
    "contract_identifier",
    "settlement_type",
    "settlement_type_source",
    "settlement_type_confidence",
)

OPTION_QUOTE_FIELDS: tuple[str, ...] = (
    *COMMON_FIELDS,
    *OPTION_CONTRACT_FIELDS,
    "bid",
    "ask",
    "bid_size",
    "ask_size",
    "bid_exchange",
    "ask_exchange",
    "bid_condition",
    "ask_condition",
    "sequence",
    "quote_timestamp_raw",
)

OPTION_TRADE_FIELDS: tuple[str, ...] = (
    *COMMON_FIELDS,
    *OPTION_CONTRACT_FIELDS,
    "price",
    "size",
    "exchange",
    "condition",
    "sequence",
)

OPTION_GREEKS_FIELDS: tuple[str, ...] = (
    *COMMON_FIELDS,
    *OPTION_CONTRACT_FIELDS,
    "implied_vol",
    "delta",
    "theta",
    "vega",
    "rho",
    "epsilon",
    "lambda",
    "underlying_price",
    "underlying_timestamp",
    "bid",
    "ask",
)

DERIVED_GAMMA_FIELDS: tuple[str, ...] = (
    *COMMON_FIELDS,
    *OPTION_CONTRACT_FIELDS,
    "gamma",
    "gamma_method",
    "gamma_method_version",
    "spot",
    "strike",
    "implied_vol",
    "rate",
    "dividend_yield_or_forward_assumption",
    "time_to_expiry_years",
    "expiry_timestamp",
    "settlement_timestamp",
    "input_source_hash",
)

OPTION_OI_FIELDS: tuple[str, ...] = (
    *COMMON_FIELDS,
    *OPTION_CONTRACT_FIELDS,
    "open_interest",
    "oi_event_timestamp",
    "oi_requested_date",
    "oi_semantics_status",
    "oi_publication_time_confirmed",
)

INDEX_PRICE_FIELDS: tuple[str, ...] = (
    *COMMON_FIELDS,
    "symbol",
    "price",
    "open",
    "high",
    "low",
    "close",
    "volume_or_null",
)

SESSION_METADATA_FIELDS: tuple[str, ...] = (
    *COMMON_FIELDS,
    "session_rth_start",
    "session_rth_end",
    "strike_range",
    "quote_interval",
    "trade_window_start",
    "trade_window_end",
    "pilot_label",
)

DATASET_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "option_quote_tick": OPTION_QUOTE_FIELDS,
    "option_quote_1s": OPTION_QUOTE_FIELDS,
    "option_trade_tick": OPTION_TRADE_FIELDS,
    "option_greeks_1m_first_order": OPTION_GREEKS_FIELDS,
    "derived_gamma_black76_1m": DERIVED_GAMMA_FIELDS,
    "option_open_interest": OPTION_OI_FIELDS,
    "index_price_tick": INDEX_PRICE_FIELDS,
    "index_price_1s": INDEX_PRICE_FIELDS,
    "session_metadata": SESSION_METADATA_FIELDS,
    "source_manifests": COMMON_FIELDS,
}

OI_SEMANTICS_DEFAULT: Final = "unconfirmed"
GAMMA_METHOD: Final = "black76"
GAMMA_METHOD_VERSION: Final = "1.0.0"
SETTLEMENT_UNKNOWN: Final = "unknown"
SETTLEMENT_SOURCE_DEFAULT: Final = "not_in_thetadata_response"
SETTLEMENT_CONFIDENCE_DEFAULT: Final = "unknown"


def dataset_schema_version(dataset: str) -> str:
    return DATASET_SCHEMA_VERSION[dataset]


def required_fields(dataset: str) -> tuple[str, ...]:
    return DATASET_REQUIRED_FIELDS[dataset]


def is_derived_dataset(dataset: str) -> bool:
    return dataset in DERIVED_DATASETS


def is_nbbo_quote_dataset(dataset: str) -> bool:
    return dataset in NBBO_QUOTE_DATASETS


def validate_required_columns(dataset: str, columns: list[str]) -> list[str]:
    """Return missing required field names (all must be present as columns)."""
    required = set(required_fields(dataset))
    present = set(columns)
    return sorted(required - present)
