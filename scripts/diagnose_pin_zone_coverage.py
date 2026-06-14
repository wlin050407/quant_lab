#!/usr/bin/env python3
"""Diagnose pin zone coverage for ML-P7.6.1 Stage A sample (no network)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_lab.ml.datasets.pin_zone_diagnosis import build_pin_zone_diagnosis_report  # noqa: E402
from quant_lab.ml.datasets.sample_builder import load_sample_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Pin zone coverage diagnosis (ML-P7.6.1)")
    parser.add_argument("--config", type=Path, default=Path("config/ml/pit_sample_ingest_v1.yaml"))
    parser.add_argument("--max-dates", type=int, default=3)
    parser.add_argument("--sample-every-n", type=int, default=5, help="Sample every N anchors")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/pit_sample_v1/pin_zone_diagnosis.json"),
    )
    args = parser.parse_args()

    config = load_sample_config(args.config)
    report = build_pin_zone_diagnosis_report(
        config,
        max_dates=args.max_dates,
        sample_every_n=args.sample_every_n,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
