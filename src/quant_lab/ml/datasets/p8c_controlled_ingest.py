"""ML-P8C.2 controlled raw lake ingest for frozen Stage-1 expansion dates."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from quant_lab.data.intraday_lake import partition_dir
from quant_lab.data.intraday_manifest import read_manifest
from quant_lab.data.thetadata_client import (
    ThetaDataConfigError,
    credential_source_label,
    refresh_thetadata_client,
    resolve_email_password,
)
from quant_lab.ml.datasets.lake_ingest import (
    INDEX_PARTITIONS,
    QUOTE_PARTITIONS,
    REQUIRED_OPTION_PARTITIONS,
    DateIngestResult,
    check_partition_readiness,
    ingest_rth_trade_date,
)
from quant_lab.ml.datasets.p8c_date_selection import KNOWN_EARLY_CLOSE

log = logging.getLogger(__name__)

HARNESS_STAGE_P8C2 = "ML-P8C.2"
SCOPE_RAW_LAKE_INGEST_ONLY = "raw_lake_ingest_only"

FROZEN_STAGE1_DATES: tuple[str, ...] = (
    "2023-02-23",
    "2023-03-21",
    "2023-05-08",
    "2023-05-30",
    "2023-06-16",
    "2023-06-22",
    "2023-06-27",
    "2023-07-03",
    "2023-08-09",
    "2023-10-25",
    "2024-01-03",
    "2024-02-20",
    "2024-05-15",
    "2024-06-06",
    "2024-10-16",
    "2024-11-20",
    "2025-01-17",
    "2025-03-05",
    "2025-03-25",
    "2025-05-13",
    "2025-05-14",
)

FROZEN_STAGE1_DATE_SET: frozenset[date] = frozenset(
    date.fromisoformat(d) for d in FROZEN_STAGE1_DATES
)

# P8C.1.1 frozen early-close session (not in KNOWN_EARLY_CLOSE calendar supplement)
P8C_FROZEN_EARLY_CLOSE: frozenset[str] = frozenset({"2023-07-03"})

DateIngestStatus = Literal["success", "failed", "skipped_complete", "incomplete"]


class P8C2ConfigError(ValueError):
    """Invalid P8C.2 ingest configuration or date request."""


class P8C2PreflightError(RuntimeError):
    """Preflight checks failed; ingest must not proceed."""


@dataclass
class P8C2IngestConfig:
    stage: str
    scope: str
    frozen_dates: tuple[date, ...]
    raw_lake_root: Path
    output_reports: Path
    root: str
    index_symbol: str
    strike_range: int
    session_rth_start: str
    session_rth_end: str
    quote_resolution: str
    index_resolution: str
    max_retries: int
    request_budget_per_date: int
    idempotent_skip_existing: bool
    allow_dataset_build: bool
    allow_feature_build: bool
    allow_model_fitting: bool
    allow_replacement_dates: bool
    allow_p8b4: bool
    minimum_free_disk_gb: float
    resume_enabled: bool
    skip_complete_dates: bool
    fail_on_incomplete_existing_partition: bool
    continue_on_date_failure: bool
    temporal_warning: str
    proxy_bucket_warning: str


@dataclass
class PreflightResult:
    passed: bool
    credential_source: str
    credentials_present: bool
    thetadata_connect_ok: bool | None
    raw_lake_root: str
    raw_lake_root_writable: bool
    free_disk_gb: float
    frozen_dates_match_owner: bool
    safety_flags_ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerDateIngestStatus:
    date: str
    status: DateIngestStatus
    started_at: str
    finished_at: str
    duration_seconds: float
    rows_by_dataset: dict[str, int]
    files_written: int
    manifest_paths: list[str]
    checksum_status: str
    completeness_status: str
    fallbacks_used: list[str]
    warnings: list[str]
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class P8C2RunResult:
    stage: str
    scope: str
    mode: Literal["dry-run", "execute"]
    preflight: PreflightResult
    attempted_dates: list[str]
    successful_dates: list[str]
    failed_dates: list[str]
    skipped_complete_dates: list[str]
    incomplete_dates: list[str]
    per_date: list[PerDateIngestStatus]
    replacement_dates_used: bool
    actual_ingest_performed: bool
    dataset_build_performed: bool
    feature_build_performed: bool
    model_fitting_performed: bool
    p8b4_authorized: bool
    temporal_warning_carried_forward: bool
    proxy_bucket_warning_carried_forward: bool
    gate_status: Literal["PASS", "PASS_WITH_FAILURES", "FAIL"]
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "scope": self.scope,
            "mode": self.mode,
            "preflight": self.preflight.to_dict(),
            "frozen_dates": list(FROZEN_STAGE1_DATES),
            "attempted_dates": self.attempted_dates,
            "successful_dates": self.successful_dates,
            "failed_dates": self.failed_dates,
            "skipped_complete_dates": self.skipped_complete_dates,
            "incomplete_dates": self.incomplete_dates,
            "replacement_dates_used": self.replacement_dates_used,
            "actual_ingest_performed": self.actual_ingest_performed,
            "dataset_build_performed": self.dataset_build_performed,
            "feature_build_performed": self.feature_build_performed,
            "model_fitting_performed": self.model_fitting_performed,
            "p8b4_authorized": self.p8b4_authorized,
            "temporal_warning_carried_forward": self.temporal_warning_carried_forward,
            "proxy_bucket_warning_carried_forward": self.proxy_bucket_warning_carried_forward,
            "gate_status": self.gate_status,
            "errors": self.errors,
            "per_date": [p.to_dict() for p in self.per_date],
        }


def load_p8c2_ingest_config(config_path: Path) -> P8C2IngestConfig:
    """Load ML-P8C.2 ingest YAML."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    frozen = tuple(date.fromisoformat(str(d)) for d in raw["frozen_dates"])
    ingest = raw.get("ingest", {})
    safety = raw["safety"]
    resume = raw["resume"]
    failure = raw.get("failure_policy", {})
    warnings_cf = raw.get("warnings_carried_forward", {})
    return P8C2IngestConfig(
        stage=str(raw["stage"]),
        scope=str(raw["scope"]),
        frozen_dates=frozen,
        raw_lake_root=Path(raw["raw_lake_root"]),
        output_reports=Path(raw["output_reports"]),
        root=str(ingest.get("root", "SPXW")),
        index_symbol=str(ingest.get("index_symbol", "SPX")),
        strike_range=int(ingest.get("strike_range", 60)),
        session_rth_start=str(ingest.get("session_rth_start", "09:30:00")),
        session_rth_end=str(ingest.get("session_rth_end", "16:00:00")),
        quote_resolution=str(ingest.get("quote_resolution", "tick_or_1s")),
        index_resolution=str(ingest.get("index_resolution", "tick_or_1s")),
        max_retries=int(ingest.get("max_retries", 2)),
        request_budget_per_date=int(ingest.get("request_budget_per_date", 12)),
        idempotent_skip_existing=bool(ingest.get("idempotent_skip_existing", True)),
        allow_dataset_build=bool(safety["allow_dataset_build"]),
        allow_feature_build=bool(safety["allow_feature_build"]),
        allow_model_fitting=bool(safety["allow_model_fitting"]),
        allow_replacement_dates=bool(safety["allow_replacement_dates"]),
        allow_p8b4=bool(safety["allow_p8b4"]),
        minimum_free_disk_gb=float(safety["minimum_free_disk_gb"]),
        resume_enabled=bool(resume["enabled"]),
        skip_complete_dates=bool(resume["skip_complete_dates"]),
        fail_on_incomplete_existing_partition=bool(
            resume["fail_on_incomplete_existing_partition"]
        ),
        continue_on_date_failure=bool(failure.get("continue_on_date_failure", True)),
        temporal_warning=str(
            warnings_cf.get(
                "temporal_warning",
                "min_new_sessions_2024 got 6 vs target 8 (accepted at P8C.1.1)",
            )
        ),
        proxy_bucket_warning=str(
            warnings_cf.get(
                "proxy_bucket_warning",
                "high_vol/trend buckets used selection_seed proxy without local index",
            )
        ),
    )


