"""Rolling history for GEXBot structure snapshots (momentum / trend)."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_DEFAULT_MAX_AGE_SEC = 30 * 60.0
_DEFAULT_SAMPLE_SEC = 60.0

_lock = threading.RLock()
_samples_by_ticker: dict[str, deque[StructureSample]] = {}


@dataclass(frozen=True)
class StructureSample:
    """One minute-ish structure observation."""

    monotonic_ts: float
    wall_ts: datetime
    spot: float | None
    sum_gex_vol: float | None
    sum_gex_oi: float | None
    zero_gamma: float | None
    gex_orderflow: float | None
    dex_orderflow: float | None


def _ticker_key(terminal_symbol: str) -> str:
    from quant_lab.data.gexbot_client import gexbot_ticker

    return gexbot_ticker(terminal_symbol)


def record_structure_sample(
    terminal_symbol: str,
    *,
    classic: dict[str, Any] | None = None,
    orderflow: dict[str, Any] | None = None,
    spot: float | None = None,
) -> None:
    """Append sample if enough time elapsed since last sample for ticker."""
    classic = classic or {}
    orderflow = orderflow or {}
    key = _ticker_key(terminal_symbol)
    now = time.monotonic()
    spot_val = spot
    if spot_val is None and classic.get("spot") is not None:
        try:
            spot_val = float(classic["spot"])
        except (TypeError, ValueError):
            spot_val = None

    sample = StructureSample(
        monotonic_ts=now,
        wall_ts=datetime.now(UTC),
        spot=spot_val,
        sum_gex_vol=_optional_float(classic.get("sum_gex_vol")),
        sum_gex_oi=_optional_float(classic.get("sum_gex_oi")),
        zero_gamma=_optional_float(classic.get("zero_gamma")),
        gex_orderflow=_optional_float(orderflow.get("gex_orderflow")),
        dex_orderflow=_optional_float(orderflow.get("dex_orderflow")),
    )

    with _lock:
        bucket = _samples_by_ticker.setdefault(key, deque())
        if bucket and (now - bucket[-1].monotonic_ts) < _DEFAULT_SAMPLE_SEC:
            bucket[-1] = sample  # coalesce within sample window
            return
        bucket.append(sample)
        _prune(bucket, max_age_sec=_DEFAULT_MAX_AGE_SEC)


def samples_for(terminal_symbol: str) -> list[StructureSample]:
    key = _ticker_key(terminal_symbol)
    with _lock:
        bucket = _samples_by_ticker.get(key)
        if not bucket:
            return []
        return list(bucket)


def trend_pct(
    terminal_symbol: str,
    field: str,
    *,
    lookback_sec: float,
) -> float | None:
    """Percent change of ``field`` over lookback window."""
    rows = samples_for(terminal_symbol)
    if len(rows) < 2:
        return None
    now = rows[-1].monotonic_ts
    cur = getattr(rows[-1], field, None)
    if cur is None:
        return None
    past_val: float | None = None
    for row in reversed(rows):
        if now - row.monotonic_ts >= lookback_sec:
            past_val = getattr(row, field, None)
            break
    if past_val is None:
        past_val = getattr(rows[0], field, None)
    if past_val is None or not _finite(past_val) or abs(past_val) < 1e-9:
        return None
    if not _finite(cur):
        return None
    return float((cur - past_val) / abs(past_val))


def spot_trend_pct(terminal_symbol: str, lookback_sec: float) -> float | None:
    return trend_pct(terminal_symbol, "spot", lookback_sec=lookback_sec)


def _prune(bucket: deque[StructureSample], *, max_age_sec: float) -> None:
    if not bucket:
        return
    cutoff = bucket[-1].monotonic_ts - max_age_sec
    while bucket and bucket[0].monotonic_ts < cutoff:
        bucket.popleft()


def _optional_float(val: Any) -> float | None:
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if _finite(out) else None


def _finite(val: float) -> bool:
    import numpy as np

    return bool(np.isfinite(val))


def clear_structure_history() -> None:
    """Test helper."""
    with _lock:
        _samples_by_ticker.clear()
