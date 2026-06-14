"""Tests for ML-P6 point-in-time dataset builder."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.ml.datasets.point_in_time import (
    AnchorConfig,
    BuildConfig,
    SyntheticOutcomeProvider,
    build_dataset_manifest,
    build_dataset_rows,
    compute_session_sample_weights,
    generate_anchors,
)
from quant_lab.ml.schemas import DATASET_SCHEMA_VERSION, AsOfContext, DatasetRow, LabelRow
from quant_lab.ml.splits import session_grouped_split

TRADE = date(2026, 6, 10)
CLOSE = session_datetime(TRADE, SESSION_CLOSE)


def _synthetic_provider(close: float = 6001.0) -> SyntheticOutcomeProvider:
    path = pd.DataFrame(
        {
            "event_timestamp": [
                session_datetime(TRADE, "13:05:00"),
                session_datetime(TRADE, "15:00:00"),
                CLOSE,
            ],
            "price": [6000.5, close - 0.5, close],
        }
    )
    return SyntheticOutcomeProvider(
        official_close=close,
        official_close_timestamp=CLOSE,
        session_close_timestamp=CLOSE,
        future_index_path=path,
    )


def _ctx() -> AsOfContext:
    return AsOfContext(
        trade_date=TRADE,
        as_of_timestamp=session_datetime(TRADE, "13:00:00"),
        spot_t=6000.0,
        primary_pin_t=6000.0,
        secondary_pin_t=6002.0,
        zone_low_t=6000.0,
        zone_high_t=6002.0,
        zone_center_t=6001.0,
        zone_break_up=6005.0,
        zone_break_down=5997.0,
        pin_score_t=0.5,
        expected_move_t=40.0,
        gamma_source="derived_black76_precomputed",
        oi_semantics_status="unconfirmed",
        spot_zone_state_at_as_of="inside_zone",
        has_valid_zone=True,
        quality_score=0.9,
        replay_state_hash="replay123",
        deterministic_bundle_hash="bundle456",
        source_partition_hashes=("sha1",),
        warning_codes=("oi_semantics_unconfirmed",),
    )


def test_regular_5min_anchors() -> None:
    cfg = AnchorConfig(anchor_type="regular_5min", interval_minutes=5)
    anchors = generate_anchors(TRADE, cfg)
    assert len(anchors) > 10
    assert anchors[0][0] == session_datetime(TRADE, "09:35:00")
    assert all(a[1] == "regular_5min" for a in anchors)


def test_manual_anchors() -> None:
    ts = session_datetime(TRADE, "13:01:00")
    cfg = AnchorConfig(anchor_type="manual", manual_timestamps=(ts,))
    assert generate_anchors(TRADE, cfg) == [(ts, "manual")]


def test_event_driven_returns_empty_pending_implementation() -> None:
    cfg = AnchorConfig(anchor_type="event_driven")
    assert generate_anchors(TRADE, cfg) == []


def test_row_schema_fields() -> None:
    row = DatasetRow(context=_ctx(), labels=LabelRow(), anchor_type="manual")
    d = row.row_dict()
    assert d["dataset_schema_version"] == DATASET_SCHEMA_VERSION
    assert d["replay_state_hash"] == "replay123"
    assert d["deterministic_bundle_hash"] == "bundle456"
    assert "labels.close_location_vs_current_zone" in d
    assert "oi_semantics_unconfirmed" in d["warning_codes"]


def test_sample_weights_sum_to_one_per_session() -> None:
    ctx = _ctx()
    rows = [
        DatasetRow(context=ctx, labels=LabelRow(), anchor_type="manual", session_id=TRADE.isoformat()),
        DatasetRow(context=ctx, labels=LabelRow(), anchor_type="manual", session_id=TRADE.isoformat()),
        DatasetRow(
            context=ctx,
            labels=LabelRow(exclusion_reasons=["no_valid_zone_at_as_of"]),
            anchor_type="manual",
            session_id=TRADE.isoformat(),
        ),
    ]
    rows[2] = DatasetRow(
        context=replace(ctx, has_valid_zone=False, zone_low_t=None, zone_high_t=None),
        labels=LabelRow(exclusion_reasons=["no_valid_zone_at_as_of"]),
        anchor_type="manual",
        session_id=TRADE.isoformat(),
    )
    weighted = compute_session_sample_weights(rows)
    total = sum(r.sample_weight for r in weighted)
    assert total == pytest.approx(1.0)
    assert weighted[2].sample_weight == 0.0


def test_manifest_generation() -> None:
    row = DatasetRow(context=_ctx(), labels=LabelRow(), anchor_type="manual")
    provider = _synthetic_provider()
    manifest = build_dataset_manifest(
        [row],
        outcome_provider=provider,
        anchor_config={"anchor_type": "manual"},
        split_config=session_grouped_split([TRADE.isoformat()]).to_dict(),
    )
    assert manifest["dataset_manifest_version"] == "pit-dataset-v1"
    assert manifest["row_count"] == 1
    assert manifest["outcome_source_hash"]


def test_synthetic_build_from_fixture_lake(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path)
    provider = _synthetic_provider(close=6001.0)
    config = BuildConfig(
        trade_date=TRADE,
        data_root=lake,
        anchor=AnchorConfig(
            anchor_type="manual",
            manual_timestamps=(session_datetime(TRADE, "13:01:00"),),
        ),
    )
    rows = build_dataset_rows(config, provider)
    assert len(rows) == 1
    assert rows[0].context.replay_state_hash
    assert rows[0].context.deterministic_bundle_hash
    if rows[0].context.has_valid_zone:
        assert rows[0].sample_weight == pytest.approx(1.0)
    else:
        assert rows[0].sample_weight == 0.0


@pytest.mark.skipif(
    not Path("artifacts/raw_lake_pilot").is_dir(),
    reason="pilot raw lake not present",
)
def test_pilot_dataset_build_if_available() -> None:
    from quant_lab.ml.datasets.point_in_time import build_pilot_dataset_if_available

    result = build_pilot_dataset_if_available()
    assert result is not None
    assert result["row_count"] == 3
