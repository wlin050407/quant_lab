"""Mock tests for ThetaData capability audit script (no network)."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.audit_thetadata_capabilities import (
    ThetaDataCapabilityAuditor,
    build_audit_plan,
    default_test_dates,
    redact_manifest,
    redact_string,
    reject_future_dates,
    summarize_dataframe,
)


def test_redact_string_masks_email() -> None:
    assert redact_string("user@example.com") == "u***@example.com"


def test_redact_manifest_strips_password_key() -> None:
    out = redact_manifest({"password": "secret123", "rows": 1})
    assert out["password"] == "***"
    assert out["rows"] == 1


def test_reject_future_dates() -> None:
    with pytest.raises(ValueError, match="future dates"):
        reject_future_dates([date(2099, 1, 1)], anchor=date(2026, 6, 10))


def test_summarize_dataframe_schema() -> None:
    df = pd.DataFrame(
        {
            "timestamp": ["2025-05-16T13:00:00"],
            "bid": [1.0],
            "ask": [1.1],
            "bid_size": [10],
            "ask_size": [12],
        }
    )
    summary = summarize_dataframe(df, max_rows=10)
    assert summary["row_count"] == 1
    assert {"bid", "ask", "timestamp"} <= {c["name"] for c in summary["columns"]}


def test_build_audit_plan_respects_max_requests() -> None:
    dates = list(default_test_dates(anchor=date(2026, 6, 10)).values())
    plan = build_audit_plan(dates, max_contracts=2, max_rows=50, max_requests=20)
    assert plan.total_calls <= 20
    assert len(plan.dates) == 5


def test_dry_run_no_network() -> None:
    auditor = ThetaDataCapabilityAuditor(
        dates=[date(2025, 5, 16)],
        max_contracts=2,
        max_rows=10,
        max_requests=10,
        dry_run=True,
    )
    manifest = auditor.run()
    assert manifest["dry_run"] is True
    assert manifest["conclusions"]["dry_run_only"] is True
    assert auditor.request_count == 0


def test_auditor_entitlement_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail() -> None:
        raise RuntimeError("AuthenticationError: invalid")

    monkeypatch.setattr(
        "scripts.audit_thetadata_capabilities.get_thetadata_client",
        _fail,
    )
    auditor = ThetaDataCapabilityAuditor(
        dates=[date(2025, 5, 16)],
        max_contracts=1,
        max_rows=5,
        max_requests=5,
        dry_run=False,
    )
    manifest = auditor.run()
    assert manifest["conclusions"]["blocked"] == "authentication"
    assert "auth_error" in manifest["client"]


def test_auditor_happy_path_mock_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.options_subscription = 1
    client.indices_subscription = 1
    client.stock_subscription = 0
    client.option_list_symbols.return_value = pd.DataFrame({"symbol": ["SPXW", "SPX"]})
    client.index_list_symbols.return_value = pd.DataFrame({"symbol": ["SPX"]})
    client.option_list_expirations.return_value = pd.DataFrame(
        {"expiration": ["2025-05-16"]}
    )
    client.option_list_contracts.return_value = pd.DataFrame(
        {"strike": [5900.0], "right": ["C"]}
    )
    client.option_history_quote.return_value = pd.DataFrame(
        {"timestamp": ["2025-05-16T13:00:00"], "bid": [1.0], "ask": [1.1]}
    )
    client.option_history_trade.return_value = pd.DataFrame()
    client.option_history_open_interest.return_value = pd.DataFrame(
        {"timestamp": ["2025-05-16T09:30:00"], "open_interest": [100]}
    )
    client.option_history_greeks_first_order.return_value = pd.DataFrame(
        {"timestamp": ["2025-05-16T13:00:00"], "delta": [0.5], "gamma": [0.01]}
    )
    client.index_at_time_price.return_value = pd.DataFrame({"price": [5900.0]})
    client.index_history_price.return_value = pd.DataFrame(
        {"timestamp": ["2025-05-16T13:00:00"], "price": [5900.0]}
    )

    monkeypatch.setattr(
        "scripts.audit_thetadata_capabilities.get_thetadata_client",
        lambda **_: client,
    )
    auditor = ThetaDataCapabilityAuditor(
        dates=[date(2025, 5, 16)],
        max_contracts=1,
        max_rows=5,
        max_requests=30,
        dry_run=False,
    )
    manifest = auditor.run()
    assert manifest["conclusions"]["dates_with_quote_rows"] >= 1
    text = json.dumps(manifest)
    assert "secret123" not in text


def test_malformed_schema_empty_dataframe() -> None:
    summary = summarize_dataframe(pd.DataFrame(), max_rows=5)
    assert summary["row_count"] == 0


def test_max_contracts_limits_pick() -> None:
    from scripts.audit_thetadata_capabilities import _pick_contracts

    df = pd.DataFrame({"strike": [5800.0, 5900.0, 6000.0], "right": ["C", "C", "C"]})
    picked = _pick_contracts(df, max_contracts=2)
    assert len(picked) == 2
