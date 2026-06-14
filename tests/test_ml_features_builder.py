"""Tests for ML-P7 feature builder."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from quant_lab.data.intraday_time import session_datetime
from quant_lab.ml.features.builder import (
    build_feature_row_from_replay,
    build_pilot_feature_dataset_if_available,
)
from quant_lab.ml.features.manifest import build_feature_manifest

TRADE = date(2026, 6, 10)
AS_OF = session_datetime(TRADE, "13:01:00")


def test_context_and_deterministic_from_fixture(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path)
    row = build_feature_row_from_replay(TRADE, AS_OF, lake)
    assert row.replay_state_hash
    assert row.deterministic_bundle_hash
    assert row.features["minutes_since_open"] is not None
    assert row.features["spot_t"] == pytest.approx(6001.0)
    assert row.features["gamma_is_derived_black76"] is True
    assert "oi_semantics_unconfirmed" in row.feature_warnings or row.features["oi_semantics_unconfirmed"]


def test_missing_zone_nullable_not_zero(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path)
    row = build_feature_row_from_replay(TRADE, AS_OF, lake)
    assert row.features["spot_position_in_zone"] is None or isinstance(
        row.features["spot_position_in_zone"], float
    )


def test_manifest_generated(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path)
    row = build_feature_row_from_replay(TRADE, AS_OF, lake)
    manifest = build_feature_manifest([row], feature_config={"test": True})
    assert manifest["feature_manifest_version"] == "pit-features-v1"
    assert manifest["row_count"] == 1
    assert manifest["feature_count"] > 0
    assert "feature_groups" in manifest
    assert "code_commit" in manifest


def test_source_timestamp_max_leq_as_of(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path)
    row = build_feature_row_from_replay(TRADE, AS_OF, lake)
    if row.source_timestamp_max is not None:
        assert row.source_timestamp_max <= row.as_of_timestamp


def test_join_keys_preserved(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_point_in_time_replay import _build_fixture_lake

    lake = _build_fixture_lake(tmp_path)
    row = build_feature_row_from_replay(TRADE, AS_OF, lake)
    d = row.row_dict()
    assert d["replay_state_hash"] == row.replay_state_hash
    assert d["deterministic_bundle_hash"] == row.deterministic_bundle_hash


@pytest.mark.skipif(
    not Path("artifacts/datasets/pit_pilot/dataset.parquet").is_file(),
    reason="pilot dataset not present",
)
def test_pilot_feature_build() -> None:
    result = build_pilot_feature_dataset_if_available()
    assert result is not None
    assert result["row_count"] >= 1
    assert result["source_max_leq_as_of"] is True
