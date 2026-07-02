"""Tests for Terminal chain provider resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from quant_lab.terminal.chain_provider import (
    TerminalDataConfigError,
    any_terminal_data_credentials_configured,
    resolve_terminal_chain_provider,
)


def test_auto_prefers_gexbot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERMINAL_CHAIN_PROVIDER", "auto")
    monkeypatch.setenv("GEXBOT_API_KEY", "gexbot_custom_x")
    monkeypatch.delenv("THETADATA_EMAIL", raising=False)
    monkeypatch.delenv("THETADATA_PASSWORD", raising=False)
    assert resolve_terminal_chain_provider() == "vendor"


def test_explicit_thetadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERMINAL_CHAIN_PROVIDER", "thetadata")
    monkeypatch.setenv("THETADATA_EMAIL", "a@b.com")
    monkeypatch.setenv("THETADATA_PASSWORD", "secret")
    assert resolve_terminal_chain_provider() == "thetadata"


def test_no_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERMINAL_CHAIN_PROVIDER", "auto")
    monkeypatch.delenv("GEXBOT_API_KEY", raising=False)
    monkeypatch.delenv("GEXBOT_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("THETADATA_EMAIL", raising=False)
    monkeypatch.delenv("THETADATA_PASSWORD", raising=False)
    monkeypatch.delenv("THETADATA_CREDENTIALS_FILE", raising=False)
    with patch("quant_lab.terminal.chain_provider.resolve_email_password", return_value=None):
        with pytest.raises(TerminalDataConfigError):
            resolve_terminal_chain_provider()


def test_any_credentials_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEXBOT_API_KEY", "k")
    assert any_terminal_data_credentials_configured() is True
