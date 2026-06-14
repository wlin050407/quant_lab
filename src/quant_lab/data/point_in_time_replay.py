"""Point-in-time replay over immutable raw event lake (ML-P4)."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from quant_lab.data.base import MARKET_TZ
from quant_lab.data.intraday_lake import PILOT_LAKE_ROOT, git_commit, partition_dir
from quant_lab.data.intraday_time import SESSION_CLOSE, SESSION_OPEN
from quant_lab.data.replay_integrity import (
    LoadedPartition,
    PartitionManifestSummary,
    load_verified_partition,
)
from quant_lab.data.replay_quality import ReplayQuality, compute_replay_quality

log = logging.getLogger(__name__)

SessionPhase = Literal["pre_market", "regular", "post_close", "early_close", "unknown"]

SORT_KEYS = ("event_timestamp", "sequence", "contract_identifier")
OPTION_CHAIN_COLUMNS: tuple[str, ...] = (
    "contract_identifier",
    "root",
    "expiration",
    "strike",
    "right",
    "latest_bid",
    "latest_ask",
    "latest_bid_size",
    "latest_ask_size",
    "latest_quote_timestamp",
    "quote_age_seconds",
    "quote_source_dataset",
    "last_trade_price",
    "last_trade_size",
    "last_trade_timestamp",
    "trade_age_seconds",
    "cumulative_trade_volume",
    "cumulative_trade_count",
    "trade_notional_proxy",
    "implied_vol",
    "delta",
    "theta",
    "vega",
    "rho",
    "underlying_price_from_greeks",
    "underlying_timestamp_from_greeks",
    "greek_timestamp",
    "greek_age_seconds",
    "gamma",
    "gamma_method",
    "gamma_method_version",
    "gamma_timestamp",
    "open_interest",
    "oi_event_timestamp",
    "oi_requested_date",
    "oi_semantics_status",
    "oi_publication_time_confirmed",
    "data_quality_flags",
)


@dataclass(frozen=True)
class ReplayRequest:
    trade_date: date
    as_of_timestamp: datetime
    root: str = "SPXW"
    expiration: date | None = None
    data_root: Path = Path("data/raw/thetadata")
    include_quote_tick: bool = True
    include_quote_1s: bool = True
    include_trade_tick: bool = True
    include_greeks_1m: bool = True
    include_derived_gamma: bool = True
    include_open_interest: bool = True
    include_index_tick: bool = True
    include_index_1s: bool = True
    strict_manifests: bool = True
    max_quote_age_seconds: int = 60
    max_greek_age_seconds: int = 120
    max_index_age_seconds: int = 10
    index_symbol: str = "SPX"

    def resolved_expiration(self) -> date:
        return self.expiration or self.trade_date

    def stable_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "as_of_timestamp": _ts_iso(self.as_of_timestamp),
            "root": self.root,
            "expiration": self.resolved_expiration().isoformat(),
            "data_root": str(self.data_root),
            "include_quote_tick": self.include_quote_tick,
            "include_quote_1s": self.include_quote_1s,
            "include_trade_tick": self.include_trade_tick,
            "include_greeks_1m": self.include_greeks_1m,
            "include_derived_gamma": self.include_derived_gamma,
            "include_open_interest": self.include_open_interest,
            "include_index_tick": self.include_index_tick,
            "include_index_1s": self.include_index_1s,
            "strict_manifests": self.strict_manifests,
            "max_quote_age_seconds": self.max_quote_age_seconds,
            "max_greek_age_seconds": self.max_greek_age_seconds,
            "max_index_age_seconds": self.max_index_age_seconds,
            "index_symbol": self.index_symbol,
        }


@dataclass(frozen=True)
class SessionReplayState:
    trade_date: date
    phase: SessionPhase
    rth_start: time
    rth_end: time
    as_of_timestamp: datetime
    metadata_available: bool
    pilot_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "phase": self.phase,
            "rth_start": self.rth_start.isoformat(),
            "rth_end": self.rth_end.isoformat(),
            "as_of_timestamp": _ts_iso(self.as_of_timestamp),
            "metadata_available": self.metadata_available,
            "pilot_label": self.pilot_label,
        }


@dataclass(frozen=True)
class IndexReplayState:
    symbol: str
    price: float | None
    index_timestamp: datetime | None
    index_age_seconds: float | None
    index_source_dataset: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "index_timestamp": _ts_iso(self.index_timestamp) if self.index_timestamp else None,
            "index_age_seconds": self.index_age_seconds,
            "index_source_dataset": self.index_source_dataset,
        }


@dataclass(frozen=True)
class OpenInterestReplayState:
    contract_count: int
    oi_semantics_status: str | None
    oi_publication_time_confirmed: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_count": self.contract_count,
            "oi_semantics_status": self.oi_semantics_status,
            "oi_publication_time_confirmed": self.oi_publication_time_confirmed,
        }


@dataclass(frozen=True)
class PointInTimeState:
    request: ReplayRequest
    as_of_timestamp: datetime
    session: SessionReplayState
    option_chain: pd.DataFrame
    index_state: IndexReplayState | None
    oi_state: OpenInterestReplayState | None
    quality: ReplayQuality
    warnings: tuple[str, ...]
    source_partitions: tuple[PartitionManifestSummary, ...]
    state_hash: str

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "as_of_timestamp": _ts_iso(self.as_of_timestamp),
            "state_hash": self.state_hash,
            "contract_count": int(len(self.option_chain)),
            "session_phase": self.session.phase,
            "quality": self.quality.to_dict(),
            "warnings": list(self.warnings),
            "index_source_dataset": (
                self.index_state.index_source_dataset if self.index_state else None
            ),
        }


def replay_state(
    trade_date: date,
    as_of_timestamp: datetime,
    *,
    root: str = "SPXW",
    expiration: date | None = None,
    data_root: Path | None = None,
    config: ReplayRequest | None = None,
    **kwargs: Any,
) -> PointInTimeState:
    """Replay lake state visible at ``as_of_timestamp`` (no lookahead)."""
    if config is not None:
        request = config
    else:
        request = ReplayRequest(
            trade_date=trade_date,
            as_of_timestamp=as_of_timestamp,
            root=root,
            expiration=expiration,
            data_root=data_root or Path("data/raw/thetadata"),
            **kwargs,
        )
    as_of = _ensure_tz(request.as_of_timestamp)
    warnings: list[str] = []
    partitions: list[PartitionManifestSummary] = []
    duplicate_ratios: list[float] = []
    out_of_order_ratios: list[float] = []

    session_part = _try_load(
        request,
        "session_metadata",
        root=request.root,
        expiration=None,
        warnings=warnings,
        partitions=partitions,
    )
    session = _resolve_session(request, session_part, as_of, warnings)

    if session.phase in {"pre_market", "post_close"}:
        warnings.append(f"session_outside_rth:{session.phase}")

    quote_tick = _load_dataset(
        request, "option_quote_tick", warnings, partitions, duplicate_ratios, out_of_order_ratios
    )
    quote_1s = _load_dataset(
        request, "option_quote_1s", warnings, partitions, duplicate_ratios, out_of_order_ratios
    )
    trades = _load_dataset(
        request, "option_trade_tick", warnings, partitions, duplicate_ratios, out_of_order_ratios
    )
    greeks = _load_dataset(
        request,
        "option_greeks_1m_first_order",
        warnings,
        partitions,
        duplicate_ratios,
        out_of_order_ratios,
    )
    gamma = _load_dataset(
        request,
        "derived_gamma_black76_1m",
        warnings,
        partitions,
        duplicate_ratios,
        out_of_order_ratios,
    )
    oi = _load_dataset(
        request, "option_open_interest", warnings, partitions, duplicate_ratios, out_of_order_ratios
    )
    index_tick = _load_index(request, "index_price_tick", warnings, partitions)
    index_1s = _load_index(request, "index_price_1s", warnings, partitions)

    contracts = _collect_contract_ids(quote_tick, quote_1s, trades, greeks, gamma, oi)
    chain_rows: list[dict[str, Any]] = []

    for cid in sorted(contracts):
        row = _empty_chain_row(cid)
        _apply_quote_state(row, cid, quote_tick, quote_1s, as_of, request, warnings)
        _apply_trade_state(row, cid, trades, as_of, request)
        _apply_greek_state(row, cid, greeks, as_of, request)
        _apply_gamma_state(row, cid, gamma, as_of, warnings)
        _apply_oi_state(row, cid, oi, as_of, warnings)
        chain_rows.append(row)

    option_chain = pd.DataFrame(chain_rows, columns=list(OPTION_CHAIN_COLUMNS))

    index_state = _resolve_index(index_tick, index_1s, as_of, request, warnings)
    oi_state = _resolve_oi_summary(option_chain, warnings)

    dup_ratio = max(duplicate_ratios) if duplicate_ratios else 0.0
    ooo_ratio = max(out_of_order_ratios) if out_of_order_ratios else 0.0
    if dup_ratio > 0:
        warnings.append(f"duplicate_ratio={dup_ratio:.4f}")
    if ooo_ratio > 0:
        warnings.append(f"out_of_order_ratio={ooo_ratio:.4f}")

    quality = compute_replay_quality(
        option_chain,
        index_available=index_state is not None and index_state.price is not None,
        stale_index=bool(index_state and index_state.index_age_seconds is not None
                         and index_state.index_age_seconds > request.max_index_age_seconds),
        duplicate_ratio=dup_ratio,
        out_of_order_ratio=ooo_ratio,
        warnings=warnings,
    )

    state_hash = compute_state_hash(
        request=request,
        partitions=partitions,
        as_of=as_of,
        option_chain=option_chain,
        index_state=index_state,
        warnings=warnings,
    )

    return PointInTimeState(
        request=request,
        as_of_timestamp=as_of,
        session=session,
        option_chain=option_chain,
        index_state=index_state,
        oi_state=oi_state,
        quality=quality,
        warnings=tuple(dict.fromkeys(warnings)),
        source_partitions=tuple(partitions),
        state_hash=state_hash,
    )


def compute_state_hash(
    *,
    request: ReplayRequest,
    partitions: list[PartitionManifestSummary],
    as_of: datetime,
    option_chain: pd.DataFrame,
    index_state: IndexReplayState | None,
    warnings: list[str],
) -> str:
    """Deterministic hash — excludes manifest ``created_at``."""
    part_hashes = sorted(
        json.dumps(p.stable_hash_input(), sort_keys=True) for p in partitions
    )
    chain_summary: list[dict[str, Any]] = []
    if not option_chain.empty:
        for _, r in option_chain.sort_values("contract_identifier").iterrows():
            chain_summary.append(
                {
                    "contract_identifier": r["contract_identifier"],
                    "latest_quote_timestamp": _ts_iso(r.get("latest_quote_timestamp")),
                    "last_trade_timestamp": _ts_iso(r.get("last_trade_timestamp")),
                    "greek_timestamp": _ts_iso(r.get("greek_timestamp")),
                    "gamma_timestamp": _ts_iso(r.get("gamma_timestamp")),
                    "oi_event_timestamp": _ts_iso(r.get("oi_event_timestamp")),
                }
            )
    payload = {
        "request": request.stable_dict(),
        "as_of_timestamp": _ts_iso(as_of),
        "partition_hashes": part_hashes,
        "row_counts_used": {p.dataset: p.row_count for p in partitions},
        "chain_summary": chain_summary,
        "index_timestamp": (
            _ts_iso(index_state.index_timestamp) if index_state and index_state.index_timestamp else None
        ),
        "schema_versions": sorted({p.dataset_schema_version for p in partitions}),
        "code_commit": git_commit(),
        "warnings": sorted(set(warnings)),
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def to_gex_adapter_frame(option_chain: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible GEX subset; prefer ``to_deterministic_input_frame``."""
    if option_chain.empty:
        return pd.DataFrame(
            columns=["strike", "right", "open_interest", "spot", "implied_vol", "gamma"]
        )
    spot = (
        float(option_chain["underlying_price_from_greeks"].dropna().iloc[0])
        if option_chain["underlying_price_from_greeks"].notna().any()
        else float("nan")
    )
    full = to_deterministic_input_frame(option_chain, spot=spot)
    cols = ["strike", "right", "open_interest", "spot", "implied_vol", "gamma", "contract_identifier"]
    return full[cols]


