"""Tests for ML-P7.6.2 long-gamma candidate discovery."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from quant_lab.ml.datasets.long_gamma_discovery import (
    AnchorScanResult,
    DateCandidateMetrics,
    aggregate_anchor_metrics,
    discover_long_gamma_candidates,
    rank_candidates,
    scan_anchor_times_for_day_type,
    stage_a_plus_date_count,
)
from quant_lab.ml.datasets.sample_builder import DateEntry, SampleBuildConfig


def _make_config(lake: Path, *, ingest: bool = False) -> SampleBuildConfig:
    return SampleBuildConfig(
        version="test-lg",
        root="SPXW",
        index_symbol="SPX",
        strike_range=60,
        strike_range_fallback=30,
        anchor_type="regular_5min",
        anchor_start_offset_minutes=5,
        anchor_end_offset_minutes=5,
        session_rth_start="09:30:00",
        session_rth_end="16:00:00",
        lake_root=lake,
        dataset_root=lake / "ds",
        feature_root=lake / "ft",
        report_root=lake / "rp",
        joined_root=lake / "jn",
        ingest_enabled=ingest,
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
            DateEntry(trade_date=date(2024, 1, 5), day_type="normal"),
            DateEntry(trade_date=date(2024, 7, 3), day_type="early_close"),
        ),
    )


def test_early_close_scan_anchors_shorter() -> None:
    normal = scan_anchor_times_for_day_type("normal")
    early = scan_anchor_times_for_day_type("early_close")
    assert len(normal) == 6
    assert len(early) == 3
    assert max(early) <= "12:00:00"


def test_aggregate_long_gamma_and_valid_zone_ratios() -> None:
    entry = DateEntry(trade_date=date(2024, 6, 7), day_type="normal")
    anchors = [
        AnchorScanResult(
            trade_date=entry.trade_date,
            as_of_timestamp="2024-06-07T10:00:00-04:00",
            net_gex=1.0,
            regime="long_gamma",
            pin_reliability="high",
            primary_pin_t=6000.0,
            secondary_pin_t=6005.0,
            pin_score_t=75.0,
            zone_low_t=6000.0,
            zone_high_t=6005.0,
            strength_ratio=0.85,
            is_valid_zone=True,
            zone_failure_reason="valid_cluster",
        ),
        AnchorScanResult(
            trade_date=entry.trade_date,
            as_of_timestamp="2024-06-07T11:00:00-04:00",
            net_gex=-1.0,
            regime="short_gamma",
            pin_reliability="caution",
            primary_pin_t=5990.0,
            secondary_pin_t=5995.0,
            pin_score_t=72.0,
            zone_low_t=None,
            zone_high_t=None,
            strength_ratio=0.80,
            is_valid_zone=False,
            zone_failure_reason="short_gamma_regime_gate",
        ),
    ]
    metrics = aggregate_anchor_metrics(entry, anchors, lake_status="raw_lake_exists")
    assert metrics.long_gamma_anchor_ratio == 0.5
    assert metrics.valid_zone_anchor_ratio == 0.5
    assert metrics.secondary_strength_pass_ratio == 1.0
    assert metrics.zone_failure_reason_distribution["short_gamma_regime_gate"] == 1


def test_rank_candidates_prefers_valid_zone() -> None:
    low = DateCandidateMetrics(
        trade_date=date(2024, 1, 5),
        day_type="normal",
        lake_status="raw_lake_exists",
        anchor_count=6,
        long_gamma_anchor_ratio=0.0,
        valid_zone_anchor_ratio=0.0,
        net_gex_positive_ratio=0.0,
        secondary_pin_nonnull_ratio=1.0,
        secondary_strength_pass_ratio=0.5,
        pin_reliability_mean=2.0,
        zone_failure_reason_distribution={"short_gamma_regime_gate": 6},
        composite_score=10.0,
    )
    high = DateCandidateMetrics(
        trade_date=date(2024, 6, 7),
        day_type="normal",
        lake_status="raw_lake_exists",
        anchor_count=6,
        long_gamma_anchor_ratio=0.83,
        valid_zone_anchor_ratio=0.67,
        net_gex_positive_ratio=0.83,
        secondary_pin_nonnull_ratio=1.0,
        secondary_strength_pass_ratio=0.83,
        pin_reliability_mean=3.5,
        zone_failure_reason_distribution={"short_gamma_regime_gate": 2},
        composite_score=80.0,
    )
    ranked = rank_candidates([low, high], top_n=2)
    assert ranked[0].trade_date == date(2024, 6, 7)


def test_failure_reason_aggregation_missing_secondary() -> None:
    entry = DateEntry(trade_date=date(2024, 7, 3), day_type="early_close")
    anchors = [
        AnchorScanResult(
            trade_date=entry.trade_date,
            as_of_timestamp="2024-07-03T10:00:00-04:00",
            net_gex=0.5,
            regime="long_gamma",
            pin_reliability="moderate",
            primary_pin_t=5500.0,
            secondary_pin_t=None,
            pin_score_t=55.0,
            zone_low_t=None,
            zone_high_t=None,
            strength_ratio=None,
            is_valid_zone=False,
            zone_failure_reason="missing_secondary_pin",
        ),
    ]
    metrics = aggregate_anchor_metrics(entry, anchors, lake_status="raw_lake_exists")
    assert metrics.zone_failure_reason_distribution["missing_secondary_pin"] == 1


def test_strength_threshold_fail_reason() -> None:
    entry = DateEntry(trade_date=date(2024, 7, 3), day_type="early_close")
    anchors = [
        AnchorScanResult(
            trade_date=entry.trade_date,
            as_of_timestamp="2024-07-03T11:00:00-04:00",
            net_gex=0.5,
            regime="long_gamma",
            pin_reliability="high",
            primary_pin_t=5500.0,
            secondary_pin_t=5520.0,
            pin_score_t=70.0,
            zone_low_t=None,
            zone_high_t=None,
            strength_ratio=0.55,
            is_valid_zone=False,
            zone_failure_reason="secondary_strength_too_low",
        ),
    ]
    metrics = aggregate_anchor_metrics(entry, anchors, lake_status="raw_lake_exists")
    assert metrics.secondary_strength_pass_ratio == 0.0
    assert metrics.zone_failure_reason_distribution["secondary_strength_too_low"] == 1


def test_discover_dry_run_missing_lake_no_network(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path / "empty_lake", ingest=False)
    report = discover_long_gamma_candidates(cfg, max_dates=2, dry_run=True)
    assert report["dry_run"] is True
    assert report["dates_failed"] >= 1
    text = str(report)
    assert "password" not in text.lower()


def test_scan_existing_fixture_lake(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path / "lake")
    cfg = _make_config(lake)
    cfg = SampleBuildConfig(
        **{
            **cfg.__dict__,
            "dates": (
                DateEntry(
                    trade_date=date(2026, 6, 10),
                    day_type="pilot",
                    anchor_type="manual",
                    manual_anchors=("13:01:00",),
                ),
            ),
        }
    )
    report = discover_long_gamma_candidates(cfg, max_dates=1, dry_run=False)
    assert report["dates_with_lake"] == 1


def test_stage_a_plus_date_count() -> None:
    assert stage_a_plus_date_count(["2024-06-07", "2024-04-05"], min_dates=5, max_dates=10) == 5
    assert stage_a_plus_date_count([f"2024-0{i}-01" for i in range(1, 9)], min_dates=5, max_dates=8) == 8


def test_top_candidate_selection() -> None:
    metrics = [
        DateCandidateMetrics(
            trade_date=date(2024, d, 1),
            day_type="normal",
            lake_status="raw_lake_exists",
            anchor_count=6,
            long_gamma_anchor_ratio=r,
            valid_zone_anchor_ratio=v,
            net_gex_positive_ratio=r,
            secondary_pin_nonnull_ratio=1.0,
            secondary_strength_pass_ratio=0.7,
            pin_reliability_mean=3.0,
            zone_failure_reason_distribution={},
            composite_score=score,
        )
        for d, r, v, score in [(5, 0.0, 0.0, 1.0), (6, 0.5, 0.2, 50.0), (7, 0.8, 0.5, 90.0)]
    ]
    top = rank_candidates(metrics, top_n=2)
    assert top[0].trade_date == date(2024, 7, 1)
    assert top[1].trade_date == date(2024, 6, 1)