def assert_frozen_dates_match_owner(config: P8C2IngestConfig) -> None:
    """Config frozen_dates must match P8C.1.1 owner record exactly."""
    config_set = frozenset(config.frozen_dates)
    if config_set != FROZEN_STAGE1_DATE_SET:
        missing = sorted(FROZEN_STAGE1_DATE_SET - config_set)
        extra = sorted(config_set - FROZEN_STAGE1_DATE_SET)
        raise P8C2ConfigError(
            f"frozen_dates mismatch vs P8C.1.1 owner record: missing={missing} extra={extra}"
        )


def assert_safety_flags(config: P8C2IngestConfig) -> None:
    """Reject any enabled build/fit/replacement flags."""
    violations: list[str] = []
    if config.allow_dataset_build:
        violations.append("allow_dataset_build")
    if config.allow_feature_build:
        violations.append("allow_feature_build")
    if config.allow_model_fitting:
        violations.append("allow_model_fitting")
    if config.allow_replacement_dates:
        violations.append("allow_replacement_dates")
    if config.allow_p8b4:
        violations.append("allow_p8b4")
    if violations:
        raise P8C2ConfigError(f"safety flags must remain false: {violations}")


def validate_date_subset(requested: list[date]) -> None:
    """Every requested date must be in the frozen owner list."""
    for d in requested:
        if d not in FROZEN_STAGE1_DATE_SET:
            raise P8C2ConfigError(
                f"non-frozen date rejected: {d.isoformat()} (replacement dates forbidden)"
            )


