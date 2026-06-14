# Live vs Replay Parity Report (ML-P5)

**Date:** 2026-06-11  
**Pilot:** `artifacts/raw_lake_pilot/` @ 2026-06-10 13:01:00 ET

## Synthetic parity

| Check | Result |
|-------|--------|
| Same normalized input → same bundle (2× run) | PASS |
| Recomputed gamma path vs `_row_from_chain` (net GEX, king, pin) | PASS |
| Terminal helper does not mutate input frame | PASS |
| OI `unconfirmed` metadata preserved | PASS |
| Black-76 `gamma_method` preserved | PASS |

## Pilot replay summary

| Field | Value |
|-------|-------|
| Input contract count | 8 |
| Spot | ~7319.23 |
| Expiration | 2026-06-10 (0DTE) |
| Gamma source | `derived_black76_precomputed` |
| OI status | `unconfirmed` |
| Net GEX (USD/$1 move) | ~−2.27e11 |
| King node | 7345 |
| Pin score | ~75.5 |
| Gamma flip | ~6788 |
| Call wall | 7350 |
| Put wall | 7345 |
| Expected move 1σ | ~87.1 |
| Outputs deterministic | Yes |
| Warnings | `oi_semantics_unconfirmed`, duplicate/out-of-order ratios |

No raw market rows pasted. No artifacts committed.

## Pin / Zone threshold tests

Contract matches `pin_cluster.py` constants:

- Distance merge: `< 0.3%` of spot — tested just below/above
- Strength merge: `>= 70%` of primary — tested just below/above
- Valid exit buffer: `max(5 pts, 0.25 × width)` — state machine tested

## Expected Move

`expected_move_1sd(spot, iv, time_years=T)` — unit test verifies `spot × IV × sqrt(T)`.

## ML-P6 readiness

Contract frozen; replay adapter schema fixed. **Ready for ML-P6 label specification** when scheduled — labels not built in ML-P5.