def _load_dataset(
    request: ReplayRequest,
    dataset: str,
    warnings: list[str],
    partitions: list[PartitionManifestSummary],
    duplicate_ratios: list[float],
    out_of_order_ratios: list[float],
) -> pd.DataFrame | None:
    flags = {
        "option_quote_tick": request.include_quote_tick,
        "option_quote_1s": request.include_quote_1s,
        "option_trade_tick": request.include_trade_tick,
        "option_greeks_1m_first_order": request.include_greeks_1m,
        "derived_gamma_black76_1m": request.include_derived_gamma,
        "option_open_interest": request.include_open_interest,
    }
    if not flags.get(dataset, True):
        return None
    loaded = _try_load(
        request,
        dataset,
        root=request.root,
        expiration=request.resolved_expiration(),
        warnings=warnings,
        partitions=partitions,
    )
    if loaded is None:
        return None
    frame = _filter_at_or_before(loaded.frame, request.as_of_timestamp)
    frame = _stable_sort(frame)
    dup, ooo = _dataset_quality_ratios(loaded.manifest, frame)
    duplicate_ratios.append(dup)
    out_of_order_ratios.append(ooo)
    return frame


def _load_index(
    request: ReplayRequest,
    dataset: str,
    warnings: list[str],
    partitions: list[PartitionManifestSummary],
) -> pd.DataFrame | None:
    flag = request.include_index_tick if dataset == "index_price_tick" else request.include_index_1s
    if not flag:
        return None
    loaded = _try_load(
        request,
        dataset,
        symbol=request.index_symbol,
        expiration=None,
        warnings=warnings,
        partitions=partitions,
    )
    if loaded is None:
        return None
    return _stable_sort(_filter_at_or_before(loaded.frame, request.as_of_timestamp))


