# ML-P7.6.6 Valid-Zone Top 5 Sample Build Report

**Phase:** ML-P7.6.6 — Valid-Zone Top 5 Sample Build  
**Config:** `config/ml/pit_sample_valid_zone_top5.yaml`  
**Branch:** `research/zdte-fusion-model`  
**Prior commit (P7.6.5):** `2dc09de`

## Ranking Source

**File:** `artifacts/reports/pit_long_gamma_candidates_v1/candidate_ranking.json`  
**Scan:** 19 dates, hourly anchors, terminal parity (ML-P7.6.2)

### Ranking Top 10（`top_candidates`，按 `composite_score`）

| Rank | Date | day_type | long_γ ratio | valid zone ratio (hourly) | Dominant failure |
|------|------|----------|-------------|---------------------------|------------------|
| 1 | 2024-01-19 | monthly_opex | 100% | **67%** | secondary_strength, pin_distance |
| 2 | 2024-10-04 | monthly_opex | 100% | **67%** | pin_distance_too_wide |
| 3 | 2025-05-02 | recent | 100% | 0% | pin_distance_too_wide |
| 4 | 2024-05-03 | trend_up | 100% | 0% | pin_distance_too_wide |
| 5 | 2024-06-07 | normal | 100% | 0% | pin_distance_too_wide |
| 6 | 2024-07-03 | early_close | 100% | 0% | secondary_strength_too_low |
| 7 | 2024-12-06 | range | 100% | 0% | pin_distance_too_wide |
| 8 | 2024-11-29 | early_close | 100% | 0% | pin_distance_too_wide |
| 9 | 2025-01-03 | normal | 67% | 0% | pin_distance_too_wide |
| 10 | 2024-03-08 | trend_down | 67% | 0% | pin_distance_too_wide |

**Aggregate scan:** `dates_with_any_valid_zone = 2`（仅 2024-01-19、2024-10-04 hourly 有 zone 信号）

### 已完成日期（P7.6.5，未重跑）

```text
2024-01-19
2024-10-04
2025-05-02
```

### 本次新增日期

```text
2024-05-03  — composite rank #4，hourly valid_zone=0%
2024-06-07  — composite rank #5，hourly valid_zone=0%
```

### 为何选择这两日

1. Top 3 valid-zone 日期已在 P7.6.5 完成；按 composite 排名，尚未 build 的下两名即为 #4/#5。
2. 二者 `long_gamma_anchor_ratio=100%`，`failure_reason_distribution` 以 `pin_distance_too_wide` 为主，与已验证有 zone 的 opex 日不同，但仍值得用 `regular_5min` 全锚点验证。
3. **预期风险：** hourly scan 已显示 `valid_zone_anchor_ratio=0%`；本阶段目的是验证 tie-break 扩样是否能把 `included_rows` 推过 100。

## Valid-Zone Top 5 日期

```text
2024-01-19  — 复用 P7.6.3/7.6.5 per-date report
2024-10-04  — 复用 P7.6.5 per-date report
2025-05-02  — 复用 P7.6.5 per-date report
2024-05-03  — 本次 build
2024-06-07  — 本次 build
```

## Dry-Run 摘要（2024-05-03, 2024-06-07）

```text
dates: 2024-05-03, 2024-06-07
anchors per date: 77 × 2 = 154
existing raw lake partitions: complete（两日均在 raw_lake_sample）
missing raw lake partitions: none
ingest.enabled: false
expected rows: 154
output paths:
  artifacts/datasets/pit_sample_valid_zone_top5/
  artifacts/features/pit_sample_valid_zone_top5/
  artifacts/reports/pit_sample_valid_zone_top5/
resume/checkpoint: fresh（--no-resume 语义下的新 per-date checkpoint）
```

## Build 结果（新增两日）

**成功**，exit 0。Checkpoint / progress / per-date report 正常。

| 信号 | 2024-05-03 | 2024-06-07 |
|------|------------|------------|
| `[date start]` | anchors=77 | anchors=77 |
| `[progress]` | 每 10 anchors | 每 10 anchors |
| `[date complete]` | rows=77 included=0 | rows=77 included=0 |
| leakage | PASS | PASS |
| strict hash join | PASS | PASS |

**耗时（新增两日）：** ~10.3 h 总墙钟；anchor 阶段 ~938 s / ~891 s；2024-05-03 feature 阶段异常慢（~443 s/row mean）。

## Per-Date Coverage（regular_5min，五日复用合并）

| Date | 来源 | rows | included | valid_zone_ratio | close_location | replay s/anchor | feature s/row |
|------|------|------|----------|------------------|----------------|---------------|---------------|
| 2024-01-19 | 复用 top3 | 77 | **48** | **62.3%** | above: 48 | 12.6 | 16.5 |
| 2024-10-04 | 复用 top3 | 77 | **39** | **50.6%** | inside: 39 | 13.1 | 16.8 |
| 2025-05-02 | 复用 top3 | 77 | **1** | **1.3%** | below: 1 | 11.9 | 15.7 |
| 2024-05-03 | 本次 build | 77 | **0** | **0%** | — | 12.2 | 443.4* |
| 2024-06-07 | 本次 build | 77 | **0** | **0%** | — | 11.6 | 14.7 |

