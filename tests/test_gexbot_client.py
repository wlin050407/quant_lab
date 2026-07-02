"""Tests for GEXBot client (no network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quant_lab.data.gexbot_client import GexbotClient, gexbot_ticker, resolve_gexbot_api_key


def test_gexbot_ticker_maps_spx() -> None:
    assert gexbot_ticker("^SPX") == "SPX"
    assert gexbot_ticker("SPY") == "SPY"


def test_resolve_gexbot_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEXBOT_API_KEY", "gexbot_custom_test")
    assert resolve_gexbot_api_key() == "gexbot_custom_test"


@patch("quant_lab.data.gexbot_client.requests.get")
def test_classic_parses_json(mock_get: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"spot": 5000.0, "zero_gamma": 4980.0}
    mock_get.return_value = mock_resp

    client = GexbotClient("gexbot_custom_test")
    payload = client.classic("SPX", "gex_zero")
    assert payload["spot"] == 5000.0
