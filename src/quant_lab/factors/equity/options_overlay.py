"""Options positioning overlay from in-memory chain (7–45 DTE)."""

from __future__ import annotations

from dataclasses import dataclass

from quant_lab.data.base import OptionChainSnapshot
from quant_lab.factors.positioning import max_pain, put_call_ratio


OPTIONS_OVERLAY_WARNING = (
    "Options overlay is contextual (yfinance, 7–45 DTE mix), not a standalone signal."
)


@dataclass(frozen=True)
class OptionsOverlay:
    pcr_volume: float
    pcr_oi: float
    max_pain: float
    n_contracts: int
    n_expiries: int
    evidence_grade: str
    source: str
    oi_timestamp_known: bool
    warning: str


def _overlay_grade(n_contracts: int) -> str:
    if n_contracts >= 200:
        return "B"
    if n_contracts >= 40:
        return "C"
    return "C"


def options_overlay_metrics(chain_snap: OptionChainSnapshot | None) -> OptionsOverlay | None:
    if chain_snap is None or chain_snap.chain.empty:
        return None
    chain = chain_snap.chain
    pcr_vol = put_call_ratio(chain, kind="volume")
    pcr_oi = put_call_ratio(chain, kind="open_interest")
    mp = max_pain(chain)
    n_contracts = int(len(chain))
    n_expiries = int(chain["expiry"].nunique()) if "expiry" in chain.columns else 0
    return OptionsOverlay(
        pcr_volume=float(pcr_vol),
        pcr_oi=float(pcr_oi),
        max_pain=float(mp),
        n_contracts=n_contracts,
        n_expiries=n_expiries,
        evidence_grade=_overlay_grade(n_contracts),
        source="yfinance",
        oi_timestamp_known=False,
        warning=OPTIONS_OVERLAY_WARNING,
    )
