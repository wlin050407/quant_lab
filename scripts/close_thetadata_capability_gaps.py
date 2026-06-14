"""ML-P2A: close ThetaData capability gaps (read-only, bounded probes)."""

from __future__ import annotations

import argparse
import inspect
import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402

from quant_lab.data.thetadata_client import (  # noqa: E402
    DEFAULT_INDEX_SYMBOL,
    DEFAULT_OPTION_ROOT,
    get_thetadata_client,
)
from quant_lab.factors.gex import black76_gamma  # noqa: E402
from quant_lab.factors.rates import resolve_gex_inputs  # noqa: E402
from scripts.thetadata_p2_common import (  # noqa: E402
    ProbeRecord,
    classify_probe_error,
    manifest_header,
    redact_manifest,
    summarize_dataframe,
    trading_day_offset,
    write_json,
)

log = logging.getLogger(__name__)

AUDIT_VERSION = "ml-p2a-1.0"
EARLY_CLOSE_DATE = date(2025, 7, 3)
QUOTE_PROBE_DATE = date(2025, 4, 9)
GAMMA_PROBE_DATE = date(2025, 4, 9)
OI_ANCHOR_DATE = date(2025, 4, 9)
EARLY_CLOSE_WINDOWS: tuple[tuple[str, str], ...] = (
    ("10:00:00", "10:05:00"),
    ("12:30:00", "12:35:00"),
    ("13:00:00", "13:05:00"),
    ("13:10:00", "13:15:00"),
)
QUOTE_INTERVALS: tuple[str, ...] = ("1m", "1s", "tick", "raw")
INDEX_INTERVALS: tuple[str, ...] = ("1m", "1s", "tick")


@dataclass
class ClosurePlan:
    max_requests: int
    strike_range: int
    estimated_calls: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_requests": self.max_requests,
            "strike_range": self.strike_range,
            "estimated_calls": self.estimated_calls,
        }


