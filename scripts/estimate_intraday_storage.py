"""ML-P2B: single-day intraday storage and throughput pilot (artifacts/ only)."""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from quant_lab.data.thetadata_client import (  # noqa: E402
    DEFAULT_INDEX_SYMBOL,
    DEFAULT_OPTION_ROOT,
    get_thetadata_client,
)
from scripts.thetadata_p2_common import manifest_header, redact_manifest, write_json  # noqa: E402

log = logging.getLogger(__name__)

AUDIT_VERSION = "ml-p2b-1.0"
DEFAULT_ORDINARY_DATE = date(2026, 6, 10)
DEFAULT_HIGH_VOL_DATE = date(2025, 4, 9)
RTH_START = "09:30:00"
RTH_END = "16:00:00"
STRIKE_UNIVERSE_LABELS: tuple[tuple[str, int], ...] = (
    ("spot_pm_0p5_em_proxy", 15),
    ("spot_pm_1p0_em_proxy", 30),
    ("spot_pm_2p0_em_proxy", 60),
)
ZSTD_LEVELS: tuple[int, ...] = (3, 6)


@dataclass
class PilotMetrics:
    api_requests: int = 0
    download_wall_s: float = 0.0
    normalize_wall_s: float = 0.0
    write_wall_s: float = 0.0
    read_wall_s: float = 0.0
    row_counts: dict[str, int] = field(default_factory=dict)
    parquet_bytes: dict[str, int] = field(default_factory=dict)
    memory_bytes: dict[str, int] = field(default_factory=dict)


