"""Manifest and partition integrity checks for point-in-time replay (ML-P4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.data.intraday_lake import PART_FILENAME, partition_dir
from quant_lab.data.intraday_manifest import (
    is_manifest_complete,
    read_manifest,
    verify_partition_files,
)
from quant_lab.data.intraday_schema import DATASET_SCHEMA_VERSION, MANIFEST_VERSION

SUPPORTED_MANIFEST_VERSION = MANIFEST_VERSION
SUPPORTED_DATASET_SCHEMA_VERSIONS = set(DATASET_SCHEMA_VERSION.values())


class ReplayIntegrityError(RuntimeError):
    """Base class for replay partition integrity failures."""


class MissingManifestError(ReplayIntegrityError):
    """Partition manifest is absent."""


class IncompletePartitionError(ReplayIntegrityError):
    """Partition ingestion_status is not complete."""


class ChecksumMismatchError(ReplayIntegrityError):
    """Parquet checksum does not match manifest."""


class WrongDatasetError(ReplayIntegrityError):
    """Manifest dataset or partition keys do not match request."""


class UnsupportedSchemaVersionError(ReplayIntegrityError):
    """Manifest or dataset schema version is not supported."""


@dataclass(frozen=True)
class PartitionManifestSummary:
    dataset: str
    partition_dir: str
    trade_date: str
    root_or_symbol: str
    expiration: str | None
    row_count: int
    dataset_schema_version: str
    manifest_version: str
    file_sha256: str
    ingestion_status: str

    def stable_hash_input(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "trade_date": self.trade_date,
            "root_or_symbol": self.root_or_symbol,
            "expiration": self.expiration,
            "row_count": self.row_count,
            "dataset_schema_version": self.dataset_schema_version,
            "manifest_version": self.manifest_version,
            "file_sha256": self.file_sha256,
        }


@dataclass(frozen=True)
class LoadedPartition:
    dataset: str
    partition_dir: Path
    manifest: dict[str, Any]
    summary: PartitionManifestSummary
    frame: pd.DataFrame


def summarize_manifest(partition_dir: Path, manifest: dict[str, Any]) -> PartitionManifestSummary:
    files = manifest.get("files") or []
    file_sha = files[0].get("sha256", "") if files else ""
    return PartitionManifestSummary(
        dataset=str(manifest.get("dataset", "")),
        partition_dir=str(partition_dir),
        trade_date=str(manifest.get("trade_date", "")),
        root_or_symbol=str(manifest.get("root_or_symbol", "")),
        expiration=manifest.get("expiration"),
        row_count=int(manifest.get("row_count", 0)),
        dataset_schema_version=str(manifest.get("dataset_schema_version", "")),
        manifest_version=str(manifest.get("manifest_version", "")),
        file_sha256=str(file_sha),
        ingestion_status=str(manifest.get("ingestion_status", "")),
    )


def verify_manifest_schema(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("manifest_version") != SUPPORTED_MANIFEST_VERSION:
        errors.append(
            f"unsupported manifest_version: {manifest.get('manifest_version')}"
        )
    schema_ver = manifest.get("dataset_schema_version")
    if schema_ver not in SUPPORTED_DATASET_SCHEMA_VERSIONS:
        errors.append(f"unsupported dataset_schema_version: {schema_ver}")
    return errors


def verify_partition_identity(
    manifest: dict[str, Any],
    *,
    dataset: str,
    trade_date: date,
    root: str | None = None,
    symbol: str | None = None,
    expiration: date | None = None,
) -> list[str]:
    errors: list[str] = []
    if manifest.get("dataset") != dataset:
        errors.append(f"dataset mismatch: expected {dataset}, got {manifest.get('dataset')}")
    if manifest.get("trade_date") != trade_date.isoformat():
        errors.append(
            f"trade_date mismatch: expected {trade_date.isoformat()}, "
            f"got {manifest.get('trade_date')}"
        )
    if dataset.startswith("index_"):
        expected = symbol or "SPX"
        if manifest.get("root_or_symbol") != expected:
            errors.append(
                f"symbol mismatch: expected {expected}, got {manifest.get('root_or_symbol')}"
            )
    elif dataset == "session_metadata":
        expected_root = root or "SPXW"
        if manifest.get("root_or_symbol") != expected_root:
            errors.append(
                f"root mismatch: expected {expected_root}, "
                f"got {manifest.get('root_or_symbol')}"
            )
    else:
        expected_root = root or "SPXW"
        if manifest.get("root_or_symbol") != expected_root:
            errors.append(
                f"root mismatch: expected {expected_root}, "
                f"got {manifest.get('root_or_symbol')}"
            )
        exp = expiration or trade_date
        if manifest.get("expiration") != exp.isoformat():
            errors.append(
                f"expiration mismatch: expected {exp.isoformat()}, "
                f"got {manifest.get('expiration')}"
            )
    return errors


def load_partition_frame(partition_dir: Path, manifest: dict[str, Any]) -> pd.DataFrame:
    rel = PART_FILENAME
    files = manifest.get("files") or []
    if files:
        rel = str(files[0].get("path", PART_FILENAME))
    path = partition_dir / rel
    if not path.is_file():
        raise ReplayIntegrityError(f"missing parquet file: {path}")
    return pd.read_parquet(path, engine="pyarrow")


def load_verified_partition(
    data_root: Path,
    dataset: str,
    trade_date: date,
    *,
    root: str | None = None,
    symbol: str | None = None,
    expiration: date | None = None,
    strict_manifests: bool = True,
) -> LoadedPartition | None:
    """Load one lake partition with optional strict integrity enforcement."""
    part_dir = partition_dir(
        data_root,
        dataset,
        trade_date,
        root=root,
        symbol=symbol,
        expiration=expiration,
    )
    manifest = read_manifest(part_dir)
    if manifest is None:
        if strict_manifests:
            raise MissingManifestError(f"missing manifest: {part_dir}")
        return None

    errors: list[str] = []
    errors.extend(verify_manifest_schema(manifest))
    errors.extend(
        verify_partition_identity(
            manifest,
            dataset=dataset,
            trade_date=trade_date,
            root=root,
            symbol=symbol,
            expiration=expiration,
        )
    )
    if not is_manifest_complete(manifest):
        errors.append("ingestion_status is not complete")
    errors.extend(verify_partition_files(part_dir, manifest))

    row_count_manifest = int(manifest.get("row_count", 0))
    frame: pd.DataFrame | None = None
    if manifest.get("files"):
        try:
            frame = load_partition_frame(part_dir, manifest)
        except ReplayIntegrityError as exc:
            errors.append(str(exc))
        else:
            if len(frame) != row_count_manifest:
                errors.append(
                    f"row_count mismatch: manifest={row_count_manifest}, parquet={len(frame)}"
                )

    if errors:
        if strict_manifests:
            msg = "; ".join(errors)
            if any("sha256 mismatch" in e for e in errors):
                raise ChecksumMismatchError(msg)
            if any("ingestion_status" in e for e in errors):
                raise IncompletePartitionError(msg)
            if any("dataset mismatch" in e or "trade_date mismatch" in e for e in errors):
                raise WrongDatasetError(msg)
            if any("unsupported" in e for e in errors):
                raise UnsupportedSchemaVersionError(msg)
            if any("missing parquet" in e for e in errors):
                raise IncompletePartitionError(msg)
            raise ReplayIntegrityError(msg)
        return None

    assert frame is not None

    summary = summarize_manifest(part_dir, manifest)
    return LoadedPartition(
        dataset=dataset,
        partition_dir=part_dir,
        manifest=manifest,
        summary=summary,
        frame=frame,
    )


def integrity_warning_from_errors(errors: list[str]) -> str:
    return "integrity_degraded: " + "; ".join(errors)
