"""Load raw lake partitions for feature windows (at-or-before as_of only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_lake import partition_dir
from quant_lab.data.point_in_time_replay import ReplayRequest
from quant_lab.data.replay_integrity import LoadedPartition, load_verified_partition


def filter_at_or_before(frame: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    if frame.empty or "event_timestamp" not in frame.columns:
        return frame
    ts = pd.to_datetime(frame["event_timestamp"])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(MARKET_TZ)
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize(MARKET_TZ)
    return frame.loc[ts <= cutoff].copy()


def stable_sort(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    work = frame.copy()
    work["_event_timestamp"] = pd.to_datetime(work["event_timestamp"])
    if work["_event_timestamp"].dt.tz is None:
        work["_event_timestamp"] = work["_event_timestamp"].dt.tz_localize(MARKET_TZ)
    if "sequence" not in work.columns:
        work["sequence"] = -1
    else:
        work["sequence"] = pd.to_numeric(work["sequence"], errors="coerce").fillna(-1)
    if "contract_identifier" not in work.columns:
        work["contract_identifier"] = ""
    return work.sort_values(
        ["_event_timestamp", "sequence", "contract_identifier"],
        kind="mergesort",
    ).drop(columns=["_event_timestamp"])


def max_source_timestamp(frames: list[pd.DataFrame]) -> datetime | None:
    max_ts: datetime | None = None
    for frame in frames:
        if frame.empty or "event_timestamp" not in frame.columns:
            continue
        ts = pd.to_datetime(frame["event_timestamp"])
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize(MARKET_TZ)
        candidate = ts.max()
        if hasattr(candidate, "to_pydatetime"):
            candidate = candidate.to_pydatetime()
        if max_ts is None or candidate > max_ts:
            max_ts = candidate
    return max_ts


@dataclass
class FeatureRawFrames:
    quote_tick: pd.DataFrame | None = None
    quote_1s: pd.DataFrame | None = None
    trade_tick: pd.DataFrame | None = None
    greeks_1m: pd.DataFrame | None = None
    derived_gamma: pd.DataFrame | None = None
    index_tick: pd.DataFrame | None = None
    index_1s: pd.DataFrame | None = None
    duplicate_ratio: float = 0.0
    out_of_order_ratio: float = 0.0


def _try_load_partition(
    request: ReplayRequest,
    dataset: str,
    *,
    root: str | None = None,
    symbol: str | None = None,
    expiration: date | None = None,
) -> LoadedPartition | None:
    part_dir = partition_dir(
        request.data_root,
        dataset,
        request.trade_date,
        root=root,
        symbol=symbol,
        expiration=expiration,
    )
    if not part_dir.is_dir() or not (part_dir / "_manifest.json").is_file():
        return None
    try:
        return load_verified_partition(
            request.data_root,
            dataset,
            request.trade_date,
            root=root,
            symbol=symbol,
            expiration=expiration,
            strict_manifests=request.strict_manifests,
        )
    except Exception:
        if request.strict_manifests:
            raise
        return None


def load_feature_raw_frames(request: ReplayRequest) -> FeatureRawFrames:
    """Load and filter raw partitions for feature engineering."""

    exp: date = request.resolved_expiration()
    as_of = request.as_of_timestamp
    dup_ratios: list[float] = []
    ooo_ratios: list[float] = []

    def load_opt(dataset: str) -> pd.DataFrame | None:
        loaded = _try_load_partition(request, dataset, root=request.root, expiration=exp)
        if loaded is None:
            return None
        frame = stable_sort(filter_at_or_before(loaded.frame, as_of))
        manifest = loaded.manifest
        dup = float(manifest.get("duplicate_ratio") or 0.0)
        ooo = float(manifest.get("out_of_order_ratio") or 0.0)
        dup_ratios.append(dup)
        ooo_ratios.append(ooo)
        return frame

    def load_idx(dataset: str) -> pd.DataFrame | None:
        loaded = _try_load_partition(request, dataset, symbol=request.index_symbol)
        if loaded is None:
            return None
        return stable_sort(filter_at_or_before(loaded.frame, as_of))

    return FeatureRawFrames(
        quote_tick=load_opt("option_quote_tick") if request.include_quote_tick else None,
        quote_1s=load_opt("option_quote_1s") if request.include_quote_1s else None,
        trade_tick=load_opt("option_trade_tick") if request.include_trade_tick else None,
        greeks_1m=load_opt("option_greeks_1m_first_order") if request.include_greeks_1m else None,
        derived_gamma=load_opt("derived_gamma_black76_1m") if request.include_derived_gamma else None,
        index_tick=load_idx("index_price_tick") if request.include_index_tick else None,
        index_1s=load_idx("index_price_1s") if request.include_index_1s else None,
        duplicate_ratio=max(dup_ratios) if dup_ratios else 0.0,
        out_of_order_ratio=max(ooo_ratios) if ooo_ratios else 0.0,
    )