def _try_load(
    request: ReplayRequest,
    dataset: str,
    *,
    root: str | None = None,
    symbol: str | None = None,
    expiration: date | None = None,
    warnings: list[str],
    partitions: list[PartitionManifestSummary],
) -> LoadedPartition | None:
    part_dir = partition_dir(
        request.data_root,
        dataset,
        request.trade_date,
        root=root,
        symbol=symbol,
        expiration=expiration,
    )
    if not part_dir.exists():
        warnings.append(f"missing_partition:{dataset}:{part_dir}")
        return None
    if not (part_dir / "_manifest.json").is_file():
        if request.strict_manifests:
            from quant_lab.data.replay_integrity import MissingManifestError

            raise MissingManifestError(f"missing manifest: {part_dir}")
        warnings.append(f"missing_manifest:{dataset}:{part_dir}")
        return None
    try:
        loaded = load_verified_partition(
            request.data_root,
            dataset,
            request.trade_date,
            root=root,
            symbol=symbol,
            expiration=expiration,
            strict_manifests=request.strict_manifests,
        )
    except Exception as exc:
        if request.strict_manifests:
            raise
        warnings.append(f"integrity_degraded:{dataset}:{type(exc).__name__}:{exc}")
        return None
    if loaded is not None:
        partitions.append(loaded.summary)
    return loaded


