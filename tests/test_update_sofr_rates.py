"""SOFR rate update script (mocked network)."""

from __future__ import annotations

import pytest

from scripts.update_sofr_rates import fetch_sofr_dataframe


def test_fetch_sofr_parses_fred_csv(monkeypatch) -> None:
    csv_body = "DATE,SOFR\n2026-05-01,4.5\n2026-05-02,4.55\n"

    class FakeResp:
        text = csv_body

        @staticmethod
        def raise_for_status() -> None:
            return None

    monkeypatch.setattr(
        "scripts.update_sofr_rates.requests.get",
        lambda *args, **kwargs: FakeResp(),
    )
    df = fetch_sofr_dataframe()
    assert len(df) == 2
    assert float(df.iloc[-1]["rate"]) == pytest.approx(0.0455, rel=1e-6)
