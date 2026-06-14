#!/usr/bin/env python3
"""Build controlled point-in-time sample dataset (ML-P7.5)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.datasets.sample_builder import (  # noqa: E402
    SampleBuildResult,
    build_dry_run_plan,
    build_sample_dataset,
    load_sample_config,
)

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="ML-P7.5 controlled PIT sample dataset builder")
    parser.add_argument("--config", type=Path, default=Path("config/ml/pit_sample_v1.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no writes")
    parser.add_argument("--max-dates", type=int, default=20, help="Max trade dates to process")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.max_dates > 20:
        log.error("max_dates=%s exceeds ML-P7.5 cap of 20", args.max_dates)
        return 2

    config = load_sample_config(args.config)
    log.info("loaded config %s with %d dates", config.version, len(config.dates))

    if args.dry_run:
        plan = build_dry_run_plan(config, max_dates=args.max_dates)
        print(json.dumps(plan.to_dict(), indent=2))
        missing_total = sum(len(v) for v in plan.missing_partitions.values())
        if missing_total and not plan.ingest_enabled:
            log.warning(
                "dry-run: %d partition gaps across dates; enable ingest or seed pilot lake",
                missing_total,
            )
        return 0

    result = build_sample_dataset(config, max_dates=args.max_dates, dry_run=False)
    assert isinstance(result, SampleBuildResult)
    print(
        json.dumps(
            {
                "row_count": len(result.joined_rows),
                "failed_dates": len(result.failed_dates),
                "leakage_passed": result.leakage.passed,
                "coverage_summary": {
                    "valid_zone_ratio": result.coverage_report.get("valid_zone_ratio"),
                    "null_label_count": result.coverage_report.get("null_label_count"),
                },
            },
            indent=2,
        )
    )
    if not result.leakage.passed:
        log.error("leakage validation FAILED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
