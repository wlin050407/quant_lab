# Point-in-Time Replay Specification (ML-P4)

Deterministic replay over ML-P3 immutable raw event lake. **No network**, **no lookahead**.

## API

```python
from datetime import date
from quant_lab.data.intraday_time import session_datetime
from quant_lab.data.point_in_time_replay import replay_state, default_pilot_data_root

state = replay_state(
    date(2026, 6, 10),
    session_datetime(date(2026, 6, 10), "13:01:00"),
    data_root=default_pilot_data_root(),
)
```

Primary types:

| Type | Module |
|------|--------|
| `ReplayRequest` | `point_in_time_replay.py` |
| `PointInTimeState` | `point_in_time_replay.py` |
| `ReplayQuality` | `replay_quality.py` |
| `PartitionManifestSummary` | `replay_integrity.py` |

## Core rule

All datasets filter:

```text
event_timestamp <= as_of_timestamp
```

Never forward-fill future data. Missing fields remain nullable with `data_quality_flags`.

## Per-family replay rules

### Quote (NBBO — not Level 2)

1. Stable-sort `option_quote_tick` by `(event_timestamp, sequence, contract_identifier)`
2. Per contract, take **last** row at-or-before `as_of`
3. If tick empty, fallback to `option_quote_1s` → `quote_source_dataset`
4. `quote_age_seconds = as_of - latest_quote_timestamp`
5. Flag `stale_quote` if age > `max_quote_age_seconds`

### Trade

1. All `option_trade_tick` rows with `event_timestamp <= as_of`
2. Cumulative volume/count/notional proxy (`price × size × 100`)
3. Last trade fields from final row — **not** full-day totals
4. No bid/ask inference; notional is a **proxy** only

### Greeks (1m first-order)

1. Latest `option_greeks_1m_first_order` row per contract at-or-before `as_of`
2. **1m bar semantics:** `event_timestamp` is the bar label from ThetaData; replay treats it as the bar's published timestamp and selects the latest bar whose timestamp is still `<= as_of` (inclusive boundary).
3. Flag `stale_greek` / `missing_greeks` as appropriate

### Derived Black-76 gamma

1. Read `derived_gamma_black76_1m` only — **do not recompute** in replay
2. Latest row per contract at-or-before `as_of`
3. `gamma_method` must be `"black76"` — not ThetaData native gamma

### Open interest

1. Filter `oi_event_timestamp <= as_of` (and `event_timestamp` in lake)
2. Preserve `oi_semantics_status`, `oi_publication_time_confirmed`
3. When unconfirmed → warning `oi_semantics_unconfirmed` (not realtime OI)

### Index (SPX)

1. Prefer latest `index_price_tick` at-or-before `as_of`
2. Fallback `index_price_1s`
3. Record `index_source_dataset`, `index_age_seconds`

### Session metadata

Phases: `pre_market`, `regular`, `early_close`, `post_close`, `unknown`

- Uses `session_rth_start` / `session_rth_end` from lake when present
- Outside RTH → warning `session_outside_rth:<phase>`

## Duplicate / out-of-order

- Raw rows are **not** dropped at load time
- Stable sort ensures deterministic “latest per contract” selection
- Manifest + filtered-frame duplicate/out-of-order ratios recorded in quality/warnings

## Manifest integrity (`strict_manifests=True`)

Raises on:

- Missing `_manifest.json` (when partition dir exists)
- Checksum mismatch
- `ingestion_status != complete`
- Wrong dataset / trade_date / root / expiration
- Unsupported schema version

Missing partition directory → warning only (optional datasets).

## State hash

Deterministic SHA-256 over:

- `ReplayRequest` stable fields
- Partition file SHA-256 summaries (not `created_at`)
- Per-contract selected timestamps
- Schema versions, code commit, warnings

## Data quality score

Rule-based heuristic in `replay_quality.py` (starts 1.0, subtracts for missing/stale/unconfirmed). **Not ML.**

## GEX adapter

`to_gex_adapter_frame(state.option_chain)` maps replay output to `{strike, right, open_interest, spot, implied_vol, gamma}` for downstream deterministic engine — **does not change GEX formulas**.

## Out of scope (ML-P4)

- Multi-year backfill
- Model training
- Raw lake writes
- Pin/GEX/VEX formula changes
