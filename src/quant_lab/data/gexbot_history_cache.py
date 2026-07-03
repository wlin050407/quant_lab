"""Download and cache GEXBot Quant historical JSON as Parquet for fast PIT replay."""

from __future__ import annotations

import logging
import tempfile
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import ijson
import numpy as np
import pandas as pd
import requests

from quant_lab.config import settings
from quant_lab.data.gexbot_client import (
    DEFAULT_TIMEOUT_SECONDS,
    GexbotClient,
    gexbot_ticker,
)
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.thetadata_storage import load_parquet, save_parquet

log = logging.getLogger(__name__)

DEFAULT_PACKAGE = "classic"
DEFAULT_CATEGORY = "gex_zero"

# One hist download at a time — avoids Railway OOM from parallel full-day JSON pulls.
_download_lock = threading.Lock()
_HIST_DOWNLOAD_RETRIES = 5
_HIST_RETRY_BASE_SEC = 2.0


def gexbot_hist_cache_root() -> Path:
    from quant_lab.config import env_var

    override = env_var("GEXBOT_HIST_CACHE_DIR")
    if override:
        return Path(override).resolve()
    return settings.paths.processed / "gexbot_hist"


def _cache_path(ticker: str, package: str, category: str, session_date: date) -> Path:
    return (
        gexbot_hist_cache_root()
        / ticker
        / f"{package}_{category}"
        / f"{session_date.isoformat()}.parquet"
    )


