"""Unit tests for raw event lake manifests (ML-P3)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from quant_lab.data.intraday_manifest import (
    PartitionFileMeta,
    PartitionManifest,
    SourceRequestMeta,
    is_manifest_complete,
    is_partition_complete,
    manifest_path,
    read_manifest,
    redact_manifest,
    sha256_file,
    verify_partition_files,
    write_manifest,
    write_manifest_dict,
)


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"raw-lake-pilot")
    digest = sha256_file(f)
    assert len(digest) == 64
    assert digest == sha256_file(f)


def test_manifest_creation_fields(tmp_path: Path) -> None:
    part = tmp_path / "partition"
    part.mkdir()
    parquet = part / "part-000.parquet"
    parquet.write_bytes(b"abc")
    sha = sha256_file(parquet)
    pm = PartitionManifest(
        dataset="option_quote_tick",
        trade_date=date(2026, 6, 10),
        root_or_symbol="SPXW",
        expiration=date(2026, 6, 10),
        files=[
            PartitionFileMeta(
                path="part-000.parquet",
                sha256=sha,
                size_bytes=3,
                row_count=2,
            )
        ],
        source_requests=[
            SourceRequestMeta(
                endpoint="option_history_quote",
                request_id="req123",
                params_redacted={"interval": "tick"},
            )
        ],
        code_commit="deadbeef",
    )
    mpath = write_manifest(part, pm)
    data = read_manifest(part)
    assert data is not None
    assert data["manifest_version"] == "raw-lake-v1"
    assert data["dataset"] == "option_quote_tick"
    assert data["dataset_schema_version"] == "1.0.0"
    assert data["row_count"] == 2
    assert data["files"][0]["sha256"] == sha
    assert data["source_requests"][0]["endpoint"] == "option_history_quote"
    assert data["secret_redaction_checked"] is True
    assert mpath == manifest_path(part)


def test_write_manifest_dict_enriches_contract_count(tmp_path: Path) -> None:
    part = tmp_path / "p"
    part.mkdir()
    payload = {
        "manifest_version": "raw-lake-v1",
        "dataset": "index_price_tick",
        "dataset_schema_version": "1.0.0",
        "source": "thetadata",
        "trade_date": "2026-06-10",
        "root_or_symbol": "SPX",
        "expiration": None,
        "row_count": 0,
        "contract_count": 0,
        "file_count": 0,
        "files": [],
        "source_requests": [],
        "ingestion_status": "complete",
        "known_warnings": [],
        "secret_redaction_checked": True,
    }
    write_manifest_dict(part, payload)
    assert read_manifest(part) is not None


def test_is_manifest_complete_requires_files_and_status() -> None:
    assert is_manifest_complete(None) is False
    assert is_manifest_complete({"ingestion_status": "incomplete", "files": [{}]}) is False
    assert is_manifest_complete({"ingestion_status": "complete", "files": []}) is False
    assert is_manifest_complete({"ingestion_status": "complete", "files": [{"path": "x"}]}) is True


def test_verify_partition_files_detects_mismatch(tmp_path: Path) -> None:
    part = tmp_path / "partition"
    part.mkdir()
    f = part / "part-000.parquet"
    f.write_bytes(b"good")
    manifest = {
        "files": [
            {"path": "part-000.parquet", "sha256": "0" * 64},
            {"path": "missing.parquet", "sha256": "1" * 64},
        ]
    }
    errors = verify_partition_files(part, manifest)
    assert any("sha256 mismatch" in e for e in errors)
    assert any("missing file" in e for e in errors)


def test_is_partition_complete(tmp_path: Path) -> None:
    part = tmp_path / "partition"
    part.mkdir()
    f = part / "part-000.parquet"
    f.write_bytes(b"x")
    sha = sha256_file(f)
    manifest = {
        "ingestion_status": "complete",
        "files": [{"path": "part-000.parquet", "sha256": sha}],
    }
    manifest_path(part).write_text(json.dumps(manifest), encoding="utf-8")
    assert is_partition_complete(part) is True


def test_secret_redaction_email_and_token() -> None:
    payload = {
        "email": "alice@example.com",
        "authorization_token": "super-secret-token",
        "nested": {"password": "p@ss", "safe": "ok"},
        "path": r"C:\Users\ROG\secrets\creds.txt",
    }
    redacted = redact_manifest(payload)
    assert "@" not in redacted["email"] or "***" in redacted["email"]
    assert redacted["authorization_token"] == "***"
    assert redacted["nested"]["password"] == "***"
    assert "/Users/***" in redacted["path"] or "***" in redacted["path"]


def test_redact_manifest_removes_sensitive_values() -> None:
    payload = {
        "authorization": "Bearer secret-token-value",
        "note": "contact a***@example.com",
    }
    redacted = redact_manifest(payload)
    assert redacted["authorization"] == "***"
    assert "secret-token" not in str(redacted)
