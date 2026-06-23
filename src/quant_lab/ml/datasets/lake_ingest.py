"""Controlled full-RTH ThetaData raw lake ingestion (ML-P7.6)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from quant_lab.data.intraday_lake import (
    IncompletePartitionError,
    build_derived_gamma_black76,
    build_session_metadata_row,
    ingest_partition,
    make_source_request_id,
    normalize_index_price,
    normalize_option_greeks,
    normalize_option_open_interest,
    normalize_option_quote,
    normalize_option_trade,
    partition_dir,
)
from quant_lab.data.intraday_manifest import SourceRequestMeta, is_partition_complete, read_manifest
from quant_lab.data.thetadata_client import (
    DEFAULT_INDEX_SYMBOL,
    DEFAULT_OPTION_ROOT,
    refresh_thetadata_client,
)

log = logging.getLogger(__name__)

QuoteResolution = Literal["tick", "1s", "tick_or_1s"]
IndexResolution = Literal["tick", "1s", "tick_or_1s"]
EARLY_CLOSE_RTH_END = "13:00:00"
FULL_RTH_TICK_SKIP_STRIKE_RANGE = 30

REQUIRED_OPTION_PARTITIONS: tuple[str, ...] = (
    "option_trade_tick",
    "option_greeks_1m_first_order",
    "derived_gamma_black76_1m",
    "option_open_interest",
)
QUOTE_PARTITIONS: tuple[str, ...] = ("option_quote_tick", "option_quote_1s")
INDEX_PARTITIONS: tuple[str, ...] = ("index_price_tick", "index_price_1s")


@dataclass(frozen=True)
class RthIngestPlan:
    trade_date: date
    day_type: str
    window_start: str
    window_end: str
    session_rth_end: str
    strike_range: int
    quote_resolution: QuoteResolution
    index_resolution: IndexResolution
    estimated_api_calls: int
    partitions_to_skip: tuple[str, ...]
    partitions_to_fetch: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "day_type": self.day_type,
            "window": f"{self.window_start}–{self.window_end} ET",
            "session_rth_end": self.session_rth_end,
            "strike_range": self.strike_range,
            "quote_resolution": self.quote_resolution,
            "index_resolution": self.index_resolution,
            "estimated_api_calls": self.estimated_api_calls,
            "partitions_to_skip": list(self.partitions_to_skip),
            "partitions_to_fetch": list(self.partitions_to_fetch),
        }


@dataclass
class DateIngestResult:
    trade_date: date
    success: bool
    reason: str
    skipped: bool = False
    api_request_count: int = 0
    quote_resolution_used: str | None = None
    quote_fallback_reason: str | None = None
    resolutions_used: dict[str, str] = field(default_factory=dict)
    ingest_wall_sec: float = 0.0
    partition_summaries: dict[str, Any] = field(default_factory=dict)


def rth_window_for_day_type(
    day_type: str,
    *,
    session_rth_start: str,
    session_rth_end: str,
) -> tuple[str, str, str]:
    """Return (window_start, window_end, session_rth_end) for ingest + metadata."""
    if day_type == "early_close":
        return session_rth_start, EARLY_CLOSE_RTH_END, EARLY_CLOSE_RTH_END
    return session_rth_start, session_rth_end, session_rth_end


def _partition_label(
    lake_root: Path,
    dataset: str,
    trade_date: date,
    *,
    root: str,
    symbol: str,
) -> str:
    if dataset.startswith("index_"):
        return str(partition_dir(lake_root, dataset, trade_date, symbol=symbol))
    if dataset == "session_metadata":
        return str(partition_dir(lake_root, dataset, trade_date, root=root))
    return str(partition_dir(lake_root, dataset, trade_date, root=root, expiration=trade_date))


def _incomplete_partition_exists(part_dir: Path) -> bool:
    if not part_dir.exists():
        return False
    manifest = read_manifest(part_dir)
    if manifest is None:
        return True
    return manifest.get("ingestion_status") != "complete"


def check_partition_readiness(
    lake_root: Path,
    trade_date: date,
    *,
    root: str,
    symbol: str,
    idempotent_skip_existing: bool,
) -> tuple[list[str], list[str], list[str]]:
    """Return (complete, missing, incomplete_refuse)."""
    complete: list[str] = []
    missing: list[str] = []
    incomplete_refuse: list[str] = []

    all_datasets = (
        *QUOTE_PARTITIONS,
        *REQUIRED_OPTION_PARTITIONS,
        *INDEX_PARTITIONS,
        "session_metadata",
    )
    for ds in all_datasets:
        if ds.startswith("index_"):
            part = partition_dir(lake_root, ds, trade_date, symbol=symbol)
        elif ds == "session_metadata":
            part = partition_dir(lake_root, ds, trade_date, root=root)
        else:
            part = partition_dir(lake_root, ds, trade_date, root=root, expiration=trade_date)

        if is_partition_complete(part):
            complete.append(ds)
        elif _incomplete_partition_exists(part):
            incomplete_refuse.append(ds)
        else:
            missing.append(ds)

    # tick_or_1s policy: one complete quote partition satisfies the quote requirement
    if any(ds in complete for ds in QUOTE_PARTITIONS):
        missing = [ds for ds in missing if ds not in QUOTE_PARTITIONS]

    if idempotent_skip_existing and complete and not missing and not incomplete_refuse:
        return complete, [], []

    return complete, missing, incomplete_refuse


def build_rth_ingest_plan(
    *,
    trade_date: date,
    day_type: str,
    lake_root: Path,
    root: str,
    symbol: str,
    strike_range: int,
    session_rth_start: str,
    session_rth_end: str,
    quote_resolution: QuoteResolution,
    index_resolution: IndexResolution,
    idempotent_skip_existing: bool,
) -> RthIngestPlan:
    ws, we, rth_end = rth_window_for_day_type(
        day_type,
        session_rth_start=session_rth_start,
        session_rth_end=session_rth_end,
    )
    complete, missing, incomplete = check_partition_readiness(
        lake_root,
        trade_date,
        root=root,
        symbol=symbol,
        idempotent_skip_existing=idempotent_skip_existing,
    )
    if incomplete:
        raise IncompletePartitionError(
            f"incomplete partitions refuse overwrite: {','.join(incomplete)}"
        )

    to_skip = tuple(complete)
    to_fetch = tuple(missing)
    api_calls = 0
    if any(ds in missing for ds in QUOTE_PARTITIONS) or (
        quote_resolution == "tick_or_1s"
        and not any(ds in complete for ds in QUOTE_PARTITIONS)
    ):
        api_calls += 2 if quote_resolution == "tick_or_1s" else 1
    for ds in REQUIRED_OPTION_PARTITIONS:
        if ds in missing and ds != "derived_gamma_black76_1m":
            api_calls += 1
    for ds in INDEX_PARTITIONS:
        if ds in missing:
            if index_resolution == "tick_or_1s":
                api_calls += 2
            elif ds.endswith(index_resolution) or (
                index_resolution == "1s" and ds == "index_price_1s"
            ):
                api_calls += 1
    if "session_metadata" in missing:
        api_calls += 0

    if complete and not missing:
        api_calls = 0

    return RthIngestPlan(
        trade_date=trade_date,
        day_type=day_type,
        window_start=ws,
        window_end=we,
        session_rth_end=rth_end,
        strike_range=strike_range,
        quote_resolution=quote_resolution,
        index_resolution=index_resolution,
        estimated_api_calls=api_calls,
        partitions_to_skip=to_skip,
        partitions_to_fetch=to_fetch,
    )


def _is_full_rth_window(window_start: str, window_end: str) -> bool:
    """True when ingest window spans regular or early-close full session."""
    return window_start == "09:30:00" and window_end in {EARLY_CLOSE_RTH_END, "16:00:00"}


def _source_meta(endpoint: str, params: dict[str, Any]) -> SourceRequestMeta:
    return SourceRequestMeta(
        endpoint=endpoint,
        request_id=make_source_request_id(endpoint, params),
        params_redacted=params,
    )


def _ingest_frame(
    frame: pd.DataFrame,
    *,
    lake_root: Path,
    dataset: str,
    trade_date: date,
    root: str,
    symbol: str,
    source_requests: list[SourceRequestMeta],
    overwrite: bool,
) -> dict[str, Any]:
    is_index = dataset.startswith("index_")
    is_session = dataset == "session_metadata"
    result = ingest_partition(
        frame,
        lake_root=lake_root,
        dataset=dataset,
        trade_date=trade_date,
        root=root if not is_index else None,
        symbol=symbol if is_index else None,
        expiration=None if (is_index or is_session) else trade_date,
        source_requests=source_requests,
        overwrite=overwrite,
    )
    return {
        "partition_dir": str(result.partition_dir),
        "row_count": result.row_count,
        "skipped": result.skipped,
    }


def _fetch_option_quote(
    client: Any,
    *,
    interval: str,
    window_start: str,
    window_end: str,
    common: dict[str, Any],
) -> pd.DataFrame:
    return client.option_history_quote(
        interval=interval,
        start_time=window_start,
        end_time=window_end,
        strike="*",
        right="both",
        **common,
    )


def ingest_rth_trade_date(
    *,
    trade_date: date,
    day_type: str,
    lake_root: Path,
    root: str = DEFAULT_OPTION_ROOT,
    symbol: str = DEFAULT_INDEX_SYMBOL,
    strike_range: int,
    session_rth_start: str,
    session_rth_end: str,
    quote_resolution: QuoteResolution = "tick_or_1s",
    index_resolution: IndexResolution = "tick_or_1s",
    max_retries: int = 2,
    request_budget_per_date: int = 8,
    idempotent_skip_existing: bool = True,
    quote_tick_row_budget: int = 5_000_000,
    overwrite: bool = False,
    dry_run: bool = False,
) -> DateIngestResult:
    """Ingest one trade_date full RTH raw lake partitions from ThetaData."""
    t0 = time.perf_counter()
    try:
        plan = build_rth_ingest_plan(
            trade_date=trade_date,
            day_type=day_type,
            lake_root=lake_root,
            root=root,
            symbol=symbol,
            strike_range=strike_range,
            session_rth_start=session_rth_start,
            session_rth_end=session_rth_end,
            quote_resolution=quote_resolution,
            index_resolution=index_resolution,
            idempotent_skip_existing=idempotent_skip_existing,
        )
    except IncompletePartitionError as exc:
        return DateIngestResult(
            trade_date=trade_date,
            success=False,
            reason=f"incomplete_partition_refuse:{exc}",
            ingest_wall_sec=time.perf_counter() - t0,
        )

    if not plan.partitions_to_fetch:
        return DateIngestResult(
            trade_date=trade_date,
            success=True,
            reason="partitions_complete_skip",
            skipped=True,
            api_request_count=0,
            ingest_wall_sec=time.perf_counter() - t0,
            partition_summaries={"skipped": list(plan.partitions_to_skip)},
        )

    if dry_run:
        return DateIngestResult(
            trade_date=trade_date,
            success=True,
            reason="dry_run_plan_only",
            api_request_count=plan.estimated_api_calls,
            ingest_wall_sec=time.perf_counter() - t0,
            partition_summaries={"plan": plan.to_dict()},
        )

    if plan.estimated_api_calls > request_budget_per_date:
        return DateIngestResult(
            trade_date=trade_date,
            success=False,
            reason=(
                f"request_budget_exceeded:estimated={plan.estimated_api_calls}"
                f":budget={request_budget_per_date}"
            ),
            api_request_count=plan.estimated_api_calls,
            ingest_wall_sec=time.perf_counter() - t0,
        )

    ws, we = plan.window_start, plan.window_end
    common = {
        "symbol": root,
        "expiration": trade_date,
        "date": trade_date,
        "max_dte": 1,
        "strike_range": strike_range,
    }
    api_count = 0
    summaries: dict[str, Any] = {}
    resolutions: dict[str, str] = {}
    quote_used: str | None = None
    quote_fallback: str | None = None

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            client = refresh_thetadata_client()
            api_count = 0

            quote_ok = any(
                is_partition_complete(
                    partition_dir(lake_root, ds, trade_date, root=root, expiration=trade_date)
                )
                for ds in QUOTE_PARTITIONS
            )
            if not quote_ok:
                if quote_resolution == "1s":
                    api_count += 1
                    q_raw = _fetch_option_quote(
                        client, interval="1s", window_start=ws, window_end=we, common=common
                    )
                    quote_used = "option_quote_1s"
                    resolutions["quote"] = quote_used
                    meta = _source_meta("option_history_quote", {**common, "interval": "1s"})
                    df = normalize_option_quote(
                        q_raw,
                        dataset="option_quote_1s",
                        root=root,
                        trade_date=trade_date,
                        source_endpoint="option_history_quote",
                        source_request_id=meta.request_id,
                    )
                    summaries["option_quote_1s"] = _ingest_frame(
                        df,
                        lake_root=lake_root,
                        dataset="option_quote_1s",
                        trade_date=trade_date,
                        root=root,
                        symbol=symbol,
                        source_requests=[meta],
                        overwrite=overwrite,
                    )
                elif quote_resolution == "tick":
                    api_count += 1
                    q_raw = _fetch_option_quote(
                        client, interval="tick", window_start=ws, window_end=we, common=common
                    )
                    quote_used = "option_quote_tick"
                    resolutions["quote"] = quote_used
                    meta = _source_meta("option_history_quote", {**common, "interval": "tick"})
                    df = normalize_option_quote(
                        q_raw,
                        dataset="option_quote_tick",
                        root=root,
                        trade_date=trade_date,
                        source_endpoint="option_history_quote",
                        source_request_id=meta.request_id,
                    )
                    summaries["option_quote_tick"] = _ingest_frame(
                        df,
                        lake_root=lake_root,
                        dataset="option_quote_tick",
                        trade_date=trade_date,
                        root=root,
                        symbol=symbol,
                        source_requests=[meta],
                        overwrite=overwrite,
                    )
                else:
                    skip_tick = (
                        _is_full_rth_window(ws, we)
                        and strike_range >= FULL_RTH_TICK_SKIP_STRIKE_RANGE
                    )
                    if skip_tick:
                        quote_fallback = (
                            f"full_rth_strike_range_{strike_range}_skip_tick_attempt"
                        )
                        log.info(
                            "%s: %s — fetching quote 1s directly",
                            trade_date,
                            quote_fallback,
                        )
                        api_count += 1
                        q_1s = _fetch_option_quote(
                            client, interval="1s", window_start=ws, window_end=we, common=common
                        )
                        quote_used = "option_quote_1s"
                        resolutions["quote"] = quote_used
                        meta = _source_meta("option_history_quote", {**common, "interval": "1s"})
                        df = normalize_option_quote(
                            q_1s,
                            dataset="option_quote_1s",
                            root=root,
                            trade_date=trade_date,
                            source_endpoint="option_history_quote",
                            source_request_id=meta.request_id,
                        )
                        summaries["option_quote_1s"] = _ingest_frame(
                            df,
                            lake_root=lake_root,
                            dataset="option_quote_1s",
                            trade_date=trade_date,
                            root=root,
                            symbol=symbol,
                            source_requests=[meta],
                            overwrite=overwrite,
                        )
                    else:
                        try:
                            api_count += 1
                            q_tick = _fetch_option_quote(
                                client, interval="tick", window_start=ws, window_end=we, common=common
                            )
                            if len(q_tick) > quote_tick_row_budget:
                                quote_fallback = (
                                    f"tick_row_count={len(q_tick)}>budget={quote_tick_row_budget}"
                                )
                                raise RuntimeError(quote_fallback)
                            quote_used = "option_quote_tick"
                            resolutions["quote"] = quote_used
                            meta = _source_meta(
                                "option_history_quote", {**common, "interval": "tick"}
                            )
                            df = normalize_option_quote(
                                q_tick,
                                dataset="option_quote_tick",
                                root=root,
                                trade_date=trade_date,
                                source_endpoint="option_history_quote",
                                source_request_id=meta.request_id,
                            )
                            summaries["option_quote_tick"] = _ingest_frame(
                                df,
                                lake_root=lake_root,
                                dataset="option_quote_tick",
                                trade_date=trade_date,
                                root=root,
                                symbol=symbol,
                                source_requests=[meta],
                                overwrite=overwrite,
                            )
                        except Exception as tick_exc:
                            quote_fallback = str(tick_exc)
                            log.warning(
                                "quote tick failed for %s — explicit fallback to 1s: %s",
                                trade_date,
                                tick_exc,
                            )
                            api_count += 1
                            q_1s = _fetch_option_quote(
                                client, interval="1s", window_start=ws, window_end=we, common=common
                            )
                            quote_used = "option_quote_1s"
                            resolutions["quote"] = quote_used
                            meta = _source_meta("option_history_quote", {**common, "interval": "1s"})
                            df = normalize_option_quote(
                                q_1s,
                                dataset="option_quote_1s",
                                root=root,
                                trade_date=trade_date,
                                source_endpoint="option_history_quote",
                                source_request_id=meta.request_id,
                            )
                            summaries["option_quote_1s"] = _ingest_frame(
                                df,
                                lake_root=lake_root,
                                dataset="option_quote_1s",
                                trade_date=trade_date,
                                root=root,
                                symbol=symbol,
                                source_requests=[meta],
                                overwrite=overwrite,
                            )

            if not is_partition_complete(
                partition_dir(
                    lake_root,
                    "option_trade_tick",
                    trade_date,
                    root=root,
                    expiration=trade_date,
                )
            ):
                api_count += 1
                tr_params = {**common, "start_time": ws, "end_time": we}
                meta_tr = _source_meta("option_history_trade", tr_params)
                trades_raw = client.option_history_trade(
                    symbol=root,
                    expiration=trade_date,
                    date=trade_date,
                    start_time=ws,
                    end_time=we,
                    strike="*",
                    right="both",
                    max_dte=1,
                    strike_range=strike_range,
                )
                df_tr = normalize_option_trade(
                    trades_raw,
                    root=root,
                    trade_date=trade_date,
                    source_endpoint="option_history_trade",
                    source_request_id=meta_tr.request_id,
                )
                summaries["option_trade_tick"] = _ingest_frame(
                    df_tr,
                    lake_root=lake_root,
                    dataset="option_trade_tick",
                    trade_date=trade_date,
                    root=root,
                    symbol=symbol,
                    source_requests=[meta_tr],
                    overwrite=overwrite,
                )

            greeks_part = partition_dir(
                lake_root,
                "option_greeks_1m_first_order",
                trade_date,
                root=root,
                expiration=trade_date,
            )
            df_g: pd.DataFrame | None = None
            if not is_partition_complete(greeks_part):
                api_count += 1
                g_params = {**common, "interval": "1m", "start_time": ws, "end_time": we}
                meta_g = _source_meta("option_history_greeks_first_order", g_params)
                greeks_raw = client.option_history_greeks_first_order(
                    root,
                    trade_date,
                    interval="1m",
                    date=trade_date,
                    strike="*",
                    right="both",
                    start_time=ws,
                    end_time=we,
                    strike_range=strike_range,
                )
                df_g = normalize_option_greeks(
                    greeks_raw,
                    root=root,
                    trade_date=trade_date,
                    source_endpoint="option_history_greeks_first_order",
                    source_request_id=meta_g.request_id,
                )
                summaries["option_greeks_1m_first_order"] = _ingest_frame(
                    df_g,
                    lake_root=lake_root,
                    dataset="option_greeks_1m_first_order",
                    trade_date=trade_date,
                    root=root,
                    symbol=symbol,
                    source_requests=[meta_g],
                    overwrite=overwrite,
                )
            elif is_partition_complete(greeks_part):
                df_g = pd.read_parquet(greeks_part / "part-000.parquet")

            gamma_part = partition_dir(
                lake_root,
                "derived_gamma_black76_1m",
                trade_date,
                root=root,
                expiration=trade_date,
            )
            if not is_partition_complete(gamma_part):
                if df_g is None:
                    df_g = pd.read_parquet(greeks_part / "part-000.parquet")
                df_gamma = build_derived_gamma_black76(df_g, trade_date=trade_date, root=root)
                summaries["derived_gamma_black76_1m"] = _ingest_frame(
                    df_gamma,
                    lake_root=lake_root,
                    dataset="derived_gamma_black76_1m",
                    trade_date=trade_date,
                    root=root,
                    symbol=symbol,
                    source_requests=[],
                    overwrite=overwrite,
                )

            oi_part = partition_dir(
                lake_root,
                "option_open_interest",
                trade_date,
                root=root,
                expiration=trade_date,
            )
            if not is_partition_complete(oi_part):
                api_count += 1
                oi_params = {**common}
                meta_oi = _source_meta("option_history_open_interest", oi_params)
                oi_raw = client.option_history_open_interest(
                    symbol=root,
                    expiration=trade_date,
                    date=trade_date,
                    strike="*",
                    right="both",
                    max_dte=1,
                    strike_range=strike_range,
                )
                df_oi = normalize_option_open_interest(
                    oi_raw,
                    root=root,
                    trade_date=trade_date,
                    requested_date=trade_date,
                    source_endpoint="option_history_open_interest",
                    source_request_id=meta_oi.request_id,
                )
                summaries["option_open_interest"] = _ingest_frame(
                    df_oi,
                    lake_root=lake_root,
                    dataset="option_open_interest",
                    trade_date=trade_date,
                    root=root,
                    symbol=symbol,
                    source_requests=[meta_oi],
                    overwrite=overwrite,
                )

            index_1s_needed = not is_partition_complete(
                partition_dir(lake_root, "index_price_1s", trade_date, symbol=symbol)
            )
            index_tick_needed = index_resolution in {"tick", "tick_or_1s"} and not is_partition_complete(
                partition_dir(lake_root, "index_price_tick", trade_date, symbol=symbol)
            )

            if index_1s_needed:
                api_count += 1
                idx1_params = {
                    "symbol": symbol,
                    "interval": "1s",
                    "date": trade_date,
                    "start_time": ws,
                    "end_time": we,
                }
                meta_i1 = _source_meta("index_history_price", idx1_params)
                index_1s_raw = client.index_history_price(
                    symbol=symbol,
                    interval="1s",
                    date=trade_date,
                    start_time=ws,
                    end_time=we,
                )
                df_i1 = normalize_index_price(
                    index_1s_raw,
                    dataset="index_price_1s",
                    symbol=symbol,
                    trade_date=trade_date,
                    source_endpoint="index_history_price",
                    source_request_id=meta_i1.request_id,
                )
                resolutions["index"] = "index_price_1s"
                summaries["index_price_1s"] = _ingest_frame(
                    df_i1,
                    lake_root=lake_root,
                    dataset="index_price_1s",
                    trade_date=trade_date,
                    root=root,
                    symbol=symbol,
                    source_requests=[meta_i1],
                    overwrite=overwrite,
                )

            if index_tick_needed and index_resolution != "1s":
                try:
                    api_count += 1
                    idxt_params = {
                        "symbol": symbol,
                        "interval": "tick",
                        "date": trade_date,
                        "start_time": ws,
                        "end_time": we,
                    }
                    meta_it = _source_meta("index_history_price", idxt_params)
                    index_tick_raw = client.index_history_price(
                        symbol=symbol,
                        interval="tick",
                        date=trade_date,
                        start_time=ws,
                        end_time=we,
                    )
                    df_it = normalize_index_price(
                        index_tick_raw,
                        dataset="index_price_tick",
                        symbol=symbol,
                        trade_date=trade_date,
                        source_endpoint="index_history_price",
                        source_request_id=meta_it.request_id,
                    )
                    resolutions["index"] = "index_price_tick"
                    summaries["index_price_tick"] = _ingest_frame(
                        df_it,
                        lake_root=lake_root,
                        dataset="index_price_tick",
                        trade_date=trade_date,
                        root=root,
                        symbol=symbol,
                        source_requests=[meta_it],
                        overwrite=overwrite,
                    )
                except Exception as idx_exc:
                    if index_resolution == "tick":
                        raise
                    log.warning("index tick optional fallback for %s: %s", trade_date, idx_exc)
                    resolutions.setdefault("index", "index_price_1s")

            sess_part = partition_dir(lake_root, "session_metadata", trade_date, root=root)
            if not is_partition_complete(sess_part):
                quote_label = quote_used or resolutions.get("quote", "unknown")
                df_sess = build_session_metadata_row(
                    trade_date=trade_date,
                    root=root,
                    symbol=symbol,
                    strike_range=strike_range,
                    window_start=ws,
                    window_end=we,
                    quote_interval=quote_label,
                    pilot_label="ml-p7.6-rth-ingest",
                    session_rth_start=session_rth_start,
                    session_rth_end=plan.session_rth_end,
                )
                summaries["session_metadata"] = _ingest_frame(
                    df_sess,
                    lake_root=lake_root,
                    dataset="session_metadata",
                    trade_date=trade_date,
                    root=root,
                    symbol=symbol,
                    source_requests=[],
                    overwrite=overwrite,
                )

            ingest_manifest = lake_root / f"ingest_manifest_{trade_date.isoformat()}.json"
            ingest_manifest.write_text(
                json.dumps(
                    {
                        "trade_date": trade_date.isoformat(),
                        "day_type": day_type,
                        "quote_resolution_used": quote_used,
                        "quote_fallback_reason": quote_fallback,
                        "resolutions_used": resolutions,
                        "api_request_count": api_count,
                        "partitions": summaries,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            return DateIngestResult(
                trade_date=trade_date,
                success=True,
                reason="ingest_complete",
                api_request_count=api_count,
                quote_resolution_used=quote_used,
                quote_fallback_reason=quote_fallback,
                resolutions_used=resolutions,
                ingest_wall_sec=time.perf_counter() - t0,
                partition_summaries=summaries,
            )
        except Exception as exc:
            last_error = exc
            log.warning("ingest attempt %d/%d failed for %s: %s", attempt + 1, max_retries + 1, trade_date, exc)
            if attempt < max_retries:
                time.sleep(1.0 * (attempt + 1))
                continue
            break

    return DateIngestResult(
        trade_date=trade_date,
        success=False,
        reason=f"ingest_failed:{type(last_error).__name__}:{last_error}",
        api_request_count=api_count,
        ingest_wall_sec=time.perf_counter() - t0,
    )
