# 单日存储与吞吐 Pilot 报告（ML-P2B）

**版本**：`ml-p2b-1.0`  
**Manifest**：`artifacts/manifests/intraday_storage_pilot.json`（不提交）  
**Pilot 数据**：`artifacts/pilot/`（gitignored）

---

## 1. 执行摘要

在 **最高已验证 quote 分辨率 1s**（非 tick 全量）下，对 **2 个完整 RTH 交易日** 进行单日存储/吞吐 pilot：

| 日期 | 标签 | 说明 |
|------|------|------|
| 2026-06-10 | ordinary | 普通完成日 |
| 2025-04-09 | high_volatility | 高波动日（ML-P1 已探测） |

**Strike universe**：`strike_range=60`（EM 带宽代理；EM 子集从同次下载后本地过滤，见 §4）。

**结论（估算，非精确）**：

- 单日压缩 Parquet 体积 **~38–44 MB**（1s quote + tick trade + 1m Greek + OI + 1s index）
- 年化 **~10.4 GB**（base）
- 2022-05 至今 **~42.8 GB**（base，~4.1 年 trading days）

**不含**：全链 tick quote lake（tick 1 分钟窄窗已达 ~12k 行/contract-band；全日 tick quote 体积需单独 pilot）。

---

## 2. Pilot 配置

| 参数 | 值 |
|------|-----|
| option root | SPXW 0DTE (`expiration=session_date`, `max_dte=1`) |
| quote | `option_history_quote`, **1s** |
| trade | `option_history_trade`, tick |
| greeks | `option_history_greeks_first_order`, **1m**（无原生 gamma） |
| OI | `option_history_open_interest` |
| index | `index_history_price`, **1s** |
| session | 09:30–16:00 ET |
| strike_range | 60 |
| Parquet | ZSTD level 3（对比 level 6 见 §6） |

---

## 3. 实测数据量

### 2026-06-10（ordinary）

| Dataset | Rows | Parquet (bytes) | Memory (bytes) |
|---------|------|-----------------|----------------|
| index 1s | 23,401 | 175,711 | 374,548 |
| quotes 1s | **5,616,240** | 30,132,484 | 682,373,292 |
| trades tick | 1,367,215 | 11,069,607 | 177,012,988 |
| greeks 1m | 93,840 | 2,634,979 | 14,404,572 |
| OI | 240 | 7,694 | 15,852 |
| **合计** | — | **~43.0 MB** | — |

### 2025-04-09（high_volatility）

| Dataset | Rows | Parquet (bytes) |
|---------|------|-----------------|
| index 1s | 23,401 | 195,705 |
| quotes 1s | **5,616,240** | 32,188,748 |
| trades tick | 315,986 | 3,361,719 |
| greeks 1m | 93,840 | 2,992,670 |
| OI | 226 | 7,413 |
| **合计** | — | **~38.7 MB** |

**重要观测**：两日 **quote 行数完全相同（5,616,240）**，疑似 API **隐式行数上限** 或 `strike_range=60` 饱和；高活动日 **trade 行数更低**（1.37M vs 316k），与直觉相反，可能受 strike 带宽或 API 截断影响。**容量估算应视为区间，非精确计数。**

---

## 4. EM 带宽子集（本地过滤，无额外 API）

从 `strike_range=60` 单次下载后，按 spot±k×EM 过滤（IV 中位数 proxy）：

- 脚本：`estimate_intraday_storage._em_band_subsets`
- 代理：`pm_0p5_em`, `pm_1p0_em`, `pm_2p0_em`
- **注**：若 spot 提取失败则跳过；正式 EM point-in-time 稳定后替换

固定 strike_range 代理对照（设计意图）：

| 代理标签 | strike_range |
|----------|--------------|
| spot ± 0.5 EM | 15 |
| spot ± 1.0 EM | 30 |
| spot ± 2.0 EM | 60 |

---

## 5. 时间与吞吐

| 日 | API 请求 | 下载 (s) | 规范化 (s) | 写入 (s) | 读回 (s) |
|----|----------|----------|------------|----------|----------|
| 2026-06-10 | 5 | 218.1 | 0.41 | 3.73 | 0.51 |
| 2025-04-09 | 5 | 392.2 | 0.43 | 3.59 | 0.23 |

**events/s（quotes ordinary）**：5,616,240 / 21,600s ≈ **260 quote-rows/s**（含多 strike 并行 1s 桶，非单一合约 tick 率）。

---

## 6. 压缩实验（quotes 样本）

| ZSTD | Bytes | vs memory |
|------|-------|-----------|
| 3 | 30,132,484 | 4.42% |
| 6 | 29,218,141 | 4.28% |

Level 6 仅比 3 小 **~3%**，pilot 默认 **ZSTD 3** 作为 low/base 折中。

---

## 7. 质量指标（ordinary 日）

| Dataset | duplicate_ratio | out_of_order_ratio |
|---------|-----------------|---------------------|
| quotes 1s | 0.996 | ~0 |
| trades | 0.40 | ~0.0002 |
| greeks 1m | 0.996 | ~0.003 |
| OI | 0.09 | 0.49 |

Quote/Greek 高 duplicate_ratio 因 **多 strike 共享 timestamp 桶**（宽格式），非 API 重复 delivery。

---

## 8. 容量投影（估算）

来自 manifest `capacity_projection`（**estimate，非精确**）：

| 范围 | 单日 (base) | 单月 (21d) | 单年 (252d) | 2022-05→今 (~4.1y) |
|------|-------------|------------|-------------|---------------------|
| low | 37.0 MB | 776 MB | 9.1 GB | 37.3 GB |
| base | **41.4 MB** | **828 MB** | **9.7 GB** | **39.8 GB** |
| high | 52.5 MB | 1.1 GB | 12.9 GB | 53.0 GB |

**假设**：

- 含 1s quote + tick trade + 1m Greek + OI + 1s index
- **不含** 全日 tick quote raw lake
- `strike_range=60`，非全链
- 不含 manifest/checksum 开销

**若加入 tick quote 全日**：按窄窗比例粗算，体积可能 **×10–50**（需独立 pilot，本阶段 **未执行**）。

---

## 9. 建议 Raw Event Lake Schema（实测字段）

基于 pilot Parquet，建议事件类型：

**quote_1s**（NBBO，非 L2）：`symbol, expiration, strike, right, timestamp, bid, ask, bid_size, ask_size, bid_exchange, ask_exchange, bid_condition, ask_condition`

**trade_tick**：`symbol, expiration, strike, right, timestamp, sequence, price, size, exchange, condition, ext_condition*`

**greek_1m**：`timestamp, strike, right, delta, theta, vega, rho, implied_vol, underlying_price, underlying_timestamp, bid, ask`

**oi_snapshot**：`timestamp, strike, right, open_interest`（语义待官方确认）

**index_1s**：`timestamp, price`

**session_metadata**：`session_date, rth_start, rth_end, strike_range, intervals, label`

本地 **gamma** 若需要：derived 表 `gamma_bs76`，列 `timestamp, strike, right, gamma, spot, iv, r, q, t_years, model=black76`。

---

## 10. 复现

```bash
python scripts/estimate_intraday_storage.py --dry-run
python scripts/estimate_intraday_storage.py \
  --strike-range 60 --quote-interval 1s --greek-interval 1m --index-interval 1s
```