def _resolve_session(
    request: ReplayRequest,
    session_part: LoadedPartition | None,
    as_of: datetime,
    warnings: list[str],
) -> SessionReplayState:
    rth_start = SESSION_OPEN
    rth_end = SESSION_CLOSE
    pilot_label: str | None = None
    metadata_available = session_part is not None and not session_part.frame.empty

    if metadata_available:
        row = session_part.frame.iloc[0]
        if pd.notna(row.get("session_rth_start")):
            rth_start = _parse_time(str(row["session_rth_start"]))
        if pd.notna(row.get("session_rth_end")):
            rth_end = _parse_time(str(row["session_rth_end"]))
        pilot_label = str(row["pilot_label"]) if pd.notna(row.get("pilot_label")) else None
    else:
        warnings.append("missing_session_metadata")

    open_dt = datetime.combine(request.trade_date, rth_start, tzinfo=MARKET_TZ)
    close_dt = datetime.combine(request.trade_date, rth_end, tzinfo=MARKET_TZ)
    is_early_close_day = rth_end < SESSION_CLOSE

    if as_of < open_dt:
        phase: SessionPhase = "pre_market"
    elif as_of >= close_dt:
        phase = "post_close"
    elif is_early_close_day:
        phase = "early_close"
    elif metadata_available:
        phase = "regular"
    else:
        phase = "unknown"

    return SessionReplayState(
        trade_date=request.trade_date,
        phase=phase,
        rth_start=rth_start,
        rth_end=rth_end,
        as_of_timestamp=as_of,
        metadata_available=metadata_available,
        pilot_label=pilot_label,
    )


def _resolve_index(
    index_tick: pd.DataFrame | None,
    index_1s: pd.DataFrame | None,
    as_of: datetime,
    request: ReplayRequest,
    warnings: list[str],
) -> IndexReplayState | None:
    chosen: pd.Series | None = None
    source: str | None = None
    for dataset, frame in (("index_price_tick", index_tick), ("index_price_1s", index_1s)):
        if frame is None or frame.empty:
            continue
        latest = frame.iloc[-1]
        chosen = latest
        source = dataset
        break
    if chosen is None:
        warnings.append("missing_index")
        return IndexReplayState(
            symbol=request.index_symbol,
            price=None,
            index_timestamp=None,
            index_age_seconds=None,
            index_source_dataset=None,
        )
    ts = pd.Timestamp(chosen["event_timestamp"]).to_pydatetime()
    age = (as_of - _ensure_tz(ts)).total_seconds()
    if age > request.max_index_age_seconds:
        warnings.append("stale_index")
    price = float(chosen["price"]) if pd.notna(chosen.get("price")) else None
    return IndexReplayState(
        symbol=request.index_symbol,
        price=price,
        index_timestamp=_ensure_tz(ts),
        index_age_seconds=age,
        index_source_dataset=source,
    )


def _resolve_oi_summary(
    option_chain: pd.DataFrame,
    warnings: list[str],
) -> OpenInterestReplayState | None:
    if option_chain.empty:
        return None
    has_oi = option_chain["open_interest"].notna()
    if not has_oi.any():
        return OpenInterestReplayState(
            contract_count=0,
            oi_semantics_status=None,
            oi_publication_time_confirmed=None,
        )
    status = option_chain.loc[has_oi, "oi_semantics_status"].iloc[0]
    confirmed = option_chain.loc[has_oi, "oi_publication_time_confirmed"].iloc[0]
    if (confirmed is False or str(status) == "unconfirmed") and "oi_semantics_unconfirmed" not in warnings:
        warnings.append("oi_semantics_unconfirmed")
    return OpenInterestReplayState(
        contract_count=int(has_oi.sum()),
        oi_semantics_status=str(status) if pd.notna(status) else None,
        oi_publication_time_confirmed=(
            bool(confirmed) if pd.notna(confirmed) else None
        ),
    )


def _collect_contract_ids(*frames: pd.DataFrame | None) -> set[str]:
    ids: set[str] = set()
    for frame in frames:
        if frame is None or frame.empty or "contract_identifier" not in frame.columns:
            continue
        ids.update(frame["contract_identifier"].dropna().astype(str).tolist())
    return ids


def _empty_chain_row(contract_identifier: str) -> dict[str, Any]:
    parts = contract_identifier.split("|")
    root = parts[0] if len(parts) > 0 else None
    expiration = parts[1] if len(parts) > 1 else None
    strike = float(parts[2]) if len(parts) > 2 else None
    right = parts[3] if len(parts) > 3 else None
    return {
        "contract_identifier": contract_identifier,
        "root": root,
        "expiration": expiration,
        "strike": strike,
        "right": right,
        "latest_bid": None,
        "latest_ask": None,
        "latest_bid_size": None,
        "latest_ask_size": None,
        "latest_quote_timestamp": None,
        "quote_age_seconds": None,
        "quote_source_dataset": None,
        "last_trade_price": None,
        "last_trade_size": None,
        "last_trade_timestamp": None,
        "trade_age_seconds": None,
        "cumulative_trade_volume": 0.0,
        "cumulative_trade_count": 0,
        "trade_notional_proxy": 0.0,
        "implied_vol": None,
        "delta": None,
        "theta": None,
        "vega": None,
        "rho": None,
        "underlying_price_from_greeks": None,
        "underlying_timestamp_from_greeks": None,
        "greek_timestamp": None,
        "greek_age_seconds": None,
        "gamma": None,
        "gamma_method": None,
        "gamma_method_version": None,
        "gamma_timestamp": None,
        "open_interest": None,
        "oi_event_timestamp": None,
        "oi_requested_date": None,
        "oi_semantics_status": None,
        "oi_publication_time_confirmed": None,
        "data_quality_flags": "",
    }


