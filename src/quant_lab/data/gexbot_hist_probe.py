"""Probe and prefetch GEXBot Quant hist availability (metadata-only probe)."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from quant_lab.config import settings
from quant_lab.data.gexbot_client import (
    GexbotClient,
    GexbotConfigError,
    get_gexbot_client,
    gexbot_ticker,
)
from quant_lab.data.gexbot_history_cache import (
    DEFAULT_CATEGORY,
    DEFAULT_PACKAGE,
    hist_cache_path,
    load_or_fetch_hist_day,
)

log = logging.getLogger(__name__)

MANIFEST_PATH = settings.paths.project_root / "artifacts" / "manifests" / "gexbot_hist_coverage.json"


def _iter_weekdays(start: date, end: date) -> list[date]:
    out: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def probe_hist_coverage(
    terminal_symbol: str,
    *,
    start: date,
    end: date,
    client: GexbotClient | None = None,
    package: str = DEFAULT_PACKAGE,
    category: str = DEFAULT_CATEGORY,
) -> dict[str, Any]:
    """List session dates with GEXBot hist metadata (no full JSON download)."""
    if client is None:
        client = get_gexbot_client()
    ticker = gexbot_ticker(terminal_symbol)
    available: list[str] = []
    probed = 0
    for session in _iter_weekdays(start, end):
        probed += 1
        try:
            client.hist_download_url(ticker, package, category, session)
        except (FileNotFoundError, requests.HTTPError, requests.RequestException, ValueError):
            continue
        available.append(session.isoformat())
    cached = [
        d
        for d in available
        if hist_cache_path(terminal_symbol, date.fromisoformat(d), package=package, category=category).is_file()
    ]
    return {
        "terminal_symbol": terminal_symbol,
        "ticker": ticker,
        "package": package,
        "category": category,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "probed_weekdays": probed,
        "available_dates": available,
        "n_available": len(available),
        "n_cached": len(cached),
        "cached_dates": cached,
    }


def write_coverage_manifest(payload: dict[str, Any], *, path: Path | None = None) -> Path:
    out = path or MANIFEST_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def load_coverage_manifest(path: Path | None = None) -> dict[str, Any] | None:
    manifest = path or MANIFEST_PATH
    if not manifest.is_file():
        return None
    return json.loads(manifest.read_text(encoding="utf-8"))


def prefetch_hist_days(
    terminal_symbol: str,
    session_dates: list[date],
    *,
    client: GexbotClient | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Download and cache GEXBot hist for the given session dates."""
    if client is None:
        client = get_gexbot_client()
    ok: list[str] = []
    skipped_cached: list[str] = []
    failed: list[dict[str, str]] = []
    for session in session_dates:
        path = hist_cache_path(terminal_symbol, session)
        if path.is_file() and not force_refresh:
            skipped_cached.append(session.isoformat())
            continue
        try:
            frame = load_or_fetch_hist_day(
                client,
                terminal_symbol,
                session,
                force_refresh=force_refresh,
            )
            if frame.empty:
                failed.append({"date": session.isoformat(), "reason": "empty_frame"})
            else:
                ok.append(session.isoformat())
        except (FileNotFoundError, OSError, ValueError, requests.RequestException) as exc:
            failed.append({"date": session.isoformat(), "reason": type(exc).__name__})
    return {
        "terminal_symbol": terminal_symbol,
        "downloaded": ok,
        "skipped_cached": skipped_cached,
        "failed": failed,
        "n_downloaded": len(ok),
        "n_cached_skipped": len(skipped_cached),
        "n_failed": len(failed),
    }


def probe_and_prefetch(
    terminal_symbol: str,
    *,
    start: date,
    end: date,
    prefetch: bool = True,
) -> dict[str, Any]:
    """Probe coverage, optionally prefetch all available days."""
    try:
        client = get_gexbot_client()
    except GexbotConfigError as exc:
        return {"status": "skipped", "reason": str(exc)}

    coverage = probe_hist_coverage(terminal_symbol, start=start, end=end, client=client)
    manifest_path = write_coverage_manifest(coverage)
    out: dict[str, Any] = {"status": "ok", "manifest": str(manifest_path), "coverage": coverage}
    if prefetch and coverage["available_dates"]:
        dates = [date.fromisoformat(d) for d in coverage["available_dates"]]
        out["prefetch"] = prefetch_hist_days(terminal_symbol, dates, client=client)
    return out
