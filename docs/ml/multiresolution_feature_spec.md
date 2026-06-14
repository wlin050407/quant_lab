# Multi-Resolution Feature Specification (ML-P7)

Tabular multi-resolution summaries for GBDT baseline prep (ML-P8). **Not** full sequence tensors.

## Resolutions

| Resolution | Source | ML-P7 status |
|------------|--------|--------------|
| `1s` | `index_price_1s`, `option_quote_1s` | Implemented — index return/vol summaries |
| `10s` | Aggregated from tick/1s | Audit label — same at-or-before windows as 1s baseline |
| `1m` | `option_greeks_1m_first_order` | Trade count + IV ATM passthrough |
| `5m` | Audit aggregation | Trade count + IV ATM passthrough |

Native 10s lake partitions do not exist in ML-P3 pilot. ML-P7 does **not** invent synthetic 10s bars beyond labeling audit features; future phases may add true 10s resampling.

## Per-resolution features

Prefix: `mr_{resolution}_`

| Feature | Description |
|---------|-------------|
| `spot_return_30s` | Index return over 30s window ending at as_of |
| `realized_vol_60s` | Realized vol from index path 60s window |
| `quote_update_rate` | Passthrough from `quote_30s_quote_update_rate` |
| `trade_count` | Passthrough from 300s trade window (1m/5m only) |
| `iv_atm` | Passthrough from greeks IV ATM (1m/5m only) |

## Timestamp rule

Each resolution row records `source_timestamp_max <= as_of_timestamp` on the parent `FeatureRow`.

## Output

- Row-level flat dict (GBDT-ready)
- No parquet sequence tensors in ML-P7
- Full event sequences deferred to deep-model phases

## Builder API

```python
from quant_lab.ml.features.builder import (
    build_feature_row,
    build_feature_dataset,
    build_pilot_feature_dataset_if_available,
)
```

Pilot output: `artifacts/features/pit_pilot/` (gitignored).
