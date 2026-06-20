"""Controlled multi-day point-in-time sample dataset builder (ML-P7.5)."""

from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quant_lab.data.intraday_lake import partition_dir
from quant_lab.data.intraday_manifest import is_partition_complete
from quant_lab.data.intraday_time import session_datetime
from quant_lab.ml.datasets.join import JoinedRow, strict_join_batches
from quant_lab.ml.datasets.lake_ingest import (
    DateIngestResult,
    build_rth_ingest_plan,
    ingest_rth_trade_date,
)
from quant_lab.ml.datasets.point_in_time import (
    AnchorConfig,
    BuildConfig,
    PilotIndexOutcomeProvider,
    build_dataset_manifest,
    build_dataset_rows,
    generate_anchors,
    write_pilot_dataset,
)
from quant_lab.ml.datasets.reporting import (
    LeakageValidationResult,
    build_baseline_dataset_manifest,
    build_baseline_dataset_validation_report,
    build_coverage_report,
    build_per_date_baseline_report,
    build_per_date_coverage_report,
    build_split_readiness_report,
    evaluate_p8b_readiness,
    evaluate_p783_gates,
    evaluate_stage_a_gate,
    load_completed_checkpoint_dates,
    validate_joined_dataset_leakage,
    validate_label_dataset_leakage,
    verify_join_keys_match,
    write_baseline_validation_report,
    write_per_date_report,
    write_reports,
)
from quant_lab.ml.features.builder import build_feature_dataset, write_feature_dataset
from quant_lab.ml.features.schemas import FeatureConfig
from quant_lab.ml.schemas import DatasetRow
from quant_lab.ml.splits import session_grouped_split

log = logging.getLogger(__name__)

OPTION_DATASETS: tuple[str, ...] = (
    "option_quote_tick",
    "option_quote_1s",
    "option_trade_tick",
    "option_greeks_1m_first_order",
    "derived_gamma_black76_1m",
    "option_open_interest",
)
INDEX_DATASETS: tuple[str, ...] = ("index_price_tick", "index_price_1s")
SESSION_DATASET = "session_metadata"


@dataclass(frozen=True)
class DateEntry:
    trade_date: date
    day_type: str
    anchor_type: str | None = None
    manual_anchors: tuple[str, ...] = field(default_factory=tuple)
    note: str | None = None


@dataclass(frozen=True)
class SampleBuildConfig:
    version: str
    root: str
    index_symbol: str
    strike_range: int
    strike_range_fallback: int
    anchor_type: str
    anchor_start_offset_minutes: int
    anchor_end_offset_minutes: int
    session_rth_start: str
    session_rth_end: str
    lake_root: Path
    dataset_root: Path
    feature_root: Path
    report_root: Path
    joined_root: Path
    ingest_enabled: bool
    ingest_full_rth: bool
    ingest_max_retries: int
    ingest_request_budget_per_date: int
    ingest_write_raw_lake: bool
    ingest_idempotent_skip_existing: bool
    quote_resolution: str
    index_resolution: str
    stage_a_dates: tuple[date, ...]
    seed_from_pilot_lake: Path | None
    dates: tuple[DateEntry, ...]
    label_schema_version: str = "1.0.0"
    baseline_label_schema_version: str | None = None
    dataset_only: bool = False
    skip_dates: frozenset[str] = frozenset()

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "root": self.root,
            "index_symbol": self.index_symbol,
            "strike_range": self.strike_range,
            "anchor_type": self.anchor_type,
            "lake_root": str(self.lake_root),
            "dataset_root": str(self.dataset_root),
            "feature_root": str(self.feature_root),
            "dates": [
                {
                    "date": d.trade_date.isoformat(),
                    "day_type": d.day_type,
                    "anchor_type": d.anchor_type,
                    "manual_anchors": list(d.manual_anchors),
                    "note": d.note,
                }
                for d in self.dates
            ],
        }


@dataclass(frozen=True)
class SampleBuildOptions:
    """Runtime options for checkpointed multi-date builds (ML-P7.6.3)."""

    dates_filter: tuple[date, ...] = ()
    checkpoint_per_date: bool = False
    progress_every: int = 10
    resume: bool = True
    dataset_only: bool = False


@dataclass
class DateBuildFailure:
    trade_date: date
    reason: str


