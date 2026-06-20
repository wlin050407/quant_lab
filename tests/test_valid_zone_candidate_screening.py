"""Tests for ML-P7.6.7 valid-zone candidate screening."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from quant_lab.ml.datasets.sample_builder import DateEntry, SampleBuildConfig
from quant_lab.ml.datasets.valid_zone_screening import (
    AnchorScreenResult,
    DateScreenMetrics,
    LakeDateInventory,
    aggregate_anchor_results,
    discover_lake_dates,
    inventory_raw_lake,
    label_diversity_score,
    load_day_type_map,
    metrics_from_dict,
    rank_screened_dates,
    ranking_sort_key,
    rare_label_bonus,
    recommend_full_build_dates,
    screen_anchor_at,
    screen_valid_zone_candidates,
    write_per_date_screen_report,
)


def _minimal_config(tmp_path: Path) -> SampleBuildConfig:
    return SampleBuildConfig(
        version="test",
        root="SPXW",
        index_symbol="SPX",
        strike_range=60,
        strike_range_fallback=30,
        anchor_type="regular_5min",
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
        dates=(),
    )


def _metrics(
    trade_date: str,
    *,
    included: int = 0,
    valid_zone_ratio: float = 0.0,
    inside: int = 0,
    below: int = 0,
    above: int = 0,
    replay_quality: float = 0.9,
    runtime: float = 100.0,
) -> DateScreenMetrics:
    return DateScreenMetrics(
        trade_date=date.fromisoformat(trade_date),
        day_type="normal",
        lake_status="raw_lake_complete",
        anchor_count=77,
        valid_zone_count=int(valid_zone_ratio * 77),
        valid_zone_ratio=valid_zone_ratio,
        included_count=included,
        excluded_count=77 - included,
        inside_count=inside,
        below_count=below,
        above_count=above,
        primary_pin_nonnull_ratio=0.5,
        secondary_pin_nonnull_ratio=0.3,
        zone_low_nonnull_ratio=valid_zone_ratio,
        zone_high_nonnull_ratio=valid_zone_ratio,
        mean_pin_score=2.0,
        net_gex_positive_ratio=0.8,
        short_gamma_regime_ratio=0.0,
        secondary_strength_too_low_ratio=0.0,
        pin_distance_too_wide_ratio=0.5,
        low_pin_reliability_ratio=0.0,
        mean_replay_quality=replay_quality,
        runtime_seconds=runtime,
    )


def test_complete_raw_lake_date_detection(tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    sm = lake / "dataset=session_metadata/root=SPXW/trade_date=2024-01-19"
    sm.mkdir(parents=True)
    (sm / "_manifest.json").write_text("{}", encoding="utf-8")
    assert discover_lake_dates(lake) == ["2024-01-19"]


def test_skipped_incomplete_date(tmp_path: Path) -> None:
    cfg = _minimal_config(tmp_path)
    sm = cfg.lake_root / "dataset=session_metadata/root=SPXW/trade_date=2024-01-19"
    sm.mkdir(parents=True)
    inv = inventory_raw_lake(cfg, candidate_dates=["2024-01-19"])
    assert inv.complete_dates == ()
    assert "2024-01-19" in inv.incomplete_dates


def test_regular_5min_anchor_screening_aggregation() -> None:
    anchors = [
        AnchorScreenResult(
            has_valid_zone=True,
            included=True,
            close_location="inside",
            primary_pin_nonnull=True,
            secondary_pin_nonnull=True,
            zone_low_nonnull=True,
            zone_high_nonnull=True,
            pin_score=2.5,
            net_gex_positive=True,
            regime="long_gamma",
            zone_failure_reason="valid_cluster",
            replay_quality=0.95,
        ),
        AnchorScreenResult(
            has_valid_zone=False,
            included=False,
            close_location=None,
            primary_pin_nonnull=True,
            secondary_pin_nonnull=False,
            zone_low_nonnull=False,
            zone_high_nonnull=False,
            pin_score=1.0,
            net_gex_positive=True,
            regime="long_gamma",
            zone_failure_reason="pin_distance_too_wide",
            replay_quality=0.92,
        ),
    ]
    agg = aggregate_anchor_results(
        DateEntry(trade_date=date(2024, 1, 19), day_type="monthly_opex"),
        anchors,
        lake_status="raw_lake_complete",
        runtime_seconds=12.0,
    )
    assert agg.anchor_count == 2
    assert agg.valid_zone_count == 1
    assert agg.valid_zone_ratio == 0.5
    assert agg.included_count == 1
    assert agg.inside_count == 1
    assert agg.pin_distance_too_wide_ratio == 0.5


def test_valid_zone_ratio_and_class_aggregation() -> None:
    anchors = [
        AnchorScreenResult(
            has_valid_zone=True,
            included=True,
            close_location="above",
            primary_pin_nonnull=True,
            secondary_pin_nonnull=True,
            zone_low_nonnull=True,
            zone_high_nonnull=True,
            pin_score=2.0,
            net_gex_positive=True,
            regime="long_gamma",
            zone_failure_reason="valid_cluster",
            replay_quality=0.9,
        ),
        AnchorScreenResult(
            has_valid_zone=True,
            included=True,
            close_location="below",
            primary_pin_nonnull=True,
            secondary_pin_nonnull=True,
            zone_low_nonnull=True,
            zone_high_nonnull=True,
            pin_score=2.0,
            net_gex_positive=True,
            regime="long_gamma",
            zone_failure_reason="valid_cluster",
            replay_quality=0.9,
        ),
    ]
    agg = aggregate_anchor_results(
        DateEntry(trade_date=date(2024, 10, 4), day_type="monthly_opex"),
        anchors,
        lake_status="raw_lake_complete",
        runtime_seconds=1.0,
    )
    assert agg.valid_zone_ratio == 1.0
    assert agg.above_count == 1
    assert agg.below_count == 1
    assert agg.label_diversity_score == 2


def test_label_diversity_score() -> None:
    m = _metrics("2024-01-19", inside=10, above=5)
    assert label_diversity_score(m) == 2
    assert rare_label_bonus(m) == 2


def test_ranking_by_included_count() -> None:
    a = _metrics("2024-01-19", included=48, valid_zone_ratio=0.62)
    b = _metrics("2024-10-04", included=39, valid_zone_ratio=0.51)
    ranked = rank_screened_dates([b, a])
    assert ranked[0].trade_date.isoformat() == "2024-01-19"


def test_ranking_by_valid_zone_ratio() -> None:
    a = _metrics("2024-01-19", included=10, valid_zone_ratio=0.8)
    b = _metrics("2024-10-04", included=10, valid_zone_ratio=0.5)
    assert ranking_sort_key(a) > ranking_sort_key(b)


def test_ranking_with_rare_label_bonus() -> None:
    with_inside = _metrics("2024-10-04", included=20, valid_zone_ratio=0.4, inside=20)
    above_only = _metrics("2024-01-19", included=20, valid_zone_ratio=0.4, above=20)
    assert ranking_sort_key(with_inside) > ranking_sort_key(above_only)


def test_resume_skip_completed_date(tmp_path: Path) -> None:
    report_root = tmp_path / "screen_reports"
    m = _metrics("2024-01-19", included=48, valid_zone_ratio=0.62, above=48)
    write_per_date_screen_report(report_root, m)
    payload = json.loads((report_root / "per_date/2024-01-19.json").read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    restored = metrics_from_dict(payload)
    assert restored.included_count == 48


@patch("quant_lab.ml.features.builder.build_feature_dataset")
@patch("quant_lab.ml.datasets.valid_zone_screening.screen_anchor_at")
@patch("quant_lab.ml.datasets.valid_zone_screening.generate_anchors")
@patch("quant_lab.ml.datasets.valid_zone_screening.PilotIndexOutcomeProvider")
def test_no_feature_build_called(
    mock_provider: MagicMock,
    mock_generate: MagicMock,
    mock_screen: MagicMock,
    mock_feature_build: MagicMock,
    tmp_path: Path,
) -> None:
    from quant_lab.ml.datasets.valid_zone_screening import ScreeningOptions

    cfg = _minimal_config(tmp_path)
    with patch(
        "quant_lab.ml.datasets.valid_zone_screening.inventory_raw_lake",
        return_value=LakeDateInventory(
            complete_dates=("2024-01-19",),
            incomplete_dates=(),
            skipped_dates=(),
        ),
    ), patch(
        "quant_lab.ml.datasets.valid_zone_screening.load_completed_checkpoint_dates",
        return_value=set(),
    ):
        mock_generate.return_value = [(datetime(2024, 1, 19, 10, 0), "regular_5min")]
        mock_screen.return_value = AnchorScreenResult(
            has_valid_zone=True,
            included=True,
            close_location="inside",
            primary_pin_nonnull=True,
            secondary_pin_nonnull=True,
            zone_low_nonnull=True,
            zone_high_nonnull=True,
            pin_score=2.0,
            net_gex_positive=True,
            regime="long_gamma",
            zone_failure_reason="valid_cluster",
            replay_quality=0.9,
        )
        screen_valid_zone_candidates(
            cfg,
            {"2024-01-19": "monthly_opex"},
            options=ScreeningOptions(
                resume=False,
                progress_every=0,
                report_root=tmp_path / "reports",
                already_full_built=frozenset(),
            ),
        )
    mock_feature_build.assert_not_called()


def test_no_model_training_imports() -> None:
    import quant_lab.ml.datasets.valid_zone_screening as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("torch", "lightgbm", "xgboost", "sklearn"):
        assert forbidden not in src


def test_recommend_excludes_negative_controls() -> None:
    ranked = rank_screened_dates(
        [
            _metrics("2024-05-03", included=0),
            _metrics("2024-06-07", included=0),
            _metrics("2024-12-06", included=5, valid_zone_ratio=0.1, inside=5),
        ]
    )
    rec = recommend_full_build_dates(ranked, already_full_built=frozenset())
    assert "2024-05-03" not in rec
    assert "2024-06-07" not in rec
    assert "2024-12-06" in rec


def test_recommend_excludes_already_full_built() -> None:
    ranked = rank_screened_dates(
        [
            _metrics("2024-01-19", included=48, valid_zone_ratio=0.62, above=48),
            _metrics("2025-01-03", included=1, valid_zone_ratio=0.013, above=1),
        ]
    )
    rec = recommend_full_build_dates(
        ranked,
        already_full_built=frozenset({"2024-01-19"}),
    )
    assert "2024-01-19" not in rec
    assert "2025-01-03" in rec


def test_load_day_type_map(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "dates:\n  - date: '2024-07-03'\n    day_type: early_close\n",
        encoding="utf-8",
    )
    assert load_day_type_map(cfg) == {"2024-07-03": "early_close"}


@patch("quant_lab.ml.datasets.valid_zone_screening.replay_state")
def test_screen_anchor_at_uses_replay_not_features(mock_replay: MagicMock, tmp_path: Path) -> None:
    from quant_lab.data.base import MARKET_TZ

    mock_state = MagicMock()
    mock_state.index_state.price = 5000.0
    mock_state.option_chain.empty = True
    mock_state.quality.quality_score = 0.9
    mock_state.state_hash = "abc"
    mock_state.source_partitions = []
    mock_state.warnings = []
    mock_replay.return_value = mock_state
    provider = MagicMock()
    provider.get_outcome.return_value = MagicMock(
        official_close=5000.0,
        official_close_source="test",
        session_close_timestamp=datetime(2024, 1, 19, 16, 0, tzinfo=MARKET_TZ),
        future_index_path=__import__("pandas").DataFrame(),
    )
    with patch(
        "quant_lab.ml.datasets.valid_zone_screening.compute_deterministic_bundle"
    ) as mock_bundle_fn:
        mock_bundle = MagicMock()
        mock_bundle.net_gex = 1.0
        mock_bundle.pin_score = 2.0
        mock_bundle.king_node = 5000.0
        mock_bundle.max_pain = 5000.0
        mock_bundle.expected_move_1sd = 50.0
        mock_bundle.gamma_source = "test"
        mock_bundle.oi_semantics_status = "confirmed"
        mock_bundle_fn.return_value = mock_bundle
        with patch(
            "quant_lab.ml.datasets.valid_zone_screening.detect_pin_cluster"
        ) as mock_cluster:
            mock_cluster.return_value = MagicMock(
                is_cluster=False,
                merge_reason="strikes_too_far_apart",
                primary_strike=5000.0,
                secondary_strike=None,
                lower=0.0,
                upper=0.0,
                center=0.0,
                zone_break=None,
                spot_zone_state="outside",
            )
            as_of = datetime(2024, 1, 19, 10, 0, tzinfo=MARKET_TZ)
            result = screen_anchor_at(
                date(2024, 1, 19),
                as_of,
                data_root=tmp_path,
                outcome_provider=provider,
            )
    assert result.has_valid_zone is False
    assert result.zone_failure_reason == "pin_distance_too_wide"