def day_type_for_date(trade_date: date) -> str:
    """Return ingest day_type for a frozen date."""
    iso = trade_date.isoformat()
    if iso in KNOWN_EARLY_CLOSE or iso in P8C_FROZEN_EARLY_CLOSE:
        return "early_close"
    return "normal"


def select_dates_to_attempt(
    config: P8C2IngestConfig,
    *,
    dates_filter: list[date] | None,
    max_dates: int | None,
) -> list[date]:
    """Resolve ordered date batch from frozen list."""
    if dates_filter is not None:
        validate_date_subset(dates_filter)
        ordered = sorted(dates_filter)
    else:
        ordered = sorted(config.frozen_dates)
    if max_dates is not None and max_dates > 0:
        ordered = ordered[:max_dates]
    return ordered


def _disk_free_gb(path: Path) -> float:
    target = path if path.exists() else path.parent
    if not target.exists():
        target = Path.cwd()
    usage = shutil.disk_usage(target)
    return usage.free / (1024**3)


def run_preflight(
    config: P8C2IngestConfig,
    *,
    project_root: Path,
    test_connection: bool,
) -> PreflightResult:
    """Run P8C.2 preflight checks (no credential values logged)."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        assert_frozen_dates_match_owner(config)
        assert_safety_flags(config)
        frozen_ok = True
    except P8C2ConfigError as exc:
        frozen_ok = False
        errors.append(str(exc))

    cred_label = credential_source_label()
    creds_present = cred_label != "missing" and resolve_email_password() is not None
    if not creds_present:
        errors.append("ThetaData credentials not present")
        connect_ok: bool | None = False
    elif test_connection:
        try:
            refresh_thetadata_client()
            connect_ok = True
        except (ThetaDataConfigError, OSError, RuntimeError) as exc:
            connect_ok = False
            errors.append(f"ThetaData connection failed: {type(exc).__name__}")
    else:
        connect_ok = None

    lake_root = project_root / config.raw_lake_root
    try:
        lake_root.mkdir(parents=True, exist_ok=True)
        writable = True
    except OSError as exc:
        writable = False
        errors.append(f"raw lake root not writable: {exc}")

    free_gb = _disk_free_gb(lake_root)
    if free_gb < config.minimum_free_disk_gb:
        errors.append(
            f"disk free {free_gb:.1f}GB < minimum {config.minimum_free_disk_gb}GB"
        )

    safety_ok = not any(
        (
            config.allow_dataset_build,
            config.allow_feature_build,
            config.allow_model_fitting,
            config.allow_replacement_dates,
            config.allow_p8b4,
        )
    )

    passed = (
        frozen_ok
        and creds_present
        and writable
        and free_gb >= config.minimum_free_disk_gb
        and safety_ok
        and (connect_ok is not False)
        and not errors
    )

    return PreflightResult(
        passed=passed,
        credential_source=cred_label,
        credentials_present=creds_present,
        thetadata_connect_ok=connect_ok,
        raw_lake_root=str(lake_root),
        raw_lake_root_writable=writable,
        free_disk_gb=round(free_gb, 2),
        frozen_dates_match_owner=frozen_ok,
        safety_flags_ok=safety_ok,
        errors=errors,
        warnings=warnings,
    )


def _all_partition_dirs(
    lake_root: Path,
    trade_date: date,
    *,
    root: str,
    symbol: str,
) -> list[Path]:
    dirs: list[Path] = []
    for ds in (*QUOTE_PARTITIONS, *REQUIRED_OPTION_PARTITIONS, *INDEX_PARTITIONS):
        if ds.startswith("index_"):
            dirs.append(partition_dir(lake_root, ds, trade_date, symbol=symbol))
        else:
            dirs.append(
                partition_dir(lake_root, ds, trade_date, root=root, expiration=trade_date)
            )
    dirs.append(partition_dir(lake_root, "session_metadata", trade_date, root=root))
    return dirs


def _partition_audit(
    lake_root: Path,
    trade_date: date,
    *,
    root: str,
    symbol: str,
) -> tuple[dict[str, int], list[str], str, str]:
    rows: dict[str, int] = {}
    manifest_paths: list[str] = []
    checksum_issues: list[str] = []
    incomplete: list[str] = []

    for part in _all_partition_dirs(lake_root, trade_date, root=root, symbol=symbol):
        ds = next(
            (seg.split("=", 1)[1] for seg in part.parts if seg.startswith("dataset=")),
            part.name,
        )
        manifest = read_manifest(part)
        if manifest is not None:
            manifest_paths.append(str(part / "manifest.json"))
            rows[ds] = int(manifest.get("row_count", 0))
            if manifest.get("ingestion_status") != "complete":
                incomplete.append(ds)
            elif not _partition_checksum_ok(manifest):
                checksum_issues.append(ds)
        elif part.exists():
            incomplete.append(ds)

    checksum_status = "ok" if not checksum_issues else f"missing_hash:{checksum_issues}"
    completeness_status = "complete" if not incomplete else f"incomplete:{incomplete}"
    return rows, manifest_paths, checksum_status, completeness_status


def _partition_checksum_ok(manifest: dict[str, Any]) -> bool:
    files = manifest.get("files") or []
    return bool(files) and all(bool(f.get("sha256")) for f in files)


def _extract_fallbacks(result: DateIngestResult) -> list[str]:
    fallbacks: list[str] = []
    if result.quote_fallback_reason:
        fallbacks.append(result.quote_fallback_reason)
    for key, val in (result.resolutions_used or {}).items():
        fallbacks.append(f"{key}:{val}")
    plan = (result.partition_summaries or {}).get("plan") or {}
    if isinstance(plan, dict) and plan.get("quote_fallback"):
        fallbacks.append(str(plan["quote_fallback"]))
    return fallbacks


def _map_ingest_result(
    trade_date: date,
    result: DateIngestResult,
    *,
    lake_root: Path,
    root: str,
    symbol: str,
    started_at: datetime,
    finished_at: datetime,
) -> PerDateIngestStatus:
    rows, manifest_paths, checksum_status, completeness_status = _partition_audit(
        lake_root, trade_date, root=root, symbol=symbol
    )
    files_written = sum(1 for p in manifest_paths if Path(p).exists())

    if "incomplete_partition" in result.reason:
        status: DateIngestStatus = "incomplete"
    elif result.success and result.skipped:
        status = "skipped_complete"
    elif result.success:
        status = "success"
    else:
        status = "failed"

    fallbacks = _extract_fallbacks(result)
    if result.reason and "fallback" in result.reason:
        fallbacks.append(result.reason)

    error_message = None if result.success else result.reason

    return PerDateIngestStatus(
        date=trade_date.isoformat(),
        status=status,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=round(result.ingest_wall_sec, 3),
        rows_by_dataset=rows,
        files_written=files_written,
        manifest_paths=manifest_paths,
        checksum_status=checksum_status,
        completeness_status=completeness_status,
        fallbacks_used=fallbacks,
        warnings=[],
        error_message=error_message,
    )


def _status_from_readiness(
    trade_date: date,
    *,
    lake_root: Path,
    root: str,
    symbol: str,
    idempotent_skip_existing: bool,
    fail_on_incomplete: bool,
    started_at: datetime,
) -> PerDateIngestStatus | None:
    """Return terminal skip/incomplete status without calling ThetaData."""
    complete, missing, incomplete = check_partition_readiness(
        lake_root,
        trade_date,
        root=root,
        symbol=symbol,
        idempotent_skip_existing=idempotent_skip_existing,
    )
    finished_at = datetime.now(UTC)

    if incomplete and fail_on_incomplete:
        return PerDateIngestStatus(
            date=trade_date.isoformat(),
            status="incomplete",
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=0.0,
            rows_by_dataset={},
            files_written=0,
            manifest_paths=[],
            checksum_status="not_checked",
            completeness_status=f"incomplete_refuse:{incomplete}",
            fallbacks_used=[],
            warnings=[],
            error_message=f"incomplete partitions refuse overwrite: {','.join(incomplete)}",
        )

    if not missing and complete and idempotent_skip_existing:
        rows, manifest_paths, checksum_status, completeness_status = _partition_audit(
            lake_root, trade_date, root=root, symbol=symbol
        )
        return PerDateIngestStatus(
            date=trade_date.isoformat(),
            status="skipped_complete",
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=0.0,
            rows_by_dataset=rows,
            files_written=len(manifest_paths),
            manifest_paths=manifest_paths,
            checksum_status=checksum_status,
            completeness_status=completeness_status,
            fallbacks_used=[],
            warnings=[],
            error_message=None,
        )
    return None


def ingest_one_frozen_date(
    config: P8C2IngestConfig,
    trade_date: date,
    *,
    lake_root: Path,
    dry_run: bool,
) -> PerDateIngestStatus:
    """Ingest or plan one frozen date."""
    validate_date_subset([trade_date])
    started_at = datetime.now(UTC)

    if config.resume_enabled and config.skip_complete_dates and not dry_run:
        pre = _status_from_readiness(
            trade_date,
            lake_root=lake_root,
            root=config.root,
            symbol=config.index_symbol,
            idempotent_skip_existing=config.idempotent_skip_existing,
            fail_on_incomplete=config.fail_on_incomplete_existing_partition,
            started_at=started_at,
        )
        if pre is not None:
            return pre

    day_type = day_type_for_date(trade_date)
    result = ingest_rth_trade_date(
        trade_date=trade_date,
        day_type=day_type,
        lake_root=lake_root,
        root=config.root,
        symbol=config.index_symbol,
        strike_range=config.strike_range,
        session_rth_start=config.session_rth_start,
        session_rth_end=config.session_rth_end,
        quote_resolution=config.quote_resolution,  # type: ignore[arg-type]
        index_resolution=config.index_resolution,  # type: ignore[arg-type]
        max_retries=config.max_retries,
        request_budget_per_date=config.request_budget_per_date,
        idempotent_skip_existing=config.idempotent_skip_existing,
        dry_run=dry_run,
    )
    finished_at = datetime.now(UTC)
    return _map_ingest_result(
        trade_date,
        result,
        lake_root=lake_root,
        root=config.root,
        symbol=config.index_symbol,
        started_at=started_at,
        finished_at=finished_at,
    )


def run_p8c2_controlled_ingest(
    config: P8C2IngestConfig,
    *,
    project_root: Path,
    execute: bool,
    resume: bool,
    dates_filter: list[date] | None,
    max_dates: int | None,
) -> P8C2RunResult:
    """Run ML-P8C.2 controlled ingest (dry-run default)."""
    assert_frozen_dates_match_owner(config)
    assert_safety_flags(config)

    mode: Literal["dry-run", "execute"] = "execute" if execute else "dry-run"
    preflight = run_preflight(
        config,
        project_root=project_root,
        test_connection=execute,
    )

    if not preflight.passed:
        return P8C2RunResult(
            stage=HARNESS_STAGE_P8C2,
            scope=SCOPE_RAW_LAKE_INGEST_ONLY,
            mode=mode,
            preflight=preflight,
            attempted_dates=[],
            successful_dates=[],
            failed_dates=[],
            skipped_complete_dates=[],
            incomplete_dates=[],
            per_date=[],
            replacement_dates_used=False,
            actual_ingest_performed=False,
            dataset_build_performed=False,
            feature_build_performed=False,
            model_fitting_performed=False,
            p8b4_authorized=False,
            temporal_warning_carried_forward=True,
            proxy_bucket_warning_carried_forward=True,
            gate_status="FAIL",
            errors=preflight.errors,
        )

    if resume and not config.resume_enabled:
        log.warning("resume requested but config.resume.enabled=false")

    dates = select_dates_to_attempt(config, dates_filter=dates_filter, max_dates=max_dates)
    lake_root = project_root / config.raw_lake_root
    lake_root.mkdir(parents=True, exist_ok=True)

    per_date: list[PerDateIngestStatus] = []
    for trade_date in dates:
        log.info("%s ingest %s mode=%s", HARNESS_STAGE_P8C2, trade_date, mode)
        status = ingest_one_frozen_date(
            config,
            trade_date,
            lake_root=lake_root,
            dry_run=not execute,
        )
        per_date.append(status)
        if status.status == "failed" and not config.continue_on_date_failure:
            break

    successful = [p.date for p in per_date if p.status == "success"]
    failed = [p.date for p in per_date if p.status == "failed"]
    skipped = [p.date for p in per_date if p.status == "skipped_complete"]
    incomplete = [p.date for p in per_date if p.status == "incomplete"]

    if failed or incomplete:
        gate: Literal["PASS", "PASS_WITH_FAILURES", "FAIL"] = (
            "PASS_WITH_FAILURES" if execute else "PASS"
        )
    else:
        gate = "PASS"

    return P8C2RunResult(
        stage=HARNESS_STAGE_P8C2,
        scope=SCOPE_RAW_LAKE_INGEST_ONLY,
        mode=mode,
        preflight=preflight,
        attempted_dates=[d.isoformat() for d in dates],
        successful_dates=successful,
        failed_dates=failed,
        skipped_complete_dates=skipped,
        incomplete_dates=incomplete,
        per_date=per_date,
        replacement_dates_used=False,
        actual_ingest_performed=execute,
        dataset_build_performed=False,
        feature_build_performed=False,
        model_fitting_performed=False,
        p8b4_authorized=False,
        temporal_warning_carried_forward=True,
        proxy_bucket_warning_carried_forward=True,
        gate_status=gate,
    )


def write_p8c2_artifacts(result: P8C2RunResult, output_dir: Path) -> dict[str, Path]:
    """Write P8C.2 status JSON artifacts (local only; do not commit)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "p8c2_ingest_status.json"
    per_date_path = output_dir / "p8c2_per_date_status.json"
    manifest_path = output_dir / "p8c2_run_manifest.json"

    status_path.write_text(
        json.dumps(
            {
                "gate_status": result.gate_status,
                "mode": result.mode,
                "attempted_dates": result.attempted_dates,
                "successful_dates": result.successful_dates,
                "failed_dates": result.failed_dates,
                "skipped_complete_dates": result.skipped_complete_dates,
                "incomplete_dates": result.incomplete_dates,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    per_date_path.write_text(
        json.dumps([p.to_dict() for p in result.per_date], indent=2),
        encoding="utf-8",
    )
    manifest = {
        "stage": result.stage,
        "scope": result.scope,
        "frozen_dates": list(FROZEN_STAGE1_DATES),
        "attempted_dates": result.attempted_dates,
        "successful_dates": result.successful_dates,
        "failed_dates": result.failed_dates,
        "skipped_complete_dates": result.skipped_complete_dates,
        "incomplete_dates": result.incomplete_dates,
        "replacement_dates_used": result.replacement_dates_used,
        "actual_ingest_performed": result.actual_ingest_performed,
        "dataset_build_performed": result.dataset_build_performed,
        "feature_build_performed": result.feature_build_performed,
        "model_fitting_performed": result.model_fitting_performed,
        "p8b4_authorized": result.p8b4_authorized,
        "temporal_warning_carried_forward": result.temporal_warning_carried_forward,
        "proxy_bucket_warning_carried_forward": result.proxy_bucket_warning_carried_forward,
        "preflight": result.preflight.to_dict(),
        "gate_status": result.gate_status,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "status": status_path,
        "per_date": per_date_path,
        "manifest": manifest_path,
    }
