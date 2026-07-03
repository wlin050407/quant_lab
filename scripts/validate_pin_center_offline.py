"""Offline validation for Pin Center Fusion (V1 gate)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.config import settings
from quant_lab.terminal.mm_structure import build_structure_snapshot
from quant_lab.terminal.pin_center import PhysicalSnapshot, fuse_pin_center
from quant_lab.terminal.pin_center_replay import run_v1_replay


def _load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_fixture(path: Path) -> dict[str, Any]:
    payload = _load_fixture(path)
    physical = PhysicalSnapshot(**payload["physical"])
    decision = fuse_pin_center(
        physical,
        None,
        max_priors=[(float(a), float(b)) for a, b in payload.get("max_priors", [])],
    )
    return {"mode": "fixture", "status": "ok", "decision": decision.to_dict()}


def _terminal_path(symbol: str) -> Path:
    safe = symbol.replace("^", "").replace("/", "_")
    return settings.paths.processed / "terminal" / f"{safe}.parquet"


def validate_terminal_history(
    symbol: str,
    *,
    pin_min: float = 70.0,
    max_rows: int = 500,
) -> dict[str, Any]:
    """Proxy V1: median |spot - king| vs |spot - max_pain| on high-pin EoD rows."""
    path = _terminal_path(symbol)
    if not path.exists():
        return {"mode": "history", "status": "skipped", "reason": "terminal_parquet_missing", "path": str(path)}

    df = pd.read_parquet(path)
    if df.empty:
        return {"mode": "history", "status": "skipped", "reason": "empty_parquet"}

    work = df.copy()
    if "pin_score" in work.columns:
        work = work[pd.to_numeric(work["pin_score"], errors="coerce") >= pin_min]
    if "regime" in work.columns:
        work = work[work["regime"].astype(str) == "long_gamma"]
    if work.empty:
        return {"mode": "history", "status": "skipped", "reason": "no_cohort_rows"}

    work = work.tail(max_rows)
    spot = pd.to_numeric(work["spot"], errors="coerce")
    king = pd.to_numeric(work.get("king_dte1"), errors="coerce")
    pain = pd.to_numeric(work.get("max_pain_dte1"), errors="coerce")
    king_dist = (spot - king).abs()
    pain_dist = (spot - pain).abs()
    valid_k = king_dist[king_dist.notna()]
    valid_p = pain_dist[pain_dist.notna()]

    return {
        "mode": "history",
        "status": "ok",
        "symbol": symbol,
        "n_rows": int(len(work)),
        "median_abs_spot_minus_king": float(valid_k.median()) if len(valid_k) else None,
        "median_abs_spot_minus_max_pain": float(valid_p.median()) if len(valid_p) else None,
        "note": "Proxy only — fused center requires GEXBot hist replay (F3)",
    }


def validate_structure_p1(state_fixture: Path) -> dict[str, Any]:
    payload = _load_fixture(state_fixture)
    snap = build_structure_snapshot(
        terminal_symbol="^SPX",
        classic=payload.get("classic"),
        orderflow=payload.get("orderflow"),
        spot=payload.get("spot"),
        state_hubs=payload.get("state_hubs"),
    )
    if snap is None:
        return {"mode": "structure_p1", "status": "error", "reason": "snapshot_none"}
    primary = snap.primary_mm_target.level if snap.primary_mm_target else None
    return {
        "mode": "structure_p1",
        "status": "ok",
        "structure_version": snap.structure_version,
        "primary_mm_target": primary,
        "family_weights": snap.family_weights.to_dict() if snap.family_weights else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate pin center fusion offline")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/pin_center_consensus.json"),
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--history", action="store_true", help="Run terminal history proxy V1")
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Run GEXBot hist replay V1/V2 (requires API key + cache)",
    )
    parser.add_argument(
        "--state-fixture",
        type=Path,
        default=Path("tests/fixtures/mm_structure_state_hubs.json"),
    )
    args = parser.parse_args()

    out: dict[str, Any] = {}
    if args.fixture.exists():
        out["fixture"] = validate_fixture(args.fixture)
    else:
        out["fixture"] = {"status": "skipped", "reason": "fixture_missing"}

    if args.history:
        out["history"] = validate_terminal_history(args.symbol)

    if args.replay:
        out["replay"] = run_v1_replay(f"^{args.symbol}" if args.symbol.upper() == "SPX" else args.symbol)

    if args.state_fixture.exists():
        out["structure_p1"] = validate_structure_p1(args.state_fixture)
    else:
        out["structure_p1"] = {"status": "skipped", "reason": "state_fixture_missing"}

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