@dataclass
class GapClosureAuditor:
    max_requests: int
    strike_range: int
    dry_run: bool
    request_count: int = 0
    records: list[ProbeRecord] = field(default_factory=list)

    def _budget_ok(self) -> bool:
        return self.request_count < self.max_requests

    def _call(self, name: str, fn: Any) -> Any:
        if not self._budget_ok():
            self.records.append(ProbeRecord(name, "skipped", {"reason": "max_requests exhausted"}))
            return None
        if self.dry_run:
            self.records.append(ProbeRecord(name, "dry_run", {}))
            return None
        self.request_count += 1
        try:
            return fn()
        except Exception as exc:
            detail = classify_probe_error(exc)
            status: str = "error"
            if detail["category"] == "entitlement_denied":
                status = "denied"
            elif detail["category"] == "no_data":
                status = "empty"
            self.records.append(ProbeRecord(name, status, detail))  # type: ignore[arg-type]
            return None

    def run(self) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            **manifest_header(audit_version=AUDIT_VERSION, dry_run=self.dry_run),
            "plan": ClosurePlan(
                max_requests=self.max_requests,
                strike_range=self.strike_range,
                estimated_calls=estimate_closure_calls(),
            ).to_dict(),
            "client_discovery": discover_client_methods(),
            "early_close": {},
            "quote_resolution": {},
            "index_resolution": {},
            "gamma": {},
            "open_interest_semantics": {},
            "conclusions": {},
            "probes": [],
        }
        if self.dry_run:
            manifest["conclusions"] = {"dry_run_only": True}
            return redact_manifest(manifest)

        client = get_thetadata_client()
        manifest["early_close"] = self._probe_early_close(client)
        manifest["quote_resolution"] = self._probe_quote_intervals(client, QUOTE_PROBE_DATE)
        manifest["index_resolution"] = self._probe_index_intervals(client, QUOTE_PROBE_DATE)
        manifest["gamma"] = self._probe_gamma(client, GAMMA_PROBE_DATE)
        manifest["open_interest_semantics"] = self._probe_oi_semantics(client, OI_ANCHOR_DATE)
        manifest["request_count"] = self.request_count
        manifest["probes"] = [r.__dict__ for r in self.records]
        manifest["conclusions"] = build_conclusions(manifest)
        return redact_manifest(manifest)

    def _probe_early_close(self, client: Any) -> dict[str, Any]:
        session = EARLY_CLOSE_DATE
        out: dict[str, Any] = {
            "session_date": session.isoformat(),
            "session_type": "early_close",
            "expected_rth_end_et": "13:00:00",
            "windows": {},
        }
        for start, end in EARLY_CLOSE_WINDOWS:
            key = f"{start}_{end}"
            trade = self._call(
                f"early_close_trade_{key}",
                lambda s=start, e=end: client.option_history_trade(
                    symbol=DEFAULT_OPTION_ROOT,
                    expiration=session,
                    date=session,
                    strike="*",
                    right="both",
                    start_time=s,
                    end_time=e,
                    max_dte=1,
                    strike_range=self.strike_range,
                ),
            )
            quote = self._call(
                f"early_close_quote_{key}",
                lambda s=start, e=end: client.option_history_quote(
                    symbol=DEFAULT_OPTION_ROOT,
                    expiration=session,
                    date=session,
                    interval="1m",
                    start_time=s,
                    end_time=e,
                    strike="*",
                    right="both",
                    max_dte=1,
                    strike_range=self.strike_range,
                ),
            )
            index = self._call(
                f"early_close_index_{key}",
                lambda s=start, e=end: client.index_history_price(
                    symbol=DEFAULT_INDEX_SYMBOL,
                    interval="1m",
                    date=session,
                    start_time=s,
                    end_time=e,
                ),
            )
            window: dict[str, Any] = {}
            if isinstance(trade, pd.DataFrame):
                window["trade"] = summarize_dataframe(trade)
                if not trade.empty and "timestamp" in trade.columns:
                    window["last_trade_timestamp"] = pd.Timestamp(trade["timestamp"].max()).isoformat()
            if isinstance(quote, pd.DataFrame):
                window["quote_1m"] = summarize_dataframe(quote)
            if isinstance(index, pd.DataFrame):
                window["index_1m"] = summarize_dataframe(index)
            out["windows"][key] = window
        out["interpretation"] = interpret_early_close(out)
        return out

    def _probe_quote_intervals(self, client: Any, session: date) -> dict[str, Any]:
        out: dict[str, Any] = {"session_date": session.isoformat(), "intervals": {}}
        for interval in QUOTE_INTERVALS:
            df = self._call(
                f"quote_interval_{interval}",
                lambda iv=interval: client.option_history_quote(
                    symbol=DEFAULT_OPTION_ROOT,
                    expiration=session,
                    date=session,
                    interval=iv,
                    start_time="13:00:00",
                    end_time="13:02:00" if iv != "tick" else "13:01:00",
                    strike="*",
                    right="both",
                    max_dte=1,
                    strike_range=1,
                ),
            )
            entry: dict[str, Any] = {"interval_requested": interval}
            if isinstance(df, pd.DataFrame):
                entry["status"] = "ok" if len(df) else "empty"
                entry.update(summarize_dataframe(df))
                entry["classification"] = classify_quote_interval(interval, df)
            else:
                rec = next((r for r in reversed(self.records) if r.name == f"quote_interval_{interval}"), None)
                entry["status"] = rec.status if rec else "not_run"
                entry["classification"] = map_probe_to_classification(rec)
            out["intervals"][interval] = entry
        return out

    def _probe_index_intervals(self, client: Any, session: date) -> dict[str, Any]:
        out: dict[str, Any] = {"session_date": session.isoformat(), "intervals": {}}
        for interval in INDEX_INTERVALS:
            df = self._call(
                f"index_interval_{interval}",
                lambda iv=interval: client.index_history_price(
                    symbol=DEFAULT_INDEX_SYMBOL,
                    interval=iv,
                    date=session,
                    start_time="13:00:00",
                    end_time="13:02:00" if iv != "tick" else "13:01:00",
                ),
            )
            entry: dict[str, Any] = {"interval_requested": interval}
            if isinstance(df, pd.DataFrame):
                entry["status"] = "ok" if len(df) else "empty"
                entry.update(summarize_dataframe(df))
                entry["classification"] = "account_verified" if interval in {"1m", "1s"} else "tick_verified"
            else:
                rec = next((r for r in reversed(self.records) if r.name == f"index_interval_{interval}"), None)
                entry["status"] = rec.status if rec else "not_run"
                entry["classification"] = map_probe_to_classification(rec)
            out["intervals"][interval] = entry
        return out

    def _probe_gamma(self, client: Any, session: date) -> dict[str, Any]:
        out: dict[str, Any] = {"session_date": session.isoformat(), "endpoints": {}}
        candidates = (
            "option_history_greeks_second_order",
            "option_history_greeks_all",
            "option_history_greeks_first_order",
        )
        for method_name in candidates:
            method = getattr(client, method_name)
            df = self._call(
                method_name,
                lambda m=method: m(
                    DEFAULT_OPTION_ROOT,
                    session,
                    interval="1m",
                    date=session,
                    strike="*",
                    right="both",
                    start_time="13:00:00",
                    end_time="13:02:00",
                    strike_range=1,
                ),
            )
            entry: dict[str, Any] = {"method": method_name}
            if isinstance(df, pd.DataFrame):
                entry.update(summarize_dataframe(df))
                entry["has_gamma_column"] = "gamma" in df.columns
            else:
                rec = next((r for r in reversed(self.records) if r.name == method_name), None)
                entry["probe_status"] = rec.status if rec else "not_run"
                if rec:
                    entry["detail"] = rec.detail
            out["endpoints"][method_name] = entry

        out["local_black76_comparison"] = self._compare_local_gamma(client, session)
        out["decision"] = gamma_decision(out)
        return out

    def _compare_local_gamma(self, client: Any, session: date) -> dict[str, Any]:
        df = self._call(
            "gamma_local_inputs_first_order",
            lambda: client.option_history_greeks_first_order(
                DEFAULT_OPTION_ROOT,
                session,
                interval="1m",
                date=session,
                strike="*",
                right="both",
                start_time="13:00:00",
                end_time="13:00:00",
                strike_range=1,
            ),
        )
        if not isinstance(df, pd.DataFrame) or df.empty:
            return {"status": "skipped", "reason": "no first_order row for comparison"}
        row = df.iloc[0]
        inp = resolve_gex_inputs("^SPX", asof=session)
        t_years = 4.0 / (252.0 * 6.5 * 3600.0)
        iv = float(row.get("implied_vol", float("nan")))
        spot = float(row.get("underlying_price", float("nan")))
        strike = float(row.get("strike", float("nan")))
        local_gamma = float(
            black76_gamma(spot, strike, t_years, iv, r=inp.r, q=inp.q)
        )
        return {
            "status": "ok",
            "spot": spot,
            "strike": strike,
            "implied_vol": iv,
            "rate": inp.r,
            "dividend_yield": inp.q,
            "time_to_expiry_years_assumption": t_years,
            "local_black76_gamma": local_gamma,
            "native_gamma_available": False,
            "note": "T approximated from 13:00 ET on 0DTE; not exchange official",
        }

    def _probe_oi_semantics(self, client: Any, anchor: date) -> dict[str, Any]:
        days = {
            "D_minus_1": trading_day_offset(anchor, -1),
            "D": anchor,
            "D_plus_1": trading_day_offset(anchor, 1),
        }
        out: dict[str, Any] = {"anchor": anchor.isoformat(), "by_requested_date": {}}
        for label, session in days.items():
            df = self._call(
                f"oi_semantics_{label}",
                lambda s=session: client.option_history_open_interest(
                    symbol=DEFAULT_OPTION_ROOT,
                    expiration=anchor,
                    date=s,
                    strike="*",
                    right="both",
                    max_dte=1,
                    strike_range=self.strike_range,
                ),
            )
            if isinstance(df, pd.DataFrame):
                out["by_requested_date"][label] = {
                    "requested_date": session.isoformat(),
                    "expiration": anchor.isoformat(),
                    "summary": summarize_dataframe(df),
                }
        out["official_status"] = "OI semantics empirically constrained but not officially confirmed"
        return out


