# ML-P7.6.5 Valid-Zone Top 3 Sample Build Report

**Phase:** ML-P7.6.5 — Valid-Zone Candidate Top Dates Build  
**Config:** `config/ml/pit_sample_valid_zone_top3.yaml`  
**Branch:** `research/zdte-fusion-model`

## Ranking Source

**File:** `artifacts/reports/pit_long_gamma_candidates_v1/candidate_ranking.json`  
**Scan:** full ingest run (19 dates, hourly anchors, terminal parity)

### Top 10 (by composite / valid_zone ranking)

| Rank | Date | day_type | long_γ ratio | valid zone ratio (hourly) | Dominant failure |
|------|------|----------|-------------|---------------------------|------------------|
| 1 | 2024-01-19 | monthly_opex | 100% | **67%** | secondary_strength, distance |
| 2 | 2024-10-04 | monthly_opex | 100% | **67%** | pin_distance_too_wide |
| 3 | 2025-05-02 | recent | 100% | **0%** | pin_distance_too_wide |
| 4 | 2024-05-03 | trend_up | 100% | 0% | pin_distance_too_wide |
| 5 | 2024-06-07 | normal | 100% | 0% | pin_distance_too_wide |
| 6 | 2024-07-03 | early_close | 100% | 0% | secondary_strength |
| 7 | 2024-12-06 | range | 100% | 0% | pin_distance |
| 8 | 2024-11-29 | early_close | 100% | 0% | pin_distance |
| 9 | 2025-01-03 | normal | 100% | 0% | pin_distance |
| 10 | 2024-03-08 | trend_down | 67% | 0% | pin_distance |

**Ranking top 3 = 2024-01-19, 2024-10-04, 2025-05-02** ✅（与任务指定一致）

> 注：2025-05-02 hourly scan valid_zone=0%，但因 composite 仍排 #3；regular_5min build 仅 1 included row。

## Valid-Zone Top Dates

```text
2024-01-19  — 复用 ML-P7.6.3/7.6.4 per-date report（未重跑）
2024-10-04  — 本次 build
2025-05-02  — 本次 build
```

## Dry-Run 摘要（2024-10-04, 2025-05-02）

```text
anchors: 77 × 2 = 154
missing partitions: none
ingest: disabled
outputs: artifacts/.../pit_sample_valid_zone_top3/
checkpoint: fresh
```

## Build 结果

**成功**，~74 min（4431 s），exit 0。Checkpoint / progress 正常。

## Per-Date Coverage (regular_5min)

| Date | 来源 | included | valid_zone_ratio | close_location | replay s/anchor | feature s/row |
|------|------|----------|------------------|----------------|---------------|---------------|
| 2024-01-19 | 复用 top3 report | **48** | **62.3%** | above: 48 | 12.6 | 16.5 |
| 2024-10-04 | 本次 build | **39** | **50.6%** | inside: 39 | 13.1 | 16.8 |
| 2025-05-02 | 本次 build | **1** | **1.3%** | below: 1 | 11.9 | 15.7 |

**关键发现：** 2024-10-04 产生 **inside** label（与 2024-01-19 的 **above** 不同）— 首次出现多类别多样性。

## Combined 三日统计

| 指标 | 值 |
|------|-----|
| combined row_count | **231** |
| combined included_rows | **88** |
| combined excluded_rows | 143 |
| combined valid_zone_ratio (row-level) | **38.1%** (88/231) |
| combined valid_zone (included-only) | **100%** (88/88 have zone label) |
| null_label (close_location) | 143 excluded rows |

### inside / below / above（included rows only）

| 类别 | 计数 | 日期 |
|------|------|------|
| **above** | 48 | 2024-01-19 |
| **inside** | 39 | 2024-10-04 |
| **below** | 1 | 2025-05-02 |

**≥ 2 类别：✅（3 类别）**

### 质量指标（combined 估算）

| 指标 | 值 |
|------|-----|
| feature_count | 198 |
| feature_quality_score | ~0.93–0.95 mean |
| replay_quality_score | ~0.93 mean |
| leakage validation | **PASS** |
| strict hash join | **PASS**（3 日均为 true） |
| replay time / anchor | ~12.5 s |
| feature time / row | ~16.2 s |
| raw_lake reused | ~860 MB |
| joined (2-day build) | ~924 KB |

2024-01-19 报告来源：`artifacts/reports/pit_sample_long_gamma_top3/per_date/2024-01-19.json`

## 判定：Case B（偏 A）

| 判据 | 结果 |
|------|------|
| valid_zone_ratio >= 20% | ✅ 38.1% |
| included_rows >= 100 | ❌ **88** |
| >= 2 label 类别 | ✅ **above + inside + below** |
| leakage PASS | ✅ |
| strict join PASS | ✅ |

**结论：**

- **valid-zone ranking 优于 long-γ composite ranking**（2024-10-04 贡献 39 inside rows）
- **允许进入 top 5 valid-zone candidate build** 以扩大 included 和类别平衡
- **仍禁止 ML-P8B**（included < 100，row_count < 1000）
- 2025-05-02 hourly rank #3 但 regular_5min 几乎无 zone — ranking 应优先 **valid_zone_anchor_ratio** 而非 composite

## 与 ML-P7.6.4 对比

| 策略 | 日期 | included | 类别 |
|------|------|----------|------|
| long-γ top 3 | 01-19, 05-03, 06-07 | 48 | above only |
| valid-zone top 3 | 01-19, 10-04, 05-02 | **88** | **above + inside + below** |

## 限制遵守

- 未跑 8 日 / Stage B / ML-P8B
- 未训练模型
- 未修改金融公式 / label spec
- 未 ingest
- artifacts 未提交

## Artifacts

```text
artifacts/reports/pit_sample_valid_zone_top3/per_date/2024-10-04.json
artifacts/reports/pit_sample_valid_zone_top3/per_date/2025-05-02.json
artifacts/reports/pit_sample_valid_zone_top3/coverage_report.json
artifacts/reports/pit_sample_long_gamma_top3/per_date/2024-01-19.json  (reused)
```
