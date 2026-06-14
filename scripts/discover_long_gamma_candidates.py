#!/usr/bin/env python3
"""Discover long-gamma candidate dates for ML-P7.6.2 (no training)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.datasets.long_gamma_discovery import (  # noqa: E402
    discover_long_gamma_candidates,
    load_discovery_config,
    stage_a_plus_date_count,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="ML-P7.6.2 long-gamma candidate discovery")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/pit_long_gamma_candidates_v1.yaml"),
    )
    parser.add_argument("--max-dates", type=int, default=30)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--ingest-missing",
        action="store_true",
        help="Ingest missing raw lake partitions (controlled, idempotent)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/pit_long_gamma_candidates_v1/candidate_ranking.json"),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.max_dates > 30:
        log.error("max_dates=%s exceeds cap of 30", args.max_dates)
        return 2

    config = load_discovery_config(args.config)
    report = discover_long_gamma_candidates(
        config,
        max_dates=args.max_dates,
        top_n=args.top_n,
        ingest_missing=args.ingest_missing,
        dry_run=args.dry_run,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    stage_a_plus = {
        "top_candidate_dates": report["top_candidate_dates"],
        "recommended_stage_a_plus_count": stage_a_plus_date_count(report["top_candidate_dates"]),
    }
    (args.output.parent / "stage_a_plus_dates.json").write_text(
        json.dumps(stage_a_plus, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
