"""Parquet layout for ThetaData intraday pulls (Phase 4).

Layout::

    data/raw/intraday/SPX/price_1m/<YYYY-MM-DD>.parquet
    data/raw/options/SPX/<YYYY-MM-DD>/intraday/quotes_<HHMM>.parquet
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from quant_lab.config import settings

log = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_symbol(symbol: str) -> str:
    return _SAFE.sub("_", symbol.replace("^", ""))


def spx_price_1m_path(session_date: date, *, symbol: str = "SPX") -> Path:
    return (
        settings.paths.raw
        / "intraday"
        / _safe_symbol(symbol)
        / "price_1m"
        / f"{session_date.isoformat()}.parquet"
    )


def option_intraday_path(
    session_date: date,
    time_label: str,
    *,
    symbol: str = "SPX",
) -> Path:
    safe_label = time_label.replace(":", "")
    return (
        settings.paths.raw
        / "options"
        / _safe_symbol(symbol)
        / session_date.isoformat()
        / "intraday"
        / f"quotes_{safe_label}.parquet"
    )


def intraday_chain_path(
    session_date: date,
    time_label: str,
    *,
    symbol: str = "SPXW",
) -> Path:
    safe_label = time_label.replace(":", "")
    return (
        settings.paths.raw
        / "options"
        / _safe_symbol(symbol)
        / session_date.isoformat()
        / "intraday"
        / f"chain_{safe_label}.parquet"
    )


def intraday_chain_meta_path(
    session_date: date,
    time_label: str,
    *,
    symbol: str = "SPXW",
) -> Path:
    safe_label = time_label.replace(":", "")
    return intraday_chain_path(session_date, safe_label, symbol=symbol).parent / f"meta_{safe_label}.parquet"


def save_intraday_chain(
    chain: pd.DataFrame,
    session_date: date,
    time_label: str,
    *,
    symbol: str = "SPXW",
    spot: float,
    asof: datetime,
    terminal_symbol: str = "^SPX",
) -> tuple[Path, Path]:
    chain_path = intraday_chain_path(session_date, time_label, symbol=symbol)
    meta_path = intraday_chain_meta_path(session_date, time_label, symbol=symbol)
    save_parquet(chain, chain_path)
    meta = pd.DataFrame(
        [
            {
                "symbol": terminal_symbol,
                "option_root": symbol,
                "asof_utc": asof,
                "spot": spot,
                "n_rows": len(chain),
                "source": "thetadata",
            }
        ]
    )
    save_parquet(meta, meta_path)
    return chain_path, meta_path


def save_parquet(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)
    log.info("wrote %d rows → %s", len(df), path)
    return path


def load_parquet(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)
