"""Tests for ML-P7.6 lake ingest (no real ThetaData)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from quant_lab.data.intraday_lake import IncompletePartitionError
from quant_lab.ml.datasets.lake_ingest import (
    _is_full_rth_window,
    build_rth_ingest_plan,
    ingest_rth_trade_date,
    rth_window_for_day_type,
)


def test_full_rth_window_detection() -> None:
    assert _is_full_rth_window("09:30:00", "16:00:00")
    assert _is_full_rth_window("09:30:00", "13:00:00")
    assert not _is_full_rth_window("13:00:00", "13:02:00")


def test_rth_window_early_close() -> None:
    ws, we, rth_end = rth_window_for_day_type(
        "early_close",
        session_rth_start="09:30:00",
        session_rth_end="16:00:00",
    )
    assert ws == "09:30:00"
    assert we == "13:00:00"
    assert rth_end == "13:00:00"


def test_ingest_plan_empty_lake(tmp_path: Path) -> None:
    plan = build_rth_ingest_plan(
        trade_date=date(2024, 1, 5),
        day_type="normal",
        lake_root=tmp_path / "lake",
        root="SPXW",
        symbol="SPX",
        strike_range=60,
        session_rth_start="09:30:00",
        session_rth_end="16:00:00",
        quote_resolution="tick_or_1s",
        index_resolution="tick_or_1s",
        idempotent_skip_existing=True,
    )
    assert plan.estimated_api_calls > 0
    assert plan.partitions_to_fetch


def test_ingest_dry_run_no_network(tmp_path: Path) -> None:
    result = ingest_rth_trade_date(
        trade_date=date(2024, 1, 5),
        day_type="normal",
        lake_root=tmp_path / "lake",
        strike_range=60,
        session_rth_start="09:30:00",
        session_rth_end="16:00:00",
        dry_run=True,
    )
    assert result.success
    assert result.reason == "dry_run_plan_only"


def test_request_budget_exceeded(tmp_path: Path) -> None:
    with patch(
        "quant_lab.ml.datasets.lake_ingest.build_rth_ingest_plan",
    ) as mock_plan:
        mock_plan.return_value.partitions_to_fetch = ("option_trade_tick",)
        mock_plan.return_value.partitions_to_skip = ()
        mock_plan.return_value.estimated_api_calls = 99
        mock_plan.return_value.window_start = "09:30:00"
        mock_plan.return_value.window_end = "16:00:00"
        mock_plan.return_value.session_rth_end = "16:00:00"
        mock_plan.return_value.to_dict = lambda: {}
        result = ingest_rth_trade_date(
            trade_date=date(2024, 1, 5),
            day_type="normal",
            lake_root=tmp_path / "lake",
            strike_range=60,
            session_rth_start="09:30:00",
            session_rth_end="16:00:00",
            request_budget_per_date=5,
            dry_run=False,
        )
    assert not result.success
    assert "request_budget_exceeded" in result.reason


def test_incomplete_partition_refused(tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    part = (
        lake
        / "dataset=option_trade_tick"
        / "root=SPXW"
        / "trade_date=2024-01-05"
        / "expiration=2024-01-05"
    )
    part.mkdir(parents=True)
    (part / "_manifest.json").write_text('{"ingestion_status": "incomplete"}', encoding="utf-8")
    with pytest.raises(IncompletePartitionError):
        build_rth_ingest_plan(
            trade_date=date(2024, 1, 5),
            day_type="normal",
            lake_root=lake,
            root="SPXW",
            symbol="SPX",
            strike_range=60,
            session_rth_start="09:30:00",
            session_rth_end="16:00:00",
            quote_resolution="tick_or_1s",
            index_resolution="tick_or_1s",
            idempotent_skip_existing=True,
        )
