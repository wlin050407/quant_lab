"""Tests for FlashAlpha GEX client and free calibration helpers."""

from __future__ import annotations

import math

from datetime import date

import pandas as pd
import pytest

from quant_lab.data.flashalpha_gex import (
    FlashAlphaError,
    expiration_from_chain,
    fetch_gex,
    net_gex_dollars_to_bn_per_1pct,
    next_spy_weekly_expiry,
    parse_gex_payload,
    resolve_nearest_expiration,
)
from quant_lab.factors.calibration import (
    GEXSnapshot,
    check_against_external_gex,
    load_all_references,
)


def test_net_gex_dollars_to_bn_per_1pct() -> None:
    assert net_gex_dollars_to_bn_per_1pct(2_850_000_000) == pytest.approx(2.85)


def test_parse_gex_payload_positive_regime() -> None:
    payload = {
        "symbol": "SPY",
        "underlying_price": 597.5,
        "as_of": "2026-02-28T16:30:45Z",
        "gamma_flip": 595.25,
        "net_gex": 2_850_000_000,
        "net_gex_label": "positive",
        "call_wall": {"strike": 600.0},
        "put_wall": {"strike": 590.0},
    }
    quote = parse_gex_payload(payload)
    assert quote.regime == "long_gamma"
    assert quote.net_gex_bn_per_1pct == pytest.approx(2.85)
    assert quote.gamma_flip == pytest.approx(595.25)
    assert quote.call_wall == pytest.approx(600.0)


def test_parse_gex_payload_negative_label() -> None:
    payload = {
        "symbol": "SPY",
        "underlying_price": 500.0,
        "gamma_flip": 510.0,
        "net_gex": -1_000_000_000,
        "net_gex_label": "negative",
    }
    quote = parse_gex_payload(payload)
    assert quote.regime == "short_gamma"


def test_next_spy_weekly_expiry_monday() -> None:
    # 2026-05-24 is Sunday → next is Monday 2026-05-25
    assert next_spy_weekly_expiry(date(2026, 5, 24)) == date(2026, 5, 25)


def test_expiration_from_chain_picks_nearest_future() -> None:
    chain = pd.DataFrame(
        {
            "expiry": [date(2026, 5, 23), date(2026, 5, 28), date(2026, 6, 4)],
        }
    )
    assert expiration_from_chain(chain, date(2026, 5, 24)) == "2026-05-28"


def test_resolve_nearest_expiration_uses_chain() -> None:
    chain = pd.DataFrame({"expiry": [date(2026, 5, 28), date(2026, 6, 4)]})
    assert (
        resolve_nearest_expiration("SPY", asof_date=date(2026, 5, 24), chain=chain)
        == "2026-05-28"
    )


def test_fetch_gex_passes_auto_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | None] = []

    class FakeResp:
        def __init__(self, payload: dict) -> None:
            self.status_code = 200
            self._payload = payload

        @property
        def ok(self) -> bool:
            return True

        def json(self) -> dict:
            return self._payload

        @property
        def text(self) -> str:
            return ""

    def fake_get(url: str, **kwargs: object) -> FakeResp:
        params = kwargs.get("params") or {}
        exp = params.get("expiration") if isinstance(params, dict) else None
        calls.append(exp)
        return FakeResp(
            {
                "symbol": "SPY",
                "underlying_price": 500.0,
                "as_of": "2026-05-24T20:00:00Z",
                "gamma_flip": 498.0,
                "net_gex": 1_000_000_000,
                "net_gex_label": "positive",
            }
        )

    session = pytest.importorskip("requests").Session()
    monkeypatch.setattr(session, "get", fake_get)
    monkeypatch.setattr(
        "quant_lab.data.flashalpha_gex.resolve_nearest_expiration",
        lambda *a, **k: "2026-05-28",
    )

    quote = fetch_gex(
        "SPY",
        api_key="test-key",
        auto_expiration=True,
        session=session,
    )
    assert calls == ["2026-05-28"]
    assert quote.expiration == "2026-05-28"
    assert quote.regime == "long_gamma"


def test_fetch_gex_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLASHALPHA_API_KEY", raising=False)
    with pytest.raises(FlashAlphaError, match="FLASHALPHA_API_KEY"):
        fetch_gex("SPY")


def test_check_against_external_gex_passes_within_tolerance() -> None:
    snap = GEXSnapshot(
        date="2026-01-01",
        spot=597.0,
        net_gex_dollars_per_dollar=0.0,
        net_gex_bn_per_1pct=2.7,
        flip_level=594.0,
        spot_above_flip=True,
        call_wall_strike=600.0,
        put_wall_strike=590.0,
        regime="long_gamma",
    )
    result = check_against_external_gex(
        snap,
        external_regime="long_gamma",
        external_net_gex_bn_per_1pct=3.0,
        external_flip=595.0,
        external_spot=597.5,
        provider="flashalpha",
        tolerance_pct=0.30,
    )
    assert result.passed


def test_load_all_references_includes_free_yaml() -> None:
    refs = load_all_references()
    providers = {str(r.get("provider", "default")) for r in refs}
    assert "spotgamma_blog" in providers or len(refs) >= 3
