# ML-P7.8.4 — Baseline Dataset Gate Review

**Phase:** ML-P7.8.4 — Owner Review for Baseline Dataset Gate and P8A Entry  
**Branch:** `research/zdte-fusion-model`  
**Prior phase:** ML-P7.8.3 — Dataset Rebuild and Coverage Validation (`1b45e72`)  
**Evidence:** [`baseline_dataset_rebuild_validation_report.md`](baseline_dataset_rebuild_validation_report.md)  
**Config:** `config/ml/pit_sample_baseline_v1_1_validation.yaml`  
**Validation artifact:** `artifacts/reports/pit_sample_baseline_v1_1_validation/baseline_validation_report.json`（gitignore）

---

## Gate Status

```text
P7.8.3 dataset gate: PASS
ML-P8B training: still blocked
ML-P8A planning/harness: approved (see p8a_entry_approval_record.md)
Formal label_spec.md: unchanged (v1.0.0)
```

---

## Rebuild Scope

| 类别 | 值 |
|------|-----|
| rebuild_dates | **19** |
| skipped_dates | **1** (`2026-06-10` pilot fixture) |
| failed_dates | **0** |
| ingest | disabled |
| mode | **dataset-only**（无 feature builder / 无 joined build） |
| label_schema_version | `1.1.0-draft` |
| baseline_label_schema_version | `1.1.0-draft` |

### Rebuild dates（19）

```text
2024-01-05, 2024-01-19, 2024-02-13, 2024-03-08, 2024-04-05,
2024-05-03, 2024-06-07, 2024-07-03, 2024-08-02, 2024-09-06,
2024-10-04, 2024-11-01, 2024-11-29, 2024-12-06, 2025-01-03,
2025-02-07, 2025-03-07, 2025-04-04, 2025-05-02
```

---

## Coverage Summary

| 指标 | P7.8.3 Rebuild | P7.8 Screening 参考 |
|------|----------------|---------------------|
| row_count | **1391** | 1391 |
| baseline_eligible_rows | **1390** | 1390 |
| baseline_eligible_ratio | **99.9%** | 99.9% |
| eligible_sessions | **19 / 19** | 19 / 19 |
| zone_included_total | **89** | 89 |
| zone_valid_zone_ratio | **6.4%** | 6.4% |

**Exclusion reasons（rebuild）：**

| reason | count |
|--------|-------|
| remaining_em_invalid | 1 |

（2024-07-03 early_close 末 anchor，与 P7.8 一致）

---

## P1 0.25 Distribution

| 指标 | Rebuild | Screening | Δ |
|------|---------|-----------|---|
| near | **152** | 152 | 0 |
| not_near | **1238** | 1238 | 0 |
| both_classes | **true** | true | — |
| sessions dual-class | 5 | 5 | 0 |

---

## P1 0.50 Distribution

| 指标 | Rebuild | Screening | Δ |
|------|---------|-----------|---|
| near | **319** | 317 | +2 |
| not_near | **1071** | 1073 | -2 |
| both_classes | **true** | true | — |
| sessions dual-class | **12** | 12 | 0 |

+2 near @ 0.50 EM 在 tolerance（±3）内，与 screening **一致**。

---

## P2 0.25 Distribution

| 类 | Rebuild | Screening | Δ |
|----|---------|-----------|---|
| below | **512** | 512 | 0 |
| near | **152** | 152 | 0 |
| above | **726** | 726 | 0 |
| class_count_nonzero | **3** | 3 | — |

---

## P2 0.50 Distribution

| 类 | Rebuild | Screening | Δ |
|----|---------|-----------|---|
| below | **424** | 424 | 0 |
| near | **319** | 317 | +2 |
| above | **647** | 649 | -2 |
| class_count_nonzero | **3** | 3 | — |

P2 @ 0.50 与 P1 @ 0.50 同方向微小差异（±2），在 tolerance 内。

---

## P0 — `close_distance_to_primary_pin_em`

