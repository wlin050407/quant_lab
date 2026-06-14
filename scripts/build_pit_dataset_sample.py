#!/usr/bin/env python3
"""Build controlled point-in-time sample dataset (ML-P7.5 / ML-P7.6)."""

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


def _load_stage_a_gate(report_root: Path) -> dict | None:
    gate_path = report_root / "stage_a_gate.json"
    if not gate_path.is_file():
        return None
    return json.loads(gate_path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="ML-P7.5/7.6 controlled PIT sample dataset builder")
    parser.add_argument("--config", type=Path, default=Path("config/ml/pit_sample_v1.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no writes")
    parser.add_argument("--max-dates", type=int, default=20, help="Max trade dates to process")
    parser.add_argument(
        "--stage",
        choices=("a", "b"),
        default=None,
        help="Stage A=3-day smoke, Stage B=up to 20-day build (requires Stage A pass)",
    )
    parser.add_argument(
        "--require-stage-a",
        action="store_true",
        help="Fail if Stage A gate not passed (auto for --stage b)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    max_dates = args.max_dates
    if args.stage == "a":
        max_dates = min(max_dates, 3)
    elif args.stage == "b":
        max_dates = min(max_dates, 20)

    if max_dates > 20:
        log.error("max_dates=%s exceeds cap of 20", max_dates)
        return 2

    config = load_sample_config(args.config)
    log.info("loaded config %s with %d dates", config.version, len(config.dates))

    if args.dry_run:
        plan = build_dry_run_plan(config, max_dates=max_dates)
        print(json.dumps(plan.to_dict(), indent=2))
        missing_total = sum(len(v) for v in plan.missing_partitions.values())
        if missing_total and not plan.ingest_enabled:
            log.warning(
                "dry-run: %d partition gaps across dates; enable ingest or seed pilot lake",
                missing_total,
            )
        return 0

    require_stage_a = args.require_stage_a or args.stage == "b"
    if require_stage_a and max_dates > 3:
        gate = _load_stage_a_gate(config.report_root)
        if gate is None or not gate.get("passed"):
            log.error(
                "Stage B blocked: Stage A gate not passed. Run --stage a --max-dates 3 first."
            )
            if gate:
                print(json.dumps(gate, indent=2))
            return 3

    result = build_sample_dataset(config, max_dates=max_dates, dry_run=False)
    assert isinstance(result, SampleBuildResult)
    summary = {
        "row_count": len(result.joined_rows),
        "failed_dates": len(result.failed_dates),
        "leakage_passed": result.leakage.passed,
        "coverage_summary": {
            "valid_zone_ratio": result.coverage_report.get("valid_zone_ratio"),
            "included_row_count": result.coverage_report.get("included_row_count"),
            "thetadata_request_count": result.coverage_report.get("thetadata_request_count"),
        },
        "stage_a_gate": (config.report_root / "stage_a_gate.json").exists(),
        "p8b_readiness": (config.report_root / "p8b_readiness.json").exists(),
    }
    print(json.dumps(summary, indent=2))
    if not result.leakage.passed:
        log.error("leakage validation FAILED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
