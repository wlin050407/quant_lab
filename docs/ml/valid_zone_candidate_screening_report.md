# ML-P7.6.7 Regular-5min Valid-Zone Candidate Screening Report

**Phase:** ML-P7.6.7 — Regular-5min Valid-Zone Candidate Screening  
**Branch:** `research/zdte-fusion-model`  
**Script:** `scripts/screen_valid_zone_candidates.py`  
**Module:** `src/quant_lab/ml/datasets/valid_zone_screening.py`

## Screening Source

```text
artifacts/raw_lake_sample/
anchor_type: regular_5min
ingest: disabled (no auto ingest)
pipeline: replay_state → compute_deterministic_bundle → label coverage only
NOT run: feature build / joined build / model training
```

**Summary artifact:** `artifacts/reports/valid_zone_candidate_screening_v1/summary.json`（gitignore）

## Raw Lake Inventory

| 类别 | 计数 | 说明 |
|------|------|------|
| complete_dates | **20** | 全部分区 complete |
| incomplete_dates | **0** | — |
| screened_dates | **19** | regular_5min screening 完成 |
| skipped_dates | **1** | `2026-06-10`（pilot fixture，replay spot NaN） |

### Complete Raw Lake Dates（20）

```text
2024-01-05, 2024-01-19, 2024-02-13, 2024-03-08, 2024-04-05,
2024-05-03, 2024-06-07, 2024-07-03, 2024-08-02, 2024-09-06,
2024-10-04, 2024-11-01, 2024-11-29, 2024-12-06, 2025-01-03,
2025-02-07, 2025-03-07, 2025-04-04, 2025-05-02, 2026-06-10
```

### Skipped Dates

| Date | 原因 |
|------|------|
| 2026-06-10 | `ValueError: spot must be positive and finite`（pilot 分区，非生产候选） |

## Ranking 规则（新，非 composite long-γ）

```text
1. included_count DESC
2. valid_zone_ratio DESC
3. label_diversity_score DESC
4. rare_label_bonus（inside/below 优先）
5. mean_replay_quality DESC
6. runtime_seconds ASC
```

## Top Dates by included_count

| Rank | Date | included | valid_zone_ratio | inside | below | above |
|------|------|----------|------------------|--------|-------|-------|
| 1 | 2024-01-19 | **48** | 62.3% | 0 | 0 | 48 |
| 2 | 2024-10-04 | **39** | 50.6% | 39 | 0 | 0 |
| 3 | 2025-05-02 | **1** | 1.3% | 0 | 1 | 0 |
| 4 | 2025-01-03 | **1** | 1.3% | 0 | 0 | 1 |
| — | 其余 15 日 | **0** | 0% | — | — | — |

**全 lake 仅 4 日有 included > 0**（与 P7.6.6 full build 结论一致并扩展发现 `2025-01-03`）。

## Top Dates by valid_zone_ratio

与 included_count 排名相同（有 zone 的仅上述 4 日）。

## Top Dates by Label Diversity

| Date | diversity | 类别 |
|------|-----------|------|
| 2024-01-19 | 1 | above |
| 2024-10-04 | 1 | inside |
| 2025-05-02 | 1 | below |
| 2025-01-03 | 1 | above |

**跨日合并仍仅 3 类**（above / inside / below），但**无单日同时含多类**。

## inside / below / above 分布

| 类别 | 有贡献的日期 |
|------|-------------|
| **inside** | 2024-10-04 |
| **below** | 2025-05-02 |
| **above** | 2024-01-19, 2025-01-03 |

## Known Negative Controls

| Date | screening included | full build included | 结论 |
|------|-------------------|---------------------|------|
| 2024-05-03 | **0** | **0** | 维持 negative control |
| 2024-06-07 | **0** | **0** | 维持 negative control |

除非 screening 结果变化，**不得**推荐进入下一轮 full build。

## Already Full-Built（P7.6.3–7.6.6）

```text
2024-01-19, 2024-10-04, 2025-05-02, 2024-05-03, 2024-06-07
```

## Recommended Next Full-Build Dates

**仅 1 日满足「尚未 full-built + included > 0」：**

```text
2025-01-03  — screening included=1, above=1, valid_zone_ratio=1.3%
```

**无法凑满 2–4 日。** 其余 15 个已扫描 complete 日期 screening included=0。

### 建议的下一轮动作（仍属 ML-P7，非 P8B）

1. **可选：** 对 `2025-01-03` 做单日 full build（验证 screening 1-row 信号是否可复现）。
2. **必须：** 扩展 raw lake（新 trade dates）或 label governance Option B，再跑 screening；**不要**按 composite tie-break 盲目 top8 full build。
3. **禁止推荐 top8：** 当前 20 日 complete lake 中仅 4 日有 zone 信号，top8 full build 预计 ~6 日零贡献 + 重复劳动，无法把 `included_rows` 推过 100。

## 与 P7.6.6 / Hourly Scan 对比

| 方法 | 2024-05-03 | 2024-06-07 | 2024-10-04 |
|------|------------|------------|------------|
| hourly scan (P7.6.2) | valid_zone=0% | valid_zone=0% | valid_zone=67% |
| regular_5min screening | included=0 | included=0 | included=39 |
| full build (P7.6.6) | included=0 | included=0 | included=39 |

**regular_5min screening 与 full build label 阶段一致**，可用于选日；composite ranking 仍不可靠。

## 性能

| 指标 | 值 |
|------|-----|
| anchors / date | 77（early_close: 41） |
| replay-only / anchor | ~12–16 s |
| runtime / date | ~15–20 min |
| 19 日总墙钟 | ~6 h（分两次 resume） |

## 限制遵守

- 未运行 feature builder / joined builder
- 未训练模型
- 未 ingest 新日期
- 未修改金融公式 / label spec
- 未跑 top8 full build
- artifacts 未提交 git

## Tests & Ruff

```text
pytest tests/test_valid_zone_candidate_screening.py — 15 passed
ruff check scripts/screen_valid_zone_candidates.py src/quant_lab/ml/datasets/valid_zone_screening.py tests/test_valid_zone_candidate_screening.py — pass
```

## ML-P8B 状态

**仍禁止。** 即使合并 4 个有信号日期的 screening included，也仅 **89 rows**（48+39+1+1），远低于 P8B 门槛（included ≥ 100，row_count ≥ 1000）。

## 是否允许下一轮 2–4 日期 full build

**条件允许 1 日**（`2025-01-03`），**不足以**构成有意义的 2–4 日扩样；需先扩展 raw lake 或 label governance。

## 关于 P7.6.6 Git Commit（用户追问）

**已提交。** Commit `ee99b1e` 包含：

```text
config/ml/pit_sample_valid_zone_top5.yaml
docs/ml/pit_valid_zone_top5_report.md
```

**未提交** `sample_builder.py` / `reporting.py` / `point_in_time.py` — 因 P7.6.6 无 builder 代码改动，仅 config + 报告。`build_pit_dataset_sample.py` 等能力在更早 commit（如 `d221c92` P7.6.3）已提交。
