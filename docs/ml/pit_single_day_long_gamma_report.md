# ML-P7.6.3 Single-Day Long-Gamma Build Report

**Phase:** ML-P7.6.3 — Single-Day Long-Gamma Build and Checkpointed Stage A+ Runner  
**Date:** 2024-01-19 (monthly_opex, discovery rank #1)

## Raw Lake

2024-01-19 partitions **complete** (no ingest).

## Build Command

```bash
python scripts/build_pit_dataset_sample.py \
  --config config/ml/pit_sample_long_gamma_v1.yaml \
  --dates 2024-01-19 \
  --checkpoint-per-date \
  --progress-every 10 \
  --no-resume
```

## 2024-01-19 Results

| Metric | Value |
|--------|-------|
| anchor_count | 77 |
| latest_anchor | 2024-01-19T15:55:00-05:00 |
| row_count | 77 |
| included_rows | **48** |
| excluded_rows | 29 |
| valid_zone_ratio | **62.3%** |
| close_location | `above`: 48 (included only) |
| leakage | **PASS** |
| strict hash join | **PASS** |
| replay time / anchor | 12.3 s |
| feature time / row | 16.1 s |
| raw_lake reused | ~860 MB |
| joined size | ~561 KB |

## Hourly Scan vs regular_5min Build

| Path | valid_zone ratio |
|------|------------------|
| Hourly discovery scan (6 anchors) | 67% |
| regular_5min dataset build (77 anchors) | **62.3%** |

**Conclusion:** Long-γ opex date **does** convert to zone labels in full dataset build. Same lake root, same adapter fix (`regime` + `pin_reliability` in `build_as_of_context`).

## Acceptance vs ML-P7.6.3 Criteria

| Criterion | Result |
|-----------|--------|
| valid_zone_ratio > 0 | ✅ 62.3% |
| valid_zone_ratio >= 20% | ✅ |
| included_rows > 20 | ✅ 48 |
| inside/below/above >= 2 categories | ❌ only `above` |
| leakage PASS | ✅ |

## Checkpoint / Progress

- Progress logged every 10 anchors (`[date start]`, `[progress]`, `[date complete]`)
- Per-date report: `artifacts/reports/pit_sample_long_gamma_v1/per_date/2024-01-19.json`
- Resume: skip dates with `status=completed` in per_date report

## Next Step

**Can enter top 3 long-gamma dates build** (2024-01-19, 2024-05-03, 2024-06-07) — **not** 8-day or ML-P8B yet.

Label diversity (only `above` on this date) should be monitored across additional dates before baseline training.

## Not Done

- No 8-day Stage A+ build
- No model training
- No financial formula changes
- No label spec changes
