"""Background startup tasks for vendor Terminal (hist pre-warm, live cache poller)."""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from typing import Any

import requests

from quant_lab.config import env_var
from quant_lab.data.base import MARKET_TZ
from quant_lab.data.gexbot_client import GexbotClient, GexbotConfigError, get_gexbot_client
from quant_lab.data.gexbot_history_cache import gexbot_hist_cache_root, load_or_fetch_hist_day
from quant_lab.data.gexbot_stream import (
    gexbot_ws_enabled,
    start_gexbot_stream_service,
    stop_gexbot_stream_service,
    stream_status,
)
from quant_lab.terminal.chain_provider import resolve_terminal_chain_provider
from quant_lab.terminal.deploy import history_retention_days, recent_trading_dates
from quant_lab.terminal.live_chain import (
    LIVE_TIME_OF_DAY,
    fetch_intraday_chain_from_vendors,
    is_live_session,
    live_refresh_seconds,
    market_today,
)

log = logging.getLogger(__name__)

PREWARM_SYMBOLS = ("^SPX", "SPY", "QQQ")
_shutdown = threading.Event()
_threads: list[threading.Thread] = []


def _prewarm_symbols() -> tuple[str, ...]:
    """Symbols to hist-prewarm — default ^SPX only to reduce GEXBot rate limits."""
    raw = env_var("TERMINAL_PREWARM_SYMBOLS")
    if raw is not None and raw.strip():
        return tuple(s.strip() for s in raw.split(",") if s.strip())
    return ("^SPX",)


def _prewarm_delay_seconds() -> float:
    raw = env_var("TERMINAL_PREWARM_DELAY_SEC", default="2.5")
    try:
        return max(float(raw or "2.5"), 0.0)
    except ValueError:
        return 2.5


def _env_enabled(name: str, *, default: str = "1") -> bool:
    raw = env_var(name, default=default)
    return raw is not None and raw.strip().lower() not in ("0", "false", "no", "off")


def is_us_rth_now() -> bool:
    """True during regular US cash session (09:30–16:00 ET, Mon–Fri)."""
    now = datetime.now(MARKET_TZ)
    if now.weekday() >= 5:
        return False
    open_minutes = 9 * 60 + 30
    close_minutes = 16 * 60
    now_minutes = now.hour * 60 + now.minute
    return open_minutes <= now_minutes < close_minutes


def prewarm_gexbot_history(
    *,
    symbols: tuple[str, ...] | None = None,
    client: GexbotClient | None = None,
    days: int | None = None,
) -> dict[str, int]:
    """Download + cache GEXBot hist Parquet for recent session dates.

    Returns counts: ``{"ok": n, "skipped": n, "failed": n}``.
    """
    gex = client or get_gexbot_client()
    window = days if days is not None else history_retention_days()
    if window is None:
        window = 14
    dates = [date.fromisoformat(d) for d in recent_trading_dates(days=window)]
    dates.sort(reverse=True)
    stats = {"ok": 0, "skipped": 0, "failed": 0, "rate_limited": 0}
    delay = _prewarm_delay_seconds()
    sym_list = symbols if symbols is not None else _prewarm_symbols()
    for sym in sym_list:
        for session_date in dates:
            try:
                load_or_fetch_hist_day(gex, sym, session_date)
                stats["ok"] += 1
            except FileNotFoundError:
                stats["skipped"] += 1
                log.debug("gexbot hist unavailable %s %s", sym, session_date)
            except requests.HTTPError as exc:
                stats["failed"] += 1
                if exc.response is not None and exc.response.status_code == 429:
                    stats["rate_limited"] += 1
                log.warning("gexbot hist prewarm failed %s %s: %s", sym, session_date, exc)
            except OSError as exc:
                stats["failed"] += 1
                log.warning("gexbot hist prewarm failed %s %s: %s", sym, session_date, exc)
            if delay > 0:
                time.sleep(delay)
    return stats


def _run_prewarm() -> None:
    try:
        stats = prewarm_gexbot_history()
        log.info(
            "gexbot hist prewarm complete ok=%d skipped=%d failed=%d rate_limited=%d cache=%s",
            stats["ok"],
            stats["skipped"],
            stats["failed"],
            stats.get("rate_limited", 0),
            gexbot_hist_cache_root(),
        )
    except GexbotConfigError as exc:
        log.warning("gexbot hist prewarm skipped: %s", exc)
    except Exception as exc:
        log.exception("gexbot hist prewarm error: %s", exc)


def _run_vendor_live_poller() -> None:
    """Keep vendor live cache warm during RTH (REST; complements UI polling)."""
    log.info("vendor live poller started (interval=%ss)", live_refresh_seconds())
    while not _shutdown.is_set():
        if is_live_session(market_today()) and is_us_rth_now():
            for sym in PREWARM_SYMBOLS:
                if _shutdown.is_set():
                    break
                try:
                    fetch_intraday_chain_from_vendors(
                        market_today(),
                        LIVE_TIME_OF_DAY,
                        symbol=sym,
                        chain_mode="gex",
                    )
                except Exception as exc:
                    log.debug("vendor live poller %s: %s", sym, exc)
        _shutdown.wait(timeout=live_refresh_seconds())


def _live_poller_enabled() -> bool:
    """UW chain warm poller — off by default when GEXBot WS handles structure."""
    default = "0" if gexbot_ws_enabled() else "1"
    return _env_enabled("TERMINAL_VENDOR_LIVE_POLLER", default=default)


def start_background_tasks() -> None:
    """Start daemon threads when vendor provider is active."""
    global _threads
    if _threads:
        return
    try:
        provider = resolve_terminal_chain_provider()
    except Exception as exc:
        log.warning("background tasks skipped: %s", exc)
        return
    if provider != "vendor":
        log.info("background tasks skipped (provider=%s)", provider)
        return

    start_gexbot_stream_service()

    if _env_enabled("TERMINAL_PREWARM_HIST"):
        t = threading.Thread(target=_run_prewarm, name="gexbot-prewarm", daemon=True)
        t.start()
        _threads.append(t)

    if _live_poller_enabled():
        t = threading.Thread(target=_run_vendor_live_poller, name="vendor-live-poller", daemon=True)
        t.start()
        _threads.append(t)


def stop_background_tasks() -> None:
    """Signal background threads to stop (app shutdown)."""
    _shutdown.set()
    stop_gexbot_stream_service()
    for t in _threads:
        t.join(timeout=2.0)
    _threads.clear()


def cache_status() -> dict[str, Any]:
    """Lightweight status for ``/api/health``."""
    root = gexbot_hist_cache_root()
    try:
        provider = resolve_terminal_chain_provider()
    except Exception:
        provider = None
    parquet_files = list(root.glob("**/*.parquet")) if root.is_dir() else []
    ws = stream_status()
    return {
        "chain_provider": provider,
        "gexbot_hist_cache_dir": str(root),
        "gexbot_hist_parquet_files": len(parquet_files),
        "prewarm_enabled": _env_enabled("TERMINAL_PREWARM_HIST"),
        "live_poller_enabled": _live_poller_enabled(),
        "gexbot_ws_enabled": ws.get("ws_enabled"),
        "gexbot_ws_groups": ws.get("ws_groups"),
        "gexbot_ws_tickers": ws.get("tickers"),
    }
