# Feature Catalog (ML-P7)

Point-in-time tabular features for 0DTE SPXW ML. **No labels, no future outcomes.**

## Versioning

| Constant | Value |
|----------|-------|
| `feature_schema_version` | `1.0.0` |
| `feature_manifest_version` | `pit-features-v1` |

## Time rule

Every feature satisfies:

```text
source_timestamp <= as_of_timestamp
```

Join to ML-P6 label rows only via:

```text
trade_date, as_of_timestamp, replay_state_hash, deterministic_bundle_hash
```

## Feature groups

| Group | Count (catalog) | Source |
|-------|-----------------|--------|
| `context` | 9 | session metadata + clock |
| `deterministic` | 33 | ML-P5 bundle + distance norms |
| `chain_summary` | 20 | replay option_chain (OI-based GEX) |
| `quote_microstructure` | 36 | NBBO tick/1s windows 30s/60s/300s |
| `trade_flow_proxy` | 44 | trade tick windows + since_open |
| `greeks_iv` | 10 | 1m Greeks + derived Black-76 gamma |
| `index_path` | 35 | SPX index tick/1s |
| `quality` | 12 | replay + feature quality |
| `multiresolution` | 20 | 1s/10s/1m/5m audit summaries |

**Total catalog entries:** 219

## Naming conventions

- Quote: `quote_{window}s_{metric}` — e.g. `quote_30s_mean_bid_ask_spread`
- Trade: `trade_{window}_{metric}` — window `30s`, `60s`, `300s`, or `since_open`
- Index: `index_{window}_{metric}`
- Multi-resolution: `mr_{1s|10s|1m|5m}_{metric}`

## Semantics (mandatory)

| Term | Meaning |
|------|---------|
| GEX / gamma-OI | **Model-implied**, OI-based dealer exposure — not observed inventory |
| NBBO quote | Top-of-book — **not** Level 2 order book |
| OI | Prior-session semantics unless confirmed — not real-time positioning |
| Black-76 gamma | **Derived** — not ThetaData native gamma |
| Trade notional | `price × size × 100` proxy — not exchange-reported notional |

## Nullable rules

- No valid zone → distance/zone features `null` (never `0`)
- Missing expected move → EM-normalized distances `null`
- Insufficient window history → window features `null`
- Missing partition → group features `null` + quality warning

## Duplicate quote handling

- `quote_update_count` counts **all** tick rows in window (including duplicates)
- Spread/mid stats use deterministic last-row per `(contract_identifier, event_timestamp)`
- `quote_duplicate_ratio` surfaced in quality features

## Forbidden in feature dict

`official_close`, `future_index_path`, `labels.*`, `normalized_close_move`, `final_volume`, daily volume totals.

## Implementation

```python
from quant_lab.ml.features.builder import build_feature_row_from_replay
from quant_lab.ml.features.schemas import FEATURE_CATALOG, FeatureConfig
```

See `multiresolution_feature_spec.md` for resolution semantics.
