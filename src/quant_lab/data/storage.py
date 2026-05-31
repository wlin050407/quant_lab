"""Parquet storage layer.

Layout under `data/raw/`:

    underlying/{symbol}/bars_{interval}.parquet
    options/{symbol}/{asof_date}/chain.parquet
    options/{symbol}/{asof_date}/meta.parquet

`symbol` is sanitized (no `^`, `/`, `:`) for filesystem safety.

Everything is Parquet (`pyarrow`). No CSV, no pickle, no sqlite — one format
to rule them all (per `AGENTS.md`).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant_lab.config import settings
from quant_lab.data.base import OptionChainSnapshot, market_date

log = logging.getLogger(__name__)

_SAFE_SYMBOL_RE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_symbol(symbol: str) -> str:
    return _SAFE_SYMBOL_RE.sub("_", symbol)


def _underlying_path(symbol: str, interval: str) -> Path:
    return settings.paths.raw / "underlying" / _safe_symbol(symbol) / f"bars_{interval}.parquet"


def _option_dir(symbol: str, asof: datetime) -> Path:
    """Snapshot directory uses the ET market session date, NOT the UTC date.

    See `quant_lab.data.base.market_date` for why.
    """
    return (
        settings.paths.raw
        / "options"
        / _safe_symbol(symbol)
        / market_date(asof).isoformat()
    )


def save_underlying(df: pd.DataFrame, symbol: str, interval: str = "1d") -> Path:
    path = _underlying_path(symbol, interval)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = df.sort_index()

    combined.to_parquet(path, engine="pyarrow")
    log.info("wrote %d rows to %s", len(combined), path)
    return path


def load_underlying(symbol: str, interval: str = "1d") -> pd.DataFrame:
    path = _underlying_path(symbol, interval)
    if not path.exists():
        raise FileNotFoundError(f"no underlying file for {symbol!r} interval={interval!r}: {path}")
    return pd.read_parquet(path)


def save_option_chain(snapshot: OptionChainSnapshot) -> Path:
    out_dir = _option_dir(snapshot.symbol, snapshot.asof)
    out_dir.mkdir(parents=True, exist_ok=True)

    chain_path = out_dir / "chain.parquet"
    meta_path = out_dir / "meta.parquet"

    snapshot.chain.to_parquet(chain_path, engine="pyarrow")

    meta = pd.DataFrame(
        [
            {
                "symbol": snapshot.symbol,
                "asof_utc": snapshot.asof,
                "spot": snapshot.spot,
                "n_rows": len(snapshot.chain),
                "n_expiries": snapshot.chain["expiry"].nunique() if len(snapshot.chain) else 0,
            }
        ]
    )
    meta.to_parquet(meta_path, engine="pyarrow")

    log.info(
        "wrote %d option rows to %s (spot=%.2f)",
        len(snapshot.chain),
        chain_path,
        snapshot.spot,
    )
    return chain_path


def load_option_chain(symbol: str, asof_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    out_dir = settings.paths.raw / "options" / _safe_symbol(symbol) / asof_date
    chain_path = out_dir / "chain.parquet"
    meta_path = out_dir / "meta.parquet"
    if not chain_path.exists():
        raise FileNotFoundError(f"no option chain for {symbol!r} on {asof_date}: {chain_path}")
    chain = pd.read_parquet(chain_path)
    meta = pd.read_parquet(meta_path) if meta_path.exists() else pd.DataFrame()
    return chain, meta


def list_option_snapshots(symbol: str) -> list[str]:
    base = settings.paths.raw / "options" / _safe_symbol(symbol)
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())
