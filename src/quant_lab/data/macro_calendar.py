"""US macro event calendar for Pin Play hard gates (FOMC / CPI).

Embedded high-impact dates cover recent sessions for Live Terminal. Optional
``data/raw/calendar/macro_events.parquet`` extends the set without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from quant_lab.config import settings
from quant_lab.data.thetadata_storage import load_parquet

MacroEventType = Literal["fomc", "cpi", "ppi", "nfp"]

# (ISO date, type, label) — FOMC decision days + CPI release days (08:30 ET).
_EMBEDDED: tuple[tuple[str, MacroEventType, str], ...] = (
    # 2024 FOMC
    ("2024-01-31", "fomc", "FOMC decision"),
    ("2024-03-20", "fomc", "FOMC decision"),
    ("2024-05-01", "fomc", "FOMC decision"),
    ("2024-06-12", "fomc", "FOMC decision"),
    ("2024-07-31", "fomc", "FOMC decision"),
    ("2024-09-18", "fomc", "FOMC decision"),
    ("2024-11-07", "fomc", "FOMC decision"),
    ("2024-12-18", "fomc", "FOMC decision"),
    # 2024 CPI
    ("2024-01-11", "cpi", "CPI release"),
    ("2024-02-13", "cpi", "CPI release"),
    ("2024-03-12", "cpi", "CPI release"),
    ("2024-04-10", "cpi", "CPI release"),
    ("2024-05-15", "cpi", "CPI release"),
    ("2024-06-12", "cpi", "CPI release"),
    ("2024-07-11", "cpi", "CPI release"),
    ("2024-08-14", "cpi", "CPI release"),
    ("2024-09-11", "cpi", "CPI release"),
    ("2024-10-10", "cpi", "CPI release"),
    ("2024-11-13", "cpi", "CPI release"),
    ("2024-12-11", "cpi", "CPI release"),
    # 2025 FOMC
    ("2025-01-29", "fomc", "FOMC decision"),
    ("2025-03-19", "fomc", "FOMC decision"),
    ("2025-05-07", "fomc", "FOMC decision"),
    ("2025-06-18", "fomc", "FOMC decision"),
    ("2025-07-30", "fomc", "FOMC decision"),
    ("2025-09-17", "fomc", "FOMC decision"),
    ("2025-11-06", "fomc", "FOMC decision"),
    ("2025-12-17", "fomc", "FOMC decision"),
    # 2025 CPI
    ("2025-01-15", "cpi", "CPI release"),
    ("2025-02-12", "cpi", "CPI release"),
    ("2025-03-12", "cpi", "CPI release"),
    ("2025-04-10", "cpi", "CPI release"),
    ("2025-05-13", "cpi", "CPI release"),
    ("2025-06-11", "cpi", "CPI release"),
    ("2025-07-11", "cpi", "CPI release"),
    ("2025-08-13", "cpi", "CPI release"),
    ("2025-09-10", "cpi", "CPI release"),
    ("2025-10-15", "cpi", "CPI release"),
    ("2025-11-13", "cpi", "CPI release"),
    ("2025-12-10", "cpi", "CPI release"),
    # 2026 FOMC
    ("2026-01-28", "fomc", "FOMC decision"),
    ("2026-03-18", "fomc", "FOMC decision"),
    ("2026-05-06", "fomc", "FOMC decision"),
    ("2026-06-17", "fomc", "FOMC decision"),
    ("2026-07-29", "fomc", "FOMC decision"),
    ("2026-09-16", "fomc", "FOMC decision"),
    ("2026-11-04", "fomc", "FOMC decision"),
    ("2026-12-16", "fomc", "FOMC decision"),
    # 2026 CPI
    ("2026-01-14", "cpi", "CPI release"),
    ("2026-02-12", "cpi", "CPI release"),
    ("2026-03-11", "cpi", "CPI release"),
    ("2026-04-10", "cpi", "CPI release"),
    ("2026-05-13", "cpi", "CPI release"),
    ("2026-06-11", "cpi", "CPI release"),
    ("2026-07-10", "cpi", "CPI release"),
    ("2026-08-12", "cpi", "CPI release"),
    ("2026-09-10", "cpi", "CPI release"),
    ("2026-10-14", "cpi", "CPI release"),
    ("2026-11-12", "cpi", "CPI release"),
    ("2026-12-10", "cpi", "CPI release"),
    # 2027 FOMC (scheduled placeholders — update when Fed publishes)
    ("2027-01-27", "fomc", "FOMC decision"),
    ("2027-03-17", "fomc", "FOMC decision"),
    ("2027-05-05", "fomc", "FOMC decision"),
    ("2027-06-16", "fomc", "FOMC decision"),
)


@dataclass(frozen=True)
class MacroEvent:
    session_date: date
    event_type: str
    label: str


def _macro_events_path() -> Path:
    return Path(settings.paths.raw) / "calendar" / "macro_events.parquet"


@lru_cache(maxsize=1)
def _load_events_index() -> dict[date, list[MacroEvent]]:
    index: dict[date, list[MacroEvent]] = {}
    for iso, etype, label in _EMBEDDED:
        d = date.fromisoformat(iso)
        index.setdefault(d, []).append(MacroEvent(d, etype, label))

    path = _macro_events_path()
    if path.is_file():
        df = load_parquet(path)
        if not df.empty and "session_date" in df.columns:
            for row in df.itertuples(index=False):
                d = date.fromisoformat(str(row.session_date)[:10])
                etype = str(getattr(row, "event_type", "macro"))
                label = str(getattr(row, "label", etype))
                index.setdefault(d, []).append(MacroEvent(d, etype, label))
    return index


def macro_events_on(session_date: date) -> list[MacroEvent]:
    """High-impact macro events on ``session_date`` (empty if none)."""
    return list(_load_events_index().get(session_date, []))


def macro_playbook_gate(session_date: date) -> tuple[float, str | None]:
    """Pin Play §3.1 gate #5: block premium selling on FOMC / CPI days (0×).

    Returns ``(multiplier, detail)`` where multiplier is ``0.0`` or ``1.0``.
    """
    events = macro_events_on(session_date)
    if not events:
        return 1.0, None
    labels = ", ".join(dict.fromkeys(e.label for e in events))
    return 0.0, f"Macro event day — {labels} (Pin Play 0×)"


def macro_calendar_meta() -> dict[str, str]:
    """Provenance for equity L1 / terminal disclosure."""
    last_embedded = max(date.fromisoformat(iso) for iso, _, _ in _EMBEDDED)
    path = _macro_events_path()
    source = "embedded"
    if path.is_file():
        source = "embedded+parquet"
    return {
        "source": source,
        "last_embedded_date": last_embedded.isoformat(),
        "confidence": "medium",
    }


def clear_macro_calendar_cache() -> None:
    """Reset cached calendar (tests)."""
    _load_events_index.cache_clear()
