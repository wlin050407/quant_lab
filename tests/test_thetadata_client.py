"""Unit tests for ThetaData client helpers (no network)."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quant_lab.data import thetadata_client as td_client_mod
from quant_lab.data.thetadata_client import (
    _redact_email,
    credential_source_label,
    resolve_credentials_file,
    resolve_email_password,
)
from quant_lab.data.thetadata_intraday import (
    _normalize_timestamps,
    fetch_spx_price_1m,
    resolve_option_root,
)
from quant_lab.data.thetadata_storage import spx_price_1m_path


def test_resolve_email_password_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THETADATA_EMAIL", "a@b.com")
    monkeypatch.setenv("THETADATA_PASSWORD", "secret")
    monkeypatch.delenv("THETADATA_CREDENTIALS_FILE", raising=False)
    td_client_mod.get_thetadata_client.cache_clear()
    assert resolve_email_password() == ("a@b.com", "secret")


def test_resolve_credentials_file_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    creds = tmp_path / "creds.txt"
    creds.write_text("user@test.com\npass123\n", encoding="utf-8")
    monkeypatch.setenv("THETADATA_CREDENTIALS_FILE", str(creds))
    monkeypatch.delenv("THETADATA_EMAIL", raising=False)
    assert resolve_credentials_file() == creds
    assert resolve_email_password() == ("user@test.com", "pass123")


def test_normalize_timestamps_et() -> None:
    df = pd.DataFrame({"timestamp": ["2025-05-20T13:00:00"], "price": [5900.0]})
    out = _normalize_timestamps(df)
    assert str(out["timestamp"].iloc[0].tzinfo) is not None


def test_fetch_spx_price_1m_mock() -> None:
    client = MagicMock()
    client.index_history_price.return_value = pd.DataFrame(
        {"timestamp": ["2025-05-20T13:00:00"], "price": [5900.0]}
    )
    df = fetch_spx_price_1m(client, session_date=date(2025, 5, 20))
    assert len(df) == 1
    client.index_history_price.assert_called_once()


def test_resolve_option_root_prefers_spxw() -> None:
    client = MagicMock()
    client.option_list_symbols.return_value = pd.DataFrame({"symbol": ["SPY", "SPXW", "SPX", "QQQ"]})
    assert resolve_option_root(client) == "SPXW"


def test_resolve_option_root_falls_back_to_spx() -> None:
    client = MagicMock()
    client.option_list_symbols.return_value = pd.DataFrame({"symbol": ["SPY", "SPX", "QQQ"]})
    assert resolve_option_root(client) == "SPX"


def test_spx_price_path_layout() -> None:
    p = spx_price_1m_path(date(2025, 5, 20))
    assert p.as_posix().endswith("intraday/SPX/price_1m/2025-05-20.parquet")


def test_redact_email_masks_local_part() -> None:
    assert _redact_email("user@example.com") == "u***@example.com"


def test_get_thetadata_client_log_does_not_emit_full_email(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("THETADATA_EMAIL", "secret.user@example.com")
    monkeypatch.setenv("THETADATA_PASSWORD", "not-the-real-password")
    monkeypatch.delenv("THETADATA_CREDENTIALS_FILE", raising=False)
    td_client_mod.get_thetadata_client.cache_clear()
    mock_client = MagicMock()
    with patch("thetadata.ThetaClient", return_value=mock_client), caplog.at_level(
        logging.INFO, logger="quant_lab.data.thetadata_client"
    ):
        td_client_mod.get_thetadata_client()
    combined = caplog.text
    assert "secret.user@example.com" not in combined
    assert "not-the-real-password" not in combined
    assert "THETADATA_EMAIL" in combined or "credential" in combined.lower()


def test_credential_source_label_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THETADATA_EMAIL", "a@b.com")
    monkeypatch.setenv("THETADATA_PASSWORD", "x")
    monkeypatch.delenv("THETADATA_CREDENTIALS_FILE", raising=False)
    td_client_mod.get_thetadata_client.cache_clear()
    assert credential_source_label() == "THETADATA_EMAIL+THETADATA_PASSWORD"
