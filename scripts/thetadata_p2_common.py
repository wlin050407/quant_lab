"""Shared helpers for ML-P2 ThetaData probe and storage pilot scripts."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal

import pandas as pd

SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|api_key|authorization)",
    re.IGNORECASE,
)
SAFE_METADATA_KEYS = frozenset({"credential_source", "credential_source_label"})

ProbeStatus = Literal["ok", "empty", "error", "skipped", "dry_run", "denied"]


@dataclass
class ProbeRecord:
    name: str
    status: ProbeStatus
    detail: dict[str, Any] = field(default_factory=dict)


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


def redact_string(value: str) -> str:
    if "@" in value and not value.startswith("***"):
        local, _, domain = value.partition("@")
        head = local[:1] if local else "*"
        return f"{head}***@{domain}"
    if len(value) > 8:
        return value[:3] + "***" + value[-2:]
    return "***"


def redact_value(key: str, value: Any) -> Any:
    if key in SAFE_METADATA_KEYS:
        return value
    if SENSITIVE_KEY_RE.search(key):
        return "***" if value is not None else None
    if isinstance(value, str) and "@" in value:
        return redact_string(value)
    if isinstance(value, dict):
        return redact_manifest(value)
    if isinstance(value, list):
        return [redact_manifest(v) if isinstance(v, dict) else v for v in value]
    return value


def redact_manifest(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: redact_value(k, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_manifest(v) for v in obj]
    return obj


def classify_probe_error(exc: BaseException) -> dict[str, Any]:
    msg = str(exc)
    lowered = msg.lower()
    category = "unknown"
    if "permission_denied" in lowered or "professional subscription" in lowered:
        category = "entitlement_denied"
    elif "no data found" in lowered or type(exc).__name__ == "NoDataFoundError":
        category = "no_data"
    elif "invalid" in lowered or "inte" in type(exc).__name__.lower():
        category = "invalid_parameter"
    elif "timeout" in lowered:
        category = "timeout"
    return {
        "exception_type": type(exc).__name__,
        "category": category,
        "message": redact_string(msg)[:500],
    }


def summarize_dataframe(df: pd.DataFrame | None, *, max_rows: int = 5) -> dict[str, Any]:
    if df is None:
        return {"row_count": 0, "columns": [], "sample": []}
    if not isinstance(df, pd.DataFrame):
        return {"row_count": 0, "columns": [], "sample": [], "note": "non-dataframe"}
    clipped = df.head(max_rows).copy()
    cols = [
        {
            "name": str(name),
            "dtype": str(clipped[name].dtype),
            "null_rate_in_sample": float(clipped[name].isna().mean()) if len(clipped) else 0.0,
        }
        for name in clipped.columns
    ]
    sample: list[dict[str, Any]] = []
    for _, row in clipped.iterrows():
        item: dict[str, Any] = {}
        for k, v in row.items():
            if pd.isna(v):
                item[str(k)] = None
            elif isinstance(v, (pd.Timestamp, datetime)):
                item[str(k)] = pd.Timestamp(v).isoformat()
            elif isinstance(v, date):
                item[str(k)] = v.isoformat()
            else:
                item[str(k)] = v
        sample.append(redact_manifest(item))
    ts_info: dict[str, Any] = {}
    if "timestamp" in clipped.columns and not clipped.empty:
        ts = pd.to_datetime(clipped["timestamp"])
        ts_info = {
            "min": pd.Timestamp(ts.min()).isoformat(),
            "max": pd.Timestamp(ts.max()).isoformat(),
            "timezone_inferred": str(ts.dt.tz) if ts.dt.tz else "naive",
            "monotonic_increasing": bool(ts.is_monotonic_increasing),
            "duplicate_timestamps": int(ts.duplicated().sum()),
        }
    return {
        "row_count": int(len(df)),
        "columns": cols,
        "timestamp_summary": ts_info,
        "sample": sample[:3],
    }


def write_json(path: Any, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = _json_safe(redact_manifest(payload))
    path.write_text(
        json.dumps(safe, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, float) and pd.isna(obj):
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def trading_day_offset(session: date, offset: int) -> date:
    """Move by ``offset`` weekdays (Mon–Fri only; no holiday calendar)."""
    d = session
    step = 1 if offset >= 0 else -1
    remaining = abs(offset)
    while remaining:
        d = date.fromordinal(d.toordinal() + step)
        if d.weekday() < 5:
            remaining -= 1
    return d


def manifest_header(*, audit_version: str, dry_run: bool) -> dict[str, Any]:
    return {
        "audit_version": audit_version,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "dry_run": dry_run,
    }
