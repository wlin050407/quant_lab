"""Tests for macro event calendar gates."""

from __future__ import annotations

from datetime import date

import pytest

from quant_lab.data.macro_calendar import (
    clear_macro_calendar_cache,
    macro_events_on,
    macro_playbook_gate,
)


def test_fomc_day_blocks_playbook() -> None:
    clear_macro_calendar_cache()
    events = macro_events_on(date(2026, 5, 6))
    assert any(e.event_type == "fomc" for e in events)
    mult, detail = macro_playbook_gate(date(2026, 5, 6))
    assert mult == 0.0
    assert detail is not None
    assert "FOMC" in detail


def test_regular_day_passes() -> None:
    clear_macro_calendar_cache()
    assert macro_events_on(date(2026, 5, 24)) == []
    mult, detail = macro_playbook_gate(date(2026, 5, 24))
    assert mult == pytest.approx(1.0)
    assert detail is None
