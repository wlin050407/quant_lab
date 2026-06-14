"""Point-in-time supervised dataset builder (ML-P6)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_lake import PILOT_LAKE_ROOT, partition_dir
from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.data.point_in_time_replay import (
    DeterministicBundle,
    compute_deterministic_bundle,
    default_pilot_data_root,
    deterministic_input_to_factor_chain,
    replay_state,
    to_deterministic_input_frame,
)
from quant_lab.factors.gex import compute_dealer_gamma_exposure, filter_chain_by_dte
from quant_lab.factors.pin_cluster import detect_pin_cluster
from quant_lab.factors.positioning import pin_magnet_ranking
from quant_lab.ml.labels import compute_all_labels
from quant_lab.ml.schemas import (
    DATASET_MANIFEST_VERSION,
    DATASET_SCHEMA_VERSION,
    DETERMINISTIC_CONTRACT_VERSION,
    FEATURE_CUTOFF_RULE,
    FEATURE_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    LABEL_TIME_RULE,
    AnchorType,
    AsOfContext,
    DatasetRow,
    OutcomeContext,
)
from quant_lab.ml.splits import session_grouped_split

PILOT_DATASET_ROOT = Path("artifacts/datasets/pit_pilot")

EVENT_DRIVEN_ANCHOR_TYPES = (
    "zone_edge_cross",
    "primary_pin_change",
    "gamma_flip_cross",
    "iv_shock",
    "volume_shock",
)


@dataclass(frozen=True)
class AnchorConfig:
    anchor_type: AnchorType
    interval_minutes: int = 5
    start_offset_minutes: int = 5
    end_offset_minutes: int = 5
    session_close_time: str | None = None
    manual_timestamps: tuple[datetime, ...] = field(default_factory=tuple)
    event_types: tuple[str, ...] = field(default_factory=lambda: EVENT_DRIVEN_ANCHOR_TYPES)


@dataclass(frozen=True)
class BuildConfig:
    trade_date: date
    root: str = "SPXW"
    expiration: date | None = None
    data_root: Path | None = None
    anchor: AnchorConfig | None = None
    output_root: Path = PILOT_DATASET_ROOT
    symbol: str = "^SPX"


class OutcomeProvider(Protocol):
    """Contract for future outcomes (labels only)."""

    def outcome_source_hash(self) -> str: ...

    def get_outcome(
        self,
        trade_date: date,
        as_of_timestamp: datetime,
    ) -> OutcomeContext: ...


@dataclass
class SyntheticOutcomeProvider:
    """In-memory outcome source for tests and synthetic builds."""

    official_close: float
    official_close_timestamp: datetime
    session_close_timestamp: datetime
    future_index_path: pd.DataFrame
    official_close_source: str = "synthetic_fixture"

    def outcome_source_hash(self) -> str:
        payload = json.dumps(
            {
                "official_close": self.official_close,
                "official_close_timestamp": self.official_close_timestamp.isoformat(),
                "path_len": len(self.future_index_path),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def get_outcome(self, trade_date: date, as_of_timestamp: datetime) -> OutcomeContext:
        return OutcomeContext(
            official_close=self.official_close,
            official_close_timestamp=self.official_close_timestamp,
            official_close_source=self.official_close_source,
            session_close_timestamp=self.session_close_timestamp,
            future_index_path=self.future_index_path,
        )


@dataclass
class PilotIndexOutcomeProvider:
    """Load index path from ML-P3 pilot lake (no ThetaData network)."""

    data_root: Path
    symbol: str = "SPX"
    official_close_source: str = "pilot_index_price_1s_last_rth"

    def __post_init__(self) -> None:
        self._path_cache: dict[date, pd.DataFrame] = {}

    def _load_index_path(self, trade_date: date) -> pd.DataFrame:
        if trade_date in self._path_cache:
            return self._path_cache[trade_date]
        part = partition_dir(
            self.data_root,
            "index_price_1s",
            symbol=self.symbol,
            trade_date=trade_date,
        )
        fp = part / "part-000.parquet"
        if not fp.is_file():
            return pd.DataFrame(columns=["event_timestamp", "price"])
        df = pd.read_parquet(fp)
        ts_col = "event_timestamp" if "event_timestamp" in df.columns else "timestamp"
        price_col = "price" if "price" in df.columns else "close"
        ts = pd.to_datetime(df[ts_col])
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize(MARKET_TZ)
        out = pd.DataFrame({"event_timestamp": ts, "price": pd.to_numeric(df[price_col], errors="coerce")})
        self._path_cache[trade_date] = out.sort_values("event_timestamp")
        return self._path_cache[trade_date]

    def outcome_source_hash(self) -> str:
        return hashlib.sha256(str(self.data_root).encode()).hexdigest()[:16]

    def get_outcome(self, trade_date: date, as_of_timestamp: datetime) -> OutcomeContext:
        path = self._load_index_path(trade_date)
        session_close = session_datetime(trade_date, SESSION_CLOSE)
        if path.empty:
            close = float("nan")
            close_ts = session_close
        else:
            close = float(path["price"].iloc[-1])
            close_ts = path["event_timestamp"].iloc[-1]
            if hasattr(close_ts, "to_pydatetime"):
                close_ts = close_ts.to_pydatetime()
        return OutcomeContext(
            official_close=close,
            official_close_timestamp=close_ts,
            official_close_source=self.official_close_source,
            session_close_timestamp=session_close,
            future_index_path=path,
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


def hash_deterministic_bundle(bundle: DeterministicBundle, zone: tuple[float | None, float | None]) -> str:
    payload = json.dumps(
        {
            "net_gex": bundle.net_gex,
            "king_node": bundle.king_node,
            "pin_score": bundle.pin_score,
            "expected_move_1sd": bundle.expected_move_1sd,
            "gamma_source": bundle.gamma_source,
            "zone_low": zone[0],
            "zone_high": zone[1],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _build_heatmap_rows(chain: pd.DataFrame, spot: float) -> list[dict[str, float | None]]:
    if chain.empty:
        return []
    work = filter_chain_by_dte(chain, dte_max=1)
    if work.empty or "bs_gamma" not in work.columns:
        return []
    per = compute_dealer_gamma_exposure(work, spot, gamma_col="bs_gamma")
    if per.empty:
        return []
    rows: list[dict[str, float | None]] = []
    for strike, row in per.iterrows():
        rows.append(
            {
                "strike": float(strike),
                "net_gex": float(row["net_gex"]),
                "net_gex_bn": float(row["net_gex"]) / 1e9,
                "total_oi": float(row["total_oi"]),
            }
        )
    return rows


def build_as_of_context(
    trade_date: date,
    as_of_timestamp: datetime,
    *,
    root: str = "SPXW",
    expiration: date | None = None,
    data_root: Path | None = None,
    symbol: str = "^SPX",
) -> tuple[AsOfContext, list[float], DeterministicBundle]:
    """Replay + deterministic bundle + pin zone at as_of."""
    exp = expiration or trade_date
    state = replay_state(
        trade_date,
        as_of_timestamp,
        root=root,
        expiration=exp,
        data_root=data_root or default_pilot_data_root(),
    )
    spot = float(state.index_state.price) if state.index_state and state.index_state.price else float("nan")
    input_df = to_deterministic_input_frame(state.option_chain, spot=spot)
    hours = (session_datetime(trade_date, SESSION_CLOSE) - as_of_timestamp).total_seconds() / 3600.0
    bundle = compute_deterministic_bundle(
        input_df,
        spot,
        symbol=symbol,
        asof=trade_date,
        hours_to_close=max(hours, 0.0),
        use_precomputed_gamma=True,
    )
    factor_chain = deterministic_input_to_factor_chain(
        input_df,
        spot=spot,
        symbol=symbol,
        dte=0,
        hours_to_close=max(hours, 0.0),
    )
    heatmap = _build_heatmap_rows(factor_chain, spot)
    rankings = pin_magnet_ranking(
        heatmap,
        spot,
        king=bundle.king_node,
        max_pain=bundle.max_pain,
    )
    cluster = detect_pin_cluster(rankings, spot, symbol=symbol.replace("^", ""))
    has_valid = bool(cluster.is_cluster)
    z_low = float(cluster.lower) if has_valid else None
    z_high = float(cluster.upper) if has_valid else None
    z_center = float(cluster.center) if has_valid else None
    z_break_up = float(cluster.zone_break.up_break_level) if cluster.zone_break else None
    z_break_down = float(cluster.zone_break.down_break_level) if cluster.zone_break else None
    primary = float(cluster.primary_strike) if has_valid else (
        float(rankings[0]["strike"]) if rankings else bundle.king_node
    )
    secondary = (
        float(cluster.secondary_strike)
        if has_valid and cluster.secondary_strike is not None
        else (float(rankings[1]["strike"]) if len(rankings) > 1 else None)
    )
    partition_hashes = tuple(p.file_sha256 for p in state.source_partitions if p.file_sha256)
    replay_hash = state.state_hash
    zone_pair = (z_low, z_high)
    bundle_hash = hash_deterministic_bundle(bundle, zone_pair)
    warnings = tuple(state.warnings)
    if bundle.oi_semantics_status == "unconfirmed":
        warnings = warnings + ("oi_semantics_unconfirmed",)
    ctx = AsOfContext(
        trade_date=trade_date,
        as_of_timestamp=as_of_timestamp,
        spot_t=spot,
        primary_pin_t=primary,
        secondary_pin_t=secondary,
        zone_low_t=z_low,
        zone_high_t=z_high,
        zone_center_t=z_center,
        zone_break_up=z_break_up,
        zone_break_down=z_break_down,
        pin_score_t=bundle.pin_score,
        expected_move_t=bundle.expected_move_1sd,
        gamma_source=bundle.gamma_source,
        oi_semantics_status=bundle.oi_semantics_status,
        spot_zone_state_at_as_of=str(cluster.spot_zone_state),
        has_valid_zone=has_valid,
        quality_score=float(state.quality.quality_score),
        replay_state_hash=replay_hash,
        deterministic_bundle_hash=bundle_hash,
        source_partition_hashes=partition_hashes,
        warning_codes=warnings,
    )
    strikes = [float(r["strike"]) for r in rankings]
    return ctx, strikes, bundle


def generate_anchors(trade_date: date, config: AnchorConfig) -> list[tuple[datetime, AnchorType]]:
    """Generate sample anchor timestamps for one session."""
    if config.anchor_type == "manual":
        return [(ts, "manual") for ts in config.manual_timestamps]
    if config.anchor_type == "event_driven":
        return []
    open_dt = session_datetime(trade_date, "09:30:00")
    close_tod = config.session_close_time or SESSION_CLOSE.strftime("%H:%M:%S")
    close_dt = session_datetime(trade_date, close_tod)
    start = open_dt + timedelta(minutes=config.start_offset_minutes)
    end = close_dt - timedelta(minutes=config.end_offset_minutes)
    interval = timedelta(minutes=config.interval_minutes)
    anchors: list[tuple[datetime, AnchorType]] = []
    cur = start
    anchor_type: AnchorType = config.anchor_type
    while cur <= end:
        anchors.append((cur, anchor_type))
        cur += interval
    return anchors


def _row_is_excluded(row: DatasetRow) -> bool:
    return not row.context.has_valid_zone and row.labels.close_location_vs_current_zone is None


def compute_session_sample_weights(rows: list[DatasetRow]) -> list[DatasetRow]:
    """Default weight = 1 / included samples per session."""
    by_session: dict[str, list[DatasetRow]] = {}
    for row in rows:
        sid = row.session_id or row.context.trade_date.isoformat()
        by_session.setdefault(sid, []).append(row)
    out: list[DatasetRow] = []
    for group in by_session.values():
        included = [r for r in group if not _row_is_excluded(r)]
        n = max(len(included), 1)
        w = 1.0 / n
        for r in group:
            r.sample_weight = 0.0 if _row_is_excluded(r) else w
            out.append(r)
    return out


def build_dataset_rows(
    config: BuildConfig,
    outcome_provider: OutcomeProvider,
    anchors: Iterable[tuple[datetime, AnchorType]] | None = None,
) -> list[DatasetRow]:
    anchor_cfg = config.anchor or AnchorConfig(
        anchor_type="manual",
        manual_timestamps=(session_datetime(config.trade_date, "13:01:00"),),
    )
    anchor_list = list(anchors) if anchors is not None else generate_anchors(config.trade_date, anchor_cfg)
    rows: list[DatasetRow] = []
    exp = config.expiration or config.trade_date
    for as_of, anchor_type in anchor_list:
        ctx, strikes, _bundle = build_as_of_context(
            config.trade_date,
            as_of,
            root=config.root,
            expiration=exp,
            data_root=config.data_root,
            symbol=config.symbol,
        )
        outcome = outcome_provider.get_outcome(config.trade_date, as_of)
        labels = compute_all_labels(ctx, outcome, nearest_strikes=strikes)
        rows.append(
            DatasetRow(
                context=ctx,
                labels=labels,
                anchor_type=anchor_type,
                root=config.root,
                expiration=exp,
                session_id=config.trade_date.isoformat(),
            )
        )
    return compute_session_sample_weights(rows)


def build_dataset_manifest(
    rows: list[DatasetRow],
    *,
    outcome_provider: OutcomeProvider,
    anchor_config: dict[str, Any],
    split_config: dict[str, Any] | None = None,
    source_raw_lake_manifests: list[str] | None = None,
) -> dict[str, Any]:
    exclusion_counts: dict[str, int] = {}
    excluded = 0
    for row in rows:
        for reason in row.labels.exclusion_reasons:
            exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
        if row.sample_weight == 0.0:
            excluded += 1
    dates = sorted({r.context.trade_date.isoformat() for r in rows})
    return {
        "dataset_manifest_version": DATASET_MANIFEST_VERSION,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "deterministic_contract_version": DETERMINISTIC_CONTRACT_VERSION,
        "source_raw_lake_manifests": source_raw_lake_manifests or [],
        "outcome_source_hash": outcome_provider.outcome_source_hash(),
        "anchor_config": anchor_config,
        "date_range": {"min": dates[0] if dates else None, "max": dates[-1] if dates else None},
        "session_count": len({r.session_id for r in rows}),
        "row_count": len(rows),
        "excluded_row_count": excluded,
        "exclusion_reasons": exclusion_counts,
        "split_config": split_config or {},
        "feature_cutoff_rule": FEATURE_CUTOFF_RULE,
        "label_rule": LABEL_TIME_RULE,
        "known_open_questions": [
            "OI semantics not officially confirmed",
            "Pin score internal gamma recomputation",
        ],
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "code_commit": _git_commit(),
    }


def write_pilot_dataset(
    rows: list[DatasetRow],
    manifest: dict[str, Any],
    output_root: Path = PILOT_DATASET_ROOT,
) -> Path:
    """Write dataset rows + manifest to gitignored artifacts."""
    output_root.mkdir(parents=True, exist_ok=True)
    records = [r.row_dict() for r in rows]
    df = pd.DataFrame(records)
    parquet_path = output_root / "dataset.parquet"
    df.to_parquet(parquet_path, index=False)
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_root


def build_pilot_dataset_if_available(
    *,
    trade_date: date | None = None,
    manual_anchors: tuple[str, ...] = ("13:00:30", "13:01:00", "13:01:30"),
) -> dict[str, Any] | None:
    """Build pilot dataset when ``artifacts/raw_lake_pilot`` exists."""
    lake = PILOT_LAKE_ROOT if PILOT_LAKE_ROOT.is_dir() else default_pilot_data_root()
    if not lake.is_dir() or str(lake) == "data/raw/thetadata":
        return None
    td = trade_date or date(2026, 6, 10)
    anchors = [(session_datetime(td, t), "manual") for t in manual_anchors]
    provider = PilotIndexOutcomeProvider(data_root=lake)
    config = BuildConfig(trade_date=td, data_root=lake)
    rows = build_dataset_rows(config, provider, anchors=anchors)
    split = session_grouped_split([td.isoformat()])
    manifest = build_dataset_manifest(
        rows,
        outcome_provider=provider,
        anchor_config={"anchor_type": "manual", "timestamps": list(manual_anchors)},
        split_config=split.to_dict(),
    )
    write_pilot_dataset(rows, manifest)
    return {"row_count": len(rows), "output": str(PILOT_DATASET_ROOT), "manifest": manifest}
