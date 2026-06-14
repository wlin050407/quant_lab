"""ML-P5 live vs replay deterministic parity (no network)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from quant_lab.data.intraday_lake import PILOT_LAKE_ROOT
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.point_in_time_replay import (
    compute_deterministic_bundle,
    default_pilot_data_root,
    replay_state,
    to_deterministic_input_frame,
)
from quant_lab.terminal.snapshot import _row_from_chain

TRADE = date(2026, 6, 10)
AS_OF = session_datetime(TRADE, "13:01:00")


def _synthetic_input():
    from tests.test_deterministic_feature_contract import _synthetic_input as synth

    return synth()


def test_replay_adapter_to_bundle_deterministic() -> None:
    inp = _synthetic_input()
    a = compute_deterministic_bundle(inp, 6000.0, use_precomputed_gamma=True)
    b = compute_deterministic_bundle(inp, 6000.0, use_precomputed_gamma=True)
    assert a.net_gex == b.net_gex
    assert a.pin_score == b.pin_score


def test_recomputed_bundle_matches_terminal_on_same_chain() -> None:
    from quant_lab.data.point_in_time_replay import deterministic_input_to_factor_chain

    inp = _synthetic_input()
    chain = deterministic_input_to_factor_chain(inp, spot=6000.0, dte=0)
    chain["dte"] = 0
    row = _row_from_chain(chain, 6000.0, asof=TRADE, hours_to_close=3.0)
    bundle = compute_deterministic_bundle(
        inp, 6000.0, asof=TRADE, hours_to_close=3.0, use_precomputed_gamma=False
    )
    assert bundle.net_gex == pytest.approx(row["net_gex_dte1"], rel=1e-5)
    assert bundle.net_vex == pytest.approx(row["net_vex_dte1"], rel=1e-5)
    assert bundle.pin_score == pytest.approx(row["pin_score"], rel=1e-5)


def test_pilot_replay_parity_summary() -> None:
    if not PILOT_LAKE_ROOT.is_dir():
        pytest.skip("pilot lake absent")
    state = replay_state(TRADE, AS_OF, data_root=default_pilot_data_root(), strict_manifests=True)
    spot = float(state.index_state.price) if state.index_state and state.index_state.price else float("nan")
    assert np.isfinite(spot)
    inp = to_deterministic_input_frame(state.option_chain, spot=spot)
    bundle = compute_deterministic_bundle(
        inp,
        spot,
        asof=TRADE,
        hours_to_close=3.0,
        use_precomputed_gamma=True,
    )
    assert bundle.gamma_source == "derived_black76_precomputed"
    assert bundle.oi_semantics_status == "unconfirmed"
    assert len(inp) == len(state.option_chain)
    assert np.isfinite(bundle.net_gex)
    assert np.isfinite(bundle.king_node)
