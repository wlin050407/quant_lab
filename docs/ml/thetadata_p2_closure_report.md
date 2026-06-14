# ThetaData ML-P2A 能力闭环报告

**版本**：`ml-p2a-1.0`  
**Manifest**：`artifacts/manifests/thetadata_p2_closure.json`（不提交）  
**分支**：`research/zdte-fusion-model`

---

## 1. 执行摘要

| 问题 | 结论 |
|------|------|
| 历史 1s option quote | **账号实测支持**（`interval="1s"`） |
| 历史 tick/raw NBBO quote | **`tick` 实测支持**；`raw`/空 interval 为 **invalid_parameter** |
| SPX index 1s / tick | **1s 与 tick 实测支持**（`index_history_price`） |
| 原生 Gamma | **Standard 账号不支持**（`second_order` / `greeks_all` → Pro）；决策 **B：本地 Black-76 Gamma** |
| OI 06:30 ET 语义 | **实证约束，官方未确认** |
| 早收盘 trade NoData | **修订为窄窗口/已收盘，非数据缺失** |

**ML-P3**：**允许开始**（immutable raw lake 设计阶段），但 OI 官方语义与 tick quote 全量容量须在 P3 首项约束。

---

## 2. 早收盘日重测（2025-07-03）

| 窗口 (ET) | Trade 行数 | 末笔 trade | Quote 1m | Index 1m |
|-----------|------------|------------|----------|----------|
| 10:00–10:05 | 3,229 | 10:04:59 | 有 | 有 |
| 12:30–12:35 | 453 | 12:34:59 | 有 | 有 |
| 13:00–13:05 | **0** (NoData) | — | 有 | 有 |
| 13:10–13:15 | **0** (NoData) | — | 有 | 有 |

**修订结论**：

```text
窄窗口或所选合约无成交，不能视为数据缺失。
2025-07-03 10:00 与 12:30 窗口有 trade；13:00+ 无 trade，符合 13:00 ET 早收盘。
```

Index 在 13:00 后窗口仍有 1m 更新（早收盘后无新 trade 属预期）。

---

## 3. Option Quote 分辨率

**Client 方法**（`inspect`）：`option_history_quote`（默认 `interval='1s'`），另有 `option_at_time_quote`、`option_history_trade_quote`（trade 附带 quote，未在本阶段全量探测）。

| interval | 分类 | 2 分钟窄窗 (2025-04-09, sr=1) |
|----------|------|----------------------------------|
| `1m` | **1m_verified** | 有数据 |
| `1s` | **1s_verified** | 有数据 |
| `tick` | **tick_verified** | 有数据（~12k 行/1 分钟，逐 NBBO 事件） |
| `raw` | **invalid_interval_parameter** | gRPC INVALID_ARGUMENT |

**区分说明**：

- `tick`：**账号实测支持**，为 NBBO 逐事件，**非完整 Level 2 order book**
- `raw`：**endpoint 参数不支持**（非 entitlement 问题）

---

## 4. SPX Index 分辨率

| interval | 分类 |
|----------|------|
| `1m` | **1m verified** |
| `1s` | **1s verified** |
| `tick` | **tick verified** |

Index 1s 为价格序列（非 OHLC bar）；与 option 事件对齐误差在分钟/秒级（见 P2B pilot）。

---

## 5. Gamma 来源决策

### 客户端发现

存在但未授权（Standard）：

- `option_history_greeks_second_order`
- `option_history_greeks_all`
- `option_snapshot_greeks_second_order`

`option_history_greeks_first_order` 可用但 **无 `gamma` 列**。

### 实证

| Endpoint | 结果 |
|----------|------|
| `second_order` | **entitlement_denied**（需 Pro） |
| `greeks_all` | **entitlement_denied** |
| `first_order` | OK，含 `delta/theta/vega/implied_vol/underlying_price` |

### 本地 Black-76 对照（研究性，未改生产）

使用 `factors.gex.black76_gamma` + `resolve_gex_inputs("^SPX")`，参数：

- `spot`, `strike`, `implied_vol` 来自 first_order 行
- `rate`, `q` 来自 `settings`/rates 模块
- `T` 为 0DTE 13:00 ET 近似（**非交易所官方**）

### 最终决策

```text
B. 使用本地 Gamma，并有完整参数规范（Standard 账号 second_order/greeks_all 需 Pro）
```

升级 Pro 后可重新评估 **A 或 C**。

---

## 6. OI 语义实证

锚定日 **2025-04-09**（0DTE expiration），比较 `requested_date`：

| 标签 | requested_date | expiration | timestamp 范围 (ET) |
|------|----------------|------------|-------------------|
| D−1 | 2025-04-08 | 2025-04-09 | ~06:30 |
| D | 2025-04-09 | 2025-04-09 | ~06:30 |
| D+1 | 2025-04-10 | 2025-04-09 | ~06:30 |

**观测**：

- 三次请求均在 **~06:30 ET** 返回 timestamp
- D−1 请求仍返回 **expiration=D** 的合约 OI（timestamp 在 D−1 早晨）
- 同一 requested_date 多次 intraday 对比 **未在本阶段执行**（需 P3 长连接或重复 pull）

**代码行为**（`_oi_snapshot_at_time`）：

- 取 **at-or-before** cutoff 的最后一条 OI
- **不会** forward-fill 未来 timestamp
- 若 cutoff 前无数据 → 空（无 silent 未来 OI）

**官方状态**：

```text
OI semantics empirically constrained but not officially confirmed
```

支持信函草稿：`docs/ml/thetadata_oi_support_question.md`

---

## 7. Email 日志脱敏

`thetadata_client.py` 已修复：认证日志仅输出 `credential_source_label()`，不打印完整 email。  
**注意**：`thetadata` 库自身 auth 响应日志仍可能打印 email（第三方库，不在本仓库控制范围内）。

---

## 8. ML-P3 Gate

| 判据 | 状态 |
|------|------|
| 1s quote / tick quote / index 1s 有结论 | ✅ |
| Gamma 决策或阻塞说明 | ✅ B |
| OI 实证 + 官方问题文档 | ✅ |
| 早收盘重测 | ✅ |
| 未进入 bulk 回填 | ✅ |

**允许进入 ML-P3**（immutable raw event lake **设计**，非多年下载）。