@dataclass
class DryRunPlan:
    config: SampleBuildConfig
    dates: list[date]
    anchors_per_date: dict[str, int]
    total_anchors: int
    missing_partitions: dict[str, list[str]]
    partitions_to_skip: dict[str, list[str]]
    ingest_plans: dict[str, dict[str, Any]]
    output_paths: dict[str, str]
    estimated_api_calls_per_date: int
    estimated_total_api_calls: int
    estimated_runtime_minutes: float
    ingest_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "dates": [d.isoformat() for d in self.dates],
            "anchors_per_date": self.anchors_per_date,
            "total_anchors": self.total_anchors,
            "missing_partitions": self.missing_partitions,
            "partitions_to_skip": self.partitions_to_skip,
            "ingest_plans": self.ingest_plans,
            "output_paths": self.output_paths,
            "estimated_api_calls_per_date": self.estimated_api_calls_per_date,
            "estimated_total_api_calls": self.estimated_total_api_calls,
            "estimated_runtime_minutes": self.estimated_runtime_minutes,
            "ingest_enabled": self.ingest_enabled,
            "expected_partitions_per_date": len(OPTION_DATASETS) + len(INDEX_DATASETS) + 1,
            "thetadata_requests_note": "Per-date counts include quote tick fallback slot when tick_or_1s",
        }


@dataclass
class SampleBuildResult:
    joined_rows: list[JoinedRow]
    coverage_report: dict[str, Any]
    split_readiness: dict[str, Any]
    leakage: LeakageValidationResult
    failed_dates: list[DateBuildFailure]
    dataset_manifest: dict[str, Any]
    feature_manifest: dict[str, Any]
    sample_manifest: dict[str, Any]


def load_sample_config(path: Path) -> SampleBuildConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    dates: list[DateEntry] = []
    for item in raw["dates"]:
        dates.append(
            DateEntry(
                trade_date=date.fromisoformat(str(item["date"])),
                day_type=str(item.get("day_type", "normal")),
                anchor_type=item.get("anchor_type"),
                manual_anchors=tuple(item.get("manual_anchors") or ()),
                note=item.get("note"),
            )
        )
    ingest = raw.get("ingest") or {}
    seed = raw.get("seed_from_pilot_lake")
    data = raw.get("data") or {}
    stage_a_raw = raw.get("stage_a_dates") or []
    stage_a_dates = tuple(date.fromisoformat(str(d)) for d in stage_a_raw)
    build = raw.get("build") or {}
    skip_raw = raw.get("skip_dates") or []
    skip_dates = frozenset(str(d) for d in skip_raw)
    return SampleBuildConfig(
        version=str(raw["version"]),
        root=str(raw.get("root", data.get("root", "SPXW"))),
        index_symbol=str(raw.get("index_symbol", "SPX")),
        strike_range=int(raw.get("strike_range", data.get("strike_range", 60))),
        strike_range_fallback=int(raw.get("strike_range_fallback", 30)),
        anchor_type=str(raw.get("anchor_type", "regular_5min")),
        anchor_start_offset_minutes=int(raw.get("anchor_start_offset_minutes", 5)),
        anchor_end_offset_minutes=int(raw.get("anchor_end_offset_minutes", 5)),
        session_rth_start=str(raw.get("session_rth_start", "09:30:00")),
        session_rth_end=str(raw.get("session_rth_end", "16:00:00")),
        lake_root=Path(raw.get("lake_root", raw.get("outputs", {}).get("raw_lake", "artifacts/raw_lake_sample"))),
        dataset_root=Path(raw.get("dataset_root", raw.get("outputs", {}).get("dataset", "artifacts/datasets/pit_sample_v1"))),
        feature_root=Path(raw.get("feature_root", raw.get("outputs", {}).get("features", "artifacts/features/pit_sample_v1"))),
        report_root=Path(raw.get("report_root", raw.get("outputs", {}).get("reports", "artifacts/reports/pit_sample_v1"))),
        joined_root=Path(raw.get("joined_root", "artifacts/datasets/pit_sample_v1/joined")),
        ingest_enabled=bool(ingest.get("enabled", False)),
        ingest_full_rth=bool(ingest.get("full_rth", True)),
        ingest_max_retries=int(ingest.get("max_retries", 2)),
        ingest_request_budget_per_date=int(ingest.get("request_budget_per_date", 8)),
        ingest_write_raw_lake=bool(ingest.get("write_raw_lake", True)),
        ingest_idempotent_skip_existing=bool(ingest.get("idempotent_skip_existing", True)),
        quote_resolution=str(data.get("quote_resolution", ingest.get("quote_resolution", "tick_or_1s"))),
        index_resolution=str(data.get("index_resolution", ingest.get("index_resolution", "tick_or_1s"))),
        stage_a_dates=stage_a_dates,
        seed_from_pilot_lake=Path(seed) if seed else None,
        dates=tuple(dates),
        label_schema_version=str(raw.get("label_schema_version", "1.0.0")),
        baseline_label_schema_version=raw.get("baseline_label_schema_version"),
        dataset_only=bool(build.get("dataset_only") or build.get("skip_features", False)),
        skip_dates=skip_dates,
    )


