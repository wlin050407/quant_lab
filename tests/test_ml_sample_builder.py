"""Tests for ML-P7.5/7.6 sample builder."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from quant_lab.ml.datasets.lake_ingest import DateIngestResult
from quant_lab.ml.datasets.reporting import load_completed_checkpoint_dates, write_per_date_report
from quant_lab.ml.datasets.sample_builder import (
    DateEntry,
    SampleBuildConfig,
    build_dry_run_plan,
    build_sample_dataset,
    load_sample_config,
    missing_partitions_for_date,
    seed_pilot_lake_for_date,
    try_ingest_date,
    validate_dates_not_future,
)


def _minimal_config(tmp_path: Path, dates: list[DateEntry]) -> SampleBuildConfig:
    return SampleBuildConfig(
        version="test",
        root="SPXW",
        index_symbol="SPX",
        strike_range=60,
        strike_range_fallback=30,
        anchor_type="manual",
        anchor_start_offset_minutes=5,
        anchor_end_offset_minutes=5,
        session_rth_start="09:30:00",
        session_rth_end="16:00:00",
        lake_root=tmp_path / "lake",
        dataset_root=tmp_path / "dataset",
        feature_root=tmp_path / "features",
        report_root=tmp_path / "reports",
        joined_root=tmp_path / "joined",
        ingest_enabled=False,
        ingest_full_rth=True,
        ingest_max_retries=2,
        ingest_request_budget_per_date=8,
        ingest_write_raw_lake=True,
        ingest_idempotent_skip_existing=True,
        quote_resolution="tick_or_1s",
        index_resolution="tick_or_1s",
        stage_a_dates=(),
        seed_from_pilot_lake=None,
        dates=tuple(dates),
    )


def test_load_config_from_yaml(tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        yaml.dump(
            {
                "version": "pit-sample-v1",
                "root": "SPXW",
                "ingest": {"enabled": True, "max_retries": 2, "request_budget_per_date": 10},
                "data": {"quote_resolution": "tick_or_1s"},
                "dates": [{"date": "2024-01-05", "day_type": "normal"}],
            }
        ),
        encoding="utf-8",
    )
    cfg = load_sample_config(cfg_path)
    assert cfg.version == "pit-sample-v1"
    assert cfg.ingest_enabled is True
    assert cfg.quote_resolution == "tick_or_1s"
    assert cfg.ingest_request_budget_per_date == 10


def test_future_date_rejection() -> None:
    future = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="future"):
        validate_dates_not_future([future], today=date.today())


def test_dry_run_plan(tmp_path: Path) -> None:
    entry = DateEntry(
        trade_date=date(2024, 1, 5),
        day_type="normal",
        anchor_type="manual",
        manual_anchors=("13:01:00",),
    )
    cfg = _minimal_config(tmp_path, [entry])
    plan = build_dry_run_plan(cfg)
    assert plan.total_anchors == 1
    assert "2024-01-05" in plan.missing_partitions


def test_dry_run_ingest_enabled_plan(tmp_path: Path) -> None:
    entry = DateEntry(trade_date=date(2024, 1, 5), day_type="normal")
    cfg = replace(_minimal_config(tmp_path, [entry]), ingest_enabled=True)
    plan = build_dry_run_plan(cfg)
    assert plan.ingest_enabled is True
    assert "2024-01-05" in plan.ingest_plans
    assert plan.estimated_total_api_calls >= 0


def test_idempotent_seed_from_pilot(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    pilot = tmp_path / "pilot"
    sample_lake = tmp_path / "sample_lake"
    _build_fixture_lake(pilot)
    trade = date(2026, 6, 10)
    cfg = _minimal_config(
        tmp_path,
        [DateEntry(trade_date=trade, day_type="pilot", anchor_type="manual", manual_anchors=("13:01:00",))],
    )
    cfg = replace(cfg, lake_root=sample_lake, seed_from_pilot_lake=pilot)
    assert seed_pilot_lake_for_date(cfg, trade) is True
    assert seed_pilot_lake_for_date(cfg, trade) is False
    assert len(missing_partitions_for_date(cfg, trade)) == 0


def test_sample_build_from_seeded_lake(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    pilot = tmp_path / "pilot"
    _build_fixture_lake(pilot)
    trade = date(2026, 6, 10)
    cfg = _minimal_config(
        tmp_path,
        [
            DateEntry(
                trade_date=trade,
                day_type="pilot",
                anchor_type="manual",
                manual_anchors=("13:01:00",),
            )
        ],
    )
    cfg = replace(
        cfg,
        lake_root=tmp_path / "lake",
        seed_from_pilot_lake=pilot,
        dataset_root=tmp_path / "out" / "dataset",
        feature_root=tmp_path / "out" / "features",
        report_root=tmp_path / "out" / "reports",
        joined_root=tmp_path / "out" / "joined",
    )
    seed_pilot_lake_for_date(cfg, trade)
    result = build_sample_dataset(cfg, max_dates=1, dry_run=False)
    assert len(result.joined_rows) == 1
    assert result.leakage.passed
    assert (cfg.joined_root / "joined.parquet").is_file()


def test_try_ingest_disabled_records_reason(tmp_path: Path) -> None:
    entry = DateEntry(trade_date=date(2024, 1, 5), day_type="normal")
    cfg = _minimal_config(tmp_path, [entry])
    ok, reason, ingest = try_ingest_date(cfg, entry, dry_run=False)
    assert not ok
    assert "ingest_disabled" in reason
    assert ingest is None


@patch("quant_lab.ml.datasets.sample_builder.ingest_rth_trade_date")
def test_try_ingest_enabled_success(mock_ingest: MagicMock, tmp_path: Path) -> None:
    entry = DateEntry(trade_date=date(2024, 1, 5), day_type="normal")
    cfg = replace(_minimal_config(tmp_path, [entry]), ingest_enabled=True)
    mock_ingest.return_value = DateIngestResult(
        trade_date=date(2024, 1, 5),
        success=True,
        reason="ingest_complete",
    )
    with patch(
        "quant_lab.ml.datasets.sample_builder.missing_partitions_for_date",
        side_effect=[["option_trade_tick"], []],
    ):
        ok, reason, result = try_ingest_date(cfg, entry, dry_run=False)
    assert ok
    assert result is not None
    mock_ingest.assert_called_once()


@patch("quant_lab.ml.datasets.sample_builder.ingest_rth_trade_date")
def test_try_ingest_records_failure(mock_ingest: MagicMock, tmp_path: Path) -> None:
    entry = DateEntry(trade_date=date(2024, 1, 5), day_type="normal")
    cfg = replace(_minimal_config(tmp_path, [entry]), ingest_enabled=True)
    mock_ingest.return_value = DateIngestResult(
        trade_date=date(2024, 1, 5),
        success=False,
        reason="ingest_failed:RuntimeError:no creds",
    )
    ok, reason, _ = try_ingest_date(cfg, entry, dry_run=False)
    assert not ok
    assert reason.startswith("ingest_failed")


def test_early_close_anchors_respect_session_close() -> None:
    from quant_lab.data.intraday_time import session_datetime
    from quant_lab.ml.datasets.point_in_time import AnchorConfig, generate_anchors

    trade = date(2024, 7, 3)
    cfg = AnchorConfig(
        anchor_type="regular_5min",
        interval_minutes=5,
        start_offset_minutes=5,
        end_offset_minutes=5,
        session_close_time="13:00:00",
    )
    anchors = generate_anchors(trade, cfg)
    assert len(anchors) == 41
    assert max(ts for ts, _ in anchors) <= session_datetime(trade, "12:55:00")


def test_parse_dates_filter(tmp_path: Path) -> None:
    from quant_lab.ml.datasets.sample_builder import parse_dates_filter, select_date_entries

    parsed = parse_dates_filter("2024-01-19,2024-05-03")
    assert parsed == (date(2024, 1, 19), date(2024, 5, 3))
    cfg = _minimal_config(
        tmp_path,
        [
            DateEntry(trade_date=date(2024, 1, 19), day_type="monthly_opex"),
            DateEntry(trade_date=date(2024, 5, 3), day_type="trend_up"),
        ],
    )
    selected = select_date_entries(cfg, dates_filter=(date(2024, 1, 19),))
    assert len(selected) == 1
    assert selected[0].trade_date == date(2024, 1, 19)


def test_checkpoint_per_date_report_written(tmp_path: Path) -> None:
    report = {
        "status": "completed",
        "trade_date": "2024-01-19",
        "row_count": 77,
        "valid_zone_ratio": 0.5,
    }
    write_per_date_report(tmp_path / "reports", report)
    assert load_completed_checkpoint_dates(tmp_path / "reports") == {"2024-01-19"}


@patch("quant_lab.ml.datasets.sample_builder.build_dataset_rows")
@patch("quant_lab.ml.datasets.sample_builder.build_feature_dataset")
def test_resume_skips_completed_checkpoint_date(
    mock_features: MagicMock,
    mock_rows: MagicMock,
    tmp_path: Path,
) -> None:
    from quant_lab.ml.datasets.reporting import write_per_date_report
    from quant_lab.ml.datasets.sample_builder import SampleBuildOptions

    trade = date(2024, 1, 19)
    cfg = _minimal_config(tmp_path, [DateEntry(trade_date=trade, day_type="monthly_opex")])
    cfg = replace(
        cfg,
        lake_root=tmp_path / "lake",
        report_root=tmp_path / "reports",
        joined_root=tmp_path / "joined",
    )
    write_per_date_report(
        cfg.report_root,
        {"status": "completed", "trade_date": trade.isoformat(), "row_count": 1},
    )
    result = build_sample_dataset(
        cfg,
        max_dates=1,
        dry_run=False,
        options=SampleBuildOptions(
            dates_filter=(trade,),
            checkpoint_per_date=True,
            resume=True,
        ),
    )
    mock_rows.assert_not_called()
    mock_features.assert_not_called()
    assert result.joined_rows == []
