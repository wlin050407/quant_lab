"""Tests for replay partition integrity (ML-P4)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_lab.data.intraday_lake import ingest_partition, normalize_index_price, partition_dir
from quant_lab.data.intraday_manifest import manifest_path, sha256_file
from quant_lab.data.replay_integrity import (
    ChecksumMismatchError,
    IncompletePartitionError,
    MissingManifestError,
    UnsupportedSchemaVersionError,
    WrongDatasetError,
    load_verified_partition,
    summarize_manifest,
    verify_manifest_schema,
    verify_partition_identity,
)

TRADE = date(2026, 6, 10)


def _write_index_partition(tmp_path: Path, *, bad_sha: bool = False) -> Path:
    df = normalize_index_price(
        pd.DataFrame({"timestamp": ["2026-06-10T13:00:00"], "price": [6000.0]}),
        dataset="index_price_1s",
        symbol="SPX",
        trade_date=TRADE,
        source_endpoint="index_history_price",
        source_request_id="req1",
    )
    ingest_partition(
        df,
        lake_root=tmp_path,
        dataset="index_price_1s",
        trade_date=TRADE,
        symbol="SPX",
    )
    part = partition_dir(tmp_path, "index_price_1s", TRADE, symbol="SPX")
    if bad_sha:
        manifest = json.loads(manifest_path(part).read_text(encoding="utf-8"))
        manifest["files"][0]["sha256"] = "0" * 64
        manifest_path(part).write_text(json.dumps(manifest), encoding="utf-8")
    return part


def test_verify_manifest_schema_ok() -> None:
    assert verify_manifest_schema({"manifest_version": "raw-lake-v1", "dataset_schema_version": "1.0.0"}) == []


def test_verify_manifest_schema_unsupported() -> None:
    errs = verify_manifest_schema({"manifest_version": "raw-lake-v0", "dataset_schema_version": "9.9.9"})
    assert any("manifest_version" in e for e in errs)
    assert any("dataset_schema_version" in e for e in errs)


def test_verify_partition_identity_wrong_date() -> None:
    manifest = {"dataset": "index_price_1s", "trade_date": "2026-06-09", "root_or_symbol": "SPX"}
    errs = verify_partition_identity(
        manifest, dataset="index_price_1s", trade_date=TRADE, symbol="SPX"
    )
    assert any("trade_date mismatch" in e for e in errs)


def test_load_verified_partition_ok(tmp_path: Path) -> None:
    _write_index_partition(tmp_path)
    loaded = load_verified_partition(
        tmp_path, "index_price_1s", TRADE, symbol="SPX", strict_manifests=True
    )
    assert loaded is not None
    assert len(loaded.frame) == 1
    summary = summarize_manifest(loaded.partition_dir, loaded.manifest)
    assert summary.file_sha256 == sha256_file(loaded.partition_dir / "part-000.parquet")


def test_missing_manifest_strict(tmp_path: Path) -> None:
    with pytest.raises(MissingManifestError):
        load_verified_partition(
            tmp_path, "index_price_1s", TRADE, symbol="SPX", strict_manifests=True
        )


def test_checksum_mismatch_strict(tmp_path: Path) -> None:
    _write_index_partition(tmp_path, bad_sha=True)
    with pytest.raises(ChecksumMismatchError):
        load_verified_partition(
            tmp_path, "index_price_1s", TRADE, symbol="SPX", strict_manifests=True
        )


def test_incomplete_partition_strict(tmp_path: Path) -> None:
    part = partition_dir(tmp_path, "index_price_1s", TRADE, symbol="SPX")
    part.mkdir(parents=True)
    manifest_path(part).write_text(
        json.dumps({"ingestion_status": "incomplete", "files": []}),
        encoding="utf-8",
    )
    with pytest.raises(IncompletePartitionError):
        load_verified_partition(
            tmp_path, "index_price_1s", TRADE, symbol="SPX", strict_manifests=True
        )


def test_wrong_dataset_strict(tmp_path: Path) -> None:
    part = _write_index_partition(tmp_path)
    manifest = json.loads(manifest_path(part).read_text(encoding="utf-8"))
    manifest["dataset"] = "index_price_tick"
    manifest_path(part).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(WrongDatasetError):
        load_verified_partition(
            tmp_path, "index_price_1s", TRADE, symbol="SPX", strict_manifests=True
        )


def test_unsupported_schema_strict(tmp_path: Path) -> None:
    part = _write_index_partition(tmp_path)
    manifest = json.loads(manifest_path(part).read_text(encoding="utf-8"))
    manifest["dataset_schema_version"] = "99.0.0"
    manifest_path(part).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(UnsupportedSchemaVersionError):
        load_verified_partition(
            tmp_path, "index_price_1s", TRADE, symbol="SPX", strict_manifests=True
        )


def test_non_strict_returns_none(tmp_path: Path) -> None:
    _write_index_partition(tmp_path, bad_sha=True)
    loaded = load_verified_partition(
        tmp_path, "index_price_1s", TRADE, symbol="SPX", strict_manifests=False
    )
    assert loaded is None
