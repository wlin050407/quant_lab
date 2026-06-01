"""Panel-level data source metadata on dashboard snapshots."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from quant_lab.terminal.snapshot import TRINITY_SYMBOLS, build_dashboard


def test_dashboard_panels_include_data_source() -> None:
    chain = pd.DataFrame(
        {
            "symbol": ["^SPX"],
            "expiry": [date(2023, 7, 11)],
            "strike": [4500.0],
            "right": ["C"],
            "dte": [0],
            "bid": [1.0],
            "ask": [1.1],
            "last_price": [1.05],
            "implied_volatility": [0.2],
            "volume": [0],
            "open_interest": [100],
            "in_the_money": [True],
        }
    )
    row = {
        "spot": 4500.0,
        "regime": "long_gamma",
        "king_dte1": 4500.0,
        "flip_dte1": 4480.0,
        "call_wall_dte1": 4550.0,
        "put_wall_dte1": 4450.0,
        "pin_score": 75.0,
        "net_gex_dte1": 1e9,
        "pct_gex_dte1": 50.0,
        "net_vex_dte1": 0.0,
        "pct_vex_dte1": 0.0,
        "vanna_interp_dte1": "",
        "pcr_oi": 1.0,
        "oi_conc_dte1": 0.3,
        "expected_move_1sd": 40.0,
    }

    def _parallel_side_effect(requests):
        out = {}
        for req in requests:
            if req.symbol == "^SPX":
                out[("^SPX", "2023-07-11")] = (chain, 4500.0, "13:00:00", "thetadata")
            elif req.symbol == "SPY":
                out[("SPY", "2023-07-11")] = (chain, 450.0, "13:00:00", "thetadata")
        return out

    with patch("quant_lab.terminal.snapshot._load_terminal_row", return_value=row):
        with patch("quant_lab.terminal.snapshot._parallel_load_chains", side_effect=_parallel_side_effect):
            with patch("quant_lab.terminal.snapshot._prev_trading_date", return_value=None):
                with patch("quant_lab.terminal.snapshot.build_strike_heatmap", return_value=([{"strike": 4500.0}], False)):
                    dash = build_dashboard(
                        "^SPX",
                        date(2023, 7, 11),
                        time_of_day="13:00:00",
                        include_trinity=True,
                    )

    panels = {p["symbol"]: p for p in dash["panels"]}
    assert panels["^SPX"]["data_source"] == "thetadata"
    assert panels["SPY"]["data_source"] == "thetadata"
    assert panels["QQQ"]["data_source"] == "unavailable"
    assert len(dash["panels"]) == len(TRINITY_SYMBOLS)
