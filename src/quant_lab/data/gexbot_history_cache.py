"""Download and cache GEXBot Quant historical JSON as Parquet for fast PIT replay."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.config import settings
from quant_lab.data.gexbot_client import GexbotClient, gexbot_ticker
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.thetadata_storage import load_parquet, save_parquet

log = logging.getLogger(__name__)

DEFAULT_PACKAGE = "classic"
DEFAULT_CATEGORY = "gex_zero"


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
    if not rows:
        return pd.DataFrame(columns=["timestamp_unix", "spot", "zero_gamma", "payload_json"])
    records: list[dict[str, Any]] = []
    for row in rows:
        ts = int(row.get("timestamp", 0))
        records.append(
            {
                "timestamp_unix": ts,
                "spot": float(row.get("spot", np.nan)),
                "zero_gamma": float(row.get("zero_gamma", np.nan)),
                "payload_json": json.dumps(row, separators=(",", ":")),
            }
        )
    df = pd.DataFrame.from_records(records)
    df = df.sort_values("timestamp_unix").reset_index(drop=True)
    return df


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
    rows = client.download_hist_json(ticker, package, category, session_date)
    df = _normalize_hist_rows(rows)
    if df.empty:
        raise FileNotFoundError(f"empty GEXBot hist for {ticker} on {session_date}")
    save_parquet(df, path)
    return df


def snapshot_at_unix(hist: pd.DataFrame, target_unix: int) -> dict[str, Any]:
    """Nearest-at-or-before snapshot from cached hist (1Hz grid)."""
    if hist.empty:
        raise FileNotFoundError("empty hist frame")
    ts = hist["timestamp_unix"].to_numpy(dtype=np.int64)
    idx = int(np.searchsorted(ts, target_unix, side="right") - 1)
    if idx < 0:
        idx = 0
    payload_raw = hist.iloc[idx]["payload_json"]
    return json.loads(str(payload_raw))


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
