# ML-P8C.2 Raw Lake Ingest 报告

**阶段：** ML-P8C.2 — Actual Controlled Ingest / Raw Lake Expansion  
**状态：** IN PROGRESS（实现完成；分批 execute 进行中）  
**Gate：** PASS（首批 1/21 日 execute PASS；剩余 20 日待 `--resume` 继续）

---

## 1. 目标

对 P8C.1.1 owner 冻结的 **21 个日期**执行 **raw lake ingest only**：

- 写入 `artifacts/raw_lake_sample` partitions + per-date manifests
- 记录 per-date success / failure / skipped / incomplete
- 支持 resume；**不替换**失败日期
- **禁止** dataset build、feature build、`.fit()`、P8B.4

---

## 2. 冻结日期列表（21 日，不可修改）

| # | trade_date | bucket (P8C.1) | early_close |
|---|------------|----------------|-------------|
| 1 | 2023-02-23 | normal_range | |
| 2 | 2023-03-21 | monthly_opex | |
| 3 | 2023-05-08 | normal_range | |
| 4 | 2023-05-30 | normal_range | |
| 5 | 2023-06-16 | high_vol | |
| 6 | 2023-06-22 | normal_range | |
| 7 | 2023-06-27 | normal_range | |
| 8 | 2023-07-03 | early_close | **是** |
| 9 | 2023-08-09 | normal_range | |
| 10 | 2023-10-25 | trend | |
| 11 | 2024-01-03 | normal_range | |
| 12 | 2024-02-20 | normal_range | |
| 13 | 2024-05-15 | normal_range | |
| 14 | 2024-06-06 | normal_range | |
| 15 | 2024-10-16 | high_vol | |
| 16 | 2024-11-20 | monthly_opex | |
| 17 | 2025-01-17 | normal_range | |
| 18 | 2025-03-05 | normal_range | |
| 19 | 2025-03-25 | recent | |
| 20 | 2025-05-13 | normal_range | |
| 21 | 2025-05-14 | normal_range | |

---

## 3. Preflight 结果

| 检查项 | 结果 |
|--------|------|
| ThetaData credentials present（未打印 secret） | PASS — `THETADATA_CREDENTIALS_FILE` |
| ThetaData entitlement connect（execute 时） | PASS |
| raw_lake_root 可写 | PASS — `artifacts/raw_lake_sample` |
| 磁盘空闲 ≥ 20 GB | PASS — ~300 GB |
| frozen_dates 与 P8C.1.1 owner record 一致 | PASS — 21/21 |
| safety flags（no build/fit/replacement/p8b4） | PASS |

---

## 4. 执行命令摘要

```bash
# dry-run（默认，全 21 日 plan）
python scripts/run_p8c_controlled_ingest.py \
  --config config/ml/p8c2_raw_lake_ingest.yaml \
  --dry-run

# 分批 execute（推荐）
python scripts/run_p8c_controlled_ingest.py \
  --config config/ml/p8c2_raw_lake_ingest.yaml \
  --execute --resume --max-dates 5
```

**已执行：**

| 运行 | 模式 | 参数 | Gate |
|------|------|------|------|
| 1 | dry-run | `--max-dates 3` | PASS |
| 2 | execute | `--resume --max-dates 1` | PASS（2023-02-23） |

---

## 5. Per-date 状态表

| trade_date | status | duration | completeness | checksum | fallbacks |
|------------|--------|----------|--------------|----------|-----------|
| 2023-02-23 | **success** | 1155 s (~19.3 min) | complete | ok（files.sha256） | `full_rth_strike_range_60_skip_tick_attempt` → quote 1s |
| 2023-03-21 | pending | — | — | — | — |
| …（其余 19 日） | pending | — | — | — | — |

**2023-02-23 rows_by_dataset：**

| dataset | rows |
|---------|------|
| option_quote_1s | 5,616,240 |
| option_trade_tick | 337,257 |
| option_greeks_1m_first_order | 93,840 |
| derived_gamma_black76_1m | 93,600 |
| option_open_interest | 240 |
| index_price_tick | 21,829 |
| index_price_1s | 23,401 |
| session_metadata | 1 |

---

