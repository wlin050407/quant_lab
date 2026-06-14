"""Tests for ML-P7.5 sample builder."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from quant_lab.ml.datasets.sample_builder import (
    DateEntry,
    SampleBuildConfig,
    build_dry_run_plan,
    build_sample_dataset,
    load_sample_config,
    missing_partitions_for_date,
    seed_pilot_lake_for_date,
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
                "dates": [{"date": "2024-01-05", "day_type": "normal"}],
            }
        ),
        encoding="utf-8",
    )
    cfg = load_sample_config(cfg_path)
    assert cfg.version == "pit-sample-v1"
    assert len(cfg.dates) == 1


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
    assert seed_pilot_lake_for_date(cfg, trade) is False  # idempotent skip
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
