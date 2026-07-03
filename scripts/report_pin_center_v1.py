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
    parser.add_argument(
        "--full",
        action="store_true",
        help="sweep pin 70/60/50/40/0 on cached hist; add --all-regimes for max n",
    )
    parser.add_argument(
        "--all-regimes",
        action="store_true",
        help="include short_gamma/undetermined (max hist×terminal overlap)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    sym = f"^{args.symbol.upper()}" if args.symbol.upper() == "SPX" else args.symbol.upper()
    pin_levels = [70.0, 60.0, 50.0, 40.0, 0.0] if args.full else [args.pin_min]
    long_gamma_only = not args.all_regimes

    summaries: list[dict] = []
    for pin_min in pin_levels:
        result = run_v1_replay(
            sym,
            pin_min=pin_min,
            include_sessions=True,
            hist_only=True,
            max_sessions=500,
            long_gamma_only=long_gamma_only,
        )
        summaries.append(result)
        if result.get("status") != "ok":
            print(f"pin_min={pin_min}: {result}")
            continue

        sessions = result.pop("sessions", [])
        safe = sym.replace("^", "").replace("/", "_")
        out_dir = _report_dir()
        pin_tag = int(pin_min)
        summary_path = out_dir / f"{safe}_v1_pin{pin_tag}_summary.json"
        sessions_path = out_dir / f"{safe}_v1_pin{pin_tag}_sessions.parquet"
        summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if sessions:
            import pandas as pd

            pd.DataFrame(sessions).to_parquet(sessions_path, index=False)

        regime_tag = "long_gamma" if long_gamma_only else "all_regimes"
        print(f"=== V1 replay: {sym} pin_min={pin_min} cohort={regime_tag} ===")
        print(
            f"scanned={result['n_hist_dates_scanned']}  "
            f"n={result['n_sessions']}  "
            f"skip(pin/regime/hist)={result.get('skipped_pin')}/"
            f"{result.get('skipped_regime')}/{result.get('skipped_no_hist')}"
        )
        print(
            f"median |close-K|: king={result['median_abs_close_minus_king']:.2f}  "
            f"primary={result['median_abs_close_minus_primary']}  "
            f"fused={result['median_abs_close_minus_fused']:.2f}"
        )
        if result.get("fused_beats_king_rate") is not None:
            print(f"fused <= king: {result['fused_beats_king_rate']:.1%}")
        if result.get("fused_beats_primary_rate") is not None:
            print(f"fused <= primary: {result['fused_beats_primary_rate']:.1%}")
        print(f"V2 30m hit: {result.get('v2_primary_hit_30m_rate')}")
        print(
            f"v1_pass={result['v1_pass']}  tier={result.get('v1_tier')}  "
            f"v2_pass={result.get('v2_pass')}  v2_tier={result.get('v2_tier')}"
        )
        if not result["v1_pass"]:
            print(f"  v1_blocker: {result.get('v1_blocker')}")
        print(f"wrote {summary_path}")
        if sessions:
            print(f"wrote {sessions_path}")
        print()

    if args.full and len(summaries) > 1:
        print("--- full V1 sweep ---")
        for r in summaries:
            if r.get("status") != "ok":
                continue
            print(
                f"  pin>={r['pin_min']:.0f}  n={r['n_sessions']:3d}  "
                f"med_fused={r['median_abs_close_minus_fused']:.2f}  "
                f"v1={r['v1_pass']}({r.get('v1_tier')})  "
                f"v2={r.get('v2_pass')}({r.get('v2_tier')})"
            )
    return 0 if any(r.get("status") == "ok" for r in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
