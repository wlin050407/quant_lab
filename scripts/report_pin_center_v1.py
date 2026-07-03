"""V1 strike-accuracy report with per-session detail (GEXBot hist replay)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from quant_lab.config import load_dotenv_if_present, settings
from quant_lab.terminal.pin_center_replay import run_v1_replay

log = logging.getLogger(__name__)


def _report_dir() -> Path:
    out = settings.paths.project_root / "artifacts" / "reports" / "pin_center_v1"
    out.mkdir(parents=True, exist_ok=True)
    return out


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--pin-min", type=float, default=50.0)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    sym = f"^{args.symbol.upper()}" if args.symbol.upper() == "SPX" else args.symbol.upper()
    result = run_v1_replay(sym, pin_min=args.pin_min, include_sessions=True)
    if result.get("status") != "ok":
        print(json.dumps(result, indent=2))
        return 1

    sessions = result.pop("sessions", [])
    safe = sym.replace("^", "").replace("/", "_")
    out_dir = _report_dir()
    summary_path = out_dir / f"{safe}_v1_pin{int(args.pin_min)}_summary.json"
    sessions_path = out_dir / f"{safe}_v1_pin{int(args.pin_min)}_sessions.parquet"

    summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if sessions:
        import pandas as pd

        pd.DataFrame(sessions).to_parquet(sessions_path, index=False)

    print(f"=== V1 replay report: {sym} pin_min={args.pin_min} ===")
    print(f"n_sessions={result['n_sessions']}  skipped_no_hist={result['skipped_no_hist']}")
    print(f"median |close-K|: king={result['median_abs_close_minus_king']:.2f}  "
          f"primary={result['median_abs_close_minus_primary']}  "
          f"fused={result['median_abs_close_minus_fused']:.2f}")
    print(f"mean   |close-K|: king={result['mean_abs_close_minus_king']:.2f}  "
          f"fused={result['mean_abs_close_minus_fused']:.2f}")
    if result.get("fused_beats_king_rate") is not None:
        print(f"fused <= king error: {result['fused_beats_king_rate']:.1%} of sessions")
    if result.get("fused_beats_primary_rate") is not None:
        print(f"fused <= primary error: {result['fused_beats_primary_rate']:.1%} of sessions")
    print(f"V2 primary 30m hit rate: {result.get('v2_primary_hit_30m_rate')}")
    print(f"v1_pass={result['v1_pass']}  blocker={result.get('v1_blocker')}")
    print(f"wrote {summary_path}")
    if sessions:
        print(f"wrote {sessions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
