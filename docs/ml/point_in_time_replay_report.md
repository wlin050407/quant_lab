# Point-in-Time Replay Pilot Report (ML-P4)

**Date:** 2026-06-11  
**Data source:** `artifacts/raw_lake_pilot/` (ML-P3 pilot, not committed)

## Request

| Field | Value |
|-------|-------|
| `trade_date` | 2026-06-10 |
| `as_of_timestamp` | 2026-06-10 13:01:00 ET |
| `root` | SPXW |
| `expiration` | 2026-06-10 (0DTE) |
| `strict_manifests` | true |

## Results

| Metric | Value |
|--------|-------|
| Contract count | 8 |
| Quote coverage | 100% |
| Trade coverage | 100% |
| Greek coverage | 100% |
| Gamma coverage | 100% |
| OI coverage | 100% |
| Index source | `index_price_tick` |
| Session phase | `regular` |
| Quality score | 0.95 |
| `state_hash` (first 12) | `02eab6e30275` |

## Warnings

- `oi_semantics_unconfirmed` — OI publication semantics not confirmed (ML-P2/P3 convention)
- `duplicate_ratio=0.4275` — NBBO tick duplicates from pilot (not silently dropped)
- `out_of_order_ratio=0.7143` — recorded from OI partition manifest/filter

## Deterministic engine readiness

**Yes — adapter available.** `to_gex_adapter_frame()` produces `{strike, right, open_interest, spot, implied_vol, gamma}` compatible with existing GEX aggregation inputs. No formula changes required for a read-only integration spike.

## Git / secrets

- No market data pasted
- No artifacts committed
- Replay used local pilot lake only (no ThetaData network)

## ML-P5 gate

Replay engine satisfies at-or-before semantics and manifest integrity. **Ready to proceed to ML-P5 deterministic calculation contract freeze** when scheduled — not started in this phase.
