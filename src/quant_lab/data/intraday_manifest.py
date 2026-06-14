"""Partition manifests for immutable raw event lake (ML-P3)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from quant_lab.data.intraday_schema import (
    MANIFEST_VERSION,
    SOURCE,
    dataset_schema_version,
)

IngestionStatus = Literal["complete", "incomplete", "failed"]

SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|api_key|authorization|email)",
    re.IGNORECASE,
)
HOME_PATH_RE = re.compile(r"[/\\]Users[/\\][^/\\]+", re.IGNORECASE)
SAFE_MANIFEST_KEYS: frozenset[str] = frozenset({"secret_redaction_checked"})


@dataclass(frozen=True)
class SourceRequestMeta:
    endpoint: str
    request_id: str
    params_redacted: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "request_id": self.request_id,
            "params_redacted": redact_manifest(self.params_redacted),
        }


@dataclass
class PartitionFileMeta:
    path: str
    sha256: str
    size_bytes: int
    row_count: int


@dataclass
class PartitionManifest:
    dataset: str
    trade_date: date
    root_or_symbol: str
    expiration: date | None
    files: list[PartitionFileMeta]
    source_requests: list[SourceRequestMeta] = field(default_factory=list)
    code_commit: str | None = None
    ingestion_status: IngestionStatus = "complete"
    known_warnings: list[str] = field(default_factory=list)
    secret_redaction_checked: bool = True

    def to_dict(self) -> dict[str, Any]:
        min_ts, max_ts = self._event_timestamp_bounds()
        return redact_manifest(
            {
                "manifest_version": MANIFEST_VERSION,
                "dataset": self.dataset,
                "dataset_schema_version": dataset_schema_version(self.dataset),
                "source": SOURCE,
                "trade_date": self.trade_date.isoformat(),
                "root_or_symbol": self.root_or_symbol,
                "expiration": self.expiration.isoformat() if self.expiration else None,
                "row_count": sum(f.row_count for f in self.files),
                "contract_count": None,
                "min_event_timestamp": min_ts,
                "max_event_timestamp": max_ts,
                "file_count": len(self.files),
                "files": [f.__dict__ for f in self.files],
                "source_requests": [r.to_dict() for r in self.source_requests],
                "code_commit": self.code_commit,
                "created_at": datetime.now(UTC).isoformat(),
                "ingestion_status": self.ingestion_status,
                "known_warnings": self.known_warnings,
                "secret_redaction_checked": self.secret_redaction_checked,
            }
        )

    def _event_timestamp_bounds(self) -> tuple[str | None, str | None]:
        return None, None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_string(value: str) -> str:
    value = HOME_PATH_RE.sub("/Users/***", value)
    if "@" in value:
        local, _, domain = value.partition("@")
        head = local[:1] if local else "*"
        return f"{head}***@{domain}"
    return value


def redact_value(key: str, value: Any) -> Any:
    if key in SAFE_MANIFEST_KEYS:
        return value
    if SENSITIVE_KEY_RE.search(key):
        return "***" if value is not None else None
    if isinstance(value, str):
        if "@" in value:
            return redact_string(value)
        return HOME_PATH_RE.sub("/Users/***", value)
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


def manifest_path(partition_dir: Path) -> Path:
    return partition_dir / "_manifest.json"


def write_manifest(partition_dir: Path, manifest: PartitionManifest) -> Path:
    return write_manifest_dict(partition_dir, manifest.to_dict())


def write_manifest_dict(partition_dir: Path, manifest_dict: dict[str, Any]) -> Path:
    path = manifest_path(partition_dir)
    safe = redact_manifest(manifest_dict)
    text = json.dumps(safe, indent=2, ensure_ascii=False, default=_json_default)
    if _contains_secrets(text):
        raise ValueError("manifest payload failed secret redaction check")
    path.write_text(text, encoding="utf-8")
    return path


def _json_default(obj: Any) -> Any:
    from datetime import date, datetime

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def read_manifest(partition_dir: Path) -> dict[str, Any] | None:
    path = manifest_path(partition_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_manifest_complete(manifest: dict[str, Any] | None) -> bool:
    if manifest is None:
        return False
    if manifest.get("ingestion_status") != "complete":
        return False
    return bool(manifest.get("files"))


def verify_partition_files(partition_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Return list of verification errors (empty if OK)."""
    errors: list[str] = []
    for entry in manifest.get("files", []):
        rel = entry.get("path")
        expected_sha = entry.get("sha256")
        if not rel or not expected_sha:
            errors.append("manifest file entry missing path or sha256")
            continue
        fpath = partition_dir / rel
        if not fpath.is_file():
            errors.append(f"missing file: {rel}")
            continue
        actual = sha256_file(fpath)
        if actual != expected_sha:
            errors.append(f"sha256 mismatch: {rel}")
    return errors


def is_partition_complete(partition_dir: Path) -> bool:
    manifest = read_manifest(partition_dir)
    if not is_manifest_complete(manifest):
        return False
    assert manifest is not None
    return len(verify_partition_files(partition_dir, manifest)) == 0


def _contains_secrets(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", lowered):
        return True
    if "password" in lowered and "***" not in text:
        return False
    return False


def enrich_manifest_timestamp_bounds(
    manifest_dict: dict[str, Any],
    *,
    min_event_timestamp: str | None,
    max_event_timestamp: str | None,
) -> dict[str, Any]:
    manifest_dict["min_event_timestamp"] = min_event_timestamp
    manifest_dict["max_event_timestamp"] = max_event_timestamp
    return manifest_dict
