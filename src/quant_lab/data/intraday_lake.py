"""Immutable ThetaData raw event lake: paths, normalize, atomic ingest (ML-P3)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_manifest import (
    PartitionFileMeta,
    PartitionManifest,
    SourceRequestMeta,
    enrich_manifest_timestamp_bounds,
    is_partition_complete,
    manifest_path,
    read_manifest,
    sha256_file,
    verify_partition_files,
    write_manifest_dict,
)
from quant_lab.data.intraday_schema import (
    EVENT_TIMEZONE,
    GAMMA_METHOD,
    GAMMA_METHOD_VERSION,
    OI_SEMANTICS_DEFAULT,
    SETTLEMENT_CONFIDENCE_DEFAULT,
    SETTLEMENT_SOURCE_DEFAULT,
    SETTLEMENT_UNKNOWN,
    SOURCE,
    SOURCE_CLIENT,
    SOURCE_SCHEMA_VERSION,
    dataset_schema_version,
    validate_required_columns,
)
from quant_lab.data.intraday_time import intraday_time_to_expiry_years, session_datetime
from quant_lab.factors.gex import black76_gamma
from quant_lab.factors.rates import resolve_gex_inputs

log = logging.getLogger(__name__)

DEFAULT_LAKE_ROOT = Path("data/raw/thetadata")
PILOT_LAKE_ROOT = Path("artifacts/raw_lake_pilot")
PART_FILENAME = "part-000.parquet"
STAGING_DIRNAME = ".staging"


class PartitionExistsError(RuntimeError):
    """Raised when ingesting into a complete partition without overwrite=True."""


class IncompletePartitionError(RuntimeError):
    """Raised when a partition directory looks broken."""


@dataclass(frozen=True)
class DuplicateReport:
    duplicate_row_count: int
    duplicate_ratio: float
    key_columns: tuple[str, ...]


@dataclass(frozen=True)
class OutOfOrderReport:
    out_of_order_count: int
    out_of_order_ratio: float


@dataclass(frozen=True)
class IngestResult:
    dataset: str
    partition_dir: Path
    row_count: int
    skipped: bool
    manifest_path: Path
    duplicate_report: DuplicateReport | None
    out_of_order_report: OutOfOrderReport | None


def git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def production_lake_root() -> Path:
    from quant_lab.config import settings

    return settings.paths.raw / "thetadata"


def partition_dir(
    lake_root: Path,
    dataset: str,
    trade_date: date,
    *,
    root: str | None = None,
    symbol: str | None = None,
    expiration: date | None = None,
) -> Path:
    """Hive-style partition directory for one dataset slice."""
    base = lake_root / f"dataset={dataset}"
    if dataset.startswith("index_"):
        sym = symbol or "SPX"
        return base / f"symbol={sym}" / f"trade_date={trade_date.isoformat()}"
    if dataset in {"session_metadata", "source_manifests"}:
        opt_root = root or "SPXW"
        return base / f"root={opt_root}" / f"trade_date={trade_date.isoformat()}"
    opt_root = root or "SPXW"
    exp = expiration or trade_date
    return (
        base
        / f"root={opt_root}"
        / f"trade_date={trade_date.isoformat()}"
        / f"expiration={exp.isoformat()}"
    )


def _normalize_right(value: Any) -> str:
    raw = str(value).upper()
    if raw in {"C", "CALL"}:
        return "CALL"
    if raw in {"P", "PUT"}:
        return "PUT"
    return raw


def contract_identifier(root: str, expiration: date, strike: float, right: str) -> str:
    return f"{root}|{expiration.isoformat()}|{strike}|{_normalize_right(right)}"


def _base_metadata(
    *,
    dataset: str,
    trade_date: date,
    root_or_symbol: str,
    source_endpoint: str,
    source_request_id: str,
    ingested_at: datetime | None = None,
) -> dict[str, Any]:
    ts = ingested_at or datetime.now(UTC)
    return {
        "source": SOURCE,
        "source_client": SOURCE_CLIENT,
        "source_endpoint": source_endpoint,
        "source_request_id": source_request_id,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "dataset": dataset,
        "dataset_schema_version": dataset_schema_version(dataset),
        "ingested_at": ts,
        "trade_date": trade_date.isoformat(),
        "event_timezone": EVENT_TIMEZONE,
        "root_or_symbol": root_or_symbol,
    }


def _option_contract_columns(
    df: pd.DataFrame,
    *,
    root: str,
    trade_date: date,
) -> pd.DataFrame:
    out = df.copy()
    out["root"] = root
    out["expiration"] = pd.to_datetime(out["expiration"]).dt.date.astype(str)
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["right"] = out["right"].map(_normalize_right)
    out["contract_identifier"] = [
        contract_identifier(root, pd.to_datetime(e).date(), float(s), r)
        for e, s, r in zip(out["expiration"], out["strike"], out["right"], strict=True)
    ]
    out["settlement_type"] = SETTLEMENT_UNKNOWN
    out["settlement_type_source"] = SETTLEMENT_SOURCE_DEFAULT
    out["settlement_type_confidence"] = SETTLEMENT_CONFIDENCE_DEFAULT
    out["trade_date"] = trade_date.isoformat()
    return out


def _event_timestamp_series(df: pd.DataFrame, col: str = "timestamp") -> pd.Series:
    ts = pd.to_datetime(df[col])
    return ts.dt.tz_localize(MARKET_TZ) if ts.dt.tz is None else ts.dt.tz_convert(MARKET_TZ)


def normalize_option_quote(
    raw: pd.DataFrame,
    *,
    dataset: str,
    root: str,
    trade_date: date,
    source_endpoint: str,
    source_request_id: str,
) -> pd.DataFrame:
    if raw.empty:
        return _empty_frame(dataset)
    work = _option_contract_columns(raw, root=root, trade_date=trade_date)
    evt = _event_timestamp_series(work)
    meta = _base_metadata(
        dataset=dataset,
        trade_date=trade_date,
        root_or_symbol=root,
        source_endpoint=source_endpoint,
        source_request_id=source_request_id,
    )
    out = pd.DataFrame(
        {
            **meta,
            "event_timestamp": evt,
            "root": work["root"],
            "expiration": work["expiration"],
            "strike": work["strike"],
            "right": work["right"],
            "contract_identifier": work["contract_identifier"],
            "settlement_type": work["settlement_type"],
            "settlement_type_source": work["settlement_type_source"],
            "settlement_type_confidence": work["settlement_type_confidence"],
            "bid": pd.to_numeric(work.get("bid"), errors="coerce"),
            "ask": pd.to_numeric(work.get("ask"), errors="coerce"),
            "bid_size": pd.to_numeric(work.get("bid_size"), errors="coerce"),
            "ask_size": pd.to_numeric(work.get("ask_size"), errors="coerce"),
            "bid_exchange": pd.to_numeric(work.get("bid_exchange"), errors="coerce"),
            "ask_exchange": pd.to_numeric(work.get("ask_exchange"), errors="coerce"),
            "bid_condition": pd.to_numeric(work.get("bid_condition"), errors="coerce"),
            "ask_condition": pd.to_numeric(work.get("ask_condition"), errors="coerce"),
            "sequence": pd.to_numeric(work.get("sequence"), errors="coerce"),
            "quote_timestamp_raw": evt.astype(str),
        }
    )
    return _finalize_frame(out, dataset)


def normalize_option_trade(
    raw: pd.DataFrame,
    *,
    root: str,
    trade_date: date,
    source_endpoint: str,
    source_request_id: str,
) -> pd.DataFrame:
    dataset = "option_trade_tick"
    if raw.empty:
        return _empty_frame(dataset)
    work = _option_contract_columns(raw, root=root, trade_date=trade_date)
    evt = _event_timestamp_series(work)
    meta = _base_metadata(
        dataset=dataset,
        trade_date=trade_date,
        root_or_symbol=root,
        source_endpoint=source_endpoint,
        source_request_id=source_request_id,
    )
    out = pd.DataFrame(
        {
            **meta,
            "event_timestamp": evt,
            "root": work["root"],
            "expiration": work["expiration"],
            "strike": work["strike"],
            "right": work["right"],
            "contract_identifier": work["contract_identifier"],
            "settlement_type": work["settlement_type"],
            "settlement_type_source": work["settlement_type_source"],
            "settlement_type_confidence": work["settlement_type_confidence"],
            "price": pd.to_numeric(work.get("price"), errors="coerce"),
            "size": pd.to_numeric(work.get("size"), errors="coerce"),
            "exchange": pd.to_numeric(work.get("exchange"), errors="coerce"),
            "condition": pd.to_numeric(work.get("condition"), errors="coerce"),
            "sequence": pd.to_numeric(work.get("sequence"), errors="coerce"),
        }
    )
    return _finalize_frame(out, dataset)


def normalize_option_greeks(
    raw: pd.DataFrame,
    *,
    root: str,
    trade_date: date,
    source_endpoint: str,
    source_request_id: str,
) -> pd.DataFrame:
    dataset = "option_greeks_1m_first_order"
    if raw.empty:
        return _empty_frame(dataset)
    work = _option_contract_columns(raw, root=root, trade_date=trade_date)
    evt = _event_timestamp_series(work)
    if "underlying_timestamp" in work.columns:
        und_ts = pd.to_datetime(work["underlying_timestamp"], errors="coerce")
        if und_ts.dt.tz is None:
            und_ts = und_ts.dt.tz_localize(MARKET_TZ, ambiguous="NaT", nonexistent="NaT")
    else:
        und_ts = pd.Series([pd.NaT] * len(work), index=work.index)
    meta = _base_metadata(
        dataset=dataset,
        trade_date=trade_date,
        root_or_symbol=root,
        source_endpoint=source_endpoint,
        source_request_id=source_request_id,
    )
    out = pd.DataFrame(
        {
            **meta,
            "event_timestamp": evt,
            "root": work["root"],
            "expiration": work["expiration"],
            "strike": work["strike"],
            "right": work["right"],
            "contract_identifier": work["contract_identifier"],
            "settlement_type": work["settlement_type"],
            "settlement_type_source": work["settlement_type_source"],
            "settlement_type_confidence": work["settlement_type_confidence"],
            "implied_vol": pd.to_numeric(work.get("implied_vol"), errors="coerce"),
            "delta": pd.to_numeric(work.get("delta"), errors="coerce"),
            "theta": pd.to_numeric(work.get("theta"), errors="coerce"),
            "vega": pd.to_numeric(work.get("vega"), errors="coerce"),
            "rho": pd.to_numeric(work.get("rho"), errors="coerce"),
            "epsilon": pd.to_numeric(work.get("epsilon"), errors="coerce"),
            "lambda": pd.to_numeric(work.get("lambda"), errors="coerce"),
            "underlying_price": pd.to_numeric(work.get("underlying_price"), errors="coerce"),
            "underlying_timestamp": und_ts,
            "bid": pd.to_numeric(work.get("bid"), errors="coerce"),
            "ask": pd.to_numeric(work.get("ask"), errors="coerce"),
        }
    )
    return _finalize_frame(out, dataset)


def normalize_option_open_interest(
    raw: pd.DataFrame,
    *,
    root: str,
    trade_date: date,
    requested_date: date,
    source_endpoint: str,
    source_request_id: str,
) -> pd.DataFrame:
    dataset = "option_open_interest"
    if raw.empty:
        return _empty_frame(dataset)
    work = _option_contract_columns(raw, root=root, trade_date=trade_date)
    evt = _event_timestamp_series(work)
    meta = _base_metadata(
        dataset=dataset,
        trade_date=trade_date,
        root_or_symbol=root,
        source_endpoint=source_endpoint,
        source_request_id=source_request_id,
    )
    out = pd.DataFrame(
        {
            **meta,
            "event_timestamp": evt,
            "root": work["root"],
            "expiration": work["expiration"],
            "strike": work["strike"],
            "right": work["right"],
            "contract_identifier": work["contract_identifier"],
            "settlement_type": work["settlement_type"],
            "settlement_type_source": work["settlement_type_source"],
            "settlement_type_confidence": work["settlement_type_confidence"],
            "open_interest": pd.to_numeric(work.get("open_interest"), errors="coerce"),
            "oi_event_timestamp": evt,
            "oi_requested_date": requested_date.isoformat(),
            "oi_semantics_status": OI_SEMANTICS_DEFAULT,
            "oi_publication_time_confirmed": False,
        }
    )
    return _finalize_frame(out, dataset)


def normalize_index_price(
    raw: pd.DataFrame,
    *,
    dataset: str,
    symbol: str,
    trade_date: date,
    source_endpoint: str,
    source_request_id: str,
) -> pd.DataFrame:
    if raw.empty:
        return _empty_frame(dataset)
    evt = _event_timestamp_series(raw)
    meta = _base_metadata(
        dataset=dataset,
        trade_date=trade_date,
        root_or_symbol=symbol,
        source_endpoint=source_endpoint,
        source_request_id=source_request_id,
    )
    out = pd.DataFrame(
        {
            **meta,
            "event_timestamp": evt,
            "symbol": symbol,
            "price": pd.to_numeric(raw.get("price"), errors="coerce"),
            "open": pd.to_numeric(raw.get("open"), errors="coerce"),
            "high": pd.to_numeric(raw.get("high"), errors="coerce"),
            "low": pd.to_numeric(raw.get("low"), errors="coerce"),
            "close": pd.to_numeric(raw.get("close"), errors="coerce"),
            "volume_or_null": pd.to_numeric(raw.get("volume"), errors="coerce"),
        }
    )
    return _finalize_frame(out, dataset)


def build_derived_gamma_black76(
    greeks: pd.DataFrame,
    *,
    trade_date: date,
    root: str,
) -> pd.DataFrame:
    dataset = "derived_gamma_black76_1m"
    if greeks.empty:
        return _empty_frame(dataset)
    inp = resolve_gex_inputs("^SPX", asof=trade_date)
    rows: list[dict[str, Any]] = []
    for _, row in greeks.iterrows():
        evt: pd.Timestamp = row["event_timestamp"]
        spot_raw = row["underlying_price"]
        iv_raw = row["implied_vol"]
        if pd.isna(spot_raw) or pd.isna(iv_raw):
            continue
        tod = evt.strftime("%H:%M:%S")
        t_years = intraday_time_to_expiry_years(trade_date, tod)
        spot = float(spot_raw)
        strike = float(row["strike"])
        iv = float(iv_raw)
        gamma = float(black76_gamma(spot, strike, t_years, iv, r=inp.r, q=inp.q))
        source_hash = hashlib.sha256(
            json.dumps(
                {
                    "contract": row["contract_identifier"],
                    "event_timestamp": str(evt),
                    "spot": spot,
                    "iv": iv,
                    "t_years": t_years,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        expiry_ts = session_datetime(trade_date, "16:00:00")
        rows.append(
            {
                **_base_metadata(
                    dataset=dataset,
                    trade_date=trade_date,
                    root_or_symbol=root,
                    source_endpoint="derived:black76_gamma",
                    source_request_id=source_hash[:16],
                ),
                "event_timestamp": evt,
                "root": row["root"],
                "expiration": row["expiration"],
                "strike": strike,
                "right": row["right"],
                "contract_identifier": row["contract_identifier"],
                "settlement_type": row["settlement_type"],
                "settlement_type_source": row["settlement_type_source"],
                "settlement_type_confidence": row["settlement_type_confidence"],
                "gamma": gamma,
                "gamma_method": GAMMA_METHOD,
                "gamma_method_version": GAMMA_METHOD_VERSION,
                "spot": spot,
                "implied_vol": iv,
                "rate": inp.r,
                "dividend_yield_or_forward_assumption": inp.q,
                "time_to_expiry_years": t_years,
                "expiry_timestamp": expiry_ts,
                "settlement_timestamp": expiry_ts,
                "input_source_hash": source_hash,
            }
        )
    if not rows:
        return _empty_frame(dataset)
    return _finalize_frame(pd.DataFrame(rows), dataset)


def build_session_metadata_row(
    *,
    trade_date: date,
    root: str,
    symbol: str,
    strike_range: int,
    window_start: str,
    window_end: str,
    quote_interval: str,
    pilot_label: str,
    session_rth_start: str = "09:30:00",
    session_rth_end: str = "16:00:00",
) -> pd.DataFrame:
    dataset = "session_metadata"
    evt = session_datetime(trade_date, window_start)
    meta = _base_metadata(
        dataset=dataset,
        trade_date=trade_date,
        root_or_symbol=root,
        source_endpoint="session_metadata",
        source_request_id=f"pilot-{trade_date.isoformat()}",
    )
    out = pd.DataFrame(
        [
            {
                **meta,
                "event_timestamp": evt,
                "session_rth_start": session_rth_start,
                "session_rth_end": session_rth_end,
                "strike_range": strike_range,
                "quote_interval": quote_interval,
                "trade_window_start": window_start,
                "trade_window_end": window_end,
                "pilot_label": pilot_label,
            }
        ]
    )
    return _finalize_frame(out, dataset)


def detect_duplicates(df: pd.DataFrame, key_columns: tuple[str, ...]) -> DuplicateReport:
    if df.empty:
        return DuplicateReport(0, 0.0, key_columns)
    keys = [c for c in key_columns if c in df.columns]
    if not keys:
        return DuplicateReport(0, 0.0, key_columns)
    dup_mask = df.duplicated(subset=keys, keep=False)
    count = int(dup_mask.sum())
    ratio = float(count / len(df)) if len(df) else 0.0
    return DuplicateReport(count, ratio, tuple(keys))


def detect_out_of_order(df: pd.DataFrame, *, time_col: str = "event_timestamp") -> OutOfOrderReport:
    if df.empty or time_col not in df.columns:
        return OutOfOrderReport(0, 0.0)
    ts = pd.to_datetime(df[time_col])
    diffs = ts.diff()
    ooo = int((diffs < pd.Timedelta(0)).sum())
    ratio = float(ooo / max(len(df) - 1, 1))
    return OutOfOrderReport(ooo, ratio)


def ingest_partition(
    df: pd.DataFrame,
    *,
    lake_root: Path,
    dataset: str,
    trade_date: date,
    root: str | None = None,
    symbol: str | None = None,
    expiration: date | None = None,
    source_requests: list[SourceRequestMeta] | None = None,
    overwrite: bool = False,
    duplicate_keys: tuple[str, ...] | None = None,
) -> IngestResult:
    part_dir = partition_dir(
        lake_root,
        dataset,
        trade_date,
        root=root,
        symbol=symbol,
        expiration=expiration,
    )
    if is_partition_complete(part_dir) and not overwrite:
        log.info("skip complete partition %s", part_dir)
        return IngestResult(
            dataset=dataset,
            partition_dir=part_dir,
            row_count=0,
            skipped=True,
            manifest_path=manifest_path(part_dir),
            duplicate_report=None,
            out_of_order_report=None,
        )

    if part_dir.exists() and not overwrite:
        existing = read_manifest(part_dir)
        if existing and existing.get("ingestion_status") == "incomplete":
            raise IncompletePartitionError(f"incomplete partition exists: {part_dir}")

    missing = validate_required_columns(dataset, list(df.columns))
    if df.empty:
        log.warning("empty dataframe for %s — writing zero-row partition", dataset)
    elif missing:
        raise ValueError(f"dataset {dataset} missing columns: {missing}")

    dup_keys = duplicate_keys or (
        ("contract_identifier", "event_timestamp", "sequence")
        if "contract_identifier" in df.columns
        else ("event_timestamp",)
    )
    dup_report = detect_duplicates(df, dup_keys)
    ooo_report = detect_out_of_order(df)

    staging = part_dir / STAGING_DIRNAME
    staging.mkdir(parents=True, exist_ok=True)
    tmp_parquet = staging / PART_FILENAME
    try:
        df.to_parquet(tmp_parquet, engine="pyarrow", index=False, compression="zstd")
        row_count = len(df)
        read_back = pd.read_parquet(tmp_parquet, engine="pyarrow")
        if len(read_back) != row_count:
            raise RuntimeError("row_count mismatch after parquet write")

        final_parquet = part_dir / PART_FILENAME
        part_dir.mkdir(parents=True, exist_ok=True)
        os.replace(tmp_parquet, final_parquet)

        sha = sha256_file(final_parquet)
        size = final_parquet.stat().st_size
        file_meta = PartitionFileMeta(
            path=PART_FILENAME,
            sha256=sha,
            size_bytes=size,
            row_count=row_count,
        )
        warnings: list[str] = []
        if dup_report.duplicate_row_count:
            warnings.append(
                f"duplicate_rows={dup_report.duplicate_row_count} "
                f"ratio={dup_report.duplicate_ratio:.4f}"
            )
        if ooo_report.out_of_order_count:
            warnings.append(
                f"out_of_order={ooo_report.out_of_order_count} "
                f"ratio={ooo_report.out_of_order_ratio:.4f}"
            )

        min_ts = max_ts = None
        if not df.empty and "event_timestamp" in df.columns:
            ts = pd.to_datetime(df["event_timestamp"])
            min_ts = pd.Timestamp(ts.min()).isoformat()
            max_ts = pd.Timestamp(ts.max()).isoformat()

        contract_count = None
        if "contract_identifier" in df.columns and not df.empty:
            contract_count = int(df["contract_identifier"].nunique())

        pm = PartitionManifest(
            dataset=dataset,
            trade_date=trade_date,
            root_or_symbol=root or symbol or "",
            expiration=expiration,
            files=[file_meta],
            source_requests=source_requests or [],
            code_commit=git_commit(),
            ingestion_status="complete",
            known_warnings=warnings,
        )
        manifest_dict = pm.to_dict()
        manifest_dict["contract_count"] = contract_count
        enrich_manifest_timestamp_bounds(
            manifest_dict,
            min_event_timestamp=min_ts,
            max_event_timestamp=max_ts,
        )
        mpath = write_manifest_dict(part_dir, manifest_dict)
        manifest_dict = read_manifest(part_dir)
        assert manifest_dict is not None

        verify_errors = verify_partition_files(part_dir, manifest_dict)
        if verify_errors:
            manifest_dict["ingestion_status"] = "incomplete"
            manifest_path(part_dir).write_text(
                json.dumps(manifest_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            raise IncompletePartitionError("; ".join(verify_errors))

        return IngestResult(
            dataset=dataset,
            partition_dir=part_dir,
            row_count=row_count,
            skipped=False,
            manifest_path=mpath,
            duplicate_report=dup_report,
            out_of_order_report=ooo_report,
        )
    finally:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink(missing_ok=True)
            staging.rmdir()


def make_source_request_id(endpoint: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _empty_frame(dataset: str) -> pd.DataFrame:
    from quant_lab.data.intraday_schema import required_fields

    cols = required_fields(dataset)
    return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})


def _finalize_frame(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    missing = validate_required_columns(dataset, list(df.columns))
    if missing:
        raise ValueError(f"normalized frame missing {missing}")
    return df


def request_id() -> str:
    return uuid4().hex[:12]
