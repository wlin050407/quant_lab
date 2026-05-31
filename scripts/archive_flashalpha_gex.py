"""Archive FlashAlpha GEX snapshot and append to free_gex_reference.yaml.

Run once per day (free tier: 5 API calls/day) to build a free calibration history
without SpotGamma subscription.

Examples:

    # paste key into .env → FLASHALPHA_API_KEY=...
    python scripts/archive_flashalpha_gex.py --symbol SPY
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import yaml

from quant_lab.config import settings
from quant_lab.data.flashalpha_gex import FlashAlphaError, fetch_gex
from quant_lab.data.storage import list_option_snapshots

log = logging.getLogger(__name__)


def _reference_path() -> Path:
    return settings.paths.project_root / "config" / "free_gex_reference.yaml"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {"references": []}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"references": []}


def _save_yaml(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument(
        "--asof-date",
        default=None,
        help="reference date label (default: today UTC date; use last EoD date)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    snaps = list_option_snapshots(args.symbol)
    snapshot_date = snaps[-1] if snaps else None
    asof = args.asof_date or snapshot_date or date.today().isoformat()

    try:
        quote = fetch_gex(args.symbol, snapshot_date=snapshot_date or asof)
    except FlashAlphaError as exc:
        log.error("%s", exc)
        return 1

    entry = {
        "date": asof,
        "provider": "flashalpha",
        "source": (
            f"FlashAlpha API snapshot (as_of={quote.as_of}"
            f"{f', expiration={quote.expiration}' if quote.expiration else ''})"
        ),
        "net_gex_bn_per_1pct": round(quote.net_gex_bn_per_1pct, 2),
        "flip_level": round(quote.gamma_flip, 2),
        "regime": quote.regime,
    }
    if quote.expiration:
        entry["expiration"] = quote.expiration

    ref_path = _reference_path()
    data = _load_yaml(ref_path)
    refs: list[dict] = list(data.get("references", []))
    refs = [r for r in refs if not (r.get("date") == asof and r.get("provider") == "flashalpha")]
    refs.append(entry)
    data["references"] = refs
    _save_yaml(ref_path, data)

    log.info(
        "archived %s %s: net_gex=%+.2f Bn/1%% flip=%.2f regime=%s → %s",
        args.symbol,
        asof,
        quote.net_gex_bn_per_1pct,
        quote.gamma_flip,
        quote.regime,
        ref_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
