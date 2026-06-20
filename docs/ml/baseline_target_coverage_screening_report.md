# ML-P7.8 — Baseline Primary-Pin Target Coverage Screening Report

**Phase:** ML-P7.8 — Baseline Target Coverage Screening  
**Branch:** `research/zdte-fusion-model`  
**Script:** `scripts/screen_baseline_targets.py`  
**Module:** `src/quant_lab/ml/datasets/baseline_target_screening.py`  
**Owner approval:** ML-P7.7.2 — *Approved for ML-P7.8 screening only*

## Screening Source

```text
artifacts/raw_lake_sample/
anchor_type: regular_5min
ingest: disabled (no auto ingest)
pipeline: replay_state → build_as_of_context → compute_all_labels (label-only)
NOT run: feature build / joined build / model training / production label builder
```

**Summary artifact:** `artifacts/reports/baseline_target_screening_v1/summary.json`（gitignore）

## Proposed Targets Screened

| ID | Screening name | Type |
|----|----------------|------|
| P0 | `close_distance_to_primary_pin_em` | Regression |
| P1 | `close_near_primary_pin` @ 0.25 EM / 0.50 EM | Binary |
| P2 | `close_above_below_primary_pin` @ 0.25 EM / 0.50 EM | Directional (optional) |

**P0 定义：**

```text
close_distance_to_primary_pin_em =
    (official_close - primary_pin_t) / remaining_expected_move_t
```

## Raw Lake Inventory

| 类别 | 计数 | 说明 |
|------|------|------|
| complete_dates | **20** | 全部分区 complete |
| screened_dates | **19** | baseline screening 完成 |
| skipped_dates | **1** | `2026-06-10`（pilot fixture，replay spot NaN） |

### Screened Dates（19）

```text
2024-01-05, 2024-01-19, 2024-02-13, 2024-03-08, 2024-04-05,
2024-05-03, 2024-06-07, 2024-07-03, 2024-08-02, 2024-09-06,
2024-10-04, 2024-11-01, 2024-11-29, 2024-12-06, 2025-01-03,
2025-02-07, 2025-03-07, 2025-04-04, 2025-05-02
```

### Skipped Dates

| Date | 原因 |
|------|------|
| 2026-06-10 | pilot 分区，`ValueError: spot must be positive and finite`（与 P7.6.7 一致） |

## Coverage Summary

| 指标 | Baseline (P7.8) | Zone target (P7.6.7 参考) |
|------|-------------------|---------------------------|
| anchor_count_total | **1391** | 1391 |
| **eligible_rows** | **1390** | zone included = **89** |
| eligible_ratio | **99.9%** | valid_zone_ratio ≈ **6.4%** |
| eligible_sessions | **19** | 4 日有 zone 信号 |
| zone_included_total（对照） | 89 | 89 |

**结论：** baseline primary-pin target 覆盖率 **远高于** frozen Pin Zone target（1390 vs 89 rows，~15.6×）。Zone 稀疏是 composite gate 所致；baseline 仅要求 `primary_pin_t` + 正 finite `remaining_expected_move_t` + 官方收盘价。

## P0 — `close_distance_to_primary_pin_em`

| 统计量 | 值 |
|--------|-----|
| eligible_count | 1390 |
| mean | 0.669 EM |
| pooled_std | 3.959 EM |
| min | -27.65 EM |
| max | 36.87 EM |
| p01（per-date 加权近似） | ~0.00 |
| p05（加权近似） | ~0.00 |
| p25 | -0.51 |
| p50 | 0.54 |
| p75 | 1.64 |
| p95 | 4.63 |
| p99 | 8.66 |
| positive_count | 768 (55.3%) |
| negative_count | 622 (44.7%) |
| near_zero_count | 0 |
| outlier_count (\|d_em\| > 3) | 268 (19.3%) |

**null / exclusion reasons（全 lake）：**

| reason | count |
|--------|-------|
| remaining_em_invalid | 1 |

（2024-07-03 early_close 末 anchor 1 行）

## P1 — `close_near_primary_pin`

### 0.25 EM threshold

| 统计量 | 值 |
|--------|-----|
| eligible_count | 1390 |
| near_count | 152 |
| not_near_count | 1238 |
| near_ratio | **10.9%** |
| not_near_ratio | 89.1% |
| class_balance (near/not_near) | 0.123 |
| both_classes_present | **true** |
| sessions with both classes | **5 / 19** |

### 0.50 EM threshold

| 统计量 | 值 |
|--------|-----|
| eligible_count | 1390 |
| near_count | 317 |
| not_near_count | 1073 |
| near_ratio | **22.8%** |
| not_near_ratio | 77.2% |
| class_balance | 0.295 |
| both_classes_present | **true** |
| sessions with both classes | **12 / 19** |

