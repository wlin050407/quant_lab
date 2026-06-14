"""Mock tests for ML-P2A ThetaData gap closure script."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from quant_lab.data.thetadata_chain import _oi_snapshot_at_time
from scripts.close_thetadata_capability_gaps import (
    GapClosureAuditor,
    build_conclusions,
    classify_quote_interval,
    discover_client_methods,
    estimate_closure_calls,
    gamma_decision,
    interpret_early_close,
    map_probe_to_classification,
)
from scripts.thetadata_p2_common import ProbeRecord, classify_probe_error, redact_manifest


def test_discover_client_methods_lists_quote_and_greek() -> None:
    disc = discover_client_methods()
    names = {m["name"] for m in disc["option_quote_methods"]}
    assert "option_history_quote" in names
    greek_names = {m["name"] for m in disc["greek_methods"]}
    assert "option_history_greeks_second_order" in greek_names


def test_classify_probe_error_entitlement() -> None:
    exc = RuntimeError("StatusCode.PERMISSION_DENIED professional subscription")
    out = classify_probe_error(exc)
    assert out["category"] == "entitlement_denied"


def test_interpret_early_close_am_only() -> None:
    payload = {
        "windows": {
            "10:00:00_10:05:00": {"trade": {"row_count": 10}},
            "13:00:00_13:05:00": {"trade": {"row_count": 0}},
        }
    }
    msg = interpret_early_close(payload)
    assert "不能视为数据缺失" in msg


def test_gamma_decision_standard_denied() -> None:
    payload = {
        "endpoints": {
            "option_history_greeks_second_order": {
                "probe_status": "denied",
                "detail": {"category": "entitlement_denied"},
            }
        }
    }
    assert gamma_decision(payload).startswith("B.")


def test_map_probe_invalid_interval() -> None:
    rec = ProbeRecord("x", "error", {"category": "invalid_parameter"})
    assert map_probe_to_classification(rec) == "invalid_interval_parameter"


def test_dry_run_no_network() -> None:
    auditor = GapClosureAuditor(max_requests=5, strike_range=2, dry_run=True)
    manifest = auditor.run()
    assert manifest["dry_run"] is True
    assert auditor.request_count == 0


def test_auditor_early_close_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()

    def _trade(**kwargs: object) -> pd.DataFrame:
        end = str(kwargs.get("end_time", ""))
        if end <= "13:00:00":
            return pd.DataFrame(
                {"timestamp": ["2025-07-03T10:01:00"], "price": [1.0], "strike": [6200.0]}
            )
        raise RuntimeError("No data found")

    client.option_history_trade.side_effect = lambda *a, **k: _trade(**k)
    client.option_history_quote.return_value = pd.DataFrame(
        {"timestamp": ["2025-07-03T10:01:00"], "bid": [1.0], "ask": [1.1], "strike": [6200.0]}
    )
    client.index_history_price.return_value = pd.DataFrame(
        {"timestamp": ["2025-07-03T10:01:00"], "price": [6200.0]}
    )
    client.option_history_greeks_second_order.side_effect = RuntimeError("PERMISSION_DENIED")
    client.option_history_greeks_all.side_effect = RuntimeError("PERMISSION_DENIED")
    client.option_history_greeks_first_order.return_value = pd.DataFrame(
        {
            "strike": [6200.0],
            "implied_vol": [0.2],
            "underlying_price": [6200.0],
            "right": ["PUT"],
        }
    )
    client.option_history_open_interest.return_value = pd.DataFrame(
        {
            "timestamp": ["2025-04-09T06:30:00"],
            "open_interest": [100],
            "strike": [6200.0],
            "right": ["CALL"],
        }
    )

    monkeypatch.setattr(
        "scripts.close_thetadata_capability_gaps.get_thetadata_client",
        lambda: client,
    )
    auditor = GapClosureAuditor(max_requests=50, strike_range=2, dry_run=False)
    manifest = auditor.run()
    assert "不能视为数据缺失" in manifest["early_close"]["interpretation"]
    text = json.dumps(manifest)
    assert "secret123" not in text


def test_quote_1s_classification() -> None:
    df = pd.DataFrame({"timestamp": ["2025-04-09T13:00:00"], "bid": [1.0]})
    assert classify_quote_interval("1s", df) == "1s_verified"


def test_oi_snapshot_at_time_no_forward_fill() -> None:
    hist = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2025-04-09 06:30:00", "2025-04-09 12:00:00"]
            ).tz_localize("America/New_York"),
            "strike": [5000.0, 5000.0],
            "right": ["C", "C"],
            "open_interest": [100, 999],
        }
    )
    snap = _oi_snapshot_at_time(hist, date(2025, 4, 9), "09:30:00")
    assert len(snap) == 1
    assert int(snap["open_interest"].iloc[0]) == 100


def test_build_conclusions_ml_p3_gate() -> None:
    manifest = {
        "early_close": {"interpretation": "ok"},
        "quote_resolution": {"intervals": {"1s": {"classification": "1s_verified"}}},
        "index_resolution": {"intervals": {"1s": {"classification": "account_verified"}}},
        "gamma": {"decision": "B. local"},
        "open_interest_semantics": {"official_status": "not confirmed"},
    }
    out = build_conclusions(manifest)
    assert out["ml_p3_allowed"] is True


def test_estimate_closure_calls_positive() -> None:
    assert estimate_closure_calls() > 0


def test_redact_manifest_password() -> None:
    out = redact_manifest({"password": "x", "rows": 1})
    assert out["password"] == "***"