def _apply_quote_state(
    row: dict[str, Any],
    cid: str,
    quote_tick: pd.DataFrame | None,
    quote_1s: pd.DataFrame | None,
    as_of: datetime,
    request: ReplayRequest,
    warnings: list[str],
) -> None:
    flags: list[str] = []
    chosen: pd.Series | None = None
    source: str | None = None
    for dataset, frame in (("option_quote_tick", quote_tick), ("option_quote_1s", quote_1s)):
        if frame is None or frame.empty:
            continue
        sub = frame[frame["contract_identifier"] == cid]
        if sub.empty:
            continue
        chosen = sub.iloc[-1]
        source = dataset
        break
    if chosen is None:
        row["data_quality_flags"] = _join_flags(flags, "missing_quote")
        return
    ts = pd.Timestamp(chosen["event_timestamp"]).to_pydatetime()
    age = (as_of - _ensure_tz(ts)).total_seconds()
    row["latest_bid"] = _float_or_none(chosen.get("bid"))
    row["latest_ask"] = _float_or_none(chosen.get("ask"))
    row["latest_bid_size"] = _float_or_none(chosen.get("bid_size"))
    row["latest_ask_size"] = _float_or_none(chosen.get("ask_size"))
    row["latest_quote_timestamp"] = _ensure_tz(ts)
    row["quote_age_seconds"] = age
    row["quote_source_dataset"] = source
    if age > request.max_quote_age_seconds:
        flags.append("stale_quote")
    if source == "option_quote_1s":
        flags.append("quote_fallback_1s")
    row["data_quality_flags"] = _join_flags(flags)


def _apply_trade_state(
    row: dict[str, Any],
    cid: str,
    trades: pd.DataFrame | None,
    as_of: datetime,
    request: ReplayRequest,
) -> None:
    flags = _split_flags(row.get("data_quality_flags", ""))
    if trades is None or trades.empty:
        return
    sub = trades[trades["contract_identifier"] == cid]
    if sub.empty:
        return
    last = sub.iloc[-1]
    ts = pd.Timestamp(last["event_timestamp"]).to_pydatetime()
    row["last_trade_price"] = _float_or_none(last.get("price"))
    row["last_trade_size"] = _float_or_none(last.get("size"))
    row["last_trade_timestamp"] = _ensure_tz(ts)
    row["trade_age_seconds"] = (as_of - _ensure_tz(ts)).total_seconds()
    sizes = pd.to_numeric(sub["size"], errors="coerce").fillna(0)
    prices = pd.to_numeric(sub["price"], errors="coerce").fillna(0)
    row["cumulative_trade_volume"] = float(sizes.sum())
    row["cumulative_trade_count"] = int(len(sub))
    row["trade_notional_proxy"] = float((sizes * prices * 100).sum())
    row["data_quality_flags"] = _join_flags(flags)


def _apply_greek_state(
    row: dict[str, Any],
    cid: str,
    greeks: pd.DataFrame | None,
    as_of: datetime,
    request: ReplayRequest,
) -> None:
    flags = _split_flags(row.get("data_quality_flags", ""))
    if greeks is None or greeks.empty:
        flags.append("missing_greeks")
        row["data_quality_flags"] = _join_flags(flags)
        return
    sub = greeks[greeks["contract_identifier"] == cid]
    if sub.empty:
        flags.append("missing_greeks")
        row["data_quality_flags"] = _join_flags(flags)
        return
    latest = sub.iloc[-1]
    ts = pd.Timestamp(latest["event_timestamp"]).to_pydatetime()
    age = (as_of - _ensure_tz(ts)).total_seconds()
    row["implied_vol"] = _float_or_none(latest.get("implied_vol"))
    row["delta"] = _float_or_none(latest.get("delta"))
    row["theta"] = _float_or_none(latest.get("theta"))
    row["vega"] = _float_or_none(latest.get("vega"))
    row["rho"] = _float_or_none(latest.get("rho"))
    row["underlying_price_from_greeks"] = _float_or_none(latest.get("underlying_price"))
    und_ts = latest.get("underlying_timestamp")
    row["underlying_timestamp_from_greeks"] = (
        _ensure_tz(pd.Timestamp(und_ts).to_pydatetime()) if pd.notna(und_ts) else None
    )
    row["greek_timestamp"] = _ensure_tz(ts)
    row["greek_age_seconds"] = age
    if age > request.max_greek_age_seconds:
        flags.append("stale_greek")
    row["data_quality_flags"] = _join_flags(flags)


