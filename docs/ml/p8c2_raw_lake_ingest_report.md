# ML-P8C.2 Raw Lake Ingest 报告

**阶段：** ML-P8C.2 — Actual Controlled Ingest / Raw Lake Expansion  
**状态：** **COMPLETE**  
**Gate：** **PASS**（21/21 frozen dates terminal；lake partition 实扫 21/21 complete）

---

## 1. 目标

对 P8C.1.1 owner 冻结的 **21 个日期**执行 **raw lake ingest only**：

- 写入 `artifacts/raw_lake_sample` partitions + per-date manifests
- 记录 per-date success / failure / skipped / incomplete
- 支持 resume；**不替换**失败日期
- **禁止** dataset build、feature build、`.fit()`、P8B.4

---

## 2. 冻结日期列表（21 日，不可修改）

全部 21 日 **status = success**，**pending = 0**。

| trade_date | early_close |
|------------|-------------|
| 2023-02-23 … 2025-05-13 | |
| 2023-07-03 | **是** |

完整列表见 `config/ml/p8c2_raw_lake_ingest.yaml` / `p8c2_run_manifest.json`。

---

## 3. Preflight 结果（最终 execute）

| 检查项 | 结果 |
|--------|------|
| ThetaData credentials（未打印 secret） | PASS |
| ThetaData connect | PASS |
| raw_lake_root 可写 | PASS — `artifacts/raw_lake_sample` |
| 磁盘空闲 ≥ 20 GB | PASS — ~300 GB free |
| frozen_dates 与 P8C.1.1 一致 | PASS — 21/21 |
| safety flags | PASS |

---

## 4. 执行摘要

分批 `--execute --resume --max-dates 5` 完成；末日本 `--dates 2025-05-14` 补跑。

| 指标 | 值 |
|------|-----|
| successful | **21** |
| failed | **0** |
| skipped_complete | 0 |
| incomplete | **0** |
| pending | **0** |
| replacement_dates_used | **false** |

---

## 5. Per-date 状态

全部 **success**，checksum **ok**，completeness **complete**。

典型 ingest 时长（`duration_seconds > 10s` 的 16 日）：约 **12–22 min/日**；`2023-07-03` early_close 约 **7 min**。

详见本地（不提交 git）：`artifacts/reports/p8c_raw_lake_ingest/p8c2_per_date_status.json`

---

## 6. rows_by_dataset 汇总（21 日合计）

| dataset | rows |
|---------|------|
| option_quote_1s | 110,701,222 |
| option_trade_tick | 9,301,945 |
| option_greeks_1m_first_order | 1,849,762 |
| derived_gamma_black76_1m | 1,844,940 |
| option_open_interest | 4,736 |
| index_price_tick | 450,370 |
| index_price_1s | 480,621 |
| session_metadata | 21 |

---

## 7. 存储：估计 vs 实际

| 来源 | 值 |
|------|-----|
| P8C.1 估计（21 日新增） | ~16.8 GB base |
| 实际（`artifacts/raw_lake_sample` 目录 used） | **~13.2 GB**（含既有 19 日 baseline + 21 日新增） |

---

## 8. 运行时间：估计 vs 实际

| 来源 | 值 |
|------|-----|
| P8C.1 估计（21 日 base） | ~819 min (~13.7 h) |
| 实测（有 wall-time 记录的 16 日合计） | **~253 min (~4.2 h)** |
| 含 resume/skip 的全会话墙钟 | 多批累计约 **6–8 h**（含中断续跑） |

---

## 9. Fallbacks

| fallback | 说明 |
|----------|------|
| `full_rth_strike_range_60_skip_tick_attempt` | 全 RTH + strike_range=60 → 直接 `option_quote_1s` |
| `quote:option_quote_1s` | quote 分辨率记录 |
| `index:index_price_tick` | index tick 优先（部分日期） |

`option_quote_tick` 按 tick_or_1s 策略**不要求**落盘（`lake_ingest.check_partition_readiness` quote-OR 修复已合入）。

---

## 10. 警告（carried forward）

| 警告 | 处理 |
|------|------|
| temporal_warning | `min_new_sessions_2024` 6 vs 8（P8C.1.1 已接受）；**未换日** |
| proxy_bucket_warning | high_vol/trend 选日用 proxy；P8C.3 复核 |

---

## 11. 合规 attestation

| 项 | 值 |
|----|-----|
| replacement dates | **否** |
| dataset build | **否** |
| feature build | **否** |
| model fitting / `.fit()` | **否** |
| P8B.4 authorized | **否** |
| artifacts / raw data 提交 git | **否** |

---

## 12. Manifest / checksum

本地 artifacts：`artifacts/reports/p8c_raw_lake_ingest/p8c2_*.json`  
Per-partition：`ingestion_status=complete`，`files[].sha256` 已校验。

---

## 13. P8C.3 建议

**P8C.3 remains BLOCKED until owner reviews this report.**

见 [`p8c3_dataset_feature_build_owner_gate.md`](p8c3_dataset_feature_build_owner_gate.md)。仅可对 **21 个 successful frozen dates** 做 dataset/feature build；**不得**训练模型或授权 P8B.4。

---

## 14. P8B.4

**继续 BLOCKED。**

---

## 15. 实现与运维脚本

| 文件 | 说明 |
|------|------|
| `config/ml/p8c2_raw_lake_ingest.yaml` | 配置 |
| `src/quant_lab/ml/datasets/p8c_controlled_ingest.py` | 编排 / preflight / cumulative manifest |
| `scripts/run_p8c_controlled_ingest.py` | CLI |
| `scripts/run_p8c2_ingest_until_done.py` | 分批循环直至 pending=0 |
| `src/quant_lab/ml/datasets/lake_ingest.py` | quote-OR completeness 修复 |