def _normalize_hist_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Keep only replay fields — full strike payloads are not stored (memory)."""
    if not rows:
        return pd.DataFrame(columns=["timestamp_unix", "spot", "zero_gamma"])
    records: list[dict[str, Any]] = []
    for row in rows:
        ts = int(row.get("timestamp", 0))
        records.append(
            {
                "timestamp_unix": ts,
                "spot": float(row.get("spot", np.nan)),
                "zero_gamma": float(row.get("zero_gamma", np.nan)),
                "major_pos_vol": float(row.get("major_pos_vol", np.nan)),
                "major_neg_vol": float(row.get("major_neg_vol", np.nan)),
                "sum_gex_vol": float(row.get("sum_gex_vol", np.nan)),
            }
        )
    df = pd.DataFrame.from_records(records)
    return df.sort_values("timestamp_unix").reset_index(drop=True)


_HIST_BATCH_ROWS = 4096


def _download_hist_to_parquet(
    client: GexbotClient,
    ticker: str,
    package: str,
    category: str,
    session_date: date,
    path: Path,
) -> pd.DataFrame:
    """Stream hist JSON to disk, parse with ijson, save slim Parquet (Railway-safe)."""
    url = client.hist_download_url(ticker, package, category, session_date)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        last_resp: requests.Response | None = None
        for attempt in range(_HIST_DOWNLOAD_RETRIES):
            with requests.get(url, stream=True, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
                last_resp = resp
                if resp.status_code in (429, 503) and attempt < _HIST_DOWNLOAD_RETRIES - 1:
                    delay = min(_HIST_RETRY_BASE_SEC * (2**attempt), 60.0)
                    log.warning(
                        "GEXBot hist blob %s returned %s — retry in %.1fs",
                        session_date,
                        resp.status_code,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                with tmp_path.open("wb") as out:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            out.write(chunk)
                break
        else:
            status = last_resp.status_code if last_resp is not None else "unknown"
            raise requests.HTTPError(
                f"GEXBot hist download failed after retries (status={status})",
                response=last_resp,
            )

        batches: list[pd.DataFrame] = []
        batch: list[dict[str, Any]] = []
        with tmp_path.open("rb") as handle:
            for row in ijson.items(handle, "item"):
                if not isinstance(row, dict):
                    continue
                batch.append(
                    {
                        "timestamp_unix": int(row.get("timestamp", 0)),
                        "spot": float(row.get("spot", np.nan)),
                        "zero_gamma": float(row.get("zero_gamma", np.nan)),
                        "major_pos_vol": float(row.get("major_pos_vol", np.nan)),
                        "major_neg_vol": float(row.get("major_neg_vol", np.nan)),
                        "sum_gex_vol": float(row.get("sum_gex_vol", np.nan)),
                    }
                )
                if len(batch) >= _HIST_BATCH_ROWS:
                    batches.append(pd.DataFrame.from_records(batch))
                    batch = []
        if batch:
            batches.append(pd.DataFrame.from_records(batch))
        if not batches:
            raise FileNotFoundError(f"empty GEXBot hist for {ticker} on {session_date}")
        df = pd.concat(batches, ignore_index=True)
        df = df.sort_values("timestamp_unix").reset_index(drop=True)
        save_parquet(df, path)
        return df
    finally:
        tmp_path.unlink(missing_ok=True)


def hist_cache_path(
    terminal_symbol: str,
    session_date: date,
    *,
    package: str = DEFAULT_PACKAGE,
    category: str = DEFAULT_CATEGORY,
) -> Path:
    """Parquet path for a cached GEXBot hist session (may not exist)."""
    ticker = gexbot_ticker(terminal_symbol)
    return _cache_path(ticker, package, category, session_date)


def load_cached_hist_day(
    terminal_symbol: str,
    session_date: date,
    *,
    package: str = DEFAULT_PACKAGE,
    category: str = DEFAULT_CATEGORY,
) -> pd.DataFrame | None:
    """Load hist from local cache only; return None when not cached."""
    path = hist_cache_path(terminal_symbol, session_date, package=package, category=category)
    if not path.is_file():
        return None
    return load_parquet(path)


def load_or_fetch_hist_day(
    client: GexbotClient,
    terminal_symbol: str,
    session_date: date,
    *,
    package: str = DEFAULT_PACKAGE,
    category: str = DEFAULT_CATEGORY,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return cached Parquet for one session or download from GEXBot Quant hist API."""
    ticker = gexbot_ticker(terminal_symbol)
    path = _cache_path(ticker, package, category, session_date)
    if path.is_file() and not force_refresh:
        return load_parquet(path)

    log.info("downloading GEXBot hist %s %s/%s %s", ticker, package, category, session_date)
    with _download_lock:
        if path.is_file() and not force_refresh:
            return load_parquet(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return _download_hist_to_parquet(client, ticker, package, category, session_date, path)


def snapshot_at_unix(hist: pd.DataFrame, target_unix: int) -> dict[str, Any]:
    """Nearest-at-or-before snapshot from cached hist (1Hz grid)."""
    if hist.empty:
        raise FileNotFoundError("empty hist frame")
    ts = hist["timestamp_unix"].to_numpy(dtype=np.int64)
    idx = int(np.searchsorted(ts, target_unix, side="right") - 1)
    if idx < 0:
        idx = 0
    row = hist.iloc[idx]
    return {
        "timestamp": int(row["timestamp_unix"]),
        "spot": float(row["spot"]),
        "zero_gamma": float(row["zero_gamma"]),
        "major_pos_vol": _row_optional_float(row, "major_pos_vol"),
        "major_neg_vol": _row_optional_float(row, "major_neg_vol"),
        "sum_gex_vol": _row_optional_float(row, "sum_gex_vol"),
    }


def _row_optional_float(row: pd.Series, col: str) -> float:
    if col not in row.index:
        return float("nan")
    val = row[col]
    if pd.isna(val):
        return float("nan")
    return float(val)


def snapshot_at_time(
    hist: pd.DataFrame,
    session_date: date,
    time_of_day: str,
) -> dict[str, Any]:
    target = session_datetime(session_date, time_of_day)
    target_unix = int(target.timestamp())
    return snapshot_at_unix(hist, target_unix)


def spot_at_time(
    client: GexbotClient,
    terminal_symbol: str,
    session_date: date,
    time_of_day: str,
) -> float:
    hist = load_or_fetch_hist_day(client, terminal_symbol, session_date)
    snap = snapshot_at_time(hist, session_date, time_of_day)
    spot = float(snap.get("spot", np.nan))
    if not np.isfinite(spot):
        raise ValueError(f"no spot in GEXBot hist for {session_date} @ {time_of_day}")
    return spot