def _apply_gamma_state(
    row: dict[str, Any],
    cid: str,
    gamma: pd.DataFrame | None,
    as_of: datetime,
    warnings: list[str],
) -> None:
    flags = _split_flags(row.get("data_quality_flags", ""))
    if gamma is None or gamma.empty:
        flags.append("missing_gamma")
        row["data_quality_flags"] = _join_flags(flags)
        return
    sub = gamma[gamma["contract_identifier"] == cid]
    if sub.empty:
        flags.append("missing_gamma")
        row["data_quality_flags"] = _join_flags(flags)
        return
    latest = sub.iloc[-1]
    method = str(latest.get("gamma_method", ""))
    if method and method != "black76":
        warnings.append(f"unexpected_gamma_method:{method}")
    row["gamma"] = _float_or_none(latest.get("gamma"))
    row["gamma_method"] = method or "black76"
    row["gamma_method_version"] = (
        str(latest.get("gamma_method_version")) if pd.notna(latest.get("gamma_method_version")) else None
    )
    ts = pd.Timestamp(latest["event_timestamp"]).to_pydatetime()
    row["gamma_timestamp"] = _ensure_tz(ts)
    row["data_quality_flags"] = _join_flags(flags)


def _apply_oi_state(
    row: dict[str, Any],
    cid: str,
    oi: pd.DataFrame | None,
    as_of: datetime,
    warnings: list[str],
) -> None:
    flags = _split_flags(row.get("data_quality_flags", ""))
    if oi is None or oi.empty:
        flags.append("missing_oi")
        row["data_quality_flags"] = _join_flags(flags)
        return
    sub = oi[oi["contract_identifier"] == cid]
    if sub.empty:
        flags.append("missing_oi")
        row["data_quality_flags"] = _join_flags(flags)
        return
    if "oi_event_timestamp" in sub.columns:
        sub = sub.copy()
        sub["_oi_ts"] = pd.to_datetime(sub["oi_event_timestamp"], errors="coerce")
        sub = sub[sub["_oi_ts"] <= pd.Timestamp(as_of)]
    if sub.empty:
        flags.append("missing_oi")
        row["data_quality_flags"] = _join_flags(flags)
        return
    latest = sub.iloc[-1]
    row["open_interest"] = _float_or_none(latest.get("open_interest"))
    oi_ts = latest.get("oi_event_timestamp")
    row["oi_event_timestamp"] = (
        _ensure_tz(pd.Timestamp(oi_ts).to_pydatetime()) if pd.notna(oi_ts) else None
    )
    row["oi_requested_date"] = latest.get("oi_requested_date")
    row["oi_semantics_status"] = latest.get("oi_semantics_status")
    confirmed = latest.get("oi_publication_time_confirmed")
    row["oi_publication_time_confirmed"] = bool(confirmed) if pd.notna(confirmed) else None
    if row["oi_publication_time_confirmed"] is False and "oi_semantics_unconfirmed" not in warnings:
        warnings.append("oi_semantics_unconfirmed")
    row["data_quality_flags"] = _join_flags(flags)


