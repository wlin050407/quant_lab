"""Tests for replay quality heuristics (ML-P4)."""

from __future__ import annotations

import pandas as pd

from quant_lab.data.point_in_time_replay import OPTION_CHAIN_COLUMNS
from quant_lab.data.replay_quality import compute_replay_quality


def _chain(**overrides: object) -> pd.DataFrame:
    base = {c: None for c in OPTION_CHAIN_COLUMNS}
    base["data_quality_flags"] = ""
    base.update(overrides)
    return pd.DataFrame([base])


def test_quality_score_full_coverage() -> None:
    chain = _chain(
        latest_bid=1.0,
        delta=0.5,
        gamma=0.01,
        open_interest=100.0,
    )
    q = compute_replay_quality(
        chain,
        index_available=True,
        stale_index=False,
        duplicate_ratio=0.0,
        out_of_order_ratio=0.0,
        warnings=[],
    )
    assert q.quality_score > 0.9
    assert q.quote_coverage_ratio == 1.0


def test_quality_penalizes_missing_greeks_and_stale_quote() -> None:
    chain = _chain(
        latest_bid=1.0,
        data_quality_flags="stale_quote|missing_greeks",
    )
    q = compute_replay_quality(
        chain,
        index_available=False,
        stale_index=True,
        duplicate_ratio=0.1,
        out_of_order_ratio=0.05,
        warnings=["oi_semantics_unconfirmed"],
    )
    assert q.greeks_coverage_ratio == 0.0
    assert q.stale_quote_ratio == 1.0
    assert q.quality_score < 0.6
    assert "oi_semantics_unconfirmed" in q.warnings


def test_empty_chain_quality_zero() -> None:
    q = compute_replay_quality(
        pd.DataFrame(columns=list(OPTION_CHAIN_COLUMNS)),
        index_available=False,
        stale_index=False,
        duplicate_ratio=0.0,
        out_of_order_ratio=0.0,
        warnings=["missing_index"],
    )
    assert q.quality_score == 0.0
    assert q.active_contract_count == 0
