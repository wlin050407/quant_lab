"""Enrich saved SPXW intraday chains with flow-adjusted effective OI.

ThetaData Value tier serves **static daily OI** intraday; we proxy flow with
|Δ NBBO quote size| since the 10:00 ET snapshot (from saved ``quotes_*.parquet``).
Standard-tier trade volume is used automatically on new chain builds when available.

Examples::

    python scripts/enrich_intraday_chains_flow.py
    python scripts/enrich_intraday_chains_flow.py --force
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import pandas as pd

from quant_lab.data.thetadata_chain import list_intraday_chain_dates, load_built_intraday_chain
from quant_lab.data.thetadata_intraday import PIN_PLAY_TIMES_ET
from quant_lab.data.thetadata_storage import (
    intraday_chain_path,
    load_parquet,
    option_intraday_path,
    save_parquet,
)
from quant_lab.factors.effective_oi import (
    EFFECTIVE_OI_COL,
    enrich_chain_effective_oi,
    flow_delta_from_quote_sizes,
)

log = logging.getLogger(__name__)

REFERENCE_TIME = "10:00:00"
DEFAULT_OPTION_ROOT = "SPXW"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _iter_sessions(start: date | None, end: date | None) -> list[date]:
    out: list[date] = []
    for iso in list_intraday_chain_dates(option_root=DEFAULT_OPTION_ROOT):
        session = date.fromisoformat(iso)
        if start is not None and session < start:
            continue
        if end is not None and session > end:
            continue
        out.append(session)
    return sorted(out)


def _load_quotes(session_date: date, time_of_day: str) -> pd.DataFrame:
    path = option_intraday_path(session_date, time_of_day, symbol=DEFAULT_OPTION_ROOT)
    if not path.is_file():
        return pd.DataFrame()
    return load_parquet(path)


def _save_chain(chain: pd.DataFrame, session_date: date, time_of_day: str) -> None:
    label = time_of_day[:5].replace(":", "")
    path = intraday_chain_path(session_date, label, symbol=DEFAULT_OPTION_ROOT)
    save_parquet(chain, path)


def enrich_session(session_date: date, *, force: bool = False) -> int:
    """Enrich all PIN_PLAY times for one session; returns count updated."""
    reference_chain: pd.DataFrame | None = None
    reference_quotes: pd.DataFrame | None = None
    try:
        reference_chain, _ = load_built_intraday_chain(
            session_date, REFERENCE_TIME, option_root=DEFAULT_OPTION_ROOT
        )
        reference_quotes = _load_quotes(session_date, REFERENCE_TIME)
    except FileNotFoundError:
        reference_chain = None

    updated = 0
    for tod in PIN_PLAY_TIMES_ET:
        try:
            chain, _ = load_built_intraday_chain(session_date, tod, option_root=DEFAULT_OPTION_ROOT)
        except FileNotFoundError:
            continue

        if not force and EFFECTIVE_OI_COL in chain.columns:
            settled = chain["open_interest"].astype("float64")
            eff = chain[EFFECTIVE_OI_COL].astype("float64")
            if (eff - settled).abs().sum() > 0:
                continue

        quotes_now = _load_quotes(session_date, tod)
        ref_chain = reference_chain if tod != REFERENCE_TIME else None
        ref_quotes = reference_quotes if tod != REFERENCE_TIME else None

        quote_flow = None
        if not quotes_now.empty:
            quote_flow = flow_delta_from_quote_sizes(chain, quotes_now, ref_quotes)

        enriched = enrich_chain_effective_oi(
            chain,
            ref_chain,
            quote_flow=quote_flow,
        )
        _save_chain(enriched, session_date, tod)
        updated += 1
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None)
    parser.add_argument("--force", action="store_true", help="overwrite existing effective OI columns")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    sessions = _iter_sessions(args.start, args.end)
    if not sessions:
        print("no intraday sessions found", file=sys.stderr)
        return 1

    total = 0
    for i, session in enumerate(sessions, start=1):
        n = enrich_session(session, force=args.force)
        total += n
        if i % 50 == 0 or i == len(sessions):
            log.info("progress %d/%d sessions  chains_updated=%d", i, len(sessions), total)

    print(f"done: sessions={len(sessions)} chain_files_updated={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