def _filter_at_or_before(frame: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    if frame.empty or "event_timestamp" not in frame.columns:
        return frame
    ts = pd.to_datetime(frame["event_timestamp"])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(MARKET_TZ)
    cutoff = pd.Timestamp(_ensure_tz(as_of))
    return frame.loc[ts <= cutoff].copy()


def _stable_sort(frame: pd.DataFrame) -> pd.DataFrame:
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


def _dataset_quality_ratios(manifest: dict[str, Any], filtered: pd.DataFrame) -> tuple[float, float]:
    dup_ratio = 0.0
    ooo_ratio = 0.0
    for warning in manifest.get("known_warnings", []):
        if isinstance(warning, str):
            if warning.startswith("duplicate_rows=") and "ratio=" in warning:
                with suppress(ValueError):
                    dup_ratio = float(warning.split("ratio=")[1])
            if warning.startswith("out_of_order=") and "ratio=" in warning:
                with suppress(ValueError):
                    ooo_ratio = float(warning.split("ratio=")[1])
    if filtered.empty:
        return dup_ratio, ooo_ratio
    keys = [c for c in ("contract_identifier", "event_timestamp", "sequence") if c in filtered.columns]
    if keys:
        dup_count = int(filtered.duplicated(subset=keys, keep=False).sum())
        dup_ratio = max(dup_ratio, dup_count / len(filtered))
    ts = pd.to_datetime(filtered["event_timestamp"])
    ooo = int((ts.diff() < pd.Timedelta(0)).sum())
    ooo_ratio = max(ooo_ratio, ooo / max(len(filtered) - 1, 1))
    return dup_ratio, ooo_ratio


def _ensure_tz(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=MARKET_TZ)
    return ts.astimezone(MARKET_TZ)


def _ts_iso(ts: Any) -> str | None:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return None
    if isinstance(ts, str):
        return ts
    return _ensure_tz(pd.Timestamp(ts).to_pydatetime()).isoformat()


def _float_or_none(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(out) else out


def _parse_time(value: str) -> time:
    parts = value.strip().split(":")
    return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)


def _split_flags(raw: str) -> list[str]:
    if not raw:
        return []
    return [p for p in str(raw).split("|") if p]


def _join_flags(flags: list[str], extra: str | None = None) -> str:
    items = list(dict.fromkeys(flags))
    if extra and extra not in items:
        items.append(extra)
    return "|".join(items)


def default_pilot_data_root() -> Path:
    if PILOT_LAKE_ROOT.is_dir():
        return PILOT_LAKE_ROOT
    return Path("data/raw/thetadata")


# --- ML-P5 deterministic input contract (frozen) ---

DETERMINISTIC_INPUT_COLUMNS: tuple[str, ...] = (
    "strike",
    "right",
    "open_interest",
    "spot",
    "implied_vol",
    "gamma",
    "gamma_method",
    "gamma_method_version",
    "bid",
    "ask",
    "mid",
    "expiration",
    "time_to_expiry_years",
    "contract_identifier",
    "quote_timestamp",
    "greek_timestamp",
    "oi_event_timestamp",
    "oi_semantics_status",
    "oi_publication_time_confirmed",
    "data_quality_flags",
)


@dataclass(frozen=True)
class DeterministicBundle:
    """Headline deterministic outputs from one normalized chain (ML-P5 contract)."""

    net_gex: float
    net_vex: float
    flip_level: float
    call_wall: float
    put_wall: float
    king_node: float
    max_pain: float
    pin_score: float
    expected_move_1sd: float
    gamma_source: str
    oi_semantics_status: str | None
    data_quality_flags: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


def to_deterministic_input_frame(
    option_chain: pd.DataFrame,
    *,
    spot: float,
) -> pd.DataFrame:
    """Freeze replay ``option_chain`` into the ML-P5 normalized deterministic schema."""
    if option_chain.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in DETERMINISTIC_INPUT_COLUMNS})
    bid = pd.to_numeric(option_chain.get("latest_bid"), errors="coerce")
    ask = pd.to_numeric(option_chain.get("latest_ask"), errors="coerce")
    mid = (bid + ask) / 2.0
    tte = (
        option_chain["time_to_expiry_years"]
        if "time_to_expiry_years" in option_chain.columns
        else pd.Series([pd.NA] * len(option_chain), index=option_chain.index)
    )
    out = pd.DataFrame(
        {
            "strike": option_chain["strike"],
            "right": option_chain["right"],
            "open_interest": option_chain["open_interest"],
            "spot": spot,
            "implied_vol": option_chain["implied_vol"],
            "gamma": option_chain["gamma"],
            "gamma_method": option_chain["gamma_method"],
            "gamma_method_version": option_chain["gamma_method_version"],
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "expiration": option_chain["expiration"],
            "time_to_expiry_years": tte,
            "contract_identifier": option_chain["contract_identifier"],
            "quote_timestamp": option_chain.get("latest_quote_timestamp"),
            "greek_timestamp": option_chain.get("greek_timestamp"),
            "oi_event_timestamp": option_chain.get("oi_event_timestamp"),
            "oi_semantics_status": option_chain.get("oi_semantics_status"),
            "oi_publication_time_confirmed": option_chain.get("oi_publication_time_confirmed"),
            "data_quality_flags": option_chain.get("data_quality_flags", ""),
        }
    )
    return out[list(DETERMINISTIC_INPUT_COLUMNS)]


def _factor_right(value: Any) -> str:
    raw = str(value).upper()
    if raw in {"C", "CALL"}:
        return "C"
    if raw in {"P", "PUT"}:
        return "P"
    return raw[:1]


def deterministic_input_to_factor_chain(
    input_df: pd.DataFrame,
    *,
    spot: float,
    symbol: str = "^SPX",
    dte: int = 0,
    hours_to_close: float | None = None,
) -> pd.DataFrame:
    """Map frozen deterministic input to factor-layer chain columns."""
    if input_df.empty:
        return pd.DataFrame(
            columns=[
                "strike",
                "right",
                "open_interest",
                "implied_volatility",
                "dte",
                "symbol",
                "bs_gamma",
                "gamma_method",
                "oi_semantics_status",
                "data_quality_flags",
            ]
        )
    from quant_lab.factors.positioning import resolve_cohort_time_years

    out = pd.DataFrame(
        {
            "strike": pd.to_numeric(input_df["strike"], errors="coerce"),
            "right": input_df["right"].map(_factor_right),
            "open_interest": pd.to_numeric(input_df["open_interest"], errors="coerce"),
            "implied_volatility": pd.to_numeric(input_df["implied_vol"], errors="coerce"),
            "dte": dte,
            "symbol": symbol,
            "gamma_method": input_df.get("gamma_method"),
            "gamma_method_version": input_df.get("gamma_method_version"),
            "oi_semantics_status": input_df.get("oi_semantics_status"),
            "oi_publication_time_confirmed": input_df.get("oi_publication_time_confirmed"),
            "data_quality_flags": input_df.get("data_quality_flags", ""),
            "contract_identifier": input_df.get("contract_identifier"),
        }
    )
    if "time_to_expiry_years" in input_df.columns and input_df["time_to_expiry_years"].notna().any():
        out["time_to_expiry_years"] = pd.to_numeric(
            input_df["time_to_expiry_years"], errors="coerce"
        )
    elif hours_to_close is not None:
        out["time_to_expiry_years"] = resolve_cohort_time_years(
            out, dte_max=1, hours_to_close=hours_to_close
        )
    if "gamma" in input_df.columns:
        out["bs_gamma"] = pd.to_numeric(input_df["gamma"], errors="coerce")
    return out


