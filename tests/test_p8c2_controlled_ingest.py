"""Tests for ML-P8C.2 controlled raw lake ingest (no real ThetaData)."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from quant_lab.ml.datasets.p8c_controlled_ingest import (
    FROZEN_STAGE1_DATES,
    P8C2ConfigError,
    PerDateIngestStatus,
    assert_frozen_dates_match_owner,
    assert_safety_flags,
    day_type_for_date,
    load_p8c2_ingest_config,
    run_p8c2_controlled_ingest,
    select_dates_to_attempt,
    validate_date_subset,
    write_p8c2_artifacts,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _PROJECT_ROOT / "config/ml/p8c2_raw_lake_ingest.yaml"
_SCRIPT = _PROJECT_ROOT / "scripts/run_p8c_controlled_ingest.py"


@pytest.fixture
def p8c2_config(tmp_path: Path) -> Path:
    """Minimal valid P8C.2 config rooted at tmp_path lake."""
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["raw_lake_root"] = str(tmp_path / "lake")
    raw["output_reports"] = str(tmp_path / "reports")
    cfg = tmp_path / "p8c2.yaml"
    cfg.write_text(yaml.dump(raw), encoding="utf-8")
    return cfg


def _mock_preflight_pass(**overrides: object) -> MagicMock:
    base = {
        "passed": True,
        "credential_source": "THETADATA_EMAIL+THETADATA_PASSWORD",
        "credentials_present": True,
        "thetadata_connect_ok": True,
        "raw_lake_root": "/tmp/lake",
        "raw_lake_root_writable": True,
        "free_disk_gb": 50.0,
        "frozen_dates_match_owner": True,
        "safety_flags_ok": True,
        "errors": [],
        "warnings": [],
    }
    base.update(overrides)
    mock = MagicMock()
    for k, v in base.items():
        setattr(mock, k, v)
    mock.to_dict.return_value = base
    return mock


def test_frozen_dates_match_owner_record() -> None:
    config = load_p8c2_ingest_config(_CONFIG_PATH)
    assert_frozen_dates_match_owner(config)
    assert len(config.frozen_dates) == 21
    assert tuple(d.isoformat() for d in sorted(config.frozen_dates)) == tuple(
        sorted(FROZEN_STAGE1_DATES)
    )


def test_rejects_non_frozen_date() -> None:
    with pytest.raises(P8C2ConfigError, match="non-frozen"):
        validate_date_subset([date(2020, 1, 1)])


def test_rejects_replacement_date_not_in_frozen_list() -> None:
    with pytest.raises(P8C2ConfigError, match="replacement dates forbidden"):
        validate_date_subset([date(2023, 1, 3)])


def test_safety_flags_reject_dataset_build(p8c2_config: Path) -> None:
    config = load_p8c2_ingest_config(p8c2_config)
    config.allow_dataset_build = True
    with pytest.raises(P8C2ConfigError, match="allow_dataset_build"):
        assert_safety_flags(config)


def test_max_dates_batches_correctly(p8c2_config: Path) -> None:
    config = load_p8c2_ingest_config(p8c2_config)
    batch = select_dates_to_attempt(config, dates_filter=None, max_dates=5)
    assert len(batch) == 5
    assert batch == sorted(config.frozen_dates)[:5]


def test_early_close_day_type() -> None:
    assert day_type_for_date(date(2023, 7, 3)) == "early_close"
    assert day_type_for_date(date(2024, 1, 3)) == "normal"


@patch("quant_lab.ml.datasets.p8c_controlled_ingest.run_preflight")
@patch("quant_lab.ml.datasets.p8c_controlled_ingest.ingest_one_frozen_date")
def test_dry_run_performs_no_ingest(
    mock_ingest: MagicMock,
    mock_preflight: MagicMock,
    p8c2_config: Path,
    tmp_path: Path,
) -> None:
    mock_preflight.return_value = _mock_preflight_pass(
        raw_lake_root=str(tmp_path / "lake"),
    )
    mock_ingest.return_value = PerDateIngestStatus(
        date="2023-02-23",
        status="success",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_seconds=1.0,
        rows_by_dataset={},
        files_written=0,
        manifest_paths=[],
        checksum_status="ok",
        completeness_status="complete",
        fallbacks_used=[],
        warnings=[],
    )
    config = load_p8c2_ingest_config(p8c2_config)
    result = run_p8c2_controlled_ingest(
        config,
        project_root=tmp_path,
        execute=False,
        resume=False,
        dates_filter=[date(2023, 2, 23)],
        max_dates=None,
    )
    assert result.mode == "dry-run"
    assert result.actual_ingest_performed is False
    mock_ingest.assert_called_once()
    assert mock_ingest.call_args.kwargs["dry_run"] is True


@patch("quant_lab.ml.datasets.p8c_controlled_ingest.run_preflight")
@patch("quant_lab.ml.datasets.p8c_controlled_ingest.ingest_one_frozen_date")
def test_execute_calls_ingest_for_frozen_dates_only(
    mock_ingest: MagicMock,
    mock_preflight: MagicMock,
    p8c2_config: Path,
    tmp_path: Path,
) -> None:
    mock_preflight.return_value = _mock_preflight_pass(
        raw_lake_root=str(tmp_path / "lake"),
    )
    mock_ingest.return_value = PerDateIngestStatus(
        date="2023-02-23",
        status="success",
        started_at="t0",
        finished_at="t1",
        duration_seconds=1.0,
        rows_by_dataset={},
        files_written=1,
        manifest_paths=[],
        checksum_status="ok",
        completeness_status="complete",
        fallbacks_used=[],
        warnings=[],
    )
    config = load_p8c2_ingest_config(p8c2_config)
    result = run_p8c2_controlled_ingest(
        config,
        project_root=tmp_path,
        execute=True,
        resume=False,
        dates_filter=[date(2023, 2, 23)],
        max_dates=None,
    )
    assert result.actual_ingest_performed is True
    assert mock_ingest.call_args.kwargs["dry_run"] is False
    assert result.replacement_dates_used is False


@patch("quant_lab.ml.datasets.p8c_controlled_ingest.run_preflight")
@patch("quant_lab.ml.datasets.p8c_controlled_ingest._status_from_readiness")
def test_resume_skips_complete_dates(
    mock_readiness: MagicMock,
    mock_preflight: MagicMock,
    p8c2_config: Path,
    tmp_path: Path,
) -> None:
    mock_preflight.return_value = _mock_preflight_pass(
        raw_lake_root=str(tmp_path / "lake"),
    )
    mock_readiness.return_value = PerDateIngestStatus(
        date="2023-02-23",
        status="skipped_complete",
        started_at="t0",
        finished_at="t1",
        duration_seconds=0.0,
        rows_by_dataset={"option_trade_tick": 100},
        files_written=1,
        manifest_paths=["/lake/manifest.json"],
        checksum_status="ok",
        completeness_status="complete",
        fallbacks_used=[],
        warnings=[],
    )
    config = load_p8c2_ingest_config(p8c2_config)
    with patch(
        "quant_lab.ml.datasets.p8c_controlled_ingest.ingest_rth_trade_date"
    ) as mock_rth:
        result = run_p8c2_controlled_ingest(
            config,
            project_root=tmp_path,
            execute=True,
            resume=True,
            dates_filter=[date(2023, 2, 23)],
            max_dates=None,
        )
        mock_rth.assert_not_called()
    assert result.skipped_complete_dates == ["2023-02-23"]


@patch("quant_lab.ml.datasets.p8c_controlled_ingest.run_preflight")
def test_incomplete_partition_fails_closed(
    mock_preflight: MagicMock,
    p8c2_config: Path,
    tmp_path: Path,
) -> None:
    mock_preflight.return_value = _mock_preflight_pass(
        raw_lake_root=str(tmp_path / "lake"),
    )
    config = load_p8c2_ingest_config(p8c2_config)
    incomplete_status = PerDateIngestStatus(
        date="2023-02-23",
        status="incomplete",
        started_at="t0",
        finished_at="t1",
        duration_seconds=0.0,
        rows_by_dataset={},
        files_written=0,
        manifest_paths=[],
        checksum_status="not_checked",
        completeness_status="incomplete_refuse:option_trade_tick",
        fallbacks_used=[],
        warnings=[],
        error_message="incomplete partitions refuse overwrite",
    )
    with patch(
        "quant_lab.ml.datasets.p8c_controlled_ingest.ingest_one_frozen_date",
        return_value=incomplete_status,
    ):
        result = run_p8c2_controlled_ingest(
            config,
            project_root=tmp_path,
            execute=True,
            resume=True,
            dates_filter=[date(2023, 2, 23)],
            max_dates=None,
        )
    assert result.incomplete_dates == ["2023-02-23"]
    assert result.gate_status == "PASS_WITH_FAILURES"


@patch("quant_lab.ml.datasets.p8c_controlled_ingest.run_preflight")
@patch("quant_lab.ml.datasets.p8c_controlled_ingest.ingest_one_frozen_date")
def test_failure_does_not_create_replacement_date(
    mock_ingest: MagicMock,
    mock_preflight: MagicMock,
    p8c2_config: Path,
    tmp_path: Path,
) -> None:
    mock_preflight.return_value = _mock_preflight_pass(
        raw_lake_root=str(tmp_path / "lake"),
    )
    mock_ingest.return_value = PerDateIngestStatus(
        date="2023-02-23",
        status="failed",
        started_at="t0",
        finished_at="t1",
        duration_seconds=1.0,
        rows_by_dataset={},
        files_written=0,
        manifest_paths=[],
        checksum_status="not_checked",
        completeness_status="incomplete",
        fallbacks_used=[],
        warnings=[],
        error_message="api_error",
    )
    config = load_p8c2_ingest_config(p8c2_config)
    result = run_p8c2_controlled_ingest(
        config,
        project_root=tmp_path,
        execute=True,
        resume=False,
        dates_filter=[date(2023, 2, 23)],
        max_dates=None,
    )
    assert result.failed_dates == ["2023-02-23"]
    assert result.replacement_dates_used is False
    assert len(result.attempted_dates) == 1


@patch("quant_lab.ml.datasets.p8c_controlled_ingest.run_preflight")
@patch("quant_lab.ml.datasets.p8c_controlled_ingest.ingest_one_frozen_date")
def test_manifest_records_no_build_or_fit(
    mock_ingest: MagicMock,
    mock_preflight: MagicMock,
    p8c2_config: Path,
    tmp_path: Path,
) -> None:
    mock_preflight.return_value = _mock_preflight_pass(
        raw_lake_root=str(tmp_path / "lake"),
    )
    mock_ingest.return_value = PerDateIngestStatus(
        date="2023-02-23",
        status="success",
        started_at="t0",
        finished_at="t1",
        duration_seconds=1.0,
        rows_by_dataset={},
        files_written=0,
        manifest_paths=[],
        checksum_status="ok",
        completeness_status="complete",
        fallbacks_used=[],
        warnings=[],
    )
    config = load_p8c2_ingest_config(p8c2_config)
    result = run_p8c2_controlled_ingest(
        config,
        project_root=tmp_path,
        execute=True,
        resume=False,
        dates_filter=[date(2023, 2, 23)],
        max_dates=None,
    )
    paths = write_p8c2_artifacts(result, tmp_path / "reports")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["dataset_build_performed"] is False
    assert manifest["feature_build_performed"] is False
    assert manifest["model_fitting_performed"] is False
    assert manifest["p8b4_authorized"] is False
    assert manifest["temporal_warning_carried_forward"] is True
    assert manifest["proxy_bucket_warning_carried_forward"] is True
    assert manifest["replacement_dates_used"] is False


@patch("quant_lab.ml.datasets.p8c_controlled_ingest.run_preflight")
@patch("quant_lab.ml.datasets.p8c_controlled_ingest.ingest_one_frozen_date")
def test_cli_dry_run(
    mock_ingest: MagicMock,
    mock_preflight: MagicMock,
    p8c2_config: Path,
    tmp_path: Path,
) -> None:
    import importlib.util

    mock_preflight.return_value = _mock_preflight_pass(
        raw_lake_root=str(tmp_path / "lake"),
    )
    mock_ingest.return_value = PerDateIngestStatus(
        date="2023-02-23",
        status="success",
        started_at="t0",
        finished_at="t1",
        duration_seconds=0.1,
        rows_by_dataset={},
        files_written=0,
        manifest_paths=[],
        checksum_status="ok",
        completeness_status="complete",
        fallbacks_used=[],
        warnings=[],
    )
    spec = importlib.util.spec_from_file_location("run_p8c2", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    argv = [
        str(_SCRIPT),
        "--config",
        str(p8c2_config),
        "--dry-run",
        "--max-dates",
        "1",
        "--output-dir",
        str(tmp_path / "reports"),
    ]
    with patch.object(sys, "argv", argv):
        assert mod.main() == 0