| 统计量 | Rebuild | Screening |
|--------|---------|-----------|
| count | 1390 | 1390 |
| mean | 0.678 EM | 0.669 EM |
| std | 3.934 | ~3.959 |
| min / max | -27.65 / +36.87 | 同量级 |
| p25 / p50 / p75 | -1.01 / 0.37 / 1.69 | -0.51 / 0.54 / 1.64 |
| p95 / p99 | 6.31 / 14.71 | 4.63 / 8.66 |

P0 均值/分位与 screening 有小幅差异（~1% mean），原因：rebuild 走完整 `compute_all_labels()` + parquet 浮点往返；screening 为同公式内存聚合。**baseline eligible 计数完全一致（1390）。**

---

## Zone Target Comparison

| 指标 | Rebuild | P7.6.7 / P7.8 zone 参考 |
|------|---------|-------------------------|
| zone_included_total | **89** | 89 |
| 有 zone 日期 | 4 | 4 |
| close_location 字段存在 | 1391 rows | — |
| 非 null zone label | **89** | 89 |
| valid_zone_ratio | **6.4%** | 6.4% |

**Legacy zone labels 仍存在且语义未改**；`close_location_vs_current_zone` 非 null 行数与 screening zone track 一致。

---

## Screening Consistency Result

```text
consistency_pass: true
baseline_eligible_rows: MATCH (1390)
p1_025_near: MATCH (152)
p1_050_near: MATCH within tolerance (319 vs 317)
zone_included_total: MATCH (89)
```

---

## Leakage Validation

| 检查项 | 结果 |
|--------|------|
| leakage_pass | **true** |
| violation_count | **0** |
| label_source_timestamp > as_of | 逐 row 验证 |
| features 未参与 label-only build | **true** |
| official_close label-only | **true** |
| deterministic inputs source timestamps ≤ as_of | **true** |

---

## Session-Grouped Split Readiness

| 指标 | 值 |
|------|-----|
| eligible_sessions | **19** |
| baseline_eligible_rows | **1390** |
| P1 0.50 both_classes | **true** |
| can_create_session_grouped_split | **true** |
| suggested train / val / test | **11 / 3 / 5** |
| row-level random split | **未使用 / 禁止** |

---

## What Passed

```text
✓ v1.1 draft baseline labels rebuilt on 19 complete dates
✓ baseline_eligible_rows = 1390 (≥ 300 gate)
✓ eligible_sessions = 19 (≥ 10 gate)
✓ P1 0.25 and P1 0.50 both have dual classes
✓ P2 0.25 and P2 0.50 three-class distribution present
✓ zone labels preserved (89 included, semantics unchanged)
✓ screening consistency PASS
✓ leakage PASS (violation_count = 0)
✓ session-grouped split readiness PASS
✓ no feature full build
✓ no training
✓ formal label_spec.md unchanged (v1.0.0)
✓ artifacts not committed
```

---

## What Remains Blocked

```text
✗ ML-P8B model training / model fitting
✗ Production backtest or trading signal publication
✗ Formal merge of addendum v1.1 into docs/ml/label_spec.md
✗ Modification of Pin/GEX/VEX/Expected Move/Valid Exit formulas
✗ Modification of Pin Zone thresholds
✗ Replacement or removal of zone labels
✗ Row-level random split for evaluation
✗ Feature full build for training purposes
✗ Ingest of new trade dates (unless separately authorized)
```

---

## Owner Gate Decision

```text
Owner:     Weitong Lin
Date:      2026-06-20
Decision:  P7.8.3 baseline dataset gate — PASS
           ML-P8A planning/harness — APPROVED (limited scope)
           ML-P8B training — BLOCKED
Notes:     Dataset rebuild metrics match P7.8 screening within tolerance.
           Zone track remains strict secondary. Baseline track is additive draft.
           P8A may plan harness only; no training in P8A.
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial gate review post-P7.8.3 PASS |

---

**End of gate review.**