def compute_deterministic_bundle(
    input_df: pd.DataFrame,
    spot: float,
    *,
    symbol: str = "^SPX",
    asof: date | None = None,
    dte_max: int = 1,
    hours_to_close: float | None = None,
    time_to_close_pct: float | None = None,
    use_precomputed_gamma: bool = True,
    oi_mode: str = "settled",
) -> DeterministicBundle:
    """Run frozen deterministic outputs on normalized input (no network)."""
    from quant_lab.factors.effective_oi import chain_for_positioning
    from quant_lab.factors.gex import (
        add_bs_gamma_column,
        compute_gex_profile,
        compute_vex_profile,
        pct_dte_cohort_of_total,
    )
    from quant_lab.factors.positioning import (
        atm_iv_from_chain,
        expected_move_1sd,
        max_pain,
        pin_score_from_chain,
        resolve_cohort_time_years,
    )

    chain = deterministic_input_to_factor_chain(
        input_df,
        spot=spot,
        symbol=symbol,
        dte=0,
        hours_to_close=hours_to_close,
    )
    work = chain_for_positioning(chain, oi_mode=oi_mode)

    precomputed = (
        use_precomputed_gamma
        and "bs_gamma" in work.columns
        and work["bs_gamma"].notna().any()
    )
    method_ok = True
    if "gamma_method" in work.columns and work["gamma_method"].notna().any():
        method_ok = (work["gamma_method"].dropna() == "black76").all()
    has_precomputed = precomputed and method_ok
    gamma_source = "derived_black76_precomputed" if has_precomputed else "recomputed_bs_or_black76"

    if has_precomputed:
        with_gamma = work.copy()
    else:
        with_gamma = add_bs_gamma_column(work, spot, symbol=symbol, asof=asof)
        gamma_source = "recomputed_bs_or_black76"

    if has_precomputed:
        from quant_lab.factors.gex import (
            call_wall,
            compute_dealer_gamma_exposure,
            compute_gamma_flip,
            filter_chain_by_dte,
            king_node,
            put_wall,
            strongest_ceiling,
            strongest_floor,
            total_net_gex,
        )

        cohort = filter_chain_by_dte(with_gamma, dte_max=dte_max)
        per_strike = compute_dealer_gamma_exposure(cohort, spot, gamma_col="bs_gamma")
        net = total_net_gex(per_strike)
        flip = compute_gamma_flip(
            cohort, spot, symbol=symbol, asof=asof
        ).primary_flip
        cw = call_wall(per_strike)
        pw = put_wall(per_strike)
        king = king_node(per_strike)
        floor = strongest_floor(per_strike, spot)
        ceiling = strongest_ceiling(per_strike, spot)
        profile_all_cohort = filter_chain_by_dte(with_gamma, dte_max=None)
        per_all = compute_dealer_gamma_exposure(profile_all_cohort, spot, gamma_col="bs_gamma")
        net_all = total_net_gex(per_all)
    else:
        profile = compute_gex_profile(
            with_gamma,
            spot,
            symbol=symbol,
            asof=asof,
            dte_max=dte_max,
            compute_flip=True,
        )
        net = profile.net_gex
        flip = profile.flip_level
        cw = profile.call_wall
        pw = profile.put_wall
        king = profile.king_node
        floor = profile.floor_strike
        ceiling = profile.ceiling_strike
        profile_all = compute_gex_profile(
            with_gamma, spot, symbol=symbol, asof=asof, dte_max=None, compute_flip=False
        )
        net_all = profile_all.net_gex

    vex = compute_vex_profile(with_gamma, spot, symbol=symbol, asof=asof, dte_max=dte_max)
    pct_dte = pct_dte_cohort_of_total(net, net_all)
    t_years = resolve_cohort_time_years(work, dte_max=dte_max, hours_to_close=hours_to_close)
    iv = atm_iv_from_chain(work, spot, dte_max=dte_max)
    em = expected_move_1sd(spot, iv, time_years=t_years, dte=1)
    pin = pin_score_from_chain(
        work,
        spot,
        dte_max=dte_max,
        hours_to_close=hours_to_close,
        time_to_close_pct=time_to_close_pct,
        pct_gex_dte1=pct_dte,
        oi_mode=oi_mode,
    )
    oi_status = None
    if "oi_semantics_status" in input_df.columns and input_df["oi_semantics_status"].notna().any():
        oi_status = str(input_df["oi_semantics_status"].dropna().iloc[0])
    flags: set[str] = set()
    if "data_quality_flags" in input_df.columns:
        for raw in input_df["data_quality_flags"].astype(str):
            flags.update(p for p in raw.split("|") if p)
    if oi_status == "unconfirmed":
        flags.add("oi_semantics_unconfirmed")

    return DeterministicBundle(
        net_gex=float(net),
        net_vex=float(vex.net_vex),
        flip_level=float(flip),
        call_wall=float(cw),
        put_wall=float(pw),
        king_node=float(king),
        max_pain=float(max_pain(work, dte_max=dte_max)),
        pin_score=float(pin.score),
        expected_move_1sd=float(em),
        gamma_source=gamma_source,
        oi_semantics_status=oi_status,
        data_quality_flags=tuple(sorted(flags)),
        metadata={
            "n_contracts": int(len(work)),
            "pct_gex_dte1": float(pct_dte),
            "magnet_strike": float(pin.magnet_strike),
            "floor_strike": float(floor),
            "ceiling_strike": float(ceiling),
        },
    )