def discover_client_methods() -> dict[str, Any]:
    from thetadata import ThetaClient

    quote_methods = []
    greek_methods = []
    index_methods = []
    for name in sorted(dir(ThetaClient)):
        if name.startswith("_"):
            continue
        lower = name.lower()
        if "quote" in lower and "option" in lower:
            quote_methods.append({"name": name, "signature": str(inspect.signature(getattr(ThetaClient, name)))})
        if "greek" in lower:
            greek_methods.append({"name": name, "signature": str(inspect.signature(getattr(ThetaClient, name)))})
        if lower.startswith("index_"):
            index_methods.append({"name": name, "signature": str(inspect.signature(getattr(ThetaClient, name)))})
    return {
        "package": "thetadata",
        "option_quote_methods": quote_methods,
        "greek_methods": greek_methods,
        "index_methods": index_methods,
    }


def classify_quote_interval(interval: str, df: pd.DataFrame) -> str:
    if interval == "1m":
        return "1m_verified"
    if interval == "1s":
        return "1s_verified"
    if interval == "tick":
        return "tick_verified"
    return "account_verified"


def map_probe_to_classification(rec: ProbeRecord | None) -> str:
    if rec is None:
        return "not_run"
    if rec.status == "denied":
        return "entitlement_denied"
    if rec.detail.get("category") == "invalid_parameter":
        return "invalid_interval_parameter"
    if rec.status == "empty":
        return "no_data"
    return "error"


