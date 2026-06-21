"""ML-P8B.1 feature dataset build from existing label parquet (no label rebuild)."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.data.point_in_time_replay import (
    compute_deterministic_bundle,
    replay_state,
    to_deterministic_input_frame,
)
from quant_lab.ml.features.builder import build_feature_row, write_feature_dataset
from quant_lab.ml.features.manifest import build_feature_manifest
from quant_lab.ml.features.p8b1_validation import (
    compute_feature_coverage,
    validate_all_feature_rows_forbidden,
    validate_feature_timestamp_leakage,
    validate_strict_hash_join,
)
from quant_lab.ml.features.raw_frames import load_feature_raw_frames
from quant_lab.ml.features.schemas import FeatureConfig
from quant_lab.ml.harness.manifests import RunManifest
from quant_lab.ml.schemas import (
    BASELINE_LABEL_SCHEMA_VERSION,
    FEATURE_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    AsOfContext,
    DatasetRow,
    LabelRow,
)

log = logging.getLogger(__name__)

HARNESS_STAGE_P8B1 = "ML-P8B.1"


@dataclass
class FeatureBuildConfig:
    version: str
    root: str
    index_symbol: str
    baseline_label_schema_version: str
    label_schema_version: str
    lake_root: Path
    dataset_root: Path
    feature_root: Path
    report_root: Path
    dates: list[date]
    skip_dates: set[date]
    checkpoint_per_date: bool = True
    progress_every: int = 10
    strict_hash_join: bool = True
    validate_feature_timestamps: bool = True
    validate_forbidden_inputs: bool = True
    expected_row_count: int = 1391
    expected_sessions: int = 19


@dataclass
class FeatureBuildResult:
    dry_run: bool = False
    dates_built: list[str] = field(default_factory=list)
    feature_row_count: int = 0
    label_row_count: int = 0
    join_validation: dict[str, Any] = field(default_factory=dict)
    timestamp_leakage: dict[str, Any] = field(default_factory=dict)
    forbidden_validation: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    p8b1_pass: bool = False
    run_manifest_path: Path | None = None
    report_path: Path | None = None


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


def load_feature_build_config(path: Path) -> FeatureBuildConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    dates_raw = raw.get("dates") or []
    dates: list[date] = []
    for d in dates_raw:
        if isinstance(d, dict):
            dates.append(date.fromisoformat(str(d["date"])))
        else:
            dates.append(date.fromisoformat(str(d)))
    skip = {date.fromisoformat(str(d)) for d in raw.get("skip_dates") or []}
    build = raw.get("build") or {}
    expected = raw.get("expected") or {}
    return FeatureBuildConfig(
        version=str(raw.get("version", "unknown")),
        root=str(raw.get("root", "SPXW")),
        index_symbol=str(raw.get("index_symbol", "SPX")),
        baseline_label_schema_version=str(
            raw.get("baseline_label_schema_version", BASELINE_LABEL_SCHEMA_VERSION)
        ),
        label_schema_version=str(raw.get("label_schema_version", LABEL_SCHEMA_VERSION),
        ),
        lake_root=Path(raw.get("lake_root") or raw.get("input_raw_lake", "artifacts/raw_lake_sample")),
        dataset_root=Path(raw.get("dataset_root") or raw.get("input_dataset")),
        feature_root=Path(raw.get("feature_root") or raw.get("output_features")),
        report_root=Path(raw.get("report_root") or raw.get("output_reports")),
        dates=dates,
        skip_dates=skip,
        checkpoint_per_date=bool(build.get("checkpoint_per_date", True)),
        progress_every=int(build.get("progress_every", 10)),
        strict_hash_join=bool(build.get("strict_hash_join", True)),
        validate_feature_timestamps=bool(build.get("validate_feature_timestamps", True)),
        validate_forbidden_inputs=bool(build.get("validate_forbidden_inputs", True)),
        expected_row_count=int(expected.get("row_count", 1391)),
        expected_sessions=int(expected.get("sessions", 19)),
    )


def _parse_list_field(val: Any) -> list[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    if isinstance(val, (list, tuple)):
        return [str(v) for v in val]
    return list(val)


def _parse_bool(val: Any) -> bool | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return bool(val)


def label_dict_to_dataset_row(record: dict[str, Any]) -> DatasetRow:
    """Reconstruct DatasetRow from parquet label dict."""
    td = pd.Timestamp(record["trade_date"]).date()
    as_of = pd.Timestamp(record["as_of_timestamp"]).to_pydatetime()
    part_hashes = record.get("source_partition_hashes")
    if part_hashes is None or (isinstance(part_hashes, float) and pd.isna(part_hashes)):
        hashes: tuple[str, ...] = ()
    elif isinstance(part_hashes, (list, tuple)):
        hashes = tuple(str(h) for h in part_hashes)
    else:
        hashes = tuple(str(h) for h in list(part_hashes))

    zone_low = record.get("zone_low_t")
    has_zone = zone_low is not None and not (isinstance(zone_low, float) and pd.isna(zone_low))

    ctx = AsOfContext(
        trade_date=td,
        as_of_timestamp=as_of,
        spot_t=float(record["spot_t"]),
        primary_pin_t=record.get("primary_pin_t"),
        secondary_pin_t=record.get("secondary_pin_t"),
        zone_low_t=zone_low,
        zone_high_t=record.get("zone_high_t"),
        zone_center_t=record.get("zone_center_t"),
        zone_break_up=None,
        zone_break_down=None,
        pin_score_t=float(record.get("pin_score_t", 0.0)),
        expected_move_t=float(record.get("expected_move_t", 0.0)),
        gamma_source=str(record.get("gamma_source", "unknown")),
        oi_semantics_status=record.get("oi_semantics_status"),
        spot_zone_state_at_as_of=str(record.get("spot_zone_state_at_as_of", "unknown")),
        has_valid_zone=has_zone,
        quality_score=float(record.get("quality_score", 0.0)),
        replay_state_hash=str(record["replay_state_hash"]),
        deterministic_bundle_hash=str(record["deterministic_bundle_hash"]),
        source_partition_hashes=hashes,
        warning_codes=tuple(_parse_list_field(record.get("warning_codes"))),
    )

    labels = LabelRow(exclusion_reasons=_parse_list_field(record.get("exclusion_reasons")))
    for field_name in labels.__dataclass_fields__:
        if field_name == "exclusion_reasons":
            continue
        key = f"labels.{field_name}"
        if key in record:
            val = record[key]
            if field_name == "label_source_timestamp" and val is not None and not pd.isna(val):
                val = pd.Timestamp(val).to_pydatetime()
            if field_name == "first_zone_exit_timestamp" and val is not None and not pd.isna(val):
                val = pd.Timestamp(val).to_pydatetime()
            if field_name == "baseline_target_exclusion_reasons":
                val = _parse_list_field(val)
            if val is not None and isinstance(val, float) and pd.isna(val):
                val = None
            setattr(labels, field_name, val)

    exp_raw = record.get("expiration")
    expiration = pd.Timestamp(exp_raw).date() if exp_raw is not None and not pd.isna(exp_raw) else td

    return DatasetRow(
        context=ctx,
        labels=labels,
        anchor_type=str(record.get("anchor_type", "regular_5min")),  # type: ignore[arg-type]
        root=str(record.get("root", "SPXW")),
        expiration=expiration,
        session_id=str(record.get("session_id", td.isoformat())),
        sample_weight=float(record.get("sample_weight", 1.0)),
        split_group=record.get("split_group"),
    )


def load_label_dicts(
    dataset_root: Path,
    *,
    dates_filter: set[date] | None = None,
) -> list[dict[str, Any]]:
    """Load label rows from per_date shards or aggregate dataset.parquet."""
    shard_dir = dataset_root / "per_date"
    rows: list[dict[str, Any]] = []
    if shard_dir.is_dir() and any(shard_dir.glob("*.parquet")):
        for path in sorted(shard_dir.glob("*.parquet")):
            td = date.fromisoformat(path.stem)
            if dates_filter and td not in dates_filter:
                continue
            frame = pd.read_parquet(path)
            rows.extend(frame.to_dict(orient="records"))
    else:
        dataset_path = dataset_root / "dataset.parquet"
        if not dataset_path.is_file():
            raise FileNotFoundError(f"label dataset not found: {dataset_path}")
        frame = pd.read_parquet(dataset_path)
        for record in frame.to_dict(orient="records"):
            td = pd.Timestamp(record["trade_date"]).date()
            if dates_filter and td not in dates_filter:
                continue
            rows.append(record)
    return rows


def _feature_shard_path(feature_root: Path, trade_date: date) -> Path:
    return feature_root / "per_date" / f"{trade_date.isoformat()}.parquet"


def _load_feature_dicts(feature_root: Path, dates_filter: set[date] | None = None) -> list[dict[str, Any]]:
    shard_dir = feature_root / "per_date"
    rows: list[dict[str, Any]] = []
    if not shard_dir.is_dir():
        agg = feature_root / "features.parquet"
        if agg.is_file():
            frame = pd.read_parquet(agg)
            for record in frame.to_dict(orient="records"):
                td = pd.Timestamp(record["trade_date"]).date()
                if dates_filter and td not in dates_filter:
                    continue
                rows.append(record)
        return rows
    for path in sorted(shard_dir.glob("*.parquet")):
        td = date.fromisoformat(path.stem)
        if dates_filter and td not in dates_filter:
            continue
        frame = pd.read_parquet(path)
        rows.extend(frame.to_dict(orient="records"))
    return rows


def build_dry_run_plan(config: FeatureBuildConfig) -> dict[str, Any]:
    """Dry-run plan without building features."""
    dataset_exists = config.dataset_root.is_dir()
    dataset_parquet = (config.dataset_root / "dataset.parquet").is_file()
    per_date = config.dataset_root / "per_date"
    per_date_count = len(list(per_date.glob("*.parquet"))) if per_date.is_dir() else 0
    lake_ok = config.lake_root.is_dir()
    label_rows = load_label_dicts(config.dataset_root) if dataset_exists else []
    sessions = sorted({str(r.get("trade_date")) for r in label_rows})
    return {
        "dry_run": True,
        "config_version": config.version,
        "input_dataset": str(config.dataset_root),
        "input_dataset_exists": dataset_exists,
        "dataset_parquet_exists": dataset_parquet,
        "per_date_shard_count": per_date_count,
        "row_count": len(label_rows),
        "expected_row_count": config.expected_row_count,
        "sessions": len(sessions),
        "expected_sessions": config.expected_sessions,
        "raw_lake_exists": lake_ok,
        "output_features": str(config.feature_root),
        "output_reports": str(config.report_root),
        "dates_in_config": [d.isoformat() for d in config.dates],
        "baseline_label_schema_version": config.baseline_label_schema_version,
        "no_artifacts_committed": True,
    }


def _hash_manifest_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def build_p8b1_run_manifest(
    config: FeatureBuildConfig,
    *,
    leakage_status: str,
    forbidden_status: str,
    dataset_manifest_hash: str,
    feature_manifest_hash: str,
) -> RunManifest:
    return RunManifest(
        run_id=hashlib.sha256(f"{config.version}-{time.time()}".encode()).hexdigest()[:32],
        stage=HARNESS_STAGE_P8B1,
        created_at=datetime.now(tz=__import__("datetime").UTC).isoformat(),
        code_commit=_git_commit(),
        dataset_manifest_hash=dataset_manifest_hash,
        feature_manifest_hash=feature_manifest_hash,
        label_schema_version=config.label_schema_version,
        baseline_label_schema_version=config.baseline_label_schema_version,
        target_name="feature_dataset_validation_only",
        split_protocol="not_applied_p8b1",
        train_sessions=[],
        validation_sessions=[],
        test_sessions=[],
        metrics_version="p8b0-v1",
        leakage_validation_status=leakage_status,
        forbidden_input_validation_status=forbidden_status,
        model_type="feature_dataset_validation_only",
        model_fitting_allowed=False,
        artifacts_written=[
            str(config.feature_root),
            str(config.report_root),
        ],
        notes="ML-P8B.1 feature build and validation — no model fitting",
    )


def evaluate_p8b1_gates(
    *,
    join_pass: bool,
    timestamp_pass: bool,
    forbidden_pass: bool,
    feature_row_count: int,
    dates_built: int,
    expected_dates: int,
) -> bool:
    return (
        join_pass
        and timestamp_pass
        and forbidden_pass
        and feature_row_count > 0
        and dates_built == expected_dates
    )


def build_feature_dataset_p8b1(
    config: FeatureBuildConfig,
    *,
    dates_filter: set[date] | None = None,
    dry_run: bool = False,
    resume: bool = True,
) -> FeatureBuildResult:
    """Build features from label dataset and run P8B.1 validations."""
    result = FeatureBuildResult(dry_run=dry_run)
    if dry_run:
        return result

    selected_dates = [d for d in config.dates if d not in config.skip_dates]
    if dates_filter:
        selected_dates = [d for d in selected_dates if d in dates_filter]

    label_by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    all_labels = load_label_dicts(config.dataset_root, dates_filter=set(selected_dates))
    for rec in all_labels:
        td = pd.Timestamp(rec["trade_date"]).date()
        label_by_date[td].append(rec)

    config.feature_root.mkdir(parents=True, exist_ok=True)
    config.report_root.mkdir(parents=True, exist_ok=True)

    completed: set[str] = set()
    if resume and config.checkpoint_per_date:
        for p in (config.report_root / "per_date").glob("*.json"):
            try:
                rep = json.loads(p.read_text(encoding="utf-8"))
                if rep.get("feature_build_complete"):
                    completed.add(p.stem)
            except json.JSONDecodeError:
                pass

    all_feature_dicts: list[dict[str, Any]] = []

    for td in selected_dates:
        date_key = td.isoformat()
        label_dicts = label_by_date.get(td, [])
        if not label_dicts:
            log.warning("[feature skip] %s no label rows", date_key)
            continue

        if resume and config.checkpoint_per_date and date_key in completed:
            log.info("[feature resume skip] %s checkpoint complete", date_key)
            shard = _feature_shard_path(config.feature_root, td)
            if shard.is_file():
                frame = pd.read_parquet(shard)
                all_feature_dicts.extend(frame.to_dict(orient="records"))
                result.dates_built.append(date_key)
            continue

        log.info("[feature date start] %s rows=%d", date_key, len(label_dicts))
        t0 = time.perf_counter()
        dataset_rows = [label_dict_to_dataset_row(r) for r in label_dicts]
        feature_rows_objs = []
        for i, ds_row in enumerate(dataset_rows, start=1):
            state = replay_state(
                ds_row.context.trade_date,
                ds_row.context.as_of_timestamp,
                data_root=config.lake_root,
            )
            input_df = to_deterministic_input_frame(state.option_chain, spot=ds_row.context.spot_t)
            hours = (
                session_datetime(ds_row.context.trade_date, SESSION_CLOSE)
                - ds_row.context.as_of_timestamp
            ).total_seconds() / 3600.0
            bundle = compute_deterministic_bundle(
                input_df,
                ds_row.context.spot_t,
                symbol="^SPX",
                asof=ds_row.context.trade_date,
                hours_to_close=max(hours, 0.0),
                use_precomputed_gamma=True,
            )
            raw = load_feature_raw_frames(state.request)
            feature_rows_objs.append(
                build_feature_row(ds_row, state, bundle, ctx=ds_row.context, raw_frames=raw, config=FeatureConfig())
            )
            if config.progress_every > 0 and i % config.progress_every == 0:
                elapsed = time.perf_counter() - t0
                log.info(
                    "[feature progress] %s row %d/%d as_of=%s elapsed=%.1fs",
                    date_key,
                    i,
                    len(dataset_rows),
                    ds_row.context.as_of_timestamp.isoformat(),
                    elapsed,
                )

        feature_dicts = [r.row_dict() for r in feature_rows_objs]

        date_leak = validate_feature_timestamp_leakage(feature_dicts)
        date_forbidden = validate_all_feature_rows_forbidden(feature_dicts)
        leakage_ok = date_leak.timestamp_leakage_pass
        forbidden_ok = date_forbidden["forbidden_input_pass"]

        if config.checkpoint_per_date:
            shard_path = _feature_shard_path(config.feature_root, td)
            shard_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(feature_dicts).to_parquet(shard_path, index=False)
            per_date_report = {
                "trade_date": date_key,
                "feature_rows": len(feature_dicts),
                "timestamp_leakage_pass": leakage_ok,
                "forbidden_input_pass": forbidden_ok,
                "feature_build_complete": True,
            }
            per_dir = config.report_root / "per_date"
            per_dir.mkdir(parents=True, exist_ok=True)
            (per_dir / f"{date_key}.json").write_text(
                json.dumps(per_date_report, indent=2),
                encoding="utf-8",
            )

        all_feature_dicts.extend(feature_dicts)
        result.dates_built.append(date_key)
        log.info(
            "[feature date complete] %s feature_rows=%d leakage=%s",
            date_key,
            len(feature_dicts),
            "PASS" if leakage_ok else "FAIL",
        )

    result.label_row_count = len(all_labels)
    result.feature_row_count = len(all_feature_dicts)

    if all_feature_dicts:
        from quant_lab.ml.features.schemas import FeatureDatasetBuildResult, FeatureRow

        fr_for_manifest: list[FeatureRow] = []
        for d in all_feature_dicts:
            feats = {k.replace("features.", ""): v for k, v in d.items() if k.startswith("features.")}
            fr_for_manifest.append(
                FeatureRow(
                    feature_schema_version=str(d.get("feature_schema_version", FEATURE_SCHEMA_VERSION)),
                    trade_date=pd.Timestamp(d["trade_date"]).date(),
                    as_of_timestamp=pd.Timestamp(d["as_of_timestamp"]).to_pydatetime(),
                    replay_state_hash=str(d["replay_state_hash"]),
                    deterministic_bundle_hash=str(d["deterministic_bundle_hash"]),
                    features=feats,
                    source_timestamp_max=(
                        pd.Timestamp(d["source_timestamp_max"]).to_pydatetime()
                        if d.get("source_timestamp_max")
                        else None
                    ),
                )
            )
        ds_manifest = _load_dataset_manifest(config.dataset_root)
        manifest = build_feature_manifest(
            fr_for_manifest,
            feature_config={"source": "p8b1_label_dataset"},
            dataset_manifest=ds_manifest,
        )
        agg_result = FeatureDatasetBuildResult(rows=fr_for_manifest, manifest=manifest)
        write_feature_dataset(agg_result, config.feature_root)

    join_res = validate_strict_hash_join(all_labels, all_feature_dicts)
    ts_res = validate_feature_timestamp_leakage(all_feature_dicts) if config.validate_feature_timestamps else None
    forb_res = (
        validate_all_feature_rows_forbidden(all_feature_dicts)
        if config.validate_forbidden_inputs
        else {"forbidden_input_pass": True, "forbidden_columns": [], "warning_columns": []}
    )
    cov = compute_feature_coverage(all_feature_dicts)

    result.join_validation = join_res.to_dict()
    result.timestamp_leakage = ts_res.to_dict() if ts_res else {}
    result.forbidden_validation = forb_res
    result.coverage = cov.to_dict()

    ds_hash = _hash_manifest_file(config.dataset_root / "manifest.json")
    feat_hash = _hash_manifest_file(config.feature_root / "manifest.json")
    leak_status = "PASS" if (ts_res and ts_res.timestamp_leakage_pass) else "FAIL"
    forb_status = "PASS" if forb_res.get("forbidden_input_pass") else "FAIL"
    run_manifest = build_p8b1_run_manifest(
        config,
        leakage_status=leak_status,
        forbidden_status=forb_status,
        dataset_manifest_hash=ds_hash,
        feature_manifest_hash=feat_hash,
    )
    manifest_path = config.report_root / "p8b1_run_manifest.json"
    manifest_path.write_text(run_manifest.to_json(), encoding="utf-8")
    result.run_manifest_path = manifest_path

    validation_report = {
        "phase": HARNESS_STAGE_P8B1,
        "dates_built": result.dates_built,
        "label_row_count": result.label_row_count,
        "feature_row_count": result.feature_row_count,
        "strict_hash_join": result.join_validation,
        "timestamp_leakage": result.timestamp_leakage,
        "forbidden_input_validation": result.forbidden_validation,
        "coverage": result.coverage,
        "dataset_manifest_hash": ds_hash,
        "feature_manifest_hash": feat_hash,
        "artifacts_not_committed": True,
    }
    report_path = config.report_root / "p8b1_validation_report.json"
    report_path.write_text(json.dumps(validation_report, indent=2), encoding="utf-8")
    result.report_path = report_path

    result.p8b1_pass = evaluate_p8b1_gates(
        join_pass=join_res.join_pass,
        timestamp_pass=bool(ts_res and ts_res.timestamp_leakage_pass),
        forbidden_pass=bool(forb_res.get("forbidden_input_pass")),
        feature_row_count=result.feature_row_count,
        dates_built=len(result.dates_built),
        expected_dates=len(selected_dates),
    )
    return result


def _load_dataset_manifest(dataset_root: Path) -> dict[str, Any] | None:
    path = dataset_root / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
