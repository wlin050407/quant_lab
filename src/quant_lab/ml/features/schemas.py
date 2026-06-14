"""Feature schema, catalog, and row types for ML-P7."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

FEATURE_MANIFEST_VERSION = "pit-features-v1"
MAX_SOURCE_TIMESTAMP_RULE = "source_timestamp <= as_of_timestamp"

FeatureGroup = Literal[
    "context",
    "deterministic",
    "chain_summary",
    "quote_microstructure",
    "trade_flow_proxy",
    "greeks_iv",
    "index_path",
    "time_calendar",
    "quality",
    "multiresolution",
]

Resolution = Literal["1s", "10s", "1m", "5m"]

QUOTE_WINDOWS_SEC: tuple[int, ...] = (30, 60, 300)
TRADE_WINDOWS_SEC: tuple[int, ...] = (30, 60, 300)
INDEX_WINDOWS_SEC: tuple[int, ...] = (30, 60, 300)

RESOLUTIONS: tuple[Resolution, ...] = ("1s", "10s", "1m", "5m")

# Columns that must never appear in feature dicts.
FORBIDDEN_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {
        "official_close",
        "future_index_path",
        "labels.close_location_vs_current_zone",
        "close_location_vs_current_zone",
        "normalized_close_move",
        "final_volume",
        "daily_volume",
        "session_total_volume",
        "eod_volume",
    }
)

LABEL_PREFIXES: tuple[str, ...] = ("labels.", "label_")


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: FeatureGroup
    dtype: str
    unit: str | None
    source_dataset: str
    timestamp_rule: str
    normalization: str | None
    nullable: bool
    allowed_missing_reason: str | None
    leakage_risk: str


def _spec(
    name: str,
    group: FeatureGroup,
    *,
    dtype: str = "float64",
    unit: str | None = None,
    source_dataset: str = "replay",
    timestamp_rule: str = MAX_SOURCE_TIMESTAMP_RULE,
    normalization: str | None = None,
    nullable: bool = True,
    allowed_missing_reason: str | None = None,
    leakage_risk: str = "low",
) -> FeatureSpec:
    return FeatureSpec(
        name=name,
        group=group,
        dtype=dtype,
        unit=unit,
        source_dataset=source_dataset,
        timestamp_rule=timestamp_rule,
        normalization=normalization,
        nullable=nullable,
        allowed_missing_reason=allowed_missing_reason,
        leakage_risk=leakage_risk,
    )


def _context_specs() -> list[FeatureSpec]:
    names = [
        ("minutes_since_open", "minutes"),
        ("minutes_to_close", "minutes"),
        ("minutes_to_expiry", "minutes"),
        ("session_status", None),
        ("early_close", None),
        ("day_of_week", None),
        ("time_bucket", None),
        ("time_sin", None),
        ("time_cos", None),
    ]
    return [
        _spec(n, "context", dtype="float64" if u else "string", unit=u, source_dataset="session_metadata")
        for n, u in names
    ]


def _deterministic_specs() -> list[FeatureSpec]:
    names = [
        "spot_t",
        "primary_pin_t",
        "secondary_pin_t",
        "zone_low_t",
        "zone_high_t",
        "zone_center_t",
        "zone_width_points",
        "zone_width_pct",
        "zone_width_em",
        "pin_score_t",
        "expected_move_t",
        "gamma_source",
        "oi_semantics_status",
        "net_gex",
        "absolute_gex",
        "call_gex",
        "put_gex",
        "king_node",
        "call_wall",
        "put_wall",
        "gamma_flip",
        "distance_spot_to_primary_pin_points",
        "distance_spot_to_primary_pin_pct",
        "distance_spot_to_primary_pin_em",
        "distance_spot_to_secondary_pin_points",
        "distance_spot_to_secondary_pin_pct",
        "distance_spot_to_secondary_pin_em",
        "distance_spot_to_zone_center_points",
        "distance_spot_to_zone_center_pct",
        "distance_spot_to_zone_center_em",
        "distance_spot_to_zone_low_points",
        "distance_spot_to_zone_high_points",
        "spot_position_in_zone",
    ]
    return [
        _spec(
            n,
            "deterministic",
            dtype="string" if n in {"gamma_source", "oi_semantics_status"} else "float64",
            source_dataset="deterministic_bundle",
            allowed_missing_reason="no_valid_zone" if "zone" in n or "pin" in n else None,
        )
        for n in names
    ]


def _chain_specs() -> list[FeatureSpec]:
    names = [
        "contract_count",
        "active_contract_count",
        "call_contract_count",
        "put_contract_count",
        "quote_coverage_ratio",
        "greeks_coverage_ratio",
        "gamma_coverage_ratio",
        "oi_coverage_ratio",
        "total_open_interest",
        "call_open_interest",
        "put_open_interest",
        "call_put_oi_ratio",
        "total_abs_gamma_oi",
        "call_abs_gamma_oi",
        "put_abs_gamma_oi",
        "gex_hhi",
        "top_1_gex_share",
        "top_3_gex_share",
        "gex_weighted_strike",
        "gex_weighted_distance_em",
    ]
    return [
        _spec(n, "chain_summary", source_dataset="option_chain", leakage_risk="medium")
        for n in names
    ]


def _quote_specs() -> list[FeatureSpec]:
    base = [
        "quote_update_count",
        "quote_update_rate",
        "median_bid_ask_spread",
        "mean_bid_ask_spread",
        "spread_p90",
        "wide_spread_ratio",
        "bid_size_mean",
        "ask_size_mean",
        "quote_mid_change",
        "quote_mid_return",
        "quote_age_seconds_mean",
        "stale_quote_ratio",
    ]
    out: list[FeatureSpec] = []
    for w in QUOTE_WINDOWS_SEC:
        for b in base:
            out.append(
                _spec(
                    f"quote_{w}s_{b}",
                    "quote_microstructure",
                    source_dataset="option_quote_tick",
                    leakage_risk="high",
                )
            )
    return out


def _trade_specs() -> list[FeatureSpec]:
    base = [
        "trade_count",
        "trade_volume",
        "trade_notional_proxy",
        "call_trade_volume",
        "put_trade_volume",
        "call_put_trade_volume_ratio",
        "near_spot_trade_volume",
        "near_pin_trade_volume",
        "volume_hhi",
        "volume_to_oi_ratio",
        "last_trade_age_seconds",
    ]
    out: list[FeatureSpec] = []
    for w in (*TRADE_WINDOWS_SEC, "since_open"):
        suffix = f"{w}s" if isinstance(w, int) else w
        for b in base:
            out.append(
                _spec(
                    f"trade_{suffix}_{b}",
                    "trade_flow_proxy",
                    source_dataset="option_trade_tick",
                    leakage_risk="high",
                )
            )
    return out


def _greeks_specs() -> list[FeatureSpec]:
    names = [
        "iv_atm",
        "iv_weighted_mean",
        "iv_skew_call_put",
        "iv_change_1m",
        "iv_change_5m",
        "delta_weighted_exposure",
        "theta_weighted_exposure",
        "vega_weighted_exposure",
        "gamma_available_ratio",
        "gamma_method_black76_share",
    ]
    return [_spec(n, "greeks_iv", source_dataset="option_greeks_1m_first_order") for n in names]


def _index_specs() -> list[FeatureSpec]:
    base = [
        "spot_return",
        "realized_vol",
        "session_high_so_far",
        "session_low_so_far",
        "distance_to_session_high",
        "distance_to_session_low",
        "range_so_far",
        "momentum",
        "index_age_seconds",
    ]
    out: list[FeatureSpec] = []
    for w in (*INDEX_WINDOWS_SEC, "since_open"):
        suffix = f"{w}s" if isinstance(w, int) else w
        for b in base:
            if b in {"session_high_so_far", "session_low_so_far", "distance_to_session_high", "distance_to_session_low", "range_so_far", "index_age_seconds"}:
                if w != "since_open" and b == "index_age_seconds":
                    continue
                if isinstance(w, int) and b.startswith("session"):
                    continue
            name = f"index_{suffix}_{b}" if b not in {"spot_return", "realized_vol", "momentum"} else f"index_{suffix}_{b}"
            out.append(_spec(name, "index_path", source_dataset="index_price_1s", leakage_risk="high"))
    # Explicit names from spec
    explicit = [
        "index_30s_spot_return_30s",
        "index_60s_spot_return_60s",
        "index_300s_spot_return_300s",
        "index_since_open_spot_return_from_open",
        "index_60s_realized_vol_60s",
        "index_300s_realized_vol_300s",
        "index_since_open_session_high_so_far",
        "index_since_open_session_low_so_far",
        "index_since_open_distance_to_session_high",
        "index_since_open_distance_to_session_low",
        "index_since_open_range_so_far",
        "index_60s_momentum_60s",
        "index_300s_momentum_300s",
        "index_since_open_index_age_seconds",
    ]
    return out + [_spec(n, "index_path", source_dataset="index_price_1s") for n in explicit if n not in {s.name for s in out}]


def _quality_specs() -> list[FeatureSpec]:
    names = [
        "replay_quality_score",
        "feature_quality_score",
        "quote_duplicate_ratio",
        "quote_out_of_order_ratio",
        "missing_feature_count",
        "nullable_feature_count",
        "stale_quote_ratio",
        "stale_greek_ratio",
        "stale_index",
        "oi_semantics_unconfirmed",
        "gamma_is_derived_black76",
        "source_partition_count",
    ]
    return [_spec(n, "quality", source_dataset="replay_quality", dtype="float64" if n != "stale_index" else "bool") for n in names]


def _multiresolution_specs() -> list[FeatureSpec]:
    metrics = ["spot_return_30s", "quote_update_rate", "trade_count", "iv_atm", "realized_vol_60s"]
    out: list[FeatureSpec] = []
    for res in RESOLUTIONS:
        for m in metrics:
            out.append(_spec(f"mr_{res}_{m}", "multiresolution", source_dataset=f"aggregated_{res}"))
    return out


def build_feature_catalog() -> tuple[FeatureSpec, ...]:
    specs: list[FeatureSpec] = []
    specs.extend(_context_specs())
    specs.extend(_deterministic_specs())
    specs.extend(_chain_specs())
    specs.extend(_quote_specs())
    specs.extend(_trade_specs())
    specs.extend(_greeks_specs())
    specs.extend(_index_specs())
    specs.extend(_quality_specs())
    specs.extend(_multiresolution_specs())
    # Deduplicate by name
    seen: set[str] = set()
    unique: list[FeatureSpec] = []
    for s in specs:
        if s.name not in seen:
            seen.add(s.name)
            unique.append(s)
    return tuple(unique)


FEATURE_CATALOG: tuple[FeatureSpec, ...] = build_feature_catalog()
FEATURE_CATALOG_BY_NAME: dict[str, FeatureSpec] = {s.name: s for s in FEATURE_CATALOG}


@dataclass(frozen=True)
class FeatureConfig:
    quote_windows_sec: tuple[int, ...] = QUOTE_WINDOWS_SEC
    trade_windows_sec: tuple[int, ...] = TRADE_WINDOWS_SEC
    index_windows_sec: tuple[int, ...] = INDEX_WINDOWS_SEC
    resolutions: tuple[Resolution, ...] = RESOLUTIONS
    wide_spread_points: float = 5.0
    near_spot_pct: float = 0.001
    near_pin_pct: float = 0.003
    strict_unknown_features: bool = False
    max_quote_age_seconds: int = 60
    max_greek_age_seconds: int = 120
    max_index_age_seconds: int = 10


@dataclass
class FeatureRow:
    feature_schema_version: str
    trade_date: date
    as_of_timestamp: datetime
    replay_state_hash: str
    deterministic_bundle_hash: str
    features: dict[str, Any]
    feature_warnings: list[str] = field(default_factory=list)
    feature_exclusion_reasons: list[str] = field(default_factory=list)
    source_timestamp_max: datetime | None = None
    source_partition_hashes: tuple[str, ...] = field(default_factory=tuple)

    def row_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "feature_schema_version": self.feature_schema_version,
            "trade_date": self.trade_date.isoformat(),
            "as_of_timestamp": self.as_of_timestamp.isoformat(),
            "feature_cutoff_timestamp": self.as_of_timestamp.isoformat(),
            "replay_state_hash": self.replay_state_hash,
            "deterministic_bundle_hash": self.deterministic_bundle_hash,
            "source_timestamp_max": (
                self.source_timestamp_max.isoformat() if self.source_timestamp_max else None
            ),
            "source_partition_hashes": list(self.source_partition_hashes),
            "feature_warnings": self.feature_warnings,
            "feature_exclusion_reasons": self.feature_exclusion_reasons,
        }
        for k, v in self.features.items():
            out[f"features.{k}"] = v
        return out


@dataclass
class FeatureDatasetBuildResult:
    rows: list[FeatureRow]
    manifest: dict[str, Any]
    output_path: Path | None = None
