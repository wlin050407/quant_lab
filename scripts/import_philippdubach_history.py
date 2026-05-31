"""Import the Philipp Dubach historical SPY options dataset into our storage layout.

The dataset is a single ~600MB parquet file covering EoD SPY chains from
2008-01-02 to 2025-12-12. This script slices it day-by-day, normalizes each
snapshot into the project's canonical `OptionChainSnapshot` shape, and writes
each day under `data/raw/options/SPY/<YYYY-MM-DD>/chain.parquet`, identical to
what `daily_snapshot.ps1` produces from yfinance.

Defaults focus on 2022-onwards because that's when SPY daily expirations
became consistently populated; pass `--full` to import every available day.

Examples:

    # default: 2022-01-01 onwards
    python scripts/import_philippdubach_history.py

    # full 18-year history
    python scripts/import_philippdubach_history.py --full

    # explicit window
    python scripts/import_philippdubach_history.py --start 2023-01-01 --end 2023-12-31

    # dry-run (count snapshots, don't write parquet)
    python scripts/import_philippdubach_history.py --start 2025-12-01 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from quant_lab.config import settings
from quant_lab.data.philippdubach_source import (
    MIN_ROWS_PER_SNAPSHOT,
    iter_option_snapshots,
    load_underlying_dataframe,
)
from quant_lab.data.storage import (
    list_option_snapshots,
    load_option_chain,
    save_option_chain,
    save_underlying,
)
from quant_lab.quality.checks import (
    check_option_chain,
    check_snapshot_continuity,
    check_underlying,
)


log = logging.getLogger(__name__)

DEFAULT_OPTIONS_PATH = Path("data/external/philippdubach_spy_options.parquet")
DEFAULT_UNDERLYING_PATH = Path("data/external/philippdubach_spy_underlying.parquet")
DEFAULT_START = date(2022, 1, 1)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else settings.paths.project_root / path


def _build_spot_lookup(underlying_df: pd.DataFrame) -> dict[date, float]:
    """Map each trading day -> SPY close, used to fill `spot` per snapshot.

    The underlying frame's index is tz-localized UTC at midnight (preserving
    the calendar day the dataset stored), so `ts.date()` is the right session
    label. Converting to ET first would shift the midnight stamp back 5 hours
    and silently mis-attribute every day.
    """
    out: dict[date, float] = {}
    for ts, row in underlying_df.iterrows():
        out[ts.date()] = float(row["close"])
    return out


def import_underlying(parquet_path: Path, *, symbol: str = "SPY") -> int:
    df = load_underlying_dataframe(parquet_path, symbol=symbol)
    report = check_underlying(df, symbol=symbol)
    print(report.render())
    if report.has_errors:
        print("ERROR: underlying quality check failed — refusing to write.", file=sys.stderr)
        return 2
    out_path = save_underlying(df, symbol=symbol, interval="1d")
    print(f"OK: wrote {len(df)} underlying rows to {out_path}")
    return 0


def import_options(
    options_path: Path,
    *,
    symbol: str,
    start_date: date | None,
    end_date: date | None,
    spot_lookup: dict[date, float],
    skip_existing: bool,
    dry_run: bool,
    quality_sample_every: int,
) -> tuple[int, int, list[str]]:
    """Stream options day-by-day and persist each via storage.save_option_chain.

    Returns: (n_written, n_skipped_existing, list_of_error_codes_seen).
    The error code list is for the post-run summary; per-day reports are
    only printed at most every `quality_sample_every` days to keep the
    console readable.
    """
    existing = set(list_option_snapshots(symbol))
    n_written = 0
    n_skipped = 0
    error_codes: list[str] = []
    start_ts = time.monotonic()

    for i, snapshot in enumerate(
        iter_option_snapshots(
            options_path,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        ),
        start=1,
    ):
        snap_date = snapshot.asof.astimezone(
            __import__("zoneinfo").ZoneInfo("America/New_York")
        ).date()
        snap_iso = snap_date.isoformat()

        spot = spot_lookup.get(snap_date, float("nan"))
        snapshot = type(snapshot)(
            symbol=snapshot.symbol,
            asof=snapshot.asof,
            spot=spot,
            chain=snapshot.chain,
        )

        if skip_existing and snap_iso in existing:
            n_skipped += 1
            if i % quality_sample_every == 0:
                log.info("[%d] %s already imported, skipped", i, snap_iso)
            continue

        report = check_option_chain(snapshot.chain, symbol=symbol, spot=spot)
        for issue in report.issues:
            if issue.severity == "error":
                error_codes.append(f"{snap_iso}:{issue.code}")

        if report.has_errors:
            log.error("[%s] quality errors: %s", snap_iso, report.render())
            continue

        if dry_run:
            n_written += 1
            if i % quality_sample_every == 0:
                elapsed = time.monotonic() - start_ts
                rate = i / elapsed if elapsed > 0 else 0
                log.info(
                    "[%d] dry-run %s spot=%.2f rows=%d (%.1f snap/s)",
                    i,
                    snap_iso,
                    spot,
                    len(snapshot.chain),
                    rate,
                )
            continue

        save_option_chain(snapshot)
        n_written += 1

        if i % quality_sample_every == 0:
            elapsed = time.monotonic() - start_ts
            rate = i / elapsed if elapsed > 0 else 0
            log.info(
                "[%d] %s spot=%.2f rows=%d (%.1f snap/s)",
                i,
                snap_iso,
                spot,
                len(snapshot.chain),
                rate,
            )

    return n_written, n_skipped, error_codes


def post_import_continuity(symbol: str) -> None:
    snapshots = list_option_snapshots(symbol)
    if len(snapshots) < 2:
        print("[continuity] not enough snapshots to compare")
        return
    loaded = [(d, *load_option_chain(symbol, d)) for d in snapshots]
    print(check_snapshot_continuity(symbol, loaded).render())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--options",
        type=Path,
        default=DEFAULT_OPTIONS_PATH,
        help="path to the SPY options parquet (relative to project root)",
    )
    parser.add_argument(
        "--underlying",
        type=Path,
        default=DEFAULT_UNDERLYING_PATH,
        help="path to the SPY underlying parquet",
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument(
        "--start",
        type=_parse_date,
        default=None,
        help=f"inclusive lower bound on snapshot date (default {DEFAULT_START} unless --full)",
    )
    parser.add_argument(
        "--end",
        type=_parse_date,
        default=None,
        help="inclusive upper bound on snapshot date (default: no limit)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="import every available day (overrides default 2022-01-01 lower bound)",
    )
    parser.add_argument(
        "--skip-underlying",
        action="store_true",
        help="don't re-import the underlying file",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="skip snapshot dates already present in storage (default: on)",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="overwrite existing snapshots",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="iterate the file but don't write any parquet",
    )
    parser.add_argument(
        "--no-continuity",
        action="store_true",
        help="skip the post-import cross-snapshot continuity check",
    )
    parser.add_argument(
        "--quality-sample-every",
        type=int,
        default=25,
        help="print per-day status every N days (errors still log every day)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    options_path = _resolve(args.options)
    underlying_path = _resolve(args.underlying)

    if not options_path.exists():
        print(f"ERROR: options file not found at {options_path}", file=sys.stderr)
        return 2
    if not underlying_path.exists():
        print(f"ERROR: underlying file not found at {underlying_path}", file=sys.stderr)
        return 2

    underlying_df = load_underlying_dataframe(underlying_path, symbol=args.symbol)
    spot_lookup = _build_spot_lookup(underlying_df)
    print(f"loaded {len(spot_lookup)} underlying days for spot lookup")

    if not args.skip_underlying:
        rc = import_underlying(underlying_path, symbol=args.symbol)
        if rc != 0:
            return rc

    start_date = args.start
    if start_date is None and not args.full:
        start_date = DEFAULT_START
    log.info(
        "importing %s options from %s (start=%s end=%s skip_existing=%s dry_run=%s)",
        args.symbol,
        options_path,
        start_date,
        args.end,
        args.skip_existing,
        args.dry_run,
    )

    n_written, n_skipped, error_codes = import_options(
        options_path,
        symbol=args.symbol,
        start_date=start_date,
        end_date=args.end,
        spot_lookup=spot_lookup,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        quality_sample_every=args.quality_sample_every,
    )

    print()
    print("=== import summary ===")
    print(f"snapshots written:           {n_written}")
    print(f"snapshots skipped (existing): {n_skipped}")
    print(f"min rows per snapshot:        {MIN_ROWS_PER_SNAPSHOT}")
    if error_codes:
        print(f"per-day error codes seen ({len(error_codes)}):")
        for code in error_codes[:20]:
            print(f"  {code}")
        if len(error_codes) > 20:
            print(f"  ... and {len(error_codes) - 20} more")

    if not args.dry_run and not args.no_continuity and n_written > 0:
        print()
        print("=== cross-snapshot continuity ===")
        post_import_continuity(args.symbol)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