## 6. 成功 / 失败计数

| 指标 | 值 |
|------|-----|
| frozen_dates | 21 |
| attempted（累计） | 1 |
| successful | 1 |
| failed | 0 |
| skipped_complete | 0 |
| incomplete | 0 |
| replacement_dates_used | **false** |

---

## 7. 存储：估计 vs 实际

| 来源 | 值 |
|------|-----|
| P8C.1 估计（21 日） | ~16.8 GB base |
| 单日本次实际（2023-02-23） | ~0.8 GB（与 P8C.1 base 假设一致） |
| 21 日外推 | ~16–17 GB（待全部完成后核实） |

---

## 8. 运行时间：估计 vs 实际

| 来源 | 值 |
|------|-----|
| P8C.1 估计（21 日 base） | ~819 min (~13.7 h) |
| 单日本次实际 | ~19.3 min |
| 21 日外推 | ~6.7 h（若均类似；高 vol 日可能更长） |

---

## 9. Fallbacks

- **2023-02-23：** `full_rth_strike_range_60_skip_tick_attempt` — 全 RTH + strike_range=60 跳过 tick，直接拉 `option_quote_1s`（与 P7.6/P8B.1 策略一致）

---

## 10. 警告（carried forward）

| 警告 | 内容 | 处理 |
|------|------|------|
| temporal_warning | `min_new_sessions_2024` 实际 6 vs 目标 8（P8C.1.1 已接受） | manifest `temporal_warning_carried_forward=true`；**未换日** |
| proxy_bucket_warning | high_vol/trend 选日时无本地 index，用 `selection_seed=20260621` proxy | manifest `proxy_bucket_warning_carried_forward=true`；P8C.3 复核 |

---

## 11. 合规 attestation

| 项 | 值 |
|----|-----|
| replacement dates | **否** |
| dataset build | **否** — `dataset_build_performed=false` |
| feature build | **否** — `feature_build_performed=false` |
| model fitting / `.fit()` | **否** — `model_fitting_performed=false` |
| P8B.4 authorized | **否** — `p8b4_authorized=false` |
| `docs/ml/label_spec.md` 修改 | **否** |
| `requirements.txt` 修改 | **否** |
| artifacts / raw data 提交 git | **否** |

---

## 12. Manifest / checksum

本地 artifacts（不提交）：

- `artifacts/reports/p8c_raw_lake_ingest/p8c2_ingest_status.json`
- `artifacts/reports/p8c_raw_lake_ingest/p8c2_per_date_status.json`
- `artifacts/reports/p8c_raw_lake_ingest/p8c2_run_manifest.json`

Per-partition manifest：`ingestion_status=complete`，`files[].sha256` 已校验。

---

## 13. P8C.3 建议

**P8C.3 remains BLOCKED** until owner reviews this report after **all 21 dates** reach terminal status.

见 [`p8c3_dataset_feature_build_owner_gate.md`](p8c3_dataset_feature_build_owner_gate.md)。

---

## 14. P8B.4

**继续 BLOCKED。** P8C.2 不授权生产回测或交易信号。

---

## 15. 剩余工作（owner / 运维）

重复执行直至 21 日均有 terminal status：

```bash
python scripts/run_p8c_controlled_ingest.py \
  --config config/ml/p8c2_raw_lake_ingest.yaml \
  --execute --resume --max-dates 5
```

失败日期只记录，不找替代日。全部完成后更新本报告 success/failure 表并提交 owner 审阅 P8C.3 gate。

---

## 16. 实现文件

| 文件 | 说明 |
|------|------|
| `config/ml/p8c2_raw_lake_ingest.yaml` | P8C.2 配置 |
| `src/quant_lab/ml/datasets/p8c_controlled_ingest.py` | 编排 / preflight / manifest |
| `scripts/run_p8c_controlled_ingest.py` | CLI |
| `tests/test_p8c2_controlled_ingest.py` | mock 测试（13 cases） |
| `docs/ml/p8c3_dataset_feature_build_owner_gate.md` | P8C.3 owner gate |

`raw_lake_root` 使用 `artifacts/raw_lake_sample`（与 P8B.1 / P8C.1 一致，扩展同一 lake）。