def validate_dates_not_future(dates: Iterable[date], *, today: date | None = None) -> None:
    ref = today or date.today()
    for d in dates:
        if d >= ref:
            raise ValueError(f"future or same-day date not allowed: {d} (reference={ref})")


def parse_dates_filter(dates_csv: str | None) -> tuple[date, ...]:
    """Parse comma-separated ISO dates for --dates CLI filter."""
    if not dates_csv:
        return ()
    return tuple(date.fromisoformat(part.strip()) for part in dates_csv.split(",") if part.strip())


def select_date_entries(
    config: SampleBuildConfig,
    *,
    max_dates: int | None = None,
    dates_filter: tuple[date, ...] = (),
) -> list[DateEntry]:
    """Select config date entries respecting --max-dates and --dates filters."""
    entries = list(config.dates)
    if dates_filter:
        allowed = set(dates_filter)
        entries = [entry for entry in entries if entry.trade_date in allowed]
    if max_dates is not None:
        entries = entries[:max_dates]
    return entries


def _per_date_shard_path(root: Path, trade_date: date, suffix: str) -> Path:
    return root / "per_date" / f"{trade_date.isoformat()}{suffix}"


def _load_checkpoint_joined_rows(joined_root: Path) -> list[JoinedRow]:
    """Load joined rows from per-date checkpoint shards."""
    shard_dir = joined_root / "per_date"
    if not shard_dir.is_dir():
        return []
    rows: list[JoinedRow] = []
    for path in sorted(shard_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        for record in frame.to_dict(orient="records"):
            rows.append(JoinedRow(row=record))
    return rows


def _load_checkpoint_label_dicts(dataset_root: Path) -> list[dict[str, Any]]:
    """Load label row dicts from per-date dataset checkpoint shards."""
    shard_dir = dataset_root / "per_date"
    if not shard_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(shard_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        rows.extend(frame.to_dict(orient="records"))
    return rows


def _flush_date_checkpoint(
    config: SampleBuildConfig,
    *,
    trade_date: date,
    label_rows: list[DatasetRow],
    feature_rows: list[Any],
    joined_rows: list[JoinedRow],
    dataset_only: bool = False,
) -> None:
    """Write per-date dataset/feature/joined shards and refresh aggregate joined parquet."""
    config.dataset_root.mkdir(parents=True, exist_ok=True)
    label_dicts = [r.row_dict() for r in label_rows]
    if label_dicts:
        label_path = _per_date_shard_path(config.dataset_root, trade_date, ".parquet")
        label_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(label_dicts).to_parquet(label_path)
    if dataset_only:
        return

    config.feature_root.mkdir(parents=True, exist_ok=True)
    config.joined_root.mkdir(parents=True, exist_ok=True)
    shard_dir = config.joined_root / "per_date"
    shard_dir.mkdir(parents=True, exist_ok=True)

    feature_dicts = [r.row_dict() for r in feature_rows]
    if feature_dicts:
        feat_path = _per_date_shard_path(config.feature_root, trade_date, ".parquet")
        feat_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(feature_dicts).to_parquet(feat_path)
    joined_records = [j.to_dict() for j in joined_rows]
    if joined_records:
        pd.DataFrame(joined_records).to_parquet(shard_dir / f"{trade_date.isoformat()}.parquet")

    all_joined = _load_checkpoint_joined_rows(config.joined_root)
    if all_joined:
        pd.DataFrame([j.to_dict() for j in all_joined]).to_parquet(
            config.joined_root / "joined.parquet", index=False
        )


def _anchor_config_for_date(config: SampleBuildConfig, entry: DateEntry) -> AnchorConfig:
    anchor_type = entry.anchor_type or config.anchor_type
    if anchor_type == "manual":
        timestamps = tuple(session_datetime(entry.trade_date, t) for t in entry.manual_anchors)
        return AnchorConfig(anchor_type="manual", manual_timestamps=timestamps)
    session_close = "13:00:00" if entry.day_type == "early_close" else None
    return AnchorConfig(
        anchor_type=anchor_type,  # type: ignore[arg-type]
        interval_minutes=5 if anchor_type == "regular_5min" else 1,
        start_offset_minutes=config.anchor_start_offset_minutes,
        end_offset_minutes=config.anchor_end_offset_minutes,
        session_close_time=session_close,
    )


def count_anchors(config: SampleBuildConfig, entry: DateEntry) -> int:
    anchor_cfg = _anchor_config_for_date(config, entry)
    return len(generate_anchors(entry.trade_date, anchor_cfg))


def missing_partitions_for_date(config: SampleBuildConfig, trade_date: date) -> list[str]:
    missing: list[str] = []
    exp = trade_date
    for ds in OPTION_DATASETS:
        if ds in ("option_quote_tick", "option_quote_1s"):
            continue
        part = partition_dir(config.lake_root, ds, trade_date, root=config.root, expiration=exp)
        if not is_partition_complete(part):
            missing.append(ds)
    quote_ok = any(
        is_partition_complete(
            partition_dir(config.lake_root, ds, trade_date, root=config.root, expiration=exp)
        )
        for ds in ("option_quote_tick", "option_quote_1s")
    )
    if not quote_ok:
        missing.append("option_quote_tick_or_1s")
    index_ok = any(
        is_partition_complete(
            partition_dir(config.lake_root, ds, trade_date, symbol=config.index_symbol)
        )
        for ds in INDEX_DATASETS
    )
    if not index_ok:
        missing.append("index_price_tick_or_1s")
    sm = partition_dir(config.lake_root, SESSION_DATASET, trade_date, root=config.root)
    if not is_partition_complete(sm):
        missing.append(SESSION_DATASET)
    return missing


def build_dry_run_plan(
    config: SampleBuildConfig,
    *,
    max_dates: int | None = None,
    dates_filter: tuple[date, ...] = (),
) -> DryRunPlan:
    selected = select_date_entries(config, max_dates=max_dates, dates_filter=dates_filter)
    selected = [e for e in selected if e.trade_date.isoformat() not in config.skip_dates]
    validate_dates_not_future(d.trade_date for d in selected)
    anchors_map: dict[str, int] = {}
    missing: dict[str, list[str]] = {}
    skip_map: dict[str, list[str]] = {}
    ingest_plans: dict[str, dict[str, Any]] = {}
    total = 0
    api_per_date: list[int] = []
    for entry in selected:
        key = entry.trade_date.isoformat()
        anchors_map[key] = count_anchors(config, entry)
        total += anchors_map[key]
        missing[key] = missing_partitions_for_date(config, entry.trade_date)
        if config.ingest_enabled and config.ingest_full_rth:
            try:
                plan = build_rth_ingest_plan(
                    trade_date=entry.trade_date,
                    day_type=entry.day_type,
                    lake_root=config.lake_root,
                    root=config.root,
                    symbol=config.index_symbol,
                    strike_range=config.strike_range,
                    session_rth_start=config.session_rth_start,
                    session_rth_end=config.session_rth_end,
                    quote_resolution=config.quote_resolution,  # type: ignore[arg-type]
                    index_resolution=config.index_resolution,  # type: ignore[arg-type]
                    idempotent_skip_existing=config.ingest_idempotent_skip_existing,
                )
                ingest_plans[key] = plan.to_dict()
                skip_map[key] = list(plan.partitions_to_skip)
                api_per_date.append(plan.estimated_api_calls)
            except Exception as exc:
                ingest_plans[key] = {"error": str(exc)}
                api_per_date.append(0)
        else:
            api_per_date.append(7 if config.ingest_enabled else 0)
    avg_api = int(sum(api_per_date) / len(api_per_date)) if api_per_date else 0
    total_api = sum(api_per_date)
    est_runtime = total_api * 0.5 + total * 1.5  # rough minutes: 30s/request + 1.5s/anchor pipeline
    return DryRunPlan(
        config=config,
        dates=[d.trade_date for d in selected],
        anchors_per_date=anchors_map,
        total_anchors=total,
        missing_partitions=missing,
        partitions_to_skip=skip_map,
        ingest_plans=ingest_plans,
        output_paths={
            "lake_root": str(config.lake_root),
            "dataset_root": str(config.dataset_root),
            "feature_root": str(config.feature_root),
            "joined_root": str(config.joined_root),
            "report_root": str(config.report_root),
        },
        estimated_api_calls_per_date=avg_api,
        estimated_total_api_calls=total_api,
        estimated_runtime_minutes=est_runtime,
        ingest_enabled=config.ingest_enabled,
    )


def seed_pilot_lake_for_date(config: SampleBuildConfig, trade_date: date) -> bool:
    """Idempotent copy of pilot lake partitions for one trade_date."""
    if config.seed_from_pilot_lake is None or not config.seed_from_pilot_lake.is_dir():
        return False
    pilot = config.seed_from_pilot_lake
    copied = False
    for ds in (*OPTION_DATASETS, *INDEX_DATASETS, SESSION_DATASET):
        if ds in INDEX_DATASETS:
            src = partition_dir(pilot, ds, trade_date, symbol=config.index_symbol)
            dst = partition_dir(config.lake_root, ds, trade_date, symbol=config.index_symbol)
        elif ds == SESSION_DATASET:
            src = partition_dir(pilot, ds, trade_date, root=config.root)
            dst = partition_dir(config.lake_root, ds, trade_date, root=config.root)
        else:
            src = partition_dir(pilot, ds, trade_date, root=config.root, expiration=trade_date)
            dst = partition_dir(config.lake_root, ds, trade_date, root=config.root, expiration=trade_date)
        if not src.is_dir():
            continue
        if is_partition_complete(dst):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied = True
    return copied


def try_ingest_date(
    config: SampleBuildConfig,
    entry: DateEntry,
    *,
    dry_run: bool,
) -> tuple[bool, str, DateIngestResult | None]:
    """Attempt network ingestion if enabled; otherwise report missing partitions."""
    missing = missing_partitions_for_date(config, entry.trade_date)
    if not missing:
        return True, "partitions_complete_skip", None
    if seed_pilot_lake_for_date(config, entry.trade_date):
        missing = missing_partitions_for_date(config, entry.trade_date)
        if not missing:
            return True, "seeded_from_pilot_lake", None
    if dry_run:
        return False, f"missing_partitions_dry_run:{','.join(missing)}", None
    if not config.ingest_enabled:
        return False, f"missing_partitions_ingest_disabled:{','.join(missing)}", None
    if not config.ingest_full_rth:
        return False, f"missing_partitions_network_ingest_not_implemented_full_rth:{','.join(missing)}", None
    if not config.ingest_write_raw_lake:
        return False, "ingest_write_raw_lake_disabled", None

    result = ingest_rth_trade_date(
        trade_date=entry.trade_date,
        day_type=entry.day_type,
        lake_root=config.lake_root,
        root=config.root,
        symbol=config.index_symbol,
        strike_range=config.strike_range,
        session_rth_start=config.session_rth_start,
        session_rth_end=config.session_rth_end,
        quote_resolution=config.quote_resolution,  # type: ignore[arg-type]
        index_resolution=config.index_resolution,  # type: ignore[arg-type]
        max_retries=config.ingest_max_retries,
        request_budget_per_date=config.ingest_request_budget_per_date,
        idempotent_skip_existing=config.ingest_idempotent_skip_existing,
        dry_run=False,
    )
    if not result.success:
        return False, result.reason, result
    still_missing = missing_partitions_for_date(config, entry.trade_date)
    if still_missing:
        return False, f"ingest_incomplete:{','.join(still_missing)}", result
    return True, result.reason, result


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for fp in path.rglob("*"):
        if fp.is_file():
            total += fp.stat().st_size
    return total


def build_sample_dataset(
    config: SampleBuildConfig,
    *,
    max_dates: int | None = None,
    dry_run: bool = False,
    options: SampleBuildOptions | None = None,
) -> SampleBuildResult | DryRunPlan:
    opts = options or SampleBuildOptions()
    dataset_only = opts.dataset_only or config.dataset_only

    if dry_run:
        return build_dry_run_plan(
            config,
            max_dates=max_dates,
            dates_filter=opts.dates_filter,
        )

    selected = select_date_entries(
        config,
        max_dates=max_dates,
        dates_filter=opts.dates_filter,
    )
    selected = [e for e in selected if e.trade_date.isoformat() not in config.skip_dates]
    validate_dates_not_future(entry.trade_date for entry in selected)

    completed_dates: set[str] = set()
    successful_dates: list[str] = []
    if opts.resume and opts.checkpoint_per_date:
        completed_dates = load_completed_checkpoint_dates(config.report_root)
        if completed_dates:
            successful_dates = sorted(completed_dates)

    all_label_rows: list[DatasetRow] = []
    all_feature_result_rows: list[Any] = []
    failures: list[DateBuildFailure] = []
    replay_times: list[float] = []
    feature_times: list[float] = []
    ingest_results: list[DateIngestResult] = []

    if opts.resume and opts.checkpoint_per_date and not dataset_only:
        for row in _load_checkpoint_joined_rows(config.joined_root):
            td = str(row.to_dict().get("trade_date"))
            if td in completed_dates:
                successful_dates.append(td)

    for entry in selected:
        date_key = entry.trade_date.isoformat()
        if opts.checkpoint_per_date and opts.resume and date_key in completed_dates:
            log.info("[resume skip] %s checkpoint already completed", date_key)
            continue

        ok, reason, ingest_result = try_ingest_date(config, entry, dry_run=False)
        if ingest_result is not None:
            ingest_results.append(ingest_result)
        if not ok:
            failures.append(DateBuildFailure(entry.trade_date, reason))
            log.warning("skip %s: %s", entry.trade_date, reason)
            continue

        anchor_cfg = _anchor_config_for_date(config, entry)
        anchors = generate_anchors(entry.trade_date, anchor_cfg)
        if not anchors:
            failures.append(DateBuildFailure(entry.trade_date, "no_anchors_generated"))
            continue

        log.info("[date start] %s anchors=%d", date_key, len(anchors))
        progress_started = time.perf_counter()

        provider = PilotIndexOutcomeProvider(data_root=config.lake_root, symbol=config.index_symbol)
        build_cfg = BuildConfig(
            trade_date=entry.trade_date,
            root=config.root,
            data_root=config.lake_root,
            anchor=anchor_cfg,
        )

        def _on_anchor_progress(
            idx: int,
            total: int,
            as_of: datetime,
            *,
            _date_key: str = date_key,
            _started: float = progress_started,
        ) -> None:
            elapsed = time.perf_counter() - _started
            log.info(
                "[progress] %s anchor %d/%d as_of=%s elapsed=%.1fs",
                _date_key,
                idx,
                total,
                as_of.isoformat(),
                elapsed,
            )

        t0 = time.perf_counter()
        label_rows = build_dataset_rows(
            build_cfg,
            provider,
            anchors=anchors,
            progress_every=opts.progress_every if opts.checkpoint_per_date else 0,
            on_anchor_progress=_on_anchor_progress if opts.checkpoint_per_date else None,
        )
        replay_sec = (time.perf_counter() - t0) / max(len(label_rows), 1)
        replay_times.append(replay_sec)

        feature_sec = 0.0
        feature_result_rows: list[Any] = []
        if dataset_only:
            label_dicts_date = [r.row_dict() for r in label_rows]
            date_joined = [JoinedRow(row=d) for d in label_dicts_date]
        else:
            t1 = time.perf_counter()
            feature_result = build_feature_dataset(label_rows, config.lake_root, config=FeatureConfig())
            feature_sec = (time.perf_counter() - t1) / max(len(feature_result.rows), 1)
            feature_times.append(feature_sec)
            feature_result_rows = feature_result.rows
            label_dicts_date = [r.row_dict() for r in label_rows]
            feature_dicts_date = [r.row_dict() for r in feature_result_rows]
            date_joined = strict_join_batches(label_dicts_date, feature_dicts_date)

        all_label_rows.extend(label_rows)
        if not dataset_only:
            all_feature_result_rows.extend(feature_result_rows)
        successful_dates.append(date_key)

        if opts.checkpoint_per_date:
            if dataset_only:
                date_leakage = validate_label_dataset_leakage(label_dicts_date)
                strict_ok = True
            else:
                date_leakage = validate_joined_dataset_leakage(date_joined)
                strict_ok = verify_join_keys_match(date_joined)
            latest_anchor = anchors[-1][0].isoformat() if anchors else None
            if dataset_only:
                per_date_report = build_per_date_baseline_report(
                    trade_date=entry.trade_date,
                    day_type=entry.day_type,
                    label_rows=label_dicts_date,
                    replay_per_anchor_sec=replay_sec,
                    anchor_count=len(anchors),
                    latest_anchor=latest_anchor,
                    leakage_passed=date_leakage.passed,
                )
            else:
                per_date_report = build_per_date_coverage_report(
                    trade_date=entry.trade_date,
                    day_type=entry.day_type,
                    joined_rows=date_joined,
                    replay_per_anchor_sec=replay_sec,
                    feature_per_row_sec=feature_sec,
                    anchor_count=len(anchors),
                    latest_anchor=latest_anchor,
                    leakage_passed=date_leakage.passed,
                    strict_join_passed=strict_ok,
                )
            per_date_report["sizes_bytes"] = {
                "raw_lake_reused": _dir_size_bytes(config.lake_root),
            }
            write_per_date_report(config.report_root, per_date_report)
            _flush_date_checkpoint(
                config,
                trade_date=entry.trade_date,
                label_rows=label_rows,
                feature_rows=feature_result_rows,
                joined_rows=date_joined,
                dataset_only=dataset_only,
            )
            if dataset_only:
                log.info(
                    "[date complete] %s rows=%d baseline_eligible=%d zone_included=%d",
                    date_key,
                    per_date_report["row_count"],
                    per_date_report.get("baseline_eligible_count", 0),
                    per_date_report.get("zone_included_count", 0),
                )
            else:
                log.info(
                    "[date complete] %s rows=%d included=%d valid_zone_ratio=%.3f",
                    date_key,
                    per_date_report["row_count"],
                    per_date_report["included_row_count"],
                    per_date_report["valid_zone_ratio"],
                )

    if dataset_only:
        if opts.checkpoint_per_date:
            label_dicts = _load_checkpoint_label_dicts(config.dataset_root)
        else:
            label_dicts = [r.row_dict() for r in all_label_rows]
        joined = [JoinedRow(row=d) for d in label_dicts]
    elif opts.checkpoint_per_date:
        joined = _load_checkpoint_joined_rows(config.joined_root)
        if not joined and all_label_rows:
            label_dicts = [r.row_dict() for r in all_label_rows]
            feature_dicts = [r.row_dict() for r in all_feature_result_rows]
            joined = strict_join_batches(label_dicts, feature_dicts)
    else:
        label_dicts = [r.row_dict() for r in all_label_rows]
        feature_dicts = [r.row_dict() for r in all_feature_result_rows]
        joined = strict_join_batches(label_dicts, feature_dicts)

    sessions = [str(r.to_dict().get("session_id") or r.to_dict().get("trade_date")) for r in joined]
    split = session_grouped_split(sorted(set(sessions)))
    for j in joined:
        sid = str(j.to_dict().get("session_id") or j.to_dict().get("trade_date"))
        j.row["split_group"] = sid
        j.row["split"] = "train" if sid in split.train_sessions else "unassigned"

    leakage = (
        validate_label_dataset_leakage([j.to_dict() for j in joined])
        if dataset_only
        else validate_joined_dataset_leakage(joined)
    )
    if dataset_only:
        baseline_validation = build_baseline_dataset_validation_report(
            label_rows=[j.to_dict() for j in joined],
            failed_dates=[{"date": f.trade_date.isoformat(), "reason": f.reason} for f in failures],
            successful_dates=successful_dates,
            skipped_dates=sorted(config.skip_dates),
        )
        write_baseline_validation_report(config.report_root, baseline_validation)
        coverage = baseline_validation.get("coverage_summary", {})
        split_readiness = baseline_validation.get("session_split_readiness", {})
        stage_a_gate = None
        p8b_readiness = evaluate_p783_gates(baseline_validation)
    else:
        coverage = build_coverage_report(
            joined_rows=joined,
            failed_dates=[{"date": f.trade_date.isoformat(), "reason": f.reason} for f in failures],
            timings={
                "replay_per_anchor_sec": sum(replay_times) / len(replay_times) if replay_times else 0.0,
                "feature_per_row_sec": sum(feature_times) / len(feature_times) if feature_times else 0.0,
            },
            sizes_bytes={
                "raw_lake": _dir_size_bytes(config.lake_root),
                "dataset": 0,
                "features": 0,
                "joined": 0,
            },
            date_entries=[{"date": d.trade_date.isoformat(), "day_type": d.day_type} for d in selected],
            ingest_results=ingest_results,
            successful_dates=successful_dates,
        )
        split_readiness = build_split_readiness_report(sessions)
        stage_a_gate = evaluate_stage_a_gate(coverage, leakage_passed=leakage.passed)
        p8b_readiness = evaluate_p8b_readiness(coverage, leakage_passed=leakage.passed)

    config.dataset_root.mkdir(parents=True, exist_ok=True)
    if not dataset_only:
        config.feature_root.mkdir(parents=True, exist_ok=True)
        config.joined_root.mkdir(parents=True, exist_ok=True)

    label_dicts_final = [j.to_dict() for j in joined]
    if label_dicts_final:
        provider = PilotIndexOutcomeProvider(data_root=config.lake_root, symbol=config.index_symbol)
        if dataset_only:
            ds_manifest = build_baseline_dataset_manifest(
                label_dicts_final,
                outcome_provider=provider,
                anchor_config={"anchor_type": config.anchor_type},
                split_config=split.to_dict(),
                label_schema_version=config.label_schema_version,
                baseline_label_schema_version=config.baseline_label_schema_version,
            )
        elif all_label_rows:
            ds_manifest = build_dataset_manifest(
                all_label_rows,
                outcome_provider=provider,
                anchor_config={"anchor_type": config.anchor_type},
                split_config=split.to_dict(),
            )
        else:
            ds_manifest = build_baseline_dataset_manifest(
                label_dicts_final,
                outcome_provider=provider,
                anchor_config={"anchor_type": config.anchor_type},
                split_config=split.to_dict(),
                label_schema_version=config.label_schema_version,
                baseline_label_schema_version=config.baseline_label_schema_version,
            )
        if dataset_only or label_dicts_final:
            pd.DataFrame(label_dicts_final).to_parquet(
                config.dataset_root / "dataset.parquet", index=False
            )
            (config.dataset_root / "manifest.json").write_text(
                json.dumps(ds_manifest, indent=2), encoding="utf-8"
            )
            if not dataset_only:
                coverage["sizes_bytes"]["dataset"] = _dir_size_bytes(config.dataset_root)
        else:
            write_pilot_dataset(all_label_rows, ds_manifest, output_root=config.dataset_root)
            coverage["sizes_bytes"]["dataset"] = _dir_size_bytes(config.dataset_root)
    else:
        ds_manifest = {}

    feat_manifest: dict[str, Any] = {}
    if not dataset_only and all_feature_result_rows:
        from quant_lab.ml.features.manifest import build_feature_manifest

        feat_manifest = build_feature_manifest(
            all_feature_result_rows,
            feature_config={"source": "pit_sample_v1"},
            dataset_manifest=ds_manifest,
        )
        from quant_lab.ml.features.schemas import FeatureDatasetBuildResult

        write_feature_dataset(
            FeatureDatasetBuildResult(rows=all_feature_result_rows, manifest=feat_manifest),
            config.feature_root,
        )
        coverage["sizes_bytes"]["features"] = _dir_size_bytes(config.feature_root)

    if not dataset_only:
        joined_records = [j.to_dict() for j in joined]
        if joined_records:
            pd.DataFrame(joined_records).to_parquet(config.joined_root / "joined.parquet", index=False)
            coverage["sizes_bytes"]["joined"] = _dir_size_bytes(config.joined_root)

    sample_manifest = {
        "sample_manifest_version": "pit-sample-v1",
        "config": config.to_manifest_dict(),
        "row_count": len(joined),
        "failed_dates": [{"date": f.trade_date.isoformat(), "reason": f.reason} for f in failures],
        "leakage_passed": leakage.passed,
        "dataset_only": dataset_only,
        "label_schema_version": config.label_schema_version,
        "baseline_label_schema_version": config.baseline_label_schema_version,
    }
    (config.dataset_root / "sample_manifest.json").write_text(json.dumps(sample_manifest, indent=2), encoding="utf-8")

    write_reports(
        config.report_root,
        coverage=coverage,
        split_readiness=split_readiness,
        leakage=leakage,
        stage_a_gate=stage_a_gate,
        p8b_readiness=p8b_readiness,
    )

    return SampleBuildResult(
        joined_rows=joined,
        coverage_report=coverage if not dataset_only else baseline_validation.get("coverage_summary", coverage),
        split_readiness=split_readiness,
        leakage=leakage,
        failed_dates=failures,
        dataset_manifest=ds_manifest,
        feature_manifest=feat_manifest,
        sample_manifest=sample_manifest,
    )
