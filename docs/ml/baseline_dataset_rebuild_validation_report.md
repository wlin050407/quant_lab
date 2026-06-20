# ML-P7.8.3 — Baseline Dataset Rebuild and Coverage Validation Report

**Phase:** ML-P7.8.3 — Dataset Rebuild and Coverage Validation  
**Branch:** `research/zdte-fusion-model`  
**Config:** `config/ml/pit_sample_baseline_v1_1_validation.yaml`  
**Build:** `scripts/build_pit_dataset_sample.py --dataset-only` (via config `build.dataset_only: true`)

## Status

```text
ML-P7.8.3: PASS
ML-P8B: BLOCKED
Training: NOT performed
Feature full build: NOT performed
Formal label_spec.md: UNCHANGED (v1.0.0)
```

**Validation artifact:** `artifacts/reports/pit_sample_baseline_v1_1_validation/baseline_validation_report.json`（gitignore）

## Rebuild Scope

| 类别 | 值 |
|------|-----|
| rebuild_dates | **19** |
| skipped_dates | **1** (`2026-06-10` pilot fixture) |
| failed_dates | **0** |
| ingest | disabled |
| mode | **dataset-only**（无 feature builder / 无 joined build） |

### Rebuild dates（19）

```text
2024-01-05, 2024-01-19, 2024-02-13, 2024-03-08, 2024-04-05,
2024-05-03, 2024-06-07, 2024-07-03, 2024-08-02, 2024-09-06,
2024-10-04, 2024-11-01, 2024-11-29, 2024-12-06, 2025-01-03,
2025-02-07, 2025-03-07, 2025-04-04, 2025-05-02
```

## Coverage Summary

| 指标 | Rebuild (P7.8.3) | P7.8 Screening 参考 |
|------|------------------|---------------------|
| row_count | **1391** | 1391 |
| baseline_eligible_rows | **1390** | 1390 |
| baseline_eligible_ratio | **99.9%** | 99.9% |
| eligible_sessions | **19** | 19 |
| zone_included_total | **89** | 89 |
| zone_valid_zone_ratio | **6.4%** | 6.4% |

**Exclusion reasons（rebuild）：**

| reason | count |
|--------|-------|
| remaining_em_invalid | 1 |

（2024-07-03 early_close 末 anchor，与 P7.8 一致）

## P0 — `close_distance_to_primary_pin_em`

| 统计量 | Rebuild | Screening |
|--------|---------|-----------|
| count | 1390 | 1390 |
| mean | 0.678 EM | 0.669 EM |
| std | 3.934 | ~3.959 (pooled) |
| min / max | -27.65 / +36.87 | 同量级 |
| p25 / p50 / p75 | -1.01 / 0.37 / 1.69 | -0.51 / 0.54 / 1.64 |
| p95 / p99 | 6.31 / 14.71 | 4.63 / 8.66 |

P0 均值/分位与 screening 有小幅差异（~1% mean），原因：rebuild 走完整 `compute_all_labels()` + parquet 浮点往返；screening 为同公式内存聚合。**baseline eligible 计数完全一致（1390）。**

## P1 — Class Balance

### 0.25 EM

| 指标 | Rebuild | Screening | Δ |
|------|---------|-----------|---|
| near | **152** | 152 | 0 |
| not_near | 1238 | 1238 | 0 |
| both_classes | **true** | true | — |

### 0.50 EM（preferred first binary eval）

| 指标 | Rebuild | Screening | Δ |
|------|---------|-----------|---|
| near | **319** | 317 | +2 |
| not_near | 1071 | 1073 | -2 |
| both_classes | **true** | true | — |
| sessions dual-class | **12** | 12 | 0 |

+2 near @ 0.50 EM 在 tolerance（±3）内，与 screening **一致**。

## P2 — Directional（optional）

### 0.25 EM

| 类 | Rebuild | Screening |
|----|---------|-----------|
| below | 512 | 512 |
| near | 152 | 152 |
| above | 726 | 726 |

### 0.50 EM

| 类 | Rebuild | Screening |
|----|---------|-----------|
| below | 424 | 424 |
| near | 319 | 317 |
| above | 647 | 649 |

P2 @ 0.50 与 P1 @ 0.50 同方向微小差异（±2），在 tolerance 内。

## Zone Target Comparison

| 指标 | Rebuild | P7.6.7 / P7.8 zone 参考 |
|------|---------|-------------------------|
| zone_included_total | **89** | 89 |
| 有 zone 日期 | 4 | 4 |
| close_location 字段存在 | 1391 rows | — |
| 非 null zone label | **89** | 89 |

**Legacy zone labels 仍存在且语义未改**；`close_location_vs_current_zone` 非 null 行数与 screening zone track 一致。

## Screening Consistency Check

```text
consistency_pass: true
baseline_eligible_rows: MATCH (1390)
p1_025_near: MATCH (152)
p1_050_near: MATCH within tolerance (319 vs 317)
zone_included_total: MATCH (89)
```

## Leakage Validation

| 检查项 | 结果 |
|--------|------|
| leakage_pass | **true** |
| violation_count | **0** |
| label_source_timestamp > as_of | 逐 row 验证 |
| features 未参与 label-only build | **true** |
| official_close label-only | **true** |

## Session-Grouped Split Readiness

| 指标 | 值 |
|------|-----|
| eligible_sessions | 19 |
| baseline_eligible_rows | 1390 |
| P1 0.50 both_classes | **true** |
| can_create_session_grouped_split | **true** |
| suggested train / val / test | **11 / 3 / 5** |
| row-level random split | **未使用** |

## v1.1 Draft Label Fields

全部 1391 rows 包含：

```text
labels.close_distance_to_primary_pin_points
labels.close_distance_to_primary_pin_em
labels.close_near_primary_pin_025
labels.close_near_primary_pin_050
labels.close_above_below_primary_pin_025
labels.close_above_below_primary_pin_050
labels.baseline_target_eligible
labels.baseline_target_exclusion_reasons
labels.baseline_label_schema_version = 1.1.0-draft
```

Manifest：`artifacts/datasets/pit_sample_baseline_v1_1_validation/manifest.json`（gitignore）

## Artifacts Produced（未提交 git）

```text
artifacts/datasets/pit_sample_baseline_v1_1_validation/
artifacts/reports/pit_sample_baseline_v1_1_validation/
  baseline_validation_report.json
  p783_gates.json
  per_date/*.json
  rebuild.log
```

## P7.8.3 Gate Evaluation

| Gate | Result |
|------|--------|
| dataset rebuilt with v1.1 draft labels | **PASS** |
| baseline_eligible_rows ≥ 300 | **PASS** (1390) |
| eligible_sessions ≥ 10 | **PASS** (19) |
| P1 0.50 both classes | **PASS** |
| leakage PASS | **PASS** |
| session-grouped split readiness | **PASS** |
| zone labels present | **PASS** |
| screening consistency | **PASS** |
| no feature full build | **PASS** |
| no training | **PASS** |
| label_spec.md unchanged | **PASS** |

**P7.8.3 overall: PASS**

**ML-P8B: BLOCKED**

## Next Stage

```text
ML-P7.8.4 — Owner Review for Baseline Dataset Gate
```

或

```text
ML-P8A — Baseline Modeling Harness Plan
```

（均不得直接训练模型）

## Tests & Ruff

```text
tests/test_baseline_dataset_validation.py — 14 passed
tests/test_baseline_label_builder.py — 19 passed
tests/test_baseline_target_screening.py — 21 passed
full pytest — pass
ruff — pass
```