**说明：** 本阶段仅输出候选 threshold 的 class balance；**未选择最终 threshold**，未做 train calibration。

### P1 按 session 有 near 信号的日期（0.25 EM）

```text
2024-02-13 (64/77), 2024-09-06 (28/77), 2024-10-04 (22/77),
2024-12-06 (1/77), 2025-04-04 (37/77)
```

## P2 — `close_above_below_primary_pin`（optional）

### 0.25 EM

| 类 | count | ratio |
|----|-------|-------|
| below | 512 | 36.8% |
| near | 152 | 11.0% |
| above | 726 | 52.2% |
| class_count_nonzero | **3** | — |

### 0.50 EM

| 类 | count | ratio |
|----|-------|-------|
| below | 424 | 30.5% |
| near | 317 | 22.8% |
| above | 649 | 46.7% |
| class_count_nonzero | **3** | — |

P2 为 optional 诊断；**不作为 P7.8 必须通过条件**。

## Leakage / PIT Validation

| 检查项 | 结果 |
|--------|------|
| leakage_pass | **true** |
| violation_count | **0** |
| primary_pin_t source timestamp ≤ as_of | 逐 anchor 验证 |
| label_source_timestamp > as_of_timestamp | 逐 anchor 验证 |
| official_close 仅作 label 未来信息 | 是 |
| feature builder 调用 | **无** |

## Session-Grouped Split Readiness

| 指标 | 值 |
|------|-----|
| session_count | 19 |
| eligible_sessions | 19 |
| eligible_rows_per_session (mean) | 73.2 |
| eligible_rows_per_session (min / max) | 40 / 77 |
| can_create_session_grouped_split | **true** |
| suggested train / val / test sessions | **11 / 3 / 5** |
| row-level random split | **未使用** |

## Comparison vs Zone Target

| 维度 | Zone (P7.6.7) | Baseline (P7.8) |
|------|---------------|-----------------|
| included / eligible rows | 89 | **1390** |
| anchor-level ratio | 6.4% | **99.9%** |
| 有信号 session 数 | 4 | **19** |
| 跨 session 类别多样性 | 稀疏（inside/below/above 分属不同日） | P1 0.25 有 5 session 双类；P2 全 lake 3 类 |
| 训练样本门槛 (≥300 rows) | **未达**（89） | **达到**（1390） |
| ML-P8B | **仍禁止** | **仍禁止**（screening ≠ 训练批准） |

**解读：** baseline target 解决的是 **coverage / split readiness** 问题，不替代 Pin Zone 的 regime-specific 语义。两者可并存于 addendum v1.1 proposal，但均需 owner 正式批准后方可进入 production label builder。

## P7.8 Gate Evaluation

| Gate | 要求 | 结果 |
|------|------|------|
| baseline_eligible_rows ≥ 300 | 1390 | **PASS** |
| eligible_sessions ≥ 10 | 19 | **PASS** |
| P1 both classes @ ≥1 threshold | 0.25 & 0.50 均 true | **PASS** |
| leakage PASS | violation=0 | **PASS** |
| session-grouped split readiness | true | **PASS** |
| no training performed | — | **PASS** |
| official label_spec.md unchanged | — | **PASS** |

**P7.8 总体：** **PASS**

**ML-P8B：** **仍 BLOCKED**（P7.8 pass 不自动批准训练或 production label builder）

## Recommended Next Stage

```text
ML-P7.8.1 — Baseline Label Builder Proposal / Implementation Plan
```

或

```text
ML-P7.8.1 — Owner Review for Baseline Target Implementation
```

**禁止自动进入 ML-P8B。**

## 性能

| 指标 | 值 |
|------|-----|
| anchors / date | 77（early_close: 41） |
| replay + label-only / anchor | ~12–16 s |
| runtime / date | ~16 min |
| 19 日总墙钟 | ~4.8 h（单次 run，exit 0） |

## 限制遵守

- 未运行 feature builder / joined builder
- 未训练模型
- 未 ingest 新日期
- 未修改 `docs/ml/label_spec.md`
- 未修改 production label builder / 金融公式
- 未将 primary-pin target 写入正式 approved target
- artifacts 未提交 git

## Tests & Ruff

```text
pytest tests/test_baseline_target_screening.py — 21 passed
pytest (full suite) — pass
ruff check baseline_target_screening.py screen_baseline_targets.py test_baseline_target_screening.py — pass
```

## Artifacts（本地，不提交）

```text
artifacts/reports/baseline_target_screening_v1/per_date/YYYY-MM-DD.json
artifacts/reports/baseline_target_screening_v1/summary.json
artifacts/reports/baseline_target_screening_v1/screening.log
```
