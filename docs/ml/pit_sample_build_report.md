# ML-P7.5 Controlled Sample Dataset Build Report

**Phase:** ML-P7.5 — Controlled Historical Dataset Expansion  
**Branch:** `research/zdte-fusion-model`  
**Config:** `config/ml/pit_sample_v1.yaml`

## Executive summary

Batch pipeline for 20 curated trade dates is implemented and verified. **Real build: 1/20 dates succeeded** (2026-06-10 via pilot lake seed); **19/20 blocked** by missing raw lake partitions with `ingest.enabled=false`. Pipeline mechanics (replay → labels → features → strict join → reports) pass leakage validation on produced rows.

**Not suitable for ML-P8B training yet** — `valid_zone_ratio = 0%`, all primary zone labels null on pilot short-window fixture.

## Date list (20 configured)

| Date | day_type |
|------|----------|
| 2024-01-05 | normal |
| 2024-01-19 | monthly_opex |
| 2024-02-13 | high_vol |
| 2024-03-08 | trend_down |
| 2024-04-05 | range |
| 2024-05-03 | trend_up |
| 2024-06-07 | normal |
| 2024-07-03 | early_close |
| 2024-08-02 | high_vol |
| 2024-09-06 | normal |
| 2024-10-04 | monthly_opex |
| 2024-11-01 | trend_up |
| 2024-11-29 | early_close |
| 2024-12-06 | range |
| 2025-01-03 | normal |
| 2025-02-07 | high_vol |
| 2025-03-07 | trend_down |
| 2025-04-04 | monthly_opex |
| 2025-05-02 | recent |
| 2026-06-10 | pilot_fixture (manual anchors, pilot seed) |

## Dry-run summary

- **Total anchors (if all dates had data):** 1466 (77×19 + 3 pilot)
- **Missing partitions:** 140 gaps across 19 historical dates; pilot date resolvable via seed
- **Ingest enabled:** false (by design for controlled expansion)
- **Output paths:** `artifacts/raw_lake_sample/`, `artifacts/datasets/pit_sample_v1/`, `artifacts/features/pit_sample_v1/`, `artifacts/reports/pit_sample_v1/`

## Actual build summary

| Metric | Value |
|--------|-------|
| Rows built | 3 |
| Sessions | 1 (2026-06-10) |
| Anchors | 13:00:30, 13:01:00, 13:01:30 |
| Included rows (weight > 0) | 0 |
| Excluded rows | 3 |
| Failed dates | 19 |
| Leakage validation | **PASS** |

### Zone / label coverage

- `valid_zone_ratio`: **0.0**
- `close_location_distribution`: empty (no valid zone at pilot anchors)
- `null_label_count`: 3

### Feature quality

- `feature_quality_score`: 0.903 – 0.909 (mean 0.907)
- `replay_quality_score`: 0.95
- `null_feature_count_mean`: ~17.3 / row
- `gamma_source`: 100% `derived_black76_precomputed`
- `oi_unconfirmed_count`: 3

### Storage (gitignored artifacts)

| Artifact | Size |
|----------|------|
| raw_lake_sample | ~1.0 MB |
| dataset | ~45 KB |
| features | ~156 KB |
| joined | ~185 KB |

### Speed

- Replay: ~0.44 s / anchor
- Feature build: ~0.94 s / row

## Leakage validation

All checks passed on joined rows: no labels in features, no official_close in feature columns, source timestamps ≤ as_of, session-grouped split plan only.

## Split readiness

Split mechanism validated (`session_grouped`, walk-forward, locked holdout). **Sample size (1 session) insufficient for model evaluation.**

## Blockers for full 20-day expansion

1. **`ingest.enabled: false`** — historical dates need ThetaData entitlement + ingestion run per date
2. **Full RTH ingestion not wired in ML-P7.5** — pilot runner is short-window; full-day ingest is next ops step
3. **Pilot fixture** — 8 contracts, 2-minute window → no pin cluster zone → no primary labels

## ML-P8B readiness

**NOT READY** for GBDT baseline training:

- Only 1/20 dates built
- Zero valid zone labels
- Need full RTH raw lake + wider strike universe before training

Pipeline code **READY** for incremental date expansion once ingestion is enabled.

## Commands

```bash
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_v1.yaml --dry-run
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_v1.yaml --max-dates 20
```
