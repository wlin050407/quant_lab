#!/usr/bin/env python3
"""Baseline primary-pin target coverage screening (ML-P7.8, no feature build)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.datasets.baseline_target_screening import (  # noqa: E402
    DEFAULT_REPORT_ROOT,
    BaselineScreeningOptions,
    screen_baseline_targets,
)
from quant_lab.ml.datasets.sample_builder import load_sample_config  # noqa: E402
from quant_lab.ml.datasets.valid_zone_screening import (  # noqa: E402
    inventory_raw_lake,
    load_day_type_map,
    parse_dates_filter,
)

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ML-P7.8 baseline target coverage screening")
    p.add_argument(
        "--lake-root",
        type=Path,
        default=Path("artifacts/raw_lake_sample"),
        help="Raw lake root",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_REPORT_ROOT,
        help="Report output directory",
    )
    p.add_argument(
        "--day-type-config",
        type=Path,
        default=Path("config/ml/pit_long_gamma_candidates_v1.yaml"),
    )
    p.add_argument("--dates", type=str, default=None, help="Comma-separated ISO dates")
    p.add_argument("--progress-every", type=int, default=10)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--list-inventory", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    cfg_path = _PROJECT_ROOT / "config/ml/pit_sample_valid_zone_top5.yaml"
    if not cfg_path.is_file():
        log.error("missing config %s", cfg_path)
        return 1

    config = replace(
        load_sample_config(cfg_path),
        lake_root=args.lake_root,
        ingest_enabled=False,
    )

    if args.list_inventory:
        inv = inventory_raw_lake(config)
        print(json.dumps(inv.to_dict(), indent=2))
        return 0

    day_type_map = load_day_type_map(args.day_type_config if args.day_type_config.is_file() else None)
    options = BaselineScreeningOptions(
        dates_filter=parse_dates_filter(args.dates),
        resume=not args.no_resume,
        progress_every=args.progress_every,
        report_root=args.output_dir,
    )
    summary = screen_baseline_targets(config, day_type_map, options=options)
    print(json.dumps(summary, indent=2))
    if not summary.get("p78_gates", {}).get("p78_pass", False):
        log.warning("P7.8 gates not passed — ML-P8B remains blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
