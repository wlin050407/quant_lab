"""Mock tests for ML-P2B intraday storage pilot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.estimate_intraday_storage import DayPilot, project_capacity


def _sample_frames() -> dict[str, pd.DataFrame]:
    ts = pd.date_range("2026-06-10 09:30", periods=5, freq="1min", tz="America/New_York")
    index = pd.DataFrame({"timestamp": ts, "price": [7300.0 + i for i in range(5)]})
    quotes = pd.DataFrame(
        {
            "timestamp": ts,
            "strike": [7290.0, 7300.0, 7310.0, 7320.0, 7330.0],
            "bid": [1.0] * 5,
            "ask": [1.1] * 5,
            "right": ["CALL"] * 5,
        }
    )
    trades = quotes.copy()
    trades["price"] = 1.05
    trades["size"] = 1
    greeks = pd.DataFrame(
        {
            "timestamp": ts,
            "strike": [7300.0] * 5,
            "implied_vol": [0.15] * 5,
            "delta": [0.5] * 5,
        }
    )
    oi = pd.DataFrame(
        {
            "timestamp": [ts[0]],
            "strike": [7300.0],
            "open_interest": [100],
            "right": ["CALL"],
        }
    )
    return {
        "index": index,
        "quotes": quotes,
        "trades": trades,
        "greeks": greeks,
        "open_interest": oi,
    }


def test_day_pilot_dry_run() -> None:
    pilot = DayPilot(
        session_date=date(2026, 6, 10),
        label="ordinary",
        strike_range=60,
        quote_interval="1s",
        greek_interval="1m",
        index_interval="1s",
        output_root=Path("artifacts/pilot_test"),
        dry_run=True,
    )
    manifest = pilot.run()
    assert manifest["dry_run"] is True
    assert "index_history_price" in str(manifest["dry_run_plan"])


def test_day_pilot_writes_parquet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    frames = _sample_frames()
    client.index_history_price.return_value = frames["index"]
    client.option_history_quote.return_value = frames["quotes"]
    client.option_history_trade.return_value = frames["trades"]
    client.option_history_greeks_first_order.return_value = frames["greeks"]
    client.option_history_open_interest.return_value = frames["open_interest"]

    monkeypatch.setattr(
        "scripts.estimate_intraday_storage.get_thetadata_client",
        lambda: client,
    )
    pilot = DayPilot(
        session_date=date(2026, 6, 10),
        label="ordinary",
        strike_range=60,
        quote_interval="1s",
        greek_interval="1m",
        index_interval="1s",
        output_root=tmp_path,
        dry_run=False,
    )
    manifest = pilot.run()
    assert manifest["datasets"]["quotes"]["rows"] == 5
    assert manifest["em_band_subsets"]["bands"]["pm_1p0_em"]["quote_rows"] >= 0
    assert manifest["compression"]["zstd_3"]["bytes"] > 0
    text = json.dumps(manifest)
    assert "password" not in text


def test_project_capacity_from_manifests() -> None:
    manifests = [
        {
            "datasets": {
                "quotes": {"parquet_bytes": 1000},
                "trades": {"parquet_bytes": 2000},
            }
        },
        {
            "datasets": {
                "quotes": {"parquet_bytes": 1500},
                "trades": {"parquet_bytes": 2500},
            }
        },
    ]
    proj = project_capacity(manifests)
    assert proj["status"] == "estimate"
    assert proj["per_day_bytes"]["base"] == 3500.0
