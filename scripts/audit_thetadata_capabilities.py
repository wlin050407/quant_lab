"""Read-only ThetaData capability audit (ML-P1).

Probes a small, bounded set of API calls and writes a redacted JSON manifest.
Does not bulk-download history or write to ``data/raw/``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from quant_lab.data.thetadata_client import (
    DEFAULT_INDEX_SYMBOL,
    get_thetadata_client,
    resolve_credentials_file,
    resolve_email_password,
)

log = logging.getLogger(__name__)

AUDIT_VERSION = "ml-p1-1.0"
SUBSCRIPTION_LABEL = {0: "FREE", 1: "Value", 2: "Standard", 3: "Pro"}
DEFAULT_PROBE_TIME = "13:00:00"
DEFAULT_WINDOW_END = "13:02:00"
OPTION_ROOTS = ("SPXW", "SPX")
SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|api_key|authorization)",
    re.IGNORECASE,
)
SAFE_METADATA_KEYS = frozenset({"credential_source"})


@dataclass(frozen=True)
class AuditPlan:
    dates: tuple[date, ...]
    max_contracts: int
    max_rows: int
    max_requests: int
    per_date_calls: int
    global_calls: int
    total_calls: int
    window_start: str
    window_end: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dates": [d.isoformat() for d in self.dates],
            "max_contracts": self.max_contracts,
            "max_rows": self.max_rows,
            "max_requests": self.max_requests,
            "per_date_estimated_calls": self.per_date_calls,
            "global_estimated_calls": self.global_calls,
            "total_estimated_calls": self.total_calls,
            "quote_window": f"{self.window_start}–{self.window_end} ET",
            "trade_window": f"{DEFAULT_PROBE_TIME}–13:05:00 ET",
        }


@dataclass
class ProbeRecord:
    name: str
    status: Literal["ok", "empty", "error", "skipped", "dry_run"]
    detail: dict[str, Any] = field(default_factory=dict)


def _git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def redact_string(value: str) -> str:
    if "@" in value and not value.startswith("***"):
        local, _, domain = value.partition("@")
        head = local[:1] if local else "*"
        return f"{head}***@{domain}"
    if len(value) > 8:
        return value[:3] + "***" + value[-2:]
    return "***"


def redact_value(key: str, value: Any) -> Any:
    if key in SAFE_METADATA_KEYS:
        return value
    if SENSITIVE_KEY_RE.search(key):
        if value is None:
            return None
        return "***"
    if isinstance(value, str) and "@" in value:
        return redact_string(value)
    if isinstance(value, dict):
        return redact_manifest(value)
    if isinstance(value, list):
        return [redact_manifest(v) if isinstance(v, dict) else v for v in value]
    return value


def redact_manifest(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: redact_value(k, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_manifest(v) for v in obj]
    return obj


def reject_future_dates(dates: list[date], *, anchor: date | None = None) -> None:
    today = anchor or date.today()
    future = [d for d in dates if d > today]
    if future:
        raise ValueError(f"future dates not allowed for audit: {[d.isoformat() for d in future]}")


def default_test_dates(*, anchor: date | None = None) -> dict[str, date]:
    today = anchor or date.today()
    ordinary = today - timedelta(days=1)
    while ordinary.weekday() >= 5:
        ordinary -= timedelta(days=1)
    return {
        "ordinary_recent": ordinary,
        "monthly_expiration": date(2025, 5, 16),
        "early_close": date(2025, 7, 3),
        "high_volatility_event": date(2025, 4, 9),
        "near_historical_start": date(2022, 1, 3),
    }


def build_audit_plan(
    dates: list[date],
    *,
    max_contracts: int,
    max_rows: int,
    max_requests: int,
) -> AuditPlan:
    global_calls = 2 + len(OPTION_ROOTS) + len(OPTION_ROOTS)
    per_date_spxw = 4 + 2
    monthly_extra = 4 if any(d == date(2025, 5, 16) for d in dates) else 0
    error_calls = 3
    total = global_calls + per_date_spxw * len(dates) + monthly_extra + error_calls
    total = min(total, max_requests)
    return AuditPlan(
        dates=tuple(dates),
        max_contracts=max_contracts,
        max_rows=max_rows,
        max_requests=max_requests,
        per_date_calls=per_date_spxw,
        global_calls=global_calls,
        total_calls=total,
        window_start=DEFAULT_PROBE_TIME,
        window_end=DEFAULT_WINDOW_END,
    )


def summarize_dataframe(df: pd.DataFrame | None, *, max_rows: int) -> dict[str, Any]:
    if df is None:
        return {"row_count": 0, "columns": [], "sample": []}
    if not isinstance(df, pd.DataFrame):
        return {"row_count": 0, "columns": [], "sample": [], "note": "non-dataframe response"}
    clipped = df.head(max_rows).copy()
    cols: list[dict[str, Any]] = []
    for name in clipped.columns:
        dtype = str(clipped[name].dtype)
        null_rate = float(clipped[name].isna().mean()) if len(clipped) else 0.0
        cols.append({"name": name, "dtype": dtype, "null_rate_in_sample": null_rate})
    sample_rows: list[dict[str, Any]] = []
    for _, row in clipped.iterrows():
        item: dict[str, Any] = {}
        for k, v in row.items():
            if pd.isna(v):
                item[str(k)] = None
            elif isinstance(v, (pd.Timestamp, datetime)):
                item[str(k)] = pd.Timestamp(v).isoformat()
            elif isinstance(v, date):
                item[str(k)] = v.isoformat()
            else:
                item[str(k)] = v
        sample_rows.append(redact_manifest(item))
    ts_info: dict[str, Any] = {}
    if "timestamp" in clipped.columns and not clipped.empty:
        ts = pd.to_datetime(clipped["timestamp"])
        ts_info = {
            "min": pd.Timestamp(ts.min()).isoformat(),
            "max": pd.Timestamp(ts.max()).isoformat(),
            "timezone_inferred": str(ts.dt.tz) if ts.dt.tz else "naive",
            "monotonic_increasing": bool(ts.is_monotonic_increasing),
        }
    return {
        "row_count": int(len(df)),
        "columns": cols,
        "timestamp_summary": ts_info,
        "sample": sample_rows[:3],
    }


def _exc_record(exc: BaseException) -> dict[str, Any]:
    return {
        "exception_type": type(exc).__name__,
        "message": redact_string(str(exc))[:500],
    }


def _subscription_label(tier: int | None) -> str | None:
    if tier is None:
        return None
    return SUBSCRIPTION_LABEL.get(tier, f"tier_{tier}")


def _credential_source() -> str:
    if resolve_email_password() is not None:
        return "THETADATA_EMAIL+THETADATA_PASSWORD"
    creds = resolve_credentials_file()
    if creds is not None:
        return f"THETADATA_CREDENTIALS_FILE ({creds.name})"
    return "missing"


def _pick_contracts(contracts: pd.DataFrame, *, max_contracts: int) -> pd.DataFrame:
    if contracts.empty:
        return contracts
    work = contracts.copy()
    if "strike" in work.columns:
        work["strike"] = pd.to_numeric(work["strike"], errors="coerce")
        mid = work["strike"].median()
        work["_dist"] = (work["strike"] - mid).abs()
        work = work.sort_values("_dist")
    return work.head(max_contracts).drop(columns=["_dist"], errors="ignore")


def _roots_for_session(label: str) -> tuple[str, ...]:
    if label == "monthly_expiration":
        return OPTION_ROOTS
    return ("SPXW",)


def _record_dataframe_probe(
    manifest: dict[str, Any],
    section: str,
    bucket_key: str,
    root: str,
    df: pd.DataFrame | None,
    *,
    max_rows: int,
) -> None:
    if df is None:
        return
    summary = summarize_dataframe(df, max_rows=max_rows)
    manifest[section].setdefault(bucket_key, {})[root] = summary


class ThetaDataCapabilityAuditor:
    def __init__(
        self,
        *,
        dates: list[date],
        max_contracts: int,
        max_rows: int,
        max_requests: int,
        dry_run: bool,
    ) -> None:
        reject_future_dates(dates)
        self.dates = dates
        self.max_contracts = max_contracts
        self.max_rows = max_rows
        self.max_requests = max_requests
        self.dry_run = dry_run
        self.request_count = 0
        self.records: list[ProbeRecord] = []

    def _budget_ok(self) -> bool:
        return self.request_count < self.max_requests

    def _call(self, name: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if not self._budget_ok():
            self.records.append(
                ProbeRecord(name, "skipped", {"reason": "max_requests exhausted"})
            )
            return None
        if self.dry_run:
            self.records.append(ProbeRecord(name, "dry_run", {}))
            return None
        self.request_count += 1
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            log.debug("probe %s failed: %s", name, exc)
            self.records.append(ProbeRecord(name, "error", _exc_record(exc)))
            return None

    def run(self) -> dict[str, Any]:
        plan = build_audit_plan(
            self.dates,
            max_contracts=self.max_contracts,
            max_rows=self.max_rows,
            max_requests=self.max_requests,
        )
        manifest: dict[str, Any] = {
            "audit_version": AUDIT_VERSION,
            "run_timestamp": datetime.now(UTC).isoformat(),
            "git_commit": _git_commit(),
            "dry_run": self.dry_run,
            "account_entitlements": {},
            "client": {
                "library": "thetadata Python package (ThetaClient)",
                "transport": "gRPC to ThetaData cloud (v3 library)",
                "credential_source": _credential_source(),
            },
            "test_dates": dict(
                zip(self._date_labels(), [d.isoformat() for d in self.dates], strict=True)
            ),
            "request_budget": plan.to_dict(),
            "contract_discovery": {},
            "quotes": {},
            "trades": {},
            "greeks": {},
            "open_interest": {},
            "underlying": {},
            "realtime": {},
            "time_semantics": {},
            "limits": {"max_rows_applied": self.max_rows},
            "errors": {},
            "conclusions": {},
            "probes": [],
        }

        if self.dry_run:
            manifest["conclusions"] = {"dry_run_only": True, "ml_p2_allowed": False}
            return redact_manifest(manifest)

        try:
            client = get_thetadata_client(dataframe_type="pandas")
        except Exception as exc:
            manifest["client"]["auth_error"] = _exc_record(exc)
            manifest["conclusions"] = {"blocked": "authentication", "ml_p2_allowed": False}
            return redact_manifest(manifest)

        idx_tier = getattr(client, "indices_subscription", None)
        if idx_tier is None:
            idx_tier = getattr(client, "index_subscription", None)
        manifest["account_entitlements"] = {
            "options_subscription": _subscription_label(getattr(client, "options_subscription", None)),
            "indices_subscription": _subscription_label(idx_tier),
            "stock_subscription": _subscription_label(getattr(client, "stock_subscription", None)),
        }
        self._probe_global_discovery(client, manifest)
        for label, session in zip(self._date_labels(), self.dates, strict=True):
            self._probe_session(client, manifest, label=label, session=session)
        self._probe_error_cases(client, manifest)
        manifest["realtime"] = {
            "status": "not_tested",
            "reason": "ThetaClient exposes history/snapshot methods only; no streaming API in installed package.",
        }
        manifest["request_budget"]["actual_requests"] = self.request_count
        manifest["probes"] = [r.__dict__ for r in self.records]
        manifest["conclusions"] = self._build_conclusions(manifest)
        return redact_manifest(manifest)

    def _date_labels(self) -> list[str]:
        defaults = default_test_dates()
        inv = {v: k for k, v in defaults.items()}
        return [inv.get(d, "custom") for d in self.dates]

    def _probe_global_discovery(self, client: Any, manifest: dict[str, Any]) -> None:
        sym_df = self._call("option_list_symbols", client.option_list_symbols)
        if isinstance(sym_df, pd.DataFrame):
            symbols = sorted(sym_df.get("symbol", pd.Series(dtype=str)).astype(str).unique().tolist())
            manifest["contract_discovery"]["option_list_symbols"] = {
                "status": "ok",
                "count": len(symbols),
                "contains": {r: r in symbols for r in OPTION_ROOTS},
                "sample": symbols[:10],
            }
        idx_df = self._call("index_list_symbols", client.index_list_symbols)
        if isinstance(idx_df, pd.DataFrame):
            idx = sorted(idx_df.get("symbol", pd.Series(dtype=str)).astype(str).unique().tolist())
            manifest["contract_discovery"]["index_list_symbols"] = {
                "status": "ok",
                "contains_spx": DEFAULT_INDEX_SYMBOL in idx,
                "sample": idx[:10],
            }
        for root in OPTION_ROOTS:
            exp = self._call(f"option_list_expirations_{root}", client.option_list_expirations, root)
            if isinstance(exp, pd.DataFrame) and not exp.empty:
                col = "expiration" if "expiration" in exp.columns else exp.columns[0]
                exps = pd.to_datetime(exp[col]).dt.date.tolist()
                manifest["contract_discovery"].setdefault("expirations_by_root", {})[root] = {
                    "count": len(exps),
                    "min": min(exps).isoformat(),
                    "max": max(exps).isoformat(),
                    "sample": [d.isoformat() for d in exps[:5]],
                }
        if self.dates:
            sample_date = self.dates[0]
            for root in OPTION_ROOTS:
                contracts = self._call(
                    f"option_list_contracts_{root}_{sample_date.isoformat()}",
                    client.option_list_contracts,
                    "quote",
                    sample_date,
                    root,
                    1,
                )
                if isinstance(contracts, pd.DataFrame) and not contracts.empty:
                    manifest["contract_discovery"].setdefault("contracts_sample", {})[
                        f"sample_{sample_date.isoformat()}_{root}"
                    ] = summarize_dataframe(
                        _pick_contracts(contracts, max_contracts=self.max_contracts),
                        max_rows=self.max_rows,
                    )

    def _probe_session(
        self,
        client: Any,
        manifest: dict[str, Any],
        *,
        label: str,
        session: date,
    ) -> None:
        bucket_key = f"{label}_{session.isoformat()}"
        for root in _roots_for_session(label):
            if not self._budget_ok():
                break
            use_0dte = root == "SPXW" or label != "monthly_expiration"
            max_dte = 1 if use_0dte else None

            quote = self._call(
                f"option_history_quote_{root}_{session.isoformat()}",
                lambda r=root, md=max_dte: client.option_history_quote(
                    symbol=r,
                    expiration=session,
                    date=session,
                    interval="1m",
                    start_time=DEFAULT_PROBE_TIME,
                    end_time=DEFAULT_WINDOW_END,
                    strike="*",
                    right="both",
                    max_dte=md,
                    strike_range=self.max_contracts,
                ),
            )
            _record_dataframe_probe(
                manifest, "quotes", bucket_key, root, quote, max_rows=self.max_rows
            )

            trade = self._call(
                f"option_history_trade_{root}_{session.isoformat()}",
                lambda r=root, md=max_dte: client.option_history_trade(
                    symbol=r,
                    expiration=session,
                    date=session,
                    start_time=DEFAULT_PROBE_TIME,
                    end_time="13:05:00",
                    strike="*",
                    right="both",
                    max_dte=md,
                    strike_range=self.max_contracts,
                ),
            )
            _record_dataframe_probe(
                manifest, "trades", bucket_key, root, trade, max_rows=self.max_rows
            )

            oi = self._call(
                f"option_history_open_interest_{root}_{session.isoformat()}",
                lambda r=root, md=max_dte: client.option_history_open_interest(
                    symbol=r,
                    expiration=session,
                    date=session,
                    strike="*",
                    right="both",
                    max_dte=md,
                    strike_range=self.max_contracts,
                ),
            )
            _record_dataframe_probe(
                manifest, "open_interest", bucket_key, root, oi, max_rows=self.max_rows
            )

            greeks = self._call(
                f"option_history_greeks_first_order_{root}_{session.isoformat()}",
                lambda r=root: client.option_history_greeks_first_order(
                    r,
                    session,
                    interval="1m",
                    date=session,
                    strike="*",
                    right="both",
                    start_time=DEFAULT_PROBE_TIME,
                    end_time=DEFAULT_WINDOW_END,
                    strike_range=self.max_contracts,
                ),
            )
            _record_dataframe_probe(
                manifest, "greeks", bucket_key, root, greeks, max_rows=self.max_rows
            )

        spot = self._call(
            f"index_at_time_price_{session.isoformat()}",
            client.index_at_time_price,
            DEFAULT_INDEX_SYMBOL,
            session,
            session,
            DEFAULT_PROBE_TIME,
        )
        if isinstance(spot, pd.DataFrame):
            manifest["underlying"].setdefault(bucket_key, {})["index_at_time_price"] = summarize_dataframe(
                spot, max_rows=self.max_rows
            )

        idx_1m = self._call(
            f"index_history_price_1m_{session.isoformat()}",
            lambda: client.index_history_price(
                symbol=DEFAULT_INDEX_SYMBOL,
                date=session,
                interval="1m",
                start_time=DEFAULT_PROBE_TIME,
                end_time=DEFAULT_WINDOW_END,
            ),
        )
        if isinstance(idx_1m, pd.DataFrame):
            manifest["underlying"].setdefault(bucket_key, {})["index_history_price_1m"] = summarize_dataframe(
                idx_1m, max_rows=self.max_rows
            )

    def _probe_error_cases(self, client: Any, manifest: dict[str, Any]) -> None:
        future = date.today() + timedelta(days=30)
        self._call(
            "error_future_date_quote",
            lambda: client.option_history_quote(
                symbol="SPXW",
                expiration=future,
                date=future,
                interval="1m",
                start_time=DEFAULT_PROBE_TIME,
                end_time=DEFAULT_WINDOW_END,
                strike="*",
                right="C",
                max_dte=1,
            ),
        )
        self._call(
            "error_invalid_time_window",
            lambda: client.index_history_price(
                symbol=DEFAULT_INDEX_SYMBOL,
                date=self.dates[0],
                interval="1m",
                start_time="16:00:00",
                end_time="09:30:00",
            ),
        )
        self._call(
            "error_nonexistent_strike",
            lambda: client.option_history_quote(
                symbol="SPXW",
                expiration=self.dates[0],
                date=self.dates[0],
                interval="1m",
                start_time=DEFAULT_PROBE_TIME,
                end_time=DEFAULT_WINDOW_END,
                strike="99999",
                right="C",
                max_dte=1,
            ),
        )
        manifest["errors"] = {
            "probes_executed": ["future_date", "start_after_end", "nonexistent_strike"],
            "see_probes_array": True,
        }

    def _build_conclusions(self, manifest: dict[str, Any]) -> dict[str, Any]:
        dates_ok = sum(
            1
            for v in manifest.get("quotes", {}).values()
            if isinstance(v, dict)
            and any(isinstance(x, dict) and x.get("row_count", 0) > 0 for x in v.values())
        )
        underlying_ok = any(
            sess.get("index_at_time_price", {}).get("row_count", 0) > 0
            for sess in manifest.get("underlying", {}).values()
            if isinstance(sess, dict)
        )
        if underlying_ok:
            underlying_verdict = "B. 部分足够，但需要验证/补齐"
        else:
            underlying_verdict = "C. 不足，需要单独 index 数据源"
        return {
            "dates_with_quote_rows": dates_ok,
            "finest_reliable_resolution_observed": "1m in probes; library supports 1s interval parameter",
            "oi_timestamp_semantics": "需要 ThetaData 官方说明或支持确认",
            "underlying_verdict": underlying_verdict,
            "point_in_time_replay_feasible": dates_ok >= 2,
            "ml_p2_allowed": dates_ok >= 2,
            "nbbo_not_full_l2": True,
            "trade_side_is_execution_side_proxy_only": True,
        }


def parse_dates(raw: str | None) -> list[date]:
    if not raw:
        return list(default_test_dates().values())
    out = [date.fromisoformat(part.strip()) for part in raw.split(",") if part.strip()]
    reject_future_dates(out)
    return out


def print_plan_banner(plan: AuditPlan) -> None:
    print("=== ThetaData ML-P1 audit plan ===")
    print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
    print(f"预计请求数量: {plan.total_calls} (hard cap {plan.max_requests})")
    print(f"预计日期数量: {len(plan.dates)}")
    print(f"预计合约数量上限: {plan.max_contracts} per root per date")
    print(f"每次 quote/greek 窗口: {plan.window_start}–{plan.window_end} ET")
    print(f"最大返回行数 (manifest sample): {plan.max_rows}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", type=str, default=None)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--max-contracts", type=int, default=2)
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument("--max-requests", type=int, default=45)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/manifests/thetadata_capabilities.json"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)s %(name)s: %(message)s",
    )

    dates = [date.fromisoformat(args.date)] if args.date else parse_dates(args.dates)
    reject_future_dates(dates)

    plan = build_audit_plan(
        dates,
        max_contracts=args.max_contracts,
        max_rows=args.max_rows,
        max_requests=args.max_requests,
    )
    print_plan_banner(plan)

    auditor = ThetaDataCapabilityAuditor(
        dates=dates,
        max_contracts=args.max_contracts,
        max_rows=args.max_rows,
        max_requests=args.max_requests,
        dry_run=args.dry_run,
    )
    manifest = auditor.run()

    if args.dry_run:
        print("DRY RUN — no network requests executed.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote redacted manifest → {args.output}")
    print(f"Actual requests: {auditor.request_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