@dataclass
class DayPilot:
    session_date: date
    label: str
    strike_range: int
    quote_interval: str
    greek_interval: str
    index_interval: str
    output_root: Path
    dry_run: bool
    metrics: PilotMetrics = field(default_factory=PilotMetrics)

    def run(self) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            **manifest_header(audit_version=AUDIT_VERSION, dry_run=self.dry_run),
            "session_date": self.session_date.isoformat(),
            "label": self.label,
            "strike_range": self.strike_range,
            "quote_interval": self.quote_interval,
            "greek_interval": self.greek_interval,
            "index_interval": self.index_interval,
            "rth": {"start": RTH_START, "end": RTH_END},
            "strike_universe_note": (
                "EM bands approximated via strike_range proxy until point-in-time EM is stable"
            ),
            "datasets": {},
            "compression": {},
            "quality": {},
        }
        if self.dry_run:
            manifest["dry_run_plan"] = self._dry_run_plan()
            return redact_manifest(manifest)

        client = get_thetadata_client()
        t0 = time.perf_counter()
        datasets = self._download_all(client)
        self.metrics.download_wall_s = time.perf_counter() - t0

        t1 = time.perf_counter()
        normalized = {k: self._normalize(k, v) for k, v in datasets.items() if v is not None}
        self.metrics.normalize_wall_s = time.perf_counter() - t1

        t2 = time.perf_counter()
        paths = self._write_parquet(normalized)
        self.metrics.write_wall_s = time.perf_counter() - t2

        t3 = time.perf_counter()
        read_stats = self._read_back(paths)
        self.metrics.read_wall_s = time.perf_counter() - t3

        manifest["datasets"] = {
            name: {
                "rows": self.metrics.row_counts.get(name, 0),
                "path": str(paths[name]) if name in paths else None,
                "parquet_bytes": self.metrics.parquet_bytes.get(name),
                "memory_bytes": self.metrics.memory_bytes.get(name),
            }
            for name in normalized
        }
        manifest["compression"] = self._compression_experiment(normalized)
        manifest["quality"] = self._quality_stats(normalized)
        manifest["em_band_subsets"] = self._em_band_subsets(normalized)
        manifest["timing"] = {
            "api_requests": self.metrics.api_requests,
            "download_wall_s": round(self.metrics.download_wall_s, 3),
            "normalize_wall_s": round(self.metrics.normalize_wall_s, 3),
            "write_wall_s": round(self.metrics.write_wall_s, 3),
            "read_wall_s": round(self.metrics.read_wall_s, 3),
        }
        manifest["read_back"] = read_stats
        return redact_manifest(manifest)

    def _dry_run_plan(self) -> dict[str, Any]:
        return {
            "api_calls": [
                "index_history_price",
                "option_history_quote",
                "option_history_trade",
                "option_history_greeks_first_order",
                "option_history_open_interest",
            ],
            "strike_range": self.strike_range,
            "session_hours": f"{RTH_START}-{RTH_END} ET",
        }

    def _download_all(self, client: Any) -> dict[str, pd.DataFrame | None]:
        session = self.session_date
        sr = self.strike_range
        out: dict[str, pd.DataFrame | None] = {}

        out["index"] = self._fetch(
            "index",
            lambda: client.index_history_price(
                symbol=DEFAULT_INDEX_SYMBOL,
                interval=self.index_interval,
                date=session,
                start_time=RTH_START,
                end_time=RTH_END,
            ),
        )
        out["quotes"] = self._fetch(
            "quotes",
            lambda: client.option_history_quote(
                symbol=DEFAULT_OPTION_ROOT,
                expiration=session,
                date=session,
                interval=self.quote_interval,
                start_time=RTH_START,
                end_time=RTH_END,
                strike="*",
                right="both",
                max_dte=1,
                strike_range=sr,
            ),
        )
        out["trades"] = self._fetch(
            "trades",
            lambda: client.option_history_trade(
                symbol=DEFAULT_OPTION_ROOT,
                expiration=session,
                date=session,
                start_time=RTH_START,
                end_time=RTH_END,
                strike="*",
                right="both",
                max_dte=1,
                strike_range=sr,
            ),
        )
        out["greeks"] = self._fetch(
            "greeks",
            lambda: client.option_history_greeks_first_order(
                DEFAULT_OPTION_ROOT,
                session,
                interval=self.greek_interval,
                date=session,
                strike="*",
                right="both",
                start_time=RTH_START,
                end_time=RTH_END,
                strike_range=sr,
            ),
        )
        out["open_interest"] = self._fetch(
            "open_interest",
            lambda: client.option_history_open_interest(
                symbol=DEFAULT_OPTION_ROOT,
                expiration=session,
                date=session,
                strike="*",
                right="both",
                max_dte=1,
                strike_range=sr,
            ),
        )
        meta = pd.DataFrame(
            [
                {
                    "session_date": session.isoformat(),
                    "option_root": DEFAULT_OPTION_ROOT,
                    "index_symbol": DEFAULT_INDEX_SYMBOL,
                    "rth_start": RTH_START,
                    "rth_end": RTH_END,
                    "strike_range": sr,
                    "quote_interval": self.quote_interval,
                    "greek_interval": self.greek_interval,
                    "index_interval": self.index_interval,
                    "label": self.label,
                }
            ]
        )
        self.metrics.row_counts["session_metadata"] = 1
        out["session_metadata"] = meta
        return out

    def _fetch(self, name: str, fn: Any) -> pd.DataFrame | None:
        self.metrics.api_requests += 1
        try:
            df = fn()
        except Exception as exc:
            log.warning("fetch %s failed: %s", name, exc)
            return None
        if df is None:
            return None
        self.metrics.row_counts[name] = int(len(df))
        self.metrics.memory_bytes[name] = int(df.memory_usage(deep=True).sum())
        return df

    def _normalize(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        out = df.copy()
        if "timestamp" in out.columns:
            out["timestamp"] = pd.to_datetime(out["timestamp"])
        out["dataset"] = name
        out["session_date"] = self.session_date.isoformat()
        return out

    def _write_parquet(self, datasets: dict[str, pd.DataFrame]) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        day_dir = self.output_root / self.session_date.isoformat() / f"sr{self.strike_range}"
        day_dir.mkdir(parents=True, exist_ok=True)
        for name, df in datasets.items():
            path = day_dir / f"{name}.parquet"
            df.to_parquet(path, engine="pyarrow", index=False, compression="zstd", compression_level=3)
            paths[name] = path
            self.metrics.parquet_bytes[name] = path.stat().st_size
        return paths

    def _read_back(self, paths: dict[str, Path]) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        for name, path in paths.items():
            df = pd.read_parquet(path)
            stats[name] = {"rows": len(df), "columns": list(df.columns)}
        return stats

    def _compression_experiment(self, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        sample_name = max(
            (k for k in datasets if k in {"quotes", "trades", "greeks"} and not datasets[k].empty),
            default=None,
            key=lambda k: len(datasets[k]),
        )
        if sample_name is None:
            return {"status": "skipped", "reason": "no non-empty sample dataset"}
        df = datasets[sample_name]
        for level in ZSTD_LEVELS:
            table = pa.Table.from_pandas(df, preserve_index=False)
            buf = pa.BufferOutputStream()
            pq.write_table(table, buf, compression="zstd", compression_level=level)
            results[f"zstd_{level}"] = {
                "sample_dataset": sample_name,
                "rows": len(df),
                "bytes": buf.tell(),
                "ratio_vs_uncompressed": round(buf.tell() / max(self.metrics.memory_bytes[sample_name], 1), 4),
            }
        return results

    def _quality_stats(self, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        for name, df in datasets.items():
            if df.empty or "timestamp" not in df.columns:
                continue
            ts = pd.to_datetime(df["timestamp"])
            stats[name] = {
                "duplicate_ratio": float(ts.duplicated().mean()),
                "out_of_order_ratio": float((ts.diff() < pd.Timedelta(0)).mean()),
                "missing_interval_ratio": None,
            }
        return stats

    def _em_band_subsets(self, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
        """Derive ±0.5/1.0/2.0 EM strike subsets from widest download (no extra API)."""
        quotes = datasets.get("quotes")
        index = datasets.get("index")
        greeks = datasets.get("greeks")
        if quotes is None or quotes.empty:
            return {"status": "skipped", "reason": "missing quotes"}
        spot = float("nan")
        if index is not None and not index.empty and "price" in index.columns:
            spot = float(index.sort_values("timestamp").iloc[0]["price"])
        if pd.isna(spot) and greeks is not None and not greeks.empty:
            spot = float(greeks.sort_values("timestamp").iloc[0].get("underlying_price", float("nan")))
        if pd.isna(spot):
            return {"status": "skipped", "reason": "spot unavailable for EM bands"}
        iv = 0.2
        if greeks is not None and not greeks.empty and "implied_vol" in greeks.columns:
            iv = float(greeks["implied_vol"].median())
        t_years = 6.5 / (252.0 * 6.5)
        out: dict[str, Any] = {"spot_at_open_proxy": spot, "iv_proxy": iv, "bands": {}}
        for label, mult in (("pm_0p5_em", 0.5), ("pm_1p0_em", 1.0), ("pm_2p0_em", 2.0)):
            width = spot * iv * math.sqrt(t_years) * mult
            lo, hi = spot - width, spot + width
            sub = quotes[(quotes["strike"] >= lo) & (quotes["strike"] <= hi)]
            out["bands"][label] = {
                "strike_lo": lo,
                "strike_hi": hi,
                "quote_rows": int(len(sub)),
                "trade_rows": int(
                    len(datasets["trades"][
                        (datasets["trades"]["strike"] >= lo) & (datasets["trades"]["strike"] <= hi)
                    ])
                )
                if datasets.get("trades") is not None and not datasets["trades"].empty
                else 0,
            }
        return out


def project_capacity(day_manifests: list[dict[str, Any]]) -> dict[str, Any]:
    """Rough storage projection from pilot days (estimate, not exact)."""
    daily_bytes: list[float] = []
    for m in day_manifests:
        total = sum(
            (d.get("parquet_bytes") or 0)
            for d in m.get("datasets", {}).values()
            if isinstance(d, dict)
        )
        if total:
            daily_bytes.append(float(total))

    if not daily_bytes:
        return {"status": "insufficient_data"}

    low = min(daily_bytes)
    base = sum(daily_bytes) / len(daily_bytes)
    high = max(daily_bytes) * 1.25
    trading_days_per_year = 252
    return {
        "status": "estimate",
        "assumptions": [
            "pilot uses quote 1s + trade tick + greek 1m + OI + index 1s",
            "strike_range proxy for EM bands; not full chain",
            "raw tick quote lake not included unless separately piloted",
            "manifest/checksum overhead excluded",
        ],
        "per_day_bytes": {"low": low, "base": base, "high": high},
        "per_month_bytes": {k: v * 21 for k, v in {"low": low, "base": base, "high": high}.items()},
        "per_year_bytes": {k: v * trading_days_per_year for k, v in {"low": low, "base": base, "high": high}.items()},
        "2022_05_to_present_bytes": {
            k: v * trading_days_per_year * 4.1
            for k, v in {"low": low, "base": base, "high": high}.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", type=str, default=None, help="comma-separated YYYY-MM-DD")
    parser.add_argument("--strike-range", type=int, default=60)
    parser.add_argument("--quote-interval", type=str, default="1s")
    parser.add_argument("--greek-interval", type=str, default="1m")
    parser.add_argument("--index-interval", type=str, default="1s")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/pilot"))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("artifacts/manifests/intraday_storage_pilot.json"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    if args.dates:
        dates = [date.fromisoformat(p.strip()) for p in args.dates.split(",") if p.strip()]
        labels = [f"custom_{d.isoformat()}" for d in dates]
    else:
        dates = [DEFAULT_ORDINARY_DATE, DEFAULT_HIGH_VOL_DATE]
        labels = ["ordinary", "high_volatility"]

    day_manifests: list[dict[str, Any]] = []
    for session, label in zip(dates, labels, strict=True):
        pilot = DayPilot(
            session_date=session,
            label=label,
            strike_range=args.strike_range,
            quote_interval=args.quote_interval,
            greek_interval=args.greek_interval,
            index_interval=args.index_interval,
            output_root=args.output_root,
            dry_run=args.dry_run,
        )
        day_manifests.append(pilot.run())

    aggregate: dict[str, Any] = {
        **manifest_header(audit_version=AUDIT_VERSION, dry_run=args.dry_run),
        "pilot_days": day_manifests,
        "strike_universe_proxies": [{"label": lb, "strike_range": sr} for lb, sr in STRIKE_UNIVERSE_LABELS],
        "capacity_projection": project_capacity(day_manifests) if not args.dry_run else {"status": "dry_run"},
    }
    write_json(args.manifest, aggregate)
    print(f"Wrote manifest → {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
