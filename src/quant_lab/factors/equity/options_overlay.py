"""Options positioning overlay from in-memory chain (7–45 DTE)."""

from __future__ import annotations

from dataclasses import dataclass

from quant_lab.data.base import OptionChainSnapshot
from quant_lab.factors.positioning import max_pain, put_call_ratio


@dataclass(frozen=True)
class OptionsOverlay:
    pcr_volume: float
    pcr_oi: float
    max_pain: float
    n_contracts: int
    evidence_grade: str


def options_overlay_metrics(chain_snap: OptionChainSnapshot | None) -> OptionsOverlay | None:
    if chain_snap is None or chain_snap.chain.empty:
        return None
    chain = chain_snap.chain
    pcr_vol = put_call_ratio(chain, kind="volume")
    pcr_oi = put_call_ratio(chain, kind="open_interest")
    mp = max_pain(chain)
    return OptionsOverlay(
        pcr_volume=float(pcr_vol),
        pcr_oi=float(pcr_oi),
        max_pain=float(mp),
        n_contracts=int(len(chain)),
        evidence_grade="B",
    )
