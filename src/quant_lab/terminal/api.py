"""Local FastAPI server for Ultimate Terminal M4."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from quant_lab.terminal.auth import TerminalBasicAuthMiddleware
from quant_lab.terminal.equity_live import build_equity_analysis
from quant_lab.terminal.live_chain import market_today
from quant_lab.data.thetadata_chain import ChainMode
from quant_lab.terminal.snapshot import build_dashboard, list_terminal_dates, resolve_default_terminal_date

STATIC_DIR = Path(__file__).resolve().parent / "static"
DIST_DIR = STATIC_DIR / "dist"

app = FastAPI(title="quant_lab Terminal", version="0.2.0")
app.add_middleware(TerminalBasicAuthMiddleware)
log = logging.getLogger(__name__)


def _ui_index() -> Path:
    built = DIST_DIR / "index.html"
    if built.exists():
        return built
    legacy = STATIC_DIR / "index.html"
    if legacy.exists():
        return legacy
    return built


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "ui": "react" if (DIST_DIR / "index.html").exists() else "legacy",
        "equity_api": "v1",
    }


@app.get("/api/dates")
def api_dates(symbol: str = Query(default="^SPX")) -> dict:
    dates = list_terminal_dates(symbol)
    if not dates:
        raise HTTPException(status_code=404, detail=f"no dates for {symbol}")
    return {
        "symbol": symbol,
        "dates": dates,
        "latest": dates[-1],
        "today": market_today().isoformat(),
        "default_date": resolve_default_terminal_date(symbol, dates),
    }


@app.get("/api/snapshot")
def api_snapshot(
    symbol: str = Query(default="^SPX"),
    asof: str | None = Query(default=None, alias="date"),
    time: str = Query(
        default="13:00:00",
        description="intraday ET: 'live' (follow now) or HH:MM:SS pin-play slot",
    ),
    include_trinity: bool = Query(
        default=False,
        description="Load SPY/QQQ/SPX trinity panel chains (slower; default single-symbol fast path)",
    ),
    chain_mode: ChainMode = Query(
        default="pin",
        description="0DTE chain pull: pin (ΔOI vs 09:30), full (+ session trade flow), gex (GEX-only)",
    ),
) -> dict:
    dates = list_terminal_dates(symbol)
    if not dates:
        raise HTTPException(status_code=404, detail=f"no history for {symbol}")
    if asof is None:
        iso = resolve_default_terminal_date(symbol, dates)
    else:
        iso = asof
    try:
        d = date.fromisoformat(iso)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date") from exc
    try:
        return build_dashboard(
            symbol,
            d,
            time_of_day=time,
            include_trinity=include_trinity,
            chain_mode=chain_mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("snapshot build failed for %s on %s time=%s", symbol, iso, time)
        raise HTTPException(
            status_code=503,
            detail="Terminal snapshot failed — check server logs",
        ) from exc


@app.get("/api/equity/analyze")
def api_equity_analyze(
    ticker: str = Query(..., min_length=1, max_length=16),
    refresh: bool = Query(default=False),
) -> dict:
    try:
        return build_equity_analysis(ticker, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    path = _ui_index()
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="Terminal UI not built. Run: python scripts/build_terminal_ui.py --install",
        )
    return FileResponse(path)


def _dist_icon_path(name: str) -> Path | None:
    path = (DIST_DIR / name).resolve()
    try:
        path.relative_to(DIST_DIR.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _favicon_path() -> Path | None:
    return _dist_icon_path("favicon.ico") or _dist_icon_path("favicon.png")


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
@app.get("/apple-touch-icon.png", include_in_schema=False)
def favicon(request: Request) -> FileResponse:
    name = request.url.path.lstrip("/")
    path = _dist_icon_path(name)
    if path is None and name == "favicon.ico":
        path = _dist_icon_path("favicon.png")
    if path is None:
        raise HTTPException(status_code=404, detail="favicon not built — run npm run build in terminal/web")
    media = {
        ".ico": "image/x-icon",
        ".png": "image/png",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path,
        media_type=media,
        headers={"Cache-Control": "public, max-age=86400, must-revalidate"},
    )


_assets_dir = DIST_DIR / "assets" if (DIST_DIR / "assets").is_dir() else STATIC_DIR
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    """Serve React shell for direct URLs like ``/stock`` (hash routes use ``#/stock``)."""
    if full_path.startswith("api") or full_path.startswith("assets"):
        raise HTTPException(status_code=404, detail="Not Found")
    path = _ui_index()
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="Terminal UI not built. Run: python scripts/build_terminal_ui.py --install",
        )
    return FileResponse(path)
