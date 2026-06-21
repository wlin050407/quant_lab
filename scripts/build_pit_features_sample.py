#!/usr/bin/env python3
"""Build PIT feature dataset from existing label parquet (ML-P8B.1)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.datasets.sample_builder import parse_dates_filter  # noqa: E402
from quant_lab.ml.features.p8b1_build import (  # noqa: E402
    build_dry_run_plan,
    build_feature_dataset_p8b1,
    load_feature_build_config,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="ML-P8B.1 feature dataset build from label parquet")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ml/pit_features_baseline_v1_1_validation.yaml"),
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no feature build")
    parser.add_argument(
        "--dates",
        type=str,
        default=None,
        help="Comma-separated trade dates (YYYY-MM-DD)",
    )
    parser.add_argument("--checkpoint-per-date", action="store_true", help="Write per-date feature shards")
    parser.add_argument("--progress-every", type=int, default=10, help="Log progress every N rows")
    parser.add_argument("--no-resume", action="store_true", help="Rebuild dates even if checkpoint exists")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_feature_build_config(args.config)
    if args.checkpoint_per_date:
        config.checkpoint_per_date = True
    if args.progress_every:
        config.progress_every = args.progress_every

    dates_filter: set[date] | None = None
    if args.dates:
        dates_filter = set(parse_dates_filter(args.dates))

    if args.dry_run:
        plan = build_dry_run_plan(config)
        if dates_filter:
            plan["dates_filter"] = sorted(d.isoformat() for d in dates_filter)
        print(json.dumps(plan, indent=2))
        if not plan.get("input_dataset_exists"):
            log.error("input dataset missing")
            return 2
        if plan.get("row_count", 0) == 0:
            log.error("no label rows found")
            return 2
        log.info("dry-run PASS")
        return 0

    result = build_feature_dataset_p8b1(
        config,
        dates_filter=dates_filter,
        dry_run=False,
        resume=not args.no_resume,
    )
    log.info(
        "P8B.1 complete: feature_rows=%d dates=%d p8b1_pass=%s",
        result.feature_row_count,
        len(result.dates_built),
        result.p8b1_pass,
    )
    if result.report_path:
        log.info("report: %s", result.report_path)
    return 0 if result.p8b1_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
