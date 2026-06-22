"""ML-P8C.1 deterministic expansion candidate date selection (no ingest)."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import subprocess
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

from quant_lab.data.intraday_lake import partition_dir
from quant_lab.data.intraday_manifest import is_partition_complete
from quant_lab.ml.datasets.sample_builder import (
    INDEX_DATASETS,
    SampleBuildConfig,
    load_sample_config,
    missing_partitions_for_date,
)

log = logging.getLogger(__name__)

HARNESS_STAGE_P8C1 = "ML-P8C.1"
SELECTION_RULES_VERSION = "p8c_date_rules_v1"

PRIMARY_BUCKET_PRIORITY: tuple[str, ...] = (
    "early_close",
    "monthly_opex",
    "high_vol",
    "trend",
    "recent",
    "normal_range",
)

BucketName = Literal[
    "normal_range",
    "high_vol",
    "trend",
    "monthly_opex",
    "early_close",
    "recent",
]

# NYSE early-close sessions (calendar rule supplement) through 2025-H1
KNOWN_EARLY_CLOSE: frozenset[str] = frozenset(
    {
        "2023-11-24",
        "2024-07-03",
        "2024-11-29",
        "2025-07-03",
    }
)


@dataclass
class P8CSelectionConfig:
    stage: str
    selection_seed: int
    selection_rules_version: str
    existing_sample_configs: list[Path]
    baseline_config_primary: Path
    current_session_count: int
    target_total_sessions: int
    new_sessions_required: int
    bucket_quotas: dict[str, int]
    selection_rules: dict[str, bool]
    pool_start: date
    pool_end: date
    candidate_years: list[int]
    exclude_existing_sessions: bool
    exclude_known_problem_dates: bool
    temporal_constraints: dict[str, int]
    trend_thresholds: dict[str, float]
    lake_root: Path
    dataset_root: Path
    feature_root: Path
    root: str
    index_symbol: str
    known_problem_dates: frozenset[str]
    output_dir: Path
    cost_assumptions: dict[str, float]


@dataclass
class SessionIndexStats:
    session_range_pct: float
    session_return_pct: float
    source: str


@dataclass
class CandidateRecord:
    trade_date: str
    year: int
    quarter: int
    primary_bucket: str
    secondary_buckets: list[str]
    bucket_reason: str
    selection_source: str
    selection_seed: int
    index_stats_available: bool
    owner_review_recommended: bool = False
    selected_rank_within_bucket: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AvailabilityRecord:
    date: str
    raw_lake_status: str
    dataset_status: str
    feature_status: str
    missing_partitions: list[str]
    estimated_ingest_needed: bool
    estimated_build_needed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BucketQuotaSummary:
    bucket: str
    quota: int
    selected_count: int
    selected_dates: list[str]
    underfilled_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class P8C1SelectionResult:
    phase: str = HARNESS_STAGE_P8C1
    dry_run: bool = True
    p8c1_pass: bool = False
    existing_sessions: list[str] = field(default_factory=list)
    excluded_existing_sessions: list[str] = field(default_factory=list)
    candidate_pool_size: int = 0
    selected_dates: list[dict[str, Any]] = field(default_factory=list)
    bucket_quota_summary: list[dict[str, Any]] = field(default_factory=list)
    availability_summary: list[dict[str, Any]] = field(default_factory=list)
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    manifest_path: Path | None = None
    cost_estimate_path: Path | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.manifest_path is not None:
            data["manifest_path"] = str(self.manifest_path)
        if self.cost_estimate_path is not None:
            data["cost_estimate_path"] = str(self.cost_estimate_path)
        return data


def load_p8c_selection_config(path: Path) -> P8CSelectionConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    current = raw.get("current_sample_config") or {}
    stage1 = raw.get("stage1_target") or {}
    pool = raw.get("candidate_pool") or {}
    paths = raw.get("paths") or {}
    outputs = raw.get("output_reports") or {}
    cost = raw.get("cost_estimate_assumptions") or {}
    configs = [Path(p) for p in current.get("existing_sample_configs") or []]
    known = frozenset(str(d) for d in raw.get("known_problem_dates") or [])
    return P8CSelectionConfig(
        stage=str(raw.get("stage", HARNESS_STAGE_P8C1)),
        selection_seed=int(raw.get("selection_seed", 20260621)),
        selection_rules_version=str(raw.get("selection_rules_version", SELECTION_RULES_VERSION)),
        existing_sample_configs=configs,
        baseline_config_primary=Path(
            current.get("baseline_config_primary", "config/ml/pit_sample_baseline_v1_1_validation.yaml")
        ),
        current_session_count=int(current.get("current_session_count", 19)),
        target_total_sessions=int(stage1.get("target_total_sessions", 40)),
        new_sessions_required=int(stage1.get("new_sessions_required", 21)),
        bucket_quotas={str(k): int(v) for k, v in (raw.get("bucket_quotas") or {}).items()},
        selection_rules={str(k): bool(v) for k, v in (raw.get("selection_rules") or {}).items()},
        pool_start=date.fromisoformat(str(pool.get("start_date", "2023-01-01"))),
        pool_end=date.fromisoformat(str(pool.get("end_date", "2025-06-30"))),
        candidate_years=[int(y) for y in pool.get("candidate_years") or [2023, 2024, 2025]],
        exclude_existing_sessions=bool(pool.get("exclude_existing_sessions", True)),
        exclude_known_problem_dates=bool(pool.get("exclude_known_problem_dates", True)),
        temporal_constraints={str(k): int(v) for k, v in (raw.get("temporal_constraints") or {}).items()},
        trend_thresholds={str(k): float(v) for k, v in (raw.get("trend_thresholds") or {}).items()},
        lake_root=Path(paths.get("lake_root", "artifacts/raw_lake_sample")),
        dataset_root=Path(paths.get("dataset_root", "artifacts/datasets/pit_sample_baseline_v1_1_validation")),
        feature_root=Path(paths.get("feature_root", "artifacts/features/pit_features_baseline_v1_1_validation")),
        root=str(paths.get("root", "SPXW")),
        index_symbol=str(paths.get("index_symbol", "SPX")),
        known_problem_dates=known,
        output_dir=Path(outputs.get("output_dir", "artifacts/reports/p8c_candidate_selection")),
        cost_assumptions={str(k): float(v) for k, v in cost.items()},
    )


def validate_selection_rules_flags(rules: dict[str, bool]) -> list[str]:
    errors: list[str] = []
    required = (
        "no_model_performance_selection",
        "no_target_based_selection",
        "no_pnl_selection",
        "no_manual_cherry_pick",
        "deterministic_with_seed",
    )
    for key in required:
        if not rules.get(key):
            errors.append(f"selection_rules.{key} must be true")
    return errors


def load_existing_sessions(config_paths: list[Path], project_root: Path) -> list[str]:
    sessions: set[str] = set()
    for rel in config_paths:
        path = rel if rel.is_absolute() else project_root / rel
        if not path.is_file():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for item in raw.get("dates") or []:
            sessions.add(str(item["date"]))
        for skip in raw.get("skip_dates") or []:
            sessions.discard(str(skip))
    return sorted(sessions)


def _git_commit(project_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def generate_trading_days(start: date, end: date) -> list[date]:
    cal = USFederalHolidayCalendar()
    bday = CustomBusinessDay(calendar=cal)
    idx = pd.date_range(start=start.isoformat(), end=end.isoformat(), freq=bday)
    return [d.date() for d in idx]


def _stable_bucket(key: str, seed: int, n: int) -> int:
    digest = hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()
    return int(digest[:8], 16) % n


def _proxy_vol_label(trade_date: date, seed: int) -> str:
    """Deterministic calendar stratification proxy when index path unavailable."""
    slot = _stable_bucket(trade_date.isoformat(), seed, 3)
    if slot == 2:
        return "high_vol"
    if slot == 0:
        return "low_vol"
    return "medium_vol"


def _proxy_trend_eligible(trade_date: date, seed: int) -> bool:
    """Deterministic trend-bucket proxy (not model- or label-based)."""
    return _stable_bucket(f"{trade_date.isoformat()}:trend", seed, 5) == 0


def is_third_friday(d: date) -> bool:
    if d.weekday() != 4:
        return False
    return 15 <= d.day <= 21


def is_opex_adjacent(d: date, trading_days: list[date]) -> bool:
    """T-1 trading day before monthly SPX expiration Friday."""
    if d.weekday() != 4:
        return False
    idx = trading_days.index(d) if d in trading_days else -1
    if idx < 0 or idx + 1 >= len(trading_days):
        return False
    nxt = trading_days[idx + 1]
    return is_third_friday(nxt)


def is_early_close_session(d: date) -> bool:
    iso = d.isoformat()
    return (
        iso in KNOWN_EARLY_CLOSE
        or (d.month == 7 and d.day == 3 and d.weekday() < 5)
        or (d.month == 11 and d.weekday() == 4 and 22 <= d.day <= 28)
    )


def _read_index_session_stats(
    lake_root: Path,
    trade_date: date,
    *,
    index_symbol: str,
) -> SessionIndexStats | None:
    for ds in INDEX_DATASETS:
        part = partition_dir(lake_root, ds, trade_date, symbol=index_symbol)
        if not is_partition_complete(part):
            continue
        parquet_path = part / "part-000.parquet"
        if not parquet_path.is_file():
            continue
        df = pd.read_parquet(parquet_path)
        price_col = None
        for col in ("price", "last", "close", "mid"):
            if col in df.columns:
                price_col = col
                break
        if price_col is None:
            continue
        prices = pd.to_numeric(df[price_col], errors="coerce").dropna()
        if prices.empty:
            continue
        spot_open = float(prices.iloc[0])
        spot_last = float(prices.iloc[-1])
        session_high = float(prices.max())
        session_low = float(prices.min())
        if spot_open <= 0:
            continue
        return SessionIndexStats(
            session_range_pct=(session_high - session_low) / spot_open * 100.0,
            session_return_pct=(spot_last - spot_open) / spot_open * 100.0,
            source=ds,
        )
    return None


def _vol_tercile_labels(
    stats_by_date: dict[str, SessionIndexStats],
) -> dict[str, str]:
    if not stats_by_date:
        return {}
    ranges = np.array([s.session_range_pct for s in stats_by_date.values()], dtype=float)
    p33, p67 = float(np.percentile(ranges, 33.33)), float(np.percentile(ranges, 66.67))
    out: dict[str, str] = {}
    for d_str, st in stats_by_date.items():
        if st.session_range_pct <= p33:
            out[d_str] = "low_vol"
        elif st.session_range_pct <= p67:
            out[d_str] = "medium_vol"
        else:
            out[d_str] = "high_vol"
    return out


def tag_candidate_buckets(
    trade_date: date,
    *,
    trading_days: list[date],
    vol_label: str | None,
    index_stats: SessionIndexStats | None,
    trend_thresholds: dict[str, float],
    post_test_cutoff: date,
    selection_seed: int,
) -> tuple[list[str], str, bool]:
    tags: list[str] = []
    reasons: list[str] = []
    owner_review = False

    if is_early_close_session(trade_date):
        tags.append("early_close")
        reasons.append("calendar early_close rule")
    if is_third_friday(trade_date) or is_opex_adjacent(trade_date, trading_days):
        tags.append("monthly_opex")
        reasons.append("SPX monthly OPEX calendar rule")
    if trade_date.year >= 2025 and trade_date > post_test_cutoff:
        tags.append("recent")
        reasons.append("post baseline test window / recent year")

    if vol_label is None and index_stats is None:
        vol_label = _proxy_vol_label(trade_date, selection_seed)
        reasons.append(f"proxy vol stratification ({vol_label}); owner review before P8C.2")
        owner_review = True

    if vol_label == "high_vol":
        tags.append("high_vol")
        reasons.append("session_range_pct high tercile (index path)")
    if index_stats is not None:
        ret = index_stats.session_return_pct
        up_th = float(trend_thresholds.get("trend_up_pct", 0.30))
        dn_th = float(trend_thresholds.get("trend_down_pct", -0.30))
        rb_th = float(trend_thresholds.get("range_bound_abs_pct", 0.15))
        if ret > up_th:
            tags.append("trend")
            reasons.append(f"session_return_pct>{up_th}")
        elif ret < dn_th:
            tags.append("trend")
            reasons.append(f"session_return_pct<{dn_th}")
        elif abs(ret) <= rb_th and vol_label in ("low_vol", "medium_vol"):
            tags.append("normal_range")
            reasons.append("range_bound rule")
    elif index_stats is None and _proxy_trend_eligible(trade_date, selection_seed):
        tags.append("trend")
        reasons.append("proxy trend stratification; owner review before P8C.2")
        owner_review = True
    elif not tags:
        tags.append("normal_range")
        reasons.append("default normal_range (no index stats)")
        owner_review = True
    elif "normal_range" not in tags and "high_vol" not in tags and "trend" not in tags:
        tags.append("normal_range")
        reasons.append("calendar-only candidate")

    if not tags:
        tags = ["normal_range"]
        reasons = ["fallback normal_range"]
        owner_review = True

    # primary by scarcity priority
    primary = "normal_range"
    for bucket in PRIMARY_BUCKET_PRIORITY:
        if bucket in tags:
            primary = bucket
            break

    return tags, primary, owner_review


def assign_primary_bucket(tags: list[str]) -> str:
    for bucket in PRIMARY_BUCKET_PRIORITY:
        if bucket in tags:
            return bucket
    return "normal_range"


def select_dates_for_bucket(
    candidates: list[CandidateRecord],
    bucket: str,
    quota: int,
    *,
    seed: int,
    already_selected: set[str],
) -> list[CandidateRecord]:
    pool = [
        c
        for c in candidates
        if c.trade_date not in already_selected and c.primary_bucket == bucket
    ]
    pool.sort(key=lambda c: c.trade_date)
    rng = random.Random(seed + hash(bucket) % 10000)
    rng.shuffle(pool)
    return pool[:quota]


def build_candidate_pool(
    config: P8CSelectionConfig,
    *,
    existing_sessions: set[str],
    project_root: Path,
) -> list[CandidateRecord]:
    lake_root = config.lake_root if config.lake_root.is_absolute() else project_root / config.lake_root
    trading_days = generate_trading_days(config.pool_start, config.pool_end)
    post_test = date(2025, 5, 2)

    pool_dates: list[date] = []
    for d in trading_days:
        iso = d.isoformat()
        if config.exclude_existing_sessions and iso in existing_sessions:
            continue
        if config.exclude_known_problem_dates and iso in config.known_problem_dates:
            continue
        if d.year not in config.candidate_years:
            continue
        pool_dates.append(d)

    stats_map: dict[str, SessionIndexStats] = {}
    for d in pool_dates:
        st = _read_index_session_stats(
            lake_root, d, index_symbol=config.index_symbol
        )
        if st is not None:
            stats_map[d.isoformat()] = st

    vol_labels = _vol_tercile_labels(stats_map)
    records: list[CandidateRecord] = []
    for d in pool_dates:
        iso = d.isoformat()
        st = stats_map.get(iso)
        tags, primary, owner_review = tag_candidate_buckets(
            d,
            trading_days=trading_days,
            vol_label=vol_labels.get(iso),
            index_stats=st,
            trend_thresholds=config.trend_thresholds,
            post_test_cutoff=post_test,
            selection_seed=config.selection_seed,
        )
        secondary = [t for t in tags if t != primary]
        records.append(
            CandidateRecord(
                trade_date=iso,
                year=d.year,
                quarter=(d.month - 1) // 3 + 1,
                primary_bucket=primary,
                secondary_buckets=secondary,
                bucket_reason="; ".join(
                    [
                        f"primary={primary}",
                        f"tags={','.join(tags)}",
                        f"index_stats={'yes' if st else 'no'}",
                    ]
                ),
                selection_source=SELECTION_RULES_VERSION,
                selection_seed=config.selection_seed,
                index_stats_available=st is not None,
                owner_review_recommended=owner_review,
            )
        )
    return records


def select_stage1_dates(
    candidates: list[CandidateRecord],
    quotas: dict[str, int],
    *,
    seed: int,
) -> tuple[list[CandidateRecord], list[BucketQuotaSummary]]:
    selected: list[CandidateRecord] = []
    selected_ids: set[str] = set()
    summaries: list[BucketQuotaSummary] = []

    for bucket, quota in quotas.items():
        picks_raw = select_dates_for_bucket(
            candidates, bucket, quota, seed=seed, already_selected=selected_ids
        )
        picks: list[CandidateRecord] = []
        for i, p in enumerate(picks_raw):
            selected_ids.add(p.trade_date)
            rec = replace(p, selected_rank_within_bucket=i + 1)
            picks.append(rec)
            selected.append(rec)
        reason: str | None = None
        if len(picks) < quota:
            reason = (
                f"underfilled: {len(picks)}/{quota}; "
                "owner review required before P8C.2"
            )
        summaries.append(
            BucketQuotaSummary(
                bucket=bucket,
                quota=quota,
                selected_count=len(picks),
                selected_dates=[p.trade_date for p in picks],
                underfilled_reason=reason,
            )
        )
    selected.sort(key=lambda c: c.trade_date)

    # Spill: if under target due to bucket underfill, add normal_range candidates
    target = sum(quotas.values())
    if len(selected) < target:
        spill_pool = [
            c
            for c in candidates
            if c.trade_date not in selected_ids and c.primary_bucket == "normal_range"
        ]
        spill_pool.sort(key=lambda c: c.trade_date)
        rng = random.Random(seed + 9999)
        rng.shuffle(spill_pool)
        need = target - len(selected)
        for i, c in enumerate(spill_pool[:need]):
            rec = replace(
                c,
                bucket_reason=c.bucket_reason + "; spill_fill",
                selected_rank_within_bucket=i + 1,
            )
            selected.append(rec)
            selected_ids.add(rec.trade_date)
        if need > len(spill_pool):
            summaries.append(
                BucketQuotaSummary(
                    bucket="_spill",
                    quota=need,
                    selected_count=len(spill_pool),
                    selected_dates=[c.trade_date for c in spill_pool],
                    underfilled_reason="spill pool exhausted; owner review required",
                )
            )

    selected.sort(key=lambda c: c.trade_date)
    return selected, summaries


def check_date_availability(
    trade_date: date,
    *,
    sample_config: SampleBuildConfig,
    dataset_root: Path,
    feature_root: Path,
) -> AvailabilityRecord:
    iso = trade_date.isoformat()
    missing = missing_partitions_for_date(sample_config, trade_date)
    if not missing:
        raw_status = "already_available"
    elif len(missing) <= 2:
        raw_status = "incomplete"
    else:
        raw_status = "missing"

    ds_shard = dataset_root / "per_date" / f"{iso}.parquet"
    dataset_status = "already_available" if ds_shard.is_file() else "missing"

    feat_shard = feature_root / "per_date" / f"{iso}.parquet"
    feature_status = "already_available" if feat_shard.is_file() else "missing"

    ingest_needed = raw_status != "already_available"
    build_needed = dataset_status != "already_available" or feature_status != "already_available"

    return AvailabilityRecord(
        date=iso,
        raw_lake_status=raw_status,
        dataset_status=dataset_status,
        feature_status=feature_status,
        missing_partitions=missing,
        estimated_ingest_needed=ingest_needed,
        estimated_build_needed=build_needed,
    )


def estimate_build_cost(
    availability: list[AvailabilityRecord],
    assumptions: dict[str, float],
) -> dict[str, Any]:
    ingest_days = sum(1 for a in availability if a.estimated_ingest_needed)
    build_days = sum(1 for a in availability if a.estimated_build_needed)
    n = len(availability) or 1

    def _sum(prefix: str, count: int) -> dict[str, float]:
        return {
            "low": count * assumptions.get(f"{prefix}_low", 0.0),
            "base": count * assumptions.get(f"{prefix}_base", 0.0),
            "high": count * assumptions.get(f"{prefix}_high", 0.0),
        }

    ingest_min = _sum("ingest_minutes_per_date", ingest_days)
    ds_min = _sum("dataset_build_minutes_per_date", build_days)
    feat_min = _sum("feature_build_minutes_per_date", build_days)
    storage = _sum("storage_gb_per_date", ingest_days)

    runtime_low = ingest_min["low"] + ds_min["low"] + feat_min["low"]
    runtime_base = ingest_min["base"] + ds_min["base"] + feat_min["base"]
    runtime_high = ingest_min["high"] + ds_min["high"] + feat_min["high"]

    return {
        "estimated_new_raw_lake_days": ingest_days,
        "estimated_dataset_build_days": build_days,
        "estimated_feature_build_days": build_days,
        "estimated_dates_already_available": sum(
            1 for a in availability if a.raw_lake_status == "already_available"
        ),
        "estimated_runtime_minutes": {
            "low": runtime_low,
            "base": runtime_base,
            "high": runtime_high,
        },
        "estimated_storage_gb": storage,
        "selected_date_count": n,
        "main_risk_factors": [
            "ThetaData API rate limits and entitlement",
            "early_close sessions shorter but metadata must be correct",
            "high-volume days may increase ingest wall time",
            "feature build may dominate total runtime vs ingest",
            "estimates are planning bounds — not SLA guarantees",
        ],
        "disclaimer": "Estimates based on P7.6/P8B.1 experience; actual runtime may vary.",
    }


def validate_temporal_constraints(
    selected: list[CandidateRecord],
    constraints: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    by_year: dict[int, int] = {}
    for c in selected:
        by_year[c.year] = by_year.get(c.year, 0) + 1
    for year, min_key in ((2023, "min_new_sessions_2023"), (2024, "min_new_sessions_2024"), (2025, "min_new_sessions_2025")):
        need = constraints.get(min_key, 0)
        got = by_year.get(year, 0)
        if got < need:
            errors.append(f"temporal constraint {min_key}: got {got}, need {need}")
    post_need = constraints.get("min_post_baseline_test_window", 0)
    post_got = sum(1 for c in selected if c.trade_date > "2025-05-02")
    if post_got < post_need:
        errors.append(f"post baseline test window: got {post_got}, need {post_need}")
    return errors


def run_p8c1_selection(
    config: P8CSelectionConfig,
    *,
    project_root: Path,
    execute: bool = False,
) -> P8C1SelectionResult:
    result = P8C1SelectionResult(dry_run=not execute)

    rule_errors = validate_selection_rules_flags(config.selection_rules)
    if rule_errors:
        result.errors.extend(rule_errors)
        return result

    quota_sum = sum(config.bucket_quotas.values())
    if quota_sum != config.new_sessions_required:
        result.errors.append(
            f"bucket quota sum {quota_sum} != new_sessions_required {config.new_sessions_required}"
        )
        return result

    config_paths = [
        p if p.is_absolute() else project_root / p for p in config.existing_sample_configs
    ]
    existing = load_existing_sessions(config_paths, project_root)
    result.existing_sessions = existing
    result.excluded_existing_sessions = list(existing)

    if len(existing) != config.current_session_count:
        log.warning(
            "existing session count %d != config current_session_count %d",
            len(existing),
            config.current_session_count,
        )

    candidates = build_candidate_pool(
        config, existing_sessions=set(existing), project_root=project_root
    )
    result.candidate_pool_size = len(candidates)

    if not execute:
        result.p8c1_pass = len(result.errors) == 0
        return result

    selected, quota_summary = select_stage1_dates(
        candidates,
        config.bucket_quotas,
        seed=config.selection_seed,
    )
    if len(selected) != config.new_sessions_required:
        result.errors.append(
            f"selected {len(selected)} != required {config.new_sessions_required}"
        )

    temporal_warnings = validate_temporal_constraints(selected, config.temporal_constraints)

    baseline_path = (
        config.baseline_config_primary
        if config.baseline_config_primary.is_absolute()
        else project_root / config.baseline_config_primary
    )
    sample_cfg = load_sample_config(baseline_path)
    lake_root = config.lake_root if config.lake_root.is_absolute() else project_root / config.lake_root
    dataset_root = (
        config.dataset_root if config.dataset_root.is_absolute() else project_root / config.dataset_root
    )
    feature_root = (
        config.feature_root if config.feature_root.is_absolute() else project_root / config.feature_root
    )
    sample_cfg = replace(sample_cfg, lake_root=lake_root)

    availability: list[AvailabilityRecord] = []
    for rec in selected:
        availability.append(
            check_date_availability(
                date.fromisoformat(rec.trade_date),
                sample_config=sample_cfg,
                dataset_root=dataset_root,
                feature_root=feature_root,
            )
        )

    cost = estimate_build_cost(availability, config.cost_assumptions)

    result.selected_dates = [c.to_dict() for c in selected]
    result.bucket_quota_summary = [s.to_dict() for s in quota_summary]
    result.availability_summary = [a.to_dict() for a in availability]
    result.cost_estimate = cost

    out_dir = config.output_dir if config.output_dir.is_absolute() else project_root / config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "stage": HARNESS_STAGE_P8C1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "code_commit": _git_commit(project_root),
        "selection_seed": config.selection_seed,
        "selection_rules_version": config.selection_rules_version,
        "existing_sessions": existing,
        "excluded_existing_sessions": existing,
        "candidate_pool_size": result.candidate_pool_size,
        "selected_dates": result.selected_dates,
        "bucket_quota_summary": result.bucket_quota_summary,
        "availability_summary": result.availability_summary,
        "cost_estimate_summary": cost,
        "forbidden_selection_inputs_used": False,
        "model_performance_used": False,
        "target_based_selection_used": False,
        "actual_ingest_performed": False,
        "dataset_build_performed": False,
        "feature_build_performed": False,
        "model_fitting_performed": False,
        "p8b4_authorized": False,
        "target_total_sessions": config.target_total_sessions,
        "new_sessions_required": config.new_sessions_required,
        "temporal_constraint_warnings": temporal_warnings,
    }

    manifest_path = out_dir / "p8c1_candidate_selection_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    result.manifest_path = manifest_path

    cost_path = out_dir / "p8c1_cost_estimate.json"
    cost_path.write_text(json.dumps(cost, indent=2), encoding="utf-8")
    result.cost_estimate_path = cost_path

    result.p8c1_pass = (
        len(selected) == config.new_sessions_required
        and all(s.selected_count > 0 or s.underfilled_reason for s in quota_summary)
        and not any("selected" in e for e in result.errors)
    )
    return result


__all__ = [
    "HARNESS_STAGE_P8C1",
    "P8C1SelectionResult",
    "P8CSelectionConfig",
    "assign_primary_bucket",
    "build_candidate_pool",
    "estimate_build_cost",
    "generate_trading_days",
    "load_existing_sessions",
    "load_p8c_selection_config",
    "run_p8c1_selection",
    "select_stage1_dates",
    "validate_selection_rules_flags",
]