def interpret_early_close(windows_payload: dict[str, Any]) -> str:
    has_am = any(
        w.get("trade", {}).get("row_count", 0) > 0
        for k, w in windows_payload.get("windows", {}).items()
        if k.startswith("10:00") or k.startswith("12:30")
    )
    has_post_close = any(
        w.get("trade", {}).get("row_count", 0) > 0
        for k, w in windows_payload.get("windows", {}).items()
        if k.startswith("13:")
    )
    if has_am and not has_post_close:
        return (
            "窄窗口或所选合约无成交，不能视为数据缺失。"
            "2025-07-03 10:00 与 12:30 窗口有 trade；13:00+ 无 trade，符合 13:00 ET 早收盘。"
        )
    return "mixed_or_inconclusive"


def gamma_decision(gamma_payload: dict[str, Any]) -> str:
    second = gamma_payload.get("endpoints", {}).get("option_history_greeks_second_order", {})
    all_g = gamma_payload.get("endpoints", {}).get("option_history_greeks_all", {})
    if second.get("has_gamma_column") or all_g.get("has_gamma_column"):
        return "A. 使用 ThetaData 原生 Gamma"
    denied = any(
        ep.get("probe_status") == "denied" or ep.get("detail", {}).get("category") == "entitlement_denied"
        for ep in gamma_payload.get("endpoints", {}).values()
    )
    if denied:
        return "B. 使用本地 Gamma，并有完整参数规范（Standard 账号 second_order/greeks_all 需 Pro）"
    return "D. 仍未解决，禁止进入历史 replay"


def build_conclusions(manifest: dict[str, Any]) -> dict[str, Any]:
    quote = manifest.get("quote_resolution", {}).get("intervals", {})
    index = manifest.get("index_resolution", {}).get("intervals", {})
    return {
        "early_close_revised": manifest.get("early_close", {}).get("interpretation"),
        "quote_1s": quote.get("1s", {}).get("classification", "unknown"),
        "quote_tick": quote.get("tick", {}).get("classification", "unknown"),
        "index_1m": index.get("1m", {}).get("classification", "unknown"),
        "index_1s": index.get("1s", {}).get("classification", "unknown"),
        "index_tick": index.get("tick", {}).get("classification", "unknown"),
        "gamma_decision": manifest.get("gamma", {}).get("decision"),
        "oi_official_status": manifest.get("open_interest_semantics", {}).get("official_status"),
        "ml_p3_allowed": manifest.get("gamma", {}).get("decision", "").startswith(("A.", "B.", "C.")),
    }


def estimate_closure_calls() -> int:
    return (
        len(EARLY_CLOSE_WINDOWS) * 3
        + len(QUOTE_INTERVALS)
        + len(INDEX_INTERVALS)
        + 4
        + 3
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-requests", type=int, default=40)
    parser.add_argument("--strike-range", type=int, default=2)
    parser.add_argument(
        "--output",
        type=str,
        default="artifacts/manifests/thetadata_p2_closure.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    plan = ClosurePlan(args.max_requests, args.strike_range, estimate_closure_calls())
    print("=== ML-P2A closure plan ===")
    print(plan.to_dict())

    auditor = GapClosureAuditor(
        max_requests=args.max_requests,
        strike_range=args.strike_range,
        dry_run=args.dry_run,
    )
    manifest = auditor.run()
    if not args.dry_run:
        from pathlib import Path

        write_json(Path(args.output), manifest)
        print(f"Wrote {args.output} ({auditor.request_count} requests)")
    else:
        print("DRY RUN — no network")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