\*2024-05-03 feature 阶段离群慢，与 P7.6.4 同类现象一致。

## Combined 五日统计（per-date report 合并，未重跑前三日）

| 指标 | 值 |
|------|-----|
| row_count | **385** |
| included_rows | **88**（与 P7.6.5 相同，**+0**） |
| excluded_rows | 297 |
| valid_zone_ratio (row-level) | **22.9%** (88/385) |
| valid_zone_ratio by date | 62.3% / 50.6% / 1.3% / 0% / 0% |
| null_label_count | 297（excluded rows） |
| feature_count | 198 |
| null_feature_count_mean | ~13.3（五日加权） |

### inside / below / above（included rows only）

| 类别 | 合计 | 按日 |
|------|------|------|
| **above** | 48 | 2024-01-19 |
| **inside** | 39 | 2024-10-04 |
| **below** | 1 | 2025-05-02 |

**≥ 2 类别：✅（3 类别）**

### 质量指标（combined）

| 指标 | min | max | mean |
|------|-----|-----|------|
| feature_quality_score | 0.914 | 0.954 | ~0.929 |
| replay_quality_score | 0.929 | 0.937 | ~0.931 |

| 检查项 | 结果 |
|--------|------|
| leakage validation | **PASS**（5 日 per-date 均为 true；本次 2 日 build `leakage_validation.json` passed） |
| strict hash join | **PASS**（5 日均为 true） |
| split readiness | 样本不足，仅机制验证（`no_row_level_random_split: true`） |
| average replay time / anchor | ~12.3 s |
| average feature build time / row | ~101 s（含 05-03 离群）；除离群日 ~16 s |
| per-date runtime（新增） | 05-03 ~938 s anchor + 慢 feature；06-07 ~891 s anchor |
| raw_lake reused | ~860 MB / 日 |
| dataset / features / joined（本次 2 日 build） | ~1.1 MB / ~0.8 MB / ~0.9 MB |

**Per-date report 路径：**

```text
artifacts/reports/pit_sample_long_gamma_top3/per_date/2024-01-19.json
artifacts/reports/pit_sample_valid_zone_top3/per_date/2024-10-04.json
artifacts/reports/pit_sample_valid_zone_top3/per_date/2025-05-02.json
artifacts/reports/pit_sample_valid_zone_top5/per_date/2024-05-03.json
artifacts/reports/pit_sample_valid_zone_top5/per_date/2024-06-07.json
```

## 判定

| 判据 | Case A | Case B | 实际 |
|------|--------|--------|------|
| valid_zone_ratio ≥ 20% | ✅ | ✅ | ✅ **22.9%** |
| included_rows | ≥ 150 | ≥ 100 | ❌ **88**（无增量） |
| ≥ 2 label 类别 | ✅ | ✅ | ✅ 3 类 |
| leakage PASS | ✅ | ✅ | ✅ |
| strict join PASS | ✅ | ✅ | ✅ |

**结论：未达 Case A / Case B；tie-break 扩样失败。**

- composite rank #4/#5（2024-05-03、2024-06-07）在 `regular_5min` 下 **included=0**，与 P7.6.4 long-γ top 3 一致。
- **禁止按当前 ranking tie-break 直接进入 ML-P8B**（`included_rows < 100`，`row_count << 1000`）。
- **不建议**继续按 composite #6–#10 盲目扩 top 8（hourly scan 均为 `valid_zone_anchor_ratio=0%`）。
- **下一步（仍属 ML-P7，非 P8B）：** 重跑 candidate scan 并以 `valid_zone_anchor_ratio` 为主排序；或探索未扫日期 / label governance Option B；目标是把 `included_rows` 推过 100 后再议 top 8。

### 是否允许 top 8

| 问题 | 答案 |
|------|------|
| 按 Case A（included ≥ 150） | **否** |
| 按 Case B（included ≥ 100） | **否** |
| 按 P7.6.5 预判的「valid-zone top 5 扩样」 | **已执行，未达标** |
| 建议 | 换选日策略后再议 top 8，**非** composite tie-break |

### 是否仍禁止 ML-P8B

**是。** `included_rows=88`，`row_count=385`，`p8b_readiness.ready_for_ml_p8b=false`。

## 与 P7.6.5 对比

| 指标 | Top 3 (P7.6.5) | Top 5 (P7.6.6) | Δ |
|------|----------------|----------------|---|
| row_count | 231 | 385 | +154 |
| included_rows | 88 | 88 | **0** |
| valid_zone_ratio | 38.1% | 22.9% | −15.2 pp |
| label 类别 | 3 | 3 | 无变化 |

新增 154 行全部为 excluded，稀释了 row-level valid_zone_ratio，未增加训练可用样本。

## 限制遵守

- 未跑 8 日 build / Stage B / ML-P8B
- 未训练模型
- 未修改金融公式 / label spec / feature schema
- `ingest.enabled = false`
- artifacts / parquet 未提交 git

## Tests & Ruff

```text
pytest tests/test_ml_sample_builder.py tests/test_ml_dataset_reporting.py — 22 passed
ruff check (builder/reporting/script/tests) — All checks passed
```

无 builder/reporting 代码修改。
