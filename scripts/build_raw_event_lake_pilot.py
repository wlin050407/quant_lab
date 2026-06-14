"""Build minimal raw event lake pilot partition (ML-P3, bounded network)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402

from quant_lab.data.intraday_lake import (  # noqa: E402
    PILOT_LAKE_ROOT,
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
from quant_lab.data.intraday_manifest import SourceRequestMeta  # noqa: E402
from quant_lab.data.thetadata_client import (  # noqa: E402
    DEFAULT_INDEX_SYMBOL,
    DEFAULT_OPTION_ROOT,
    refresh_thetadata_client,
)

log = logging.getLogger(__name__)

PILOT_VERSION = "ml-p3-pilot-1.0"
DEFAULT_TRADE_DATE = date(2026, 6, 10)
DEFAULT_WINDOW_START = "13:00:00"
DEFAULT_WINDOW_END = "13:02:00"


@dataclass(frozen=True)
class PilotPlan:
    trade_date: date
    root: str
    symbol: str
    strike_range: int
    window_start: str
    window_end: str
    lake_root: Path
    estimated_api_calls: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pilot_version": PILOT_VERSION,
            "trade_date": self.trade_date.isoformat(),
            "root": self.root,
            "symbol": self.symbol,
            "strike_range": self.strike_range,
            "window": f"{self.window_start}–{self.window_end} ET",
            "lake_root": str(self.lake_root),
            "estimated_api_calls": self.estimated_api_calls,
        }


def build_plan(
    *,
    trade_date: date,
    strike_range: int,
    lake_root: Path,
) -> PilotPlan:
    return PilotPlan(
        trade_date=trade_date,
        root=DEFAULT_OPTION_ROOT,
        symbol=DEFAULT_INDEX_SYMBOL,
        strike_range=strike_range,
        window_start=DEFAULT_WINDOW_START,
        window_end=DEFAULT_WINDOW_END,
        lake_root=lake_root,
        estimated_api_calls=7,
    )


def _source_meta(endpoint: str, params: dict[str, Any]) -> SourceRequestMeta:
    return SourceRequestMeta(
        endpoint=endpoint,
        request_id=make_source_request_id(endpoint, params),
        params_redacted=params,
    )


def run_pilot(
    plan: PilotPlan,
    *,
    dry_run: bool,
    overwrite: bool,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "plan": plan.to_dict(),
        "dry_run": dry_run,
        "datasets": {},
    }
    if dry_run:
        for ds in (
            "option_quote_1s",
            "option_quote_tick",
            "option_trade_tick",
            "option_greeks_1m_first_order",
            "derived_gamma_black76_1m",
            "option_open_interest",
            "index_price_1s",
            "index_price_tick",
            "session_metadata",
        ):
            summary["datasets"][ds] = {
                "partition": str(
                    partition_dir(
                        plan.lake_root,
                        ds,
                        plan.trade_date,
                        root=plan.root,
                        symbol=plan.symbol,
                        expiration=plan.trade_date,
                    )
                )
            }
        return summary

    client = refresh_thetadata_client()
    session = plan.trade_date
    root = plan.root
    sr = plan.strike_range
    ws, we = plan.window_start, plan.window_end
    common = {
        "symbol": root,
        "expiration": session,
        "date": session,
        "max_dte": 1,
        "strike_range": sr,
    }

    def fetch_quote(interval: str) -> pd.DataFrame:
        return client.option_history_quote(
            interval=interval,
            start_time=ws,
            end_time=we,
            strike="*",
            right="both",
            **common,
        )

    quote_1s_raw = fetch_quote("1s")
    quote_tick_raw = fetch_quote("tick")
    trades_raw = client.option_history_trade(
        symbol=root,
        expiration=session,
        date=session,
        start_time=ws,
        end_time=we,
        strike="*",
        right="both",
        max_dte=1,
        strike_range=sr,
    )
    greeks_raw = client.option_history_greeks_first_order(
        root,
        session,
        interval="1m",
        date=session,
        strike="*",
        right="both",
        start_time=ws,
        end_time=we,
        strike_range=sr,
    )
    oi_raw = client.option_history_open_interest(
        symbol=root,
        expiration=session,
        date=session,
        strike="*",
        right="both",
        max_dte=1,
        strike_range=sr,
    )
    index_1s_raw = client.index_history_price(
        symbol=plan.symbol,
        interval="1s",
        date=session,
        start_time=ws,
        end_time=we,
    )
    index_tick_raw = client.index_history_price(
        symbol=plan.symbol,
        interval="tick",
        date=session,
        start_time=ws,
        end_time=we,
    )

    ingest_specs: list[tuple[str, pd.DataFrame, dict[str, Any]]] = []

    q1_params = {**common, "interval": "1s", "start_time": ws, "end_time": we}
    meta_q1 = _source_meta("option_history_quote", q1_params)
    df_q1 = normalize_option_quote(
        quote_1s_raw,
        dataset="option_quote_1s",
        root=root,
        trade_date=session,
        source_endpoint="option_history_quote",
        source_request_id=meta_q1.request_id,
    )
    ingest_specs.append(("option_quote_1s", df_q1, {"source_requests": [meta_q1]}))

    qtick_params = {**common, "interval": "tick", "start_time": ws, "end_time": we}
    meta_qt = _source_meta("option_history_quote", qtick_params)
    df_qt = normalize_option_quote(
        quote_tick_raw,
        dataset="option_quote_tick",
        root=root,
        trade_date=session,
        source_endpoint="option_history_quote",
        source_request_id=meta_qt.request_id,
    )
    ingest_specs.append(("option_quote_tick", df_qt, {"source_requests": [meta_qt]}))

    tr_params = {**common, "start_time": ws, "end_time": we}
    meta_tr = _source_meta("option_history_trade", tr_params)
    df_tr = normalize_option_trade(
        trades_raw,
        root=root,
        trade_date=session,
        source_endpoint="option_history_trade",
        source_request_id=meta_tr.request_id,
    )
    ingest_specs.append(("option_trade_tick", df_tr, {"source_requests": [meta_tr]}))

    g_params = {**common, "interval": "1m", "start_time": ws, "end_time": we}
    meta_g = _source_meta("option_history_greeks_first_order", g_params)
    df_g = normalize_option_greeks(
        greeks_raw,
        root=root,
        trade_date=session,
        source_endpoint="option_history_greeks_first_order",
        source_request_id=meta_g.request_id,
    )
    ingest_specs.append(
        ("option_greeks_1m_first_order", df_g, {"source_requests": [meta_g]})
    )

    df_gamma = build_derived_gamma_black76(df_g, trade_date=session, root=root)
    ingest_specs.append(("derived_gamma_black76_1m", df_gamma, {"source_requests": []}))

    oi_params = {**common}
    meta_oi = _source_meta("option_history_open_interest", oi_params)
    df_oi = normalize_option_open_interest(
        oi_raw,
        root=root,
        trade_date=session,
        requested_date=session,
        source_endpoint="option_history_open_interest",
        source_request_id=meta_oi.request_id,
    )
    ingest_specs.append(("option_open_interest", df_oi, {"source_requests": [meta_oi]}))

    idx1_params = {"symbol": plan.symbol, "interval": "1s", "date": session, "start_time": ws, "end_time": we}
    meta_i1 = _source_meta("index_history_price", idx1_params)
    df_i1 = normalize_index_price(
        index_1s_raw,
        dataset="index_price_1s",
        symbol=plan.symbol,
        trade_date=session,
        source_endpoint="index_history_price",
        source_request_id=meta_i1.request_id,
    )
    ingest_specs.append(
        (
            "index_price_1s",
            df_i1,
            {"source_requests": [meta_i1], "symbol": plan.symbol, "expiration": None},
        )
    )

    idxt_params = {"symbol": plan.symbol, "interval": "tick", "date": session, "start_time": ws, "end_time": we}
    meta_it = _source_meta("index_history_price", idxt_params)
    df_it = normalize_index_price(
        index_tick_raw,
        dataset="index_price_tick",
        symbol=plan.symbol,
        trade_date=session,
        source_endpoint="index_history_price",
        source_request_id=meta_it.request_id,
    )
    ingest_specs.append(
        (
            "index_price_tick",
            df_it,
            {"source_requests": [meta_it], "symbol": plan.symbol, "expiration": None},
        )
    )

    df_sess = build_session_metadata_row(
        trade_date=session,
        root=root,
        symbol=plan.symbol,
        strike_range=sr,
        window_start=ws,
        window_end=we,
        quote_interval="1s+tick",
        pilot_label="ml-p3-pilot",
    )
    ingest_specs.append(
        (
            "session_metadata",
            df_sess,
            {"source_requests": []},
        )
    )

    for dataset, frame, kwargs in ingest_specs:
        is_index = dataset.startswith("index_")
        is_session = dataset == "session_metadata"
        result = ingest_partition(
            frame,
            lake_root=plan.lake_root,
            dataset=dataset,
            trade_date=session,
            root=root if not is_index else None,
            symbol=plan.symbol if is_index else None,
            expiration=None if (is_index or is_session) else session,
            source_requests=kwargs.get("source_requests"),
            overwrite=overwrite,
        )
        summary["datasets"][dataset] = {
            "partition_dir": str(result.partition_dir),
            "row_count": result.row_count,
            "skipped": result.skipped,
            "manifest": str(result.manifest_path),
            "duplicate_ratio": (
                result.duplicate_report.duplicate_ratio if result.duplicate_report else None
            ),
            "out_of_order_ratio": (
                result.out_of_order_report.out_of_order_ratio
                if result.out_of_order_report
                else None
            ),
        }

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=str, default=DEFAULT_TRADE_DATE.isoformat())
    parser.add_argument("--strike-range", type=int, default=2)
    parser.add_argument("--lake-root", type=Path, default=PILOT_LAKE_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/manifests/raw_lake_pilot_summary.json"),
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    trade_date = date.fromisoformat(args.date)
    plan = build_plan(
        trade_date=trade_date,
        strike_range=args.strike_range,
        lake_root=args.lake_root,
    )
    print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
    summary = run_pilot(plan, dry_run=args.dry_run, overwrite=args.overwrite)
    if not args.dry_run:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote summary → {args.report}")
    else:
        print("DRY RUN — no network / no writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
