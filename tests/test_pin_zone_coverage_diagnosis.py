"""Tests for ML-P7.6.1 pin zone coverage diagnosis."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from quant_lab.data.intraday_time import session_datetime
from quant_lab.factors.pin_cluster import detect_pin_cluster
from quant_lab.ml.datasets.pin_zone_diagnosis import (
    classify_merge_reason,
    diagnose_anchor_pin_zone,
)
from quant_lab.ml.datasets.point_in_time import AnchorConfig, generate_anchors


def test_early_close_anchors_end_before_close() -> None:
    trade = date(2024, 7, 3)
    cfg = AnchorConfig(
        anchor_type="regular_5min",
        session_close_time="13:00:00",
    )
    anchors = generate_anchors(trade, cfg)
    assert max(ts for ts, _ in anchors) <= session_datetime(trade, "12:55:00")


def test_classify_merge_reason_low_pin_reliability() -> None:
    assert classify_merge_reason("low_pin_reliability") == "low_pin_reliability_gate"


def test_classify_merge_reason_distance() -> None:
    assert classify_merge_reason("strikes_too_far_apart") == "pin_distance_too_wide"


def test_classify_merge_reason_strength() -> None:
    assert classify_merge_reason("secondary_too_weak") == "secondary_strength_too_low"


def test_replay_default_blocks_cluster_with_unknown_reliability() -> None:
    rankings = [
        {"strike": 6000.0, "weight_pct": 40.0},
        {"strike": 6005.0, "weight_pct": 35.0},
    ]
    default = detect_pin_cluster(rankings, 6002.0, symbol="SPX")
    assert not default.is_cluster
    assert default.merge_reason == "low_pin_reliability"


def test_terminal_parity_path_can_merge_adjacent_magnets() -> None:
    rankings = [
        {"strike": 6000.0, "weight_pct": 40.0},
        {"strike": 6005.0, "weight_pct": 35.0},
    ]
    parity = detect_pin_cluster(
        rankings,
        6002.0,
        symbol="SPX",
        regime="long_gamma",
        pin_reliability="high",
    )
    assert parity.is_cluster
    assert parity.merge_reason == "adjacent_gex_peaks"


def test_diagnose_anchor_from_fixture_lake(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path)
    trade = date(2026, 6, 10)
    as_of = session_datetime(trade, "13:01:00")
    default = diagnose_anchor_pin_zone(
        trade,
        as_of,
        data_root=lake,
        path="replay_default",
    )
    parity = diagnose_anchor_pin_zone(
        trade,
        as_of,
        data_root=lake,
        path="terminal_parity",
    )
    assert not default.is_cluster
    assert default.path == "replay_default"
    assert parity.path == "terminal_parity"
    assert parity.regime in {"long_gamma", "short_gamma", "undetermined"}


def test_leakage_label_after_as_of_early_close() -> None:
    from quant_lab.ml.leakage import check_label_timestamp_after_as_of

    trade = date(2024, 7, 3)
    as_of = session_datetime(trade, "12:55:00")
    label_ts = session_datetime(trade, "13:00:00")
    result = check_label_timestamp_after_as_of(as_of, label_ts)
    assert result.passed


def test_build_diagnosis_report_no_secrets(tmp_path: Path) -> None:
    import sys

    from quant_lab.ml.datasets.pin_zone_diagnosis import build_pin_zone_diagnosis_report
    from quant_lab.ml.datasets.sample_builder import DateEntry, SampleBuildConfig

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path / "lake")
    cfg = SampleBuildConfig(
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
        lake_root=lake,
        dataset_root=tmp_path / "ds",
        feature_root=tmp_path / "ft",
        report_root=tmp_path / "rp",
        joined_root=tmp_path / "jn",
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
        dates=(
            DateEntry(
                trade_date=date(2026, 6, 10),
                day_type="pilot",
                anchor_type="manual",
                manual_anchors=("13:01:00",),
            ),
        ),
    )
    report = build_pin_zone_diagnosis_report(cfg, max_dates=1, sample_every_n=1)
    text = str(report)
    assert "password" not in text.lower()
    assert "adapter_bug_suspected" in report
