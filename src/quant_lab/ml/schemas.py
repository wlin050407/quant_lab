"""Schema version constants and typed row shapes for ML-P6 datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

DATASET_MANIFEST_VERSION = "pit-dataset-v1"
DATASET_SCHEMA_VERSION = "1.0.0"
LABEL_SCHEMA_VERSION = "1.0.0"
BASELINE_LABEL_SCHEMA_VERSION = "1.1.0-draft"
FEATURE_SCHEMA_VERSION = "1.0.0"
DETERMINISTIC_CONTRACT_VERSION = "ml-p5-v1"

AnchorType = Literal["regular_5min", "regular_1min", "event_driven", "manual"]

FEATURE_CUTOFF_RULE = "event_timestamp <= as_of_timestamp"
LABEL_TIME_RULE = "label timestamps may be > as_of_timestamp and are stored separately"

DATASET_ROW_CONTEXT_FIELDS: tuple[str, ...] = (
    "dataset_schema_version",
    "label_schema_version",
    "feature_schema_version",
    "deterministic_contract_version",
    "trade_date",
    "as_of_timestamp",
    "feature_cutoff_timestamp",
    "expiration",
    "root",
    "session_id",
    "anchor_type",
    "replay_state_hash",
    "deterministic_bundle_hash",
    "source_partition_hashes",
    "quality_score",
    "spot_t",
    "primary_pin_t",
    "secondary_pin_t",
    "zone_low_t",
    "zone_high_t",
    "zone_center_t",
    "pin_score_t",
    "expected_move_t",
    "gamma_source",
    "oi_semantics_status",
    "spot_zone_state_at_as_of",
    "sample_weight",
    "exclusion_reasons",
    "warning_codes",
    "split_group",
)

LABEL_FIELD_NAMES: tuple[str, ...] = (
    "close_location_vs_current_zone",
    "close_inside_current_zone",
    "normalized_close_move",
    "close_distance_to_zone_center_points",
    "close_distance_to_zone_center_em",
    "close_distance_to_primary_pin_points",
    "close_distance_to_primary_pin_em",
    "close_distance_to_secondary_pin_points",
    "close_distance_to_secondary_pin_em",
    "close_near_primary_pin",
    "close_near_secondary_pin",
    "close_near_nearest_strike",
    "first_zone_exit_direction",
    "first_zone_exit_timestamp",
    "minutes_to_first_exit",
    "exit_before_close",
    "return_to_zone_after_exit",
    "return_to_zone_within_5m",
    "return_to_zone_within_15m",
    "return_to_zone_within_30m",
    "valid_upside_exit_15m",
    "valid_downside_exit_15m",
    "valid_upside_exit_30m",
    "valid_downside_exit_30m",
    "realized_vol_5m_forward",
    "realized_vol_15m_forward",
    "realized_vol_30m_forward",
    "max_upside_before_close_points",
    "max_downside_before_close_points",
    "max_favorable_excursion_to_close",
    "max_adverse_excursion_to_close",
    "label_source_timestamp",
    "official_close_source",
    "label_horizon_minutes",
    "close_near_primary_pin_025",
    "close_near_primary_pin_050",
    "close_above_below_primary_pin_025",
    "close_above_below_primary_pin_050",
    "baseline_target_eligible",
    "baseline_target_exclusion_reasons",
    "baseline_label_schema_version",
)


@dataclass(frozen=True)
class AsOfContext:
    """Deterministic context frozen at ``as_of_timestamp`` (features only)."""

    trade_date: date
    as_of_timestamp: datetime
    spot_t: float
    primary_pin_t: float | None
    secondary_pin_t: float | None
    zone_low_t: float | None
    zone_high_t: float | None
    zone_center_t: float | None
    zone_break_up: float | None
    zone_break_down: float | None
    pin_score_t: float
    expected_move_t: float
    gamma_source: str
    oi_semantics_status: str | None
    spot_zone_state_at_as_of: str
    has_valid_zone: bool
    quality_score: float
    replay_state_hash: str
    deterministic_bundle_hash: str
    source_partition_hashes: tuple[str, ...]
    warning_codes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def feature_cutoff_timestamp(self) -> datetime:
        return self.as_of_timestamp


@dataclass(frozen=True)
class OutcomeContext:
    """Future outcomes strictly after ``as_of_timestamp``."""

    official_close: float
    official_close_timestamp: datetime
    official_close_source: str
    session_close_timestamp: datetime
    future_index_path: Any  # pd.DataFrame with event_timestamp, price

    def label_source_timestamp(self) -> datetime:
        return self.official_close_timestamp


@dataclass
class LabelRow:
    """All supervised labels for one anchor (nullable where spec requires)."""

    close_location_vs_current_zone: str | None = None
    close_inside_current_zone: bool | None = None
    normalized_close_move: float | None = None
    close_distance_to_zone_center_points: float | None = None
    close_distance_to_zone_center_em: float | None = None
    close_distance_to_primary_pin_points: float | None = None
    close_distance_to_primary_pin_em: float | None = None
    close_distance_to_secondary_pin_points: float | None = None
    close_distance_to_secondary_pin_em: float | None = None
    close_near_primary_pin: bool | None = None
    close_near_secondary_pin: bool | None = None
    close_near_nearest_strike: bool | None = None
    first_zone_exit_direction: str | None = None
    first_zone_exit_timestamp: datetime | None = None
    minutes_to_first_exit: float | None = None
    exit_before_close: bool | None = None
    return_to_zone_after_exit: bool | None = None
    return_to_zone_within_5m: bool | None = None
    return_to_zone_within_15m: bool | None = None
    return_to_zone_within_30m: bool | None = None
    valid_upside_exit_15m: bool | None = None
    valid_downside_exit_15m: bool | None = None
    valid_upside_exit_30m: bool | None = None
    valid_downside_exit_30m: bool | None = None
    realized_vol_5m_forward: float | None = None
    realized_vol_15m_forward: float | None = None
    realized_vol_30m_forward: float | None = None
    max_upside_before_close_points: float | None = None
    max_downside_before_close_points: float | None = None
    max_favorable_excursion_to_close: float | None = None
    max_adverse_excursion_to_close: float | None = None
    label_source_timestamp: datetime | None = None
    official_close_source: str | None = None
    label_horizon_minutes: float | None = None
    close_near_primary_pin_025: bool | None = None
    close_near_primary_pin_050: bool | None = None
    close_above_below_primary_pin_025: str | None = None
    close_above_below_primary_pin_050: str | None = None
    baseline_target_eligible: bool = False
    baseline_target_exclusion_reasons: list[str] = field(default_factory=list)
    baseline_label_schema_version: str | None = None
    exclusion_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in LABEL_FIELD_NAMES if hasattr(self, k)}


@dataclass
class DatasetRow:
    """One leakage-proof supervised sample."""

    context: AsOfContext
    labels: LabelRow
    anchor_type: AnchorType
    root: str = "SPXW"
    expiration: date | None = None
    session_id: str = ""
    sample_weight: float = 1.0
    split_group: str | None = None

    def row_dict(self) -> dict[str, Any]:
        ctx = self.context
        out: dict[str, Any] = {
            "dataset_schema_version": DATASET_SCHEMA_VERSION,
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "deterministic_contract_version": DETERMINISTIC_CONTRACT_VERSION,
            "trade_date": ctx.trade_date.isoformat(),
            "as_of_timestamp": ctx.as_of_timestamp.isoformat(),
            "feature_cutoff_timestamp": ctx.feature_cutoff_timestamp.isoformat(),
            "expiration": (self.expiration or ctx.trade_date).isoformat(),
            "root": self.root,
            "session_id": self.session_id or ctx.trade_date.isoformat(),
            "anchor_type": self.anchor_type,
            "replay_state_hash": ctx.replay_state_hash,
            "deterministic_bundle_hash": ctx.deterministic_bundle_hash,
            "source_partition_hashes": list(ctx.source_partition_hashes),
            "quality_score": ctx.quality_score,
            "spot_t": ctx.spot_t,
            "primary_pin_t": ctx.primary_pin_t,
            "secondary_pin_t": ctx.secondary_pin_t,
            "zone_low_t": ctx.zone_low_t,
            "zone_high_t": ctx.zone_high_t,
            "zone_center_t": ctx.zone_center_t,
            "pin_score_t": ctx.pin_score_t,
            "expected_move_t": ctx.expected_move_t,
            "gamma_source": ctx.gamma_source,
            "oi_semantics_status": ctx.oi_semantics_status,
            "spot_zone_state_at_as_of": ctx.spot_zone_state_at_as_of,
            "sample_weight": self.sample_weight,
            "exclusion_reasons": self.labels.exclusion_reasons,
            "warning_codes": list(ctx.warning_codes),
            "split_group": self.split_group,
        }
        for k in LABEL_FIELD_NAMES:
            out[f"labels.{k}"] = getattr(self.labels, k, None)
        return out
