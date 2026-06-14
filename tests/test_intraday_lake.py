"""Unit tests for immutable raw event lake ingest (ML-P3)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from quant_lab.data.intraday_lake import (
    IncompletePartitionError,
    build_derived_gamma_black76,
    detect_duplicates,
    detect_out_of_order,
    ingest_partition,
    normalize_index_price,
    normalize_option_greeks,
    normalize_option_open_interest,
    normalize_option_quote,
    normalize_option_trade,
    partition_dir,
)
from quant_lab.data.intraday_manifest import is_partition_complete, read_manifest, sha256_file
from quant_lab.data.intraday_schema import OI_SEMANTICS_DEFAULT, is_nbbo_quote_dataset

TRADE_DATE = date(2026, 6, 10)
ROOT = "SPXW"
REQ = "abc123"


def _option_raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": ["2026-06-10T13:00:01", "2026-06-10T13:00:02"],
            "expiration": [TRADE_DATE, TRADE_DATE],
            "strike": [6000.0, 6005.0],
            "right": ["CALL", "PUT"],
            "bid": [1.0, 2.0],
            "ask": [1.1, 2.1],
            "bid_size": [10, 20],
            "ask_size": [11, 21],
            "sequence": [1, 2],
        }
    )


def test_partition_path_option_with_expiration(tmp_path: Path) -> None:
    p = partition_dir(
        tmp_path,
        "option_quote_tick",
        TRADE_DATE,
        root=ROOT,
        expiration=TRADE_DATE,
    )
    assert "dataset=option_quote_tick" in str(p)
    assert "root=SPXW" in str(p)
    assert "trade_date=2026-06-10" in str(p)
    assert "expiration=2026-06-10" in str(p)


def test_partition_path_index_without_expiration(tmp_path: Path) -> None:
    p = partition_dir(tmp_path, "index_price_tick", TRADE_DATE, symbol="SPX")
    assert "symbol=SPX" in str(p)
    assert "expiration=" not in str(p)


def test_partition_path_session_metadata(tmp_path: Path) -> None:
    p = partition_dir(tmp_path, "session_metadata", TRADE_DATE, root=ROOT)
    assert "dataset=session_metadata" in str(p)
    assert "expiration=" not in str(p)


def test_normalize_option_quote_required_fields() -> None:
    df = normalize_option_quote(
        _option_raw(),
        dataset="option_quote_tick",
        root=ROOT,
        trade_date=TRADE_DATE,
        source_endpoint="option_history_quote",
        source_request_id=REQ,
    )
    assert is_nbbo_quote_dataset("option_quote_tick")
    assert "level2" not in df["dataset"].iloc[0]
    assert df["bid"].notna().all()
    assert df["contract_identifier"].str.contains("SPXW").all()


def test_normalize_option_trade_no_fake_bid_ask() -> None:
    raw = pd.DataFrame(
        {
            "timestamp": ["2026-06-10T13:00:01"],
            "expiration": [TRADE_DATE],
            "strike": [6000.0],
            "right": ["CALL"],
            "price": [1.05],
            "size": [5],
            "exchange": [1],
            "condition": [0],
            "sequence": [99],
        }
    )
    df = normalize_option_trade(
        raw,
        root=ROOT,
        trade_date=TRADE_DATE,
        source_endpoint="option_history_trade",
        source_request_id=REQ,
    )
    assert "bid" not in df.columns
    assert "ask" not in df.columns


def test_normalize_oi_defaults_unconfirmed() -> None:
    raw = pd.DataFrame(
        {
            "timestamp": ["2026-06-10T06:30:00"],
            "expiration": [TRADE_DATE],
            "strike": [6000.0],
            "right": ["CALL"],
            "open_interest": [500],
        }
    )
    df = normalize_option_open_interest(
        raw,
        root=ROOT,
        trade_date=TRADE_DATE,
        requested_date=TRADE_DATE,
        source_endpoint="option_history_open_interest",
        source_request_id=REQ,
    )
    assert (df["oi_semantics_status"] == OI_SEMANTICS_DEFAULT).all()
    assert (df["oi_publication_time_confirmed"] == False).all()  # noqa: E712


def test_derived_gamma_includes_parameters() -> None:
    greeks = normalize_option_greeks(
        pd.DataFrame(
            {
                "timestamp": ["2026-06-10T13:00:00"],
                "expiration": [TRADE_DATE],
                "strike": [6000.0],
                "right": ["CALL"],
                "implied_vol": [0.15],
                "underlying_price": [6000.0],
                "delta": [0.5],
                "theta": [-1.0],
                "vega": [0.2],
                "rho": [0.01],
            }
        ),
        root=ROOT,
        trade_date=TRADE_DATE,
        source_endpoint="option_history_greeks_first_order",
        source_request_id=REQ,
    )
    with patch("quant_lab.data.intraday_lake.resolve_gex_inputs") as mock_inputs:
        mock_inputs.return_value = type("R", (), {"r": 0.04, "q": 0.0})()
        gamma_df = build_derived_gamma_black76(greeks, trade_date=TRADE_DATE, root=ROOT)
    assert len(gamma_df) == 1
    row = gamma_df.iloc[0]
    assert row["gamma_method"] == "black76"
    assert row["input_source_hash"]
    assert row["time_to_expiry_years"] > 0


def test_detect_duplicates_and_out_of_order() -> None:
    df = pd.DataFrame(
        {
            "contract_identifier": ["a", "a", "b"],
            "event_timestamp": pd.to_datetime(
                [
                    "2026-06-10T13:00:02",
                    "2026-06-10T13:00:02",
                    "2026-06-10T13:00:01",
                ]
            ),
            "sequence": [1, 1, 2],
        }
    )
    dup = detect_duplicates(df, ("contract_identifier", "event_timestamp", "sequence"))
    assert dup.duplicate_row_count == 2
    ooo = detect_out_of_order(df)
    assert ooo.out_of_order_count >= 1


def test_ingest_atomic_write_and_manifest(tmp_path: Path) -> None:
    df = normalize_index_price(
        pd.DataFrame({"timestamp": ["2026-06-10T13:00:00"], "price": [6000.0]}),
        dataset="index_price_1s",
        symbol="SPX",
        trade_date=TRADE_DATE,
        source_endpoint="index_history_price",
        source_request_id=REQ,
    )
    result = ingest_partition(
        df,
        lake_root=tmp_path,
        dataset="index_price_1s",
        trade_date=TRADE_DATE,
        symbol="SPX",
        expiration=None,
    )
    assert result.skipped is False
    assert (result.partition_dir / "part-000.parquet").is_file()
    manifest = read_manifest(result.partition_dir)
    assert manifest is not None
    assert manifest["ingestion_status"] == "complete"
    assert manifest["files"][0]["sha256"] == sha256_file(result.partition_dir / "part-000.parquet")
    assert (result.partition_dir / ".staging").exists() is False


def test_idempotent_rerun_skips_complete_partition(tmp_path: Path) -> None:
    df = normalize_index_price(
        pd.DataFrame({"timestamp": ["2026-06-10T13:00:00"], "price": [6000.0]}),
        dataset="index_price_tick",
        symbol="SPX",
        trade_date=TRADE_DATE,
        source_endpoint="index_history_price",
        source_request_id=REQ,
    )
    first = ingest_partition(
        df,
        lake_root=tmp_path,
        dataset="index_price_tick",
        trade_date=TRADE_DATE,
        symbol="SPX",
    )
    second = ingest_partition(
        df,
        lake_root=tmp_path,
        dataset="index_price_tick",
        trade_date=TRADE_DATE,
        symbol="SPX",
    )
    assert first.skipped is False
    assert second.skipped is True


def test_incomplete_partition_blocks_without_overwrite(tmp_path: Path) -> None:
    part = partition_dir(tmp_path, "option_trade_tick", TRADE_DATE, root=ROOT, expiration=TRADE_DATE)
    part.mkdir(parents=True)
    (part / "_manifest.json").write_text(
        json.dumps({"ingestion_status": "incomplete", "files": []}),
        encoding="utf-8",
    )
    df = normalize_option_trade(
        pd.DataFrame(
            {
                "timestamp": ["2026-06-10T13:00:00"],
                "expiration": [TRADE_DATE],
                "strike": [6000.0],
                "right": ["CALL"],
                "price": [1.0],
                "size": [1],
                "exchange": [1],
                "condition": [0],
                "sequence": [1],
            }
        ),
        root=ROOT,
        trade_date=TRADE_DATE,
        source_endpoint="option_history_trade",
        source_request_id=REQ,
    )
    with pytest.raises(IncompletePartitionError):
        ingest_partition(
            df,
            lake_root=tmp_path,
            dataset="option_trade_tick",
            trade_date=TRADE_DATE,
            root=ROOT,
            expiration=TRADE_DATE,
        )


def test_overwrite_allows_replace(tmp_path: Path) -> None:
    df = normalize_index_price(
        pd.DataFrame({"timestamp": ["2026-06-10T13:00:00"], "price": [6000.0]}),
        dataset="index_price_1s",
        symbol="SPX",
        trade_date=TRADE_DATE,
        source_endpoint="index_history_price",
        source_request_id=REQ,
    )
    ingest_partition(
        df,
        lake_root=tmp_path,
        dataset="index_price_1s",
        trade_date=TRADE_DATE,
        symbol="SPX",
    )
    assert is_partition_complete(
        partition_dir(tmp_path, "index_price_1s", TRADE_DATE, symbol="SPX")
    )
    second = ingest_partition(
        df,
        lake_root=tmp_path,
        dataset="index_price_1s",
        trade_date=TRADE_DATE,
        symbol="SPX",
        overwrite=True,
    )
    assert second.skipped is False


def test_no_parquet_tracked_by_git() -> None:
    import subprocess

    out = subprocess.check_output(
        ["git", "ls-files", "*.parquet"],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
    assert out == "", "tracked parquet files must not be committed"
