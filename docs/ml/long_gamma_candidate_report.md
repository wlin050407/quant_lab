# ML-P7.6.2 Long-Gamma Candidate Discovery Report

**Phase:** ML-P7.6.2 — Long-Gamma Candidate Discovery and Zone Coverage Rebuild  
**Branch:** `research/zdte-fusion-model`  
**ML-P7.6.1 commit:** `295ae3a`  
**ML-P7.6.2 commit:** `9fee323`

## Objective

Verify whether **long-γ / high pin-reliability** sessions produce valid Pin Zone labels under the frozen deterministic contract.

## Candidate Date Sources

| Source | Count | Notes |
|--------|-------|-------|
| Config `pit_long_gamma_candidates_v1.yaml` | 19 | normal, range, opex, early_close, high_vol |
| Raw lake at scan start | 3 | Stage A baseline |
| Newly ingested (prior partial run) | 5 | 2024-01-19 … 2024-05-03 |
| Scannable at full scan | **9** | incl. 2024-06-07 completed during ingest |
| Still missing (ingest not run) | 10 | 2024-08-02 … 2025-05-02 |

## Scan Method

Per date, **6 hourly anchors** (3 on early_close):

```text
10:00, 11:00, 12:00, 13:00, 14:00, 15:00 ET
```

Terminal parity path: `regime_from_net_gex` + `pin_reliability` → `detect_pin_cluster`.

## Full Scan Results (9 lake dates, ~19 min)

### Top 10 Candidates

| Rank | Date | day_type | long_γ ratio | valid zone ratio | Dominant failure |
|------|------|----------|-------------|------------------|------------------|
| 1 | **2024-01-19** | monthly_opex | **100%** | **67%** | secondary_strength (1), distance (1) |
| 2 | 2024-05-03 | trend_up | 100% | 0% | pin_distance_too_wide |
| 3 | 2024-06-07 | normal | 100% | 0% | pin_distance_too_wide |
| 4 | 2024-07-03 | early_close | 100% | 0% | secondary_strength_too_low |
| 5 | 2024-03-08 | trend_down | 67% | 0% | pin_distance_too_wide |
| 6 | 2024-04-05 | range | 17% | 0% | short_gamma_regime |
| 7 | 2024-02-13 | high_vol | 0% | 0% | short_gamma_regime |
| 8 | 2025-04-04 | monthly_opex | 0% | 0% | short_gamma_regime |
| 9 | 2024-01-05 | normal | 0% | 0% | short_gamma_regime |

### Aggregate (9 scannable dates)

```text
long_gamma_anchor_ratio_mean: 53.7%
valid_zone_anchor_ratio_mean: 7.4%
dates_with_any_valid_zone: 1 (2024-01-19)
```

**Key finding:** Long-γ date selection works — **2024-01-19** produces valid zones on 4/6 hourly anchors. Original Stage A dates were short-γ biased.

## Stage A+ Rebuild

Config: `config/ml/pit_sample_long_gamma_v1.yaml`  
Top **8** dates (all lake-complete):

```text
2024-01-19, 2024-05-03, 2024-06-07, 2024-07-03,
2024-03-08, 2024-04-05, 2024-02-13, 2025-04-04
```

Outputs:

```text
artifacts/datasets/pit_sample_long_gamma_v1/
artifacts/features/pit_sample_long_gamma_v1/
artifacts/reports/pit_sample_long_gamma_v1/
```

### Stage A+ Results (8-date build)

See `artifacts/reports/pit_sample_long_gamma_v1/coverage_report.json` after build completes.

Prior 3-date smoke (same top-3 subset): 195 rows, leakage PASS, valid_zone_ratio=0% (no 2024-01-19).

## Label Spec Verdict

**Partial Case 1 signal:** Hourly scan shows zone labels **can** be produced on long-γ opex days.  
**Stage A+ gate TBD:** Need full `regular_5min` build to measure `valid_zone_ratio` on ~600 rows.

If 8-date build yields `valid_zone_ratio >= 20%` → zone label viable with long-γ-aware sampling.  
If still < 20% → see `docs/ml/label_spec_governance_options.md` (Option B recommended).

## Restrictions Honored

- No ML-P8B / no model training
- No Pin/GEX/VEX/Expected Move formula changes
- No label spec mutation
- No raw/dataset artifacts committed

## Commands

```bash
python scripts/discover_long_gamma_candidates.py \
  --config config/ml/pit_long_gamma_candidates_v1.yaml --max-dates 19 --top-n 10

python scripts/build_pit_dataset_sample.py \
  --config config/ml/pit_sample_long_gamma_v1.yaml --max-dates 8
```
