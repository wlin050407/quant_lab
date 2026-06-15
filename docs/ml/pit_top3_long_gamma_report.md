# ML-P7.6.4 Top 3 Long-Gamma Sample Build Report

**Phase:** ML-P7.6.4 — Top 3 Long-Gamma Sample Build  
**Config:** `config/ml/pit_sample_long_gamma_top3.yaml`  
**Branch:** `research/zdte-fusion-model`

## Ranking 说明

`candidate_ranking.json` 当前 **top 3 与任务指定日期不一致**：

| 来源 | Top 3 |
|------|-------|
| ranking 文件（全量 ingest 后） | 2024-01-19, **2024-10-04**, **2025-05-02** |
| 本阶段（long-γ + zone 导向） | **2024-01-19**, **2024-05-03**, **2024-06-07** |

本 build 使用后者（discovery long-γ 排名 #1/#4/#5），**未静默替换**。

Hourly scan 曾显示 2024-05-03 / 2024-06-07 为 long-γ 但 **0% valid zone**（`pin_distance_too_wide`）；regular_5min build 结果一致。

## Dry-Run 摘要

```text
dates: 2024-01-19, 2024-05-03, 2024-06-07
anchors per date: 77 × 3 = 231
missing partitions: none
ingest: disabled
expected runtime: ~346 min (estimate)
outputs: artifacts/datasets|features|reports/pit_sample_long_gamma_top3/
checkpoint: fresh (no prior top3 checkpoints)
```

## Build 命令

```bash
python scripts/build_pit_dataset_sample.py \
  --config config/ml/pit_sample_long_gamma_top3.yaml \
  --dates 2024-01-19,2024-05-03,2024-06-07 \
  --checkpoint-per-date \
  --progress-every 10
```

**实际耗时：** ~108 min（6458 s），exit 0。Progress / per-date checkpoint 正常工作。

## 汇总指标

| 指标 | 值 |
|------|-----|
| row_count | **231** |
| included_rows | **48** |
| excluded_rows | 183 |
| valid_zone_ratio (row-level) | **33.3%** (77/231 rows with zone label) |
| valid_zone_ratio (included-only) | **48/48 = 100%** of included have zone |
| null_label_count | 154 |
| feature_count | 198 |
| null_feature_count_mean | 12.0 |
| feature_quality_score | min 0.909 / max 0.978 / mean **0.927** |
| replay_quality_score | min 0.915 / max 0.949 / mean **0.929** |
| leakage validation | **PASS** |
| strict hash join | **PASS** (all 3 per-date reports) |
| replay time / anchor | **12.0 s** |
| feature time / row | **15.9 s** |
| raw_lake reused | ~860 MB |
| dataset / features / joined | ~1.56 MB / ~1.12 MB / ~1.28 MB |

## inside / below / above 分布

| 类别 | 计数 |
|------|------|
| above | 48 |
| inside | 0 |
| below | 0 |

**仅 1 个 label 类别**（与 ML-P7.6.3 单日结果一致）。

## Per-Date Coverage

| Date | day_type | anchors | included | valid_zone_ratio | close_location | replay s/anchor | feature s/row | runtime ~ |
|------|----------|---------|----------|------------------|----------------|-----------------|---------------|-----------|
| 2024-01-19 | monthly_opex | 77 | **48** | **62.3%** | above: 48 | 12.6 | 16.5 | ~37 min |
| 2024-05-03 | trend_up | 77 | 0 | **0%** | — | 12.0 | 15.4 | ~36 min |
| 2024-06-07 | normal | 77 | 0 | **0%** | — | 11.6 | 15.8 | ~35 min |

2024-05-03 / 2024-06-07：long-γ 但 **无 valid pin cluster**（与 hourly scan `pin_distance_too_wide` 一致）。

## Split Readiness

Mechanism validated; 3 sessions → train/val/test 各 1 session。**样本量不足，不可用于真实模型评估。**

## 判定：Case B（偏 C）

| 判据 | 结果 |
|------|------|
| valid_zone_ratio >= 20% | ✅ 33.3% (row-level) |
| included_rows >= 100 | ❌ **48** |
| >= 2 label 类别 | ❌ **仅 above** |
| leakage PASS | ✅ |
| strict join PASS | ✅ |

**结论：**

- Top 3 build **机制稳定**（checkpoint、progress、leakage、join 均 OK）
- **Zone label 实际仅来自 2024-01-19**；另 2 日 long-γ 但无 cluster
- **允许进入 top 5 / top 8** 以寻找 **类别多样性** 和更多 included rows
- **仍禁止 ML-P8B**（included < 100，单类 label，row_count << 1000）

## 下一步建议

1. 重跑 candidate ranking，按 **valid_zone_anchor_ratio** 而非 composite long-γ 排序选日期
2. 优先 ingest/scan 2024-10-04、2025-05-02（ranking 文件 top 2/3）看 regular_5min zone 是否优于 2024-05-03
3. Top 5–8 build 继续用 `--checkpoint-per-date --progress-every 10`
4. 若 top 8 仍单类 label → label governance（Option B: `primary_pin_distance` baseline）

## 限制遵守

- 未跑 8 日 build
- 未训练模型
- 未修改金融公式 / label spec
- 未 ingest
- artifacts 未提交

## Artifacts 路径

```text
artifacts/reports/pit_sample_long_gamma_top3/per_date/2024-01-19.json
artifacts/reports/pit_sample_long_gamma_top3/per_date/2024-05-03.json
artifacts/reports/pit_sample_long_gamma_top3/per_date/2024-06-07.json
artifacts/reports/pit_sample_long_gamma_top3/coverage_report.json
artifacts/reports/pit_sample_long_gamma_top3/leakage_validation.json
```
