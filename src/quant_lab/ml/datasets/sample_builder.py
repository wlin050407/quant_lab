"""Controlled multi-day point-in-time sample dataset builder (ML-P7.5)."""

from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
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
    build_coverage_report,
    build_split_readiness_report,
    evaluate_p8b_readiness,
    evaluate_stage_a_gate,
    validate_joined_dataset_leakage,
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
    )


def validate_dates_not_future(dates: Iterable[date], *, today: date | None = None) -> None:
    ref = today or date.today()
    for d in dates:
        if d >= ref:
            raise ValueError(f"future or same-day date not allowed: {d} (reference={ref})")


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


def build_dry_run_plan(config: SampleBuildConfig, *, max_dates: int | None = None) -> DryRunPlan:
    selected = list(config.dates[: max_dates or len(config.dates)])
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
) -> SampleBuildResult | DryRunPlan:
    if dry_run:
        return build_dry_run_plan(config, max_dates=max_dates)

    selected = list(config.dates[: max_dates or len(config.dates)])
    validate_dates_not_future(d.trade_date for d in selected)

    all_label_rows: list[DatasetRow] = []
    all_feature_result_rows: list = []
    failures: list[DateBuildFailure] = []
    replay_times: list[float] = []
    feature_times: list[float] = []
    ingest_results: list[DateIngestResult] = []
    successful_dates: list[str] = []

    for entry in selected:
        ok, reason, ingest_result = try_ingest_date(config, entry, dry_run=False)
        if ingest_result is not None:
            ingest_results.append(ingest_result)
        if not ok:
            failures.append(DateBuildFailure(entry.trade_date, reason))
            log.warning("skip %s: %s", entry.trade_date, reason)
            continue

        successful_dates.append(entry.trade_date.isoformat())

        anchor_cfg = _anchor_config_for_date(config, entry)
        anchors = generate_anchors(entry.trade_date, anchor_cfg)
        if not anchors:
            failures.append(DateBuildFailure(entry.trade_date, "no_anchors_generated"))
            continue

        provider = PilotIndexOutcomeProvider(data_root=config.lake_root, symbol=config.index_symbol)
        build_cfg = BuildConfig(
            trade_date=entry.trade_date,
            root=config.root,
            data_root=config.lake_root,
            anchor=anchor_cfg,
        )
        t0 = time.perf_counter()
        label_rows = build_dataset_rows(build_cfg, provider, anchors=anchors)
        replay_times.append((time.perf_counter() - t0) / max(len(label_rows), 1))

        t1 = time.perf_counter()
        feature_result = build_feature_dataset(label_rows, config.lake_root, config=FeatureConfig())
        feature_times.append((time.perf_counter() - t1) / max(len(feature_result.rows), 1))

        all_label_rows.extend(label_rows)
        all_feature_result_rows.extend(feature_result.rows)

    label_dicts = [r.row_dict() for r in all_label_rows]
    feature_dicts = [r.row_dict() for r in all_feature_result_rows]
    joined = strict_join_batches(label_dicts, feature_dicts)

    sessions = [str(r.to_dict().get("session_id") or r.to_dict().get("trade_date")) for r in joined]
    split = session_grouped_split(sorted(set(sessions)))
    for j in joined:
        sid = str(j.to_dict().get("session_id") or j.to_dict().get("trade_date"))
        j.row["split_group"] = sid
        j.row["split"] = "train" if sid in split.train_sessions else "unassigned"

    leakage = validate_joined_dataset_leakage(joined)
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
    config.feature_root.mkdir(parents=True, exist_ok=True)
    config.joined_root.mkdir(parents=True, exist_ok=True)

    if all_label_rows:
        provider = PilotIndexOutcomeProvider(data_root=config.lake_root, symbol=config.index_symbol)
        ds_manifest = build_dataset_manifest(
            all_label_rows,
            outcome_provider=provider,
            anchor_config={"anchor_type": config.anchor_type},
            split_config=split.to_dict(),
        )
        write_pilot_dataset(all_label_rows, ds_manifest, output_root=config.dataset_root)
        coverage["sizes_bytes"]["dataset"] = _dir_size_bytes(config.dataset_root)
    else:
        ds_manifest = {}

    if all_feature_result_rows:
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
    else:
        feat_manifest: dict[str, Any] = {}

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
        coverage_report=coverage,
        split_readiness=split_readiness,
        leakage=leakage,
        failed_dates=failures,
        dataset_manifest=ds_manifest,
        feature_manifest=feat_manifest if all_feature_result_rows else {},
        sample_manifest=sample_manifest,
    )
