"""Multi-resolution tabular summaries."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from quant_lab.ml.features.index_path import _realized_vol, _return
from quant_lab.ml.features.raw_frames import FeatureRawFrames, filter_at_or_before
from quant_lab.ml.features.schemas import FeatureConfig


def compute_multiresolution_features(
    raw: FeatureRawFrames,
    as_of: datetime,
    config: FeatureConfig,
    *,
    spot: float | None,
    base_quote_rate_30s: float | None,
    base_trade_count_300s: float | None,
    base_iv_atm: float | None,
) -> dict[str, Any]:
    """Tabular summaries at 1s / 10s / 1m / 5m resolutions.

    Native 10s bars are derived from tick/1s aggregates in future work; current
    implementation reuses at-or-before index windows per resolution label for
    audit/sanity baselines (ML-P7 scope).
    """
    out: dict[str, Any] = {}
    idx = raw.index_1s if raw.index_1s is not None else raw.index_tick
    idx = filter_at_or_before(idx, as_of) if idx is not None else pd.DataFrame()

    for res in config.resolutions:
        prefix = f"mr_{res}"
        if idx is not None and not idx.empty and spot is not None:
            ts = pd.to_datetime(idx["event_timestamp"])
            win = idx.loc[ts > as_of - timedelta(seconds=30)]
            out[f"{prefix}_spot_return_30s"] = _return(win, spot)
            win60 = idx.loc[ts > as_of - timedelta(seconds=60)]
            out[f"{prefix}_realized_vol_60s"] = _realized_vol(win60)
        else:
            out[f"{prefix}_spot_return_30s"] = None
            out[f"{prefix}_realized_vol_60s"] = None

        out[f"{prefix}_quote_update_rate"] = base_quote_rate_30s
        out[f"{prefix}_trade_count"] = base_trade_count_300s if res in {"1m", "5m"} else None
        out[f"{prefix}_iv_atm"] = base_iv_atm if res in {"1m", "5m"} else None

    return out
