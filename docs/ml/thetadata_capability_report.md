# ThetaData 与 Underlying 数据能力审计报告（ML-P1）

**审计版本**：`ml-p1-1.0`  
**运行时间**：2026-06-12（UTC manifest：`artifacts/manifests/thetadata_capabilities.json`，**不提交 git**）  
**Git commit（审计时）**：`40239e19d70072efdbf873af3cd05ec25e9a82ad`  
**分支**：`research/zdte-fusion-model`

---

## 1. 执行摘要

本阶段为 **只读、受限请求** 能力探测（43 次实际 API 调用，无批量历史下载，无写入 `data/raw/`）。

| 维度 | 结论（账号实测） |
|------|------------------|
| 客户端 | `thetadata` Python v3 `ThetaClient`，gRPC 至 ThetaData cloud |
| Entitlement | Options **Standard**、Indices **Standard**、Stock **Value** |
| SPXW 0DTE 历史 quote | **支持**（5/5 测试日，1m，`strike_range=2`） |
| 历史 trade tick | **支持**（4/5 日；2025-07-03 早收盘日 trade 窗口无数据） |
| Greeks / IV | **支持**（1m 一阶 Greek + `implied_vol`；**无 `gamma` 字段**） |
| Open Interest | **支持**（5/5 日有返回；**发布时间语义未确认**） |
| SPX underlying | **支持**（`index_at_time_price` + `index_history_price` 1m） |
| Realtime streaming | **未测试**（已安装库无 streaming API） |
| Underlying 总评 | **B. 部分足够，但需要验证/补齐** |
| Point-in-time replay | **有条件可行**（1m quote/Greek/OI + tick trade；需 OI 语义与 1s 分辨率验证） |
| **ML-P2** | **允许开始**（storage estimator / 窄窗口验证），但 OI 语义与 1s 分辨率须在 P2 首项闭环 |

**证据分级**（全文沿用）：

- **已实测**：本次脚本真实 API 返回
- **由代码确认但未实测**：QuantLab 源码或库签名，本次未打网络
- **由官方文档声称但账号未确认**：官网/文档能力，本次未验证
- **未知**：尚无证据

---

## 2. 当前客户端结构

### 2.1 仓库内 ThetaData 模块

| 文件 | 职责 |
|------|------|
| `src/quant_lab/data/thetadata_client.py` | 凭证解析、`ThetaClient` 单例工厂 |
| `src/quant_lab/data/thetadata_intraday.py` | SPX 1m、0DTE quote/trade、flow 聚合 |
| `src/quant_lab/data/thetadata_chain.py` | OI 历史、chain 组装、IV 求解 |
| `src/quant_lab/data/thetadata_storage.py` | 日内 Parquet 布局（**本阶段未写入**） |

**调用 ThetaData 的其他模块**（代码确认）：`terminal/snapshot.py`、`terminal/live_chain.py`、`strategies/zdte_pin_fly_intraday.py`、`factors/pin_intraday_eval.py` 等。

### 2.2 协议与库

| 项 | 状态 |
|----|------|
| API 版本 | **v3 Python library**（非 v2 REST 直连、非本地 Terminal 必需） |
| 传输 | **gRPC** → `nexus-api.thetadata.us` |
| 初始化 | `get_thetadata_client(dataframe_type="pandas")` → `ThetaClient(email, password)` |

### 2.3 凭证来源

优先级（**由代码确认**）：

1. `THETADATA_CREDENTIALS_FILE` → 两行 `creds.txt`
2. `THETADATA_EMAIL` + `THETADATA_PASSWORD`（环境 / `.env`）
3. 项目根 `creds.txt`（不推荐）

**已实测**：`credential_source = THETADATA_EMAIL+THETADATA_PASSWORD`（manifest 已脱敏，不含明文）。

### 2.4 已有请求类型（代码 + 本次探测）

- **Discovery**：`option_list_symbols`、`option_list_expirations`、`option_list_contracts`
- **Options 历史**：`option_history_quote`、`option_history_trade`、`option_history_open_interest`、`option_history_greeks_first_order`
- **Index**：`index_list_symbols`、`index_at_time_price`、`index_history_price`
- **未在库中暴露**：streaming / websocket（realtime **未知**）

### 2.5 SPX / SPXW 归一化（代码）

- 默认 option root：`SPXW`（`DEFAULT_OPTION_ROOT`）
- 默认 index symbol：`SPX`（`DEFAULT_INDEX_SYMBOL`）
- `right` 归一化：`CALL/PUT` → `C/P`（`thetadata_chain.py`）

### 2.6 重试 / timeout / 错误

- **由代码确认但未实测**：客户端层无统一 retry wrapper；异常向上抛出
- **已实测错误类型**：`NoDataFoundError`（无数据/未来日/无效合约）、gRPC `_MultiThreadedRendezvous`（无效时间窗）
- **已实测**：错误 message **不泄露 password**；但 `thetadata_client.py` 的 `log.info` 会打印 **email**（生产应降级或脱敏）

### 2.7 项目内 SPX spot 来源

| 场景 | 来源 |
|------|------|
| 日内 / Terminal 实时链 | ThetaData `index_at_time_price` / `index_history_price`（**已实测**） |
| EoD / 长历史回测 | yfinance、`Philipp Dubach` SPY 代理（**代码确认**，非本审计范围） |

### 2.8 Mock / Fixture

- `tests/test_thetadata_client.py`、`tests/test_thetadata_intraday.py`、`tests/test_thetadata_chain.py`
- **新增**：`tests/test_audit_thetadata_capabilities.py`（10 项，无网络）

---

## 3. 实际 Entitlement

**已实测**（认证响应 + client 属性）：

| 产品 | Tier | 编码 |
|------|------|------|
| Options | Standard | `optionsSubscription: 2` |
| Indices | Standard | `indicesSubscription: 2` |
| Stock | Value | `stockSubscription: 1` |

**说明**：首次审计曾误读 `indices_subscription=null`（属性名映射问题）；修复后 manifest 正确显示 Indices Standard。

---

## 4. 实测请求矩阵

| 标签 | 日期 | 类型 | SPXW quote | SPXW trade | SPXW OI | SPXW Greek | SPX OI | underlying 1m |
|------|------|------|------------|------------|---------|------------|--------|---------------|
| ordinary_recent | 2026-06-10 | 普通交易日 | 24 行 | 1358 行 | 8 行 | 24 行 | — | OK |
| monthly_expiration | 2025-05-16 | 月度到期 | 24 行 | 2408 行 | 8 行 | 24 行 | 8 行 | OK |
| early_close | 2025-07-03 | 早收盘 | 24 行 | **NoData** | 8 行 | 24 行 | — | OK |
| high_volatility_event | 2025-04-09 | 高波动 | 24 行 | 196 行 | 8 行 | 24 行 | — | OK |
| near_historical_start | 2022-01-03 | 接近历史起点 | 24 行 | 189 行 | 8 行 | 24 行 | — | OK |

**探测参数**：`strike_range=2`，quote/Greek 窗口 `13:00–13:02 ET`，trade 窗口 `13:00–13:05 ET`，OI 全合约窄 strike。

**实际请求数**：43（预算上限 45）。

---

## 5. SPX / SPXW 合约发现

### 5.1 Root symbol（已实测）

- `option_list_symbols` 含 **SPXW**、**SPX**（各 15k+ 符号列表中的成员）
- `index_list_symbols` 含 **SPX**

### 5.2 历史 expiration（已实测）

| Root | 最早 | 最晚 | 数量 |
|------|------|------|------|
| SPXW | 2012-06-01 | 2089-06-30 | 2192 |
| SPX | 2012-06-16 | 2090-06-18 | 201 |

### 5.3 0DTE 筛选（`expiration == trading_date`）

- **已实测**：`option_history_*` 传 `expiration=session_date, date=session_date, max_dte=1` 可返回 SPXW 同日到期链
- **已实测**：`option_list_contracts("quote", date, root, max_dte=1)` 在 2026-06-10 样本返回 **expiration=2026-06-11**（**与 0DTE 语义不一致**）——链发现应优先用 `expiration=session_date` 而非仅依赖 list_contracts

### 5.4 编码与单位（已实测）

| 字段 | 观测 |
|------|------|
| `right` | `CALL` / `PUT`（字符串） |
| `strike` | `float64`，指数点（如 5930.0） |
| 合约标识 | `symbol + expiration + strike + right` |
| SPX vs SPXW | **`symbol` 字段可区分** |
| AM/PM settlement | **返回中无直接字段**（**未知** / 需官方说明） |
| 分页 | list 接口一次返回全量 expiration 列表（**无分页参数观测**） |

### 5.5 SPX 月度 vs SPXW 0DTE（已实测）

- 月度到期日 **2025-05-16**：SPXW 全链路 OK；**SPX** 在 `max_dte=1` 下 quote/trade/Greek **NoDataFound**（符合 0DTE 过滤器预期）
- SPX **OI** 在月度到期日 **有数据**（8 行，`strike_range=2`）

---

## 6. Quote 能力

| 项 | 状态 |
|----|------|
| 历史可用 | **账号实测支持**（SPXW，5/5 日） |
| 最细粒度（本次） | **1m**（`interval="1m"`） |
| 1s | **尚未确认**（库签名支持 `interval="1s"`，本次未探测） |
| 逐事件 | **否**（1m 为桶/快照，非 tick quote） |
| Timestamp | `datetime64[us, America/New_York]`，事件时间 |
| bid/ask/size | **有** |
| exchange | `bid_exchange` / `ask_exchange`（int 编码） |
| condition | `bid_condition` / `ask_condition` |
| NBBO | **是**（双侧报价；**非完整 Level 2 order book**） |
| 排序 | **无严格单调保证**（样本 `monotonic_increasing: false`） |
| 空数据 | `NoDataFoundError` |
| Entitlement 拒绝 | 本次未触发 |

---

## 7. Trade 能力

| 项 | 状态 |
|----|------|
| 历史 tick | **账号实测支持**（非聚合；含 `sequence`） |
| timestamp | 微秒精度，`America/New_York` |
| price / size / exchange / condition | **有** |
| 附带 NBBO | **本次响应无 bid/ask 列** |
| 窗口 | 5 分钟窄窗仍可返回 **数百–2000+** 行（受 `strike_range` 限制） |
| 2025-07-03 | **NoDataFound**（早收盘日 13:00–13:05 无 trade；**原因未确认**） |
| execution-side | 仅能作为未来 **execution-side proxy** 构造，**非真实买卖方** |

---

## 8. Greeks / IV

**Endpoint**：`option_history_greeks_first_order`（**已实测**）

| 字段 | 存在 | 历史 1m | 备注 |
|------|------|---------|------|
| `implied_vol` | ✓ | ✓ | ThetaData 计算 |
| `delta` | ✓ | ✓ | |
| `theta` | ✓ | ✓ | |
| `vega` | ✓ | ✓ | |
| `rho` | ✓ | ✓ | |
| `epsilon`, `lambda` | ✓ | ✓ | |
| **`gamma`** | **✗** | — | 一阶 endpoint **无 gamma** |
| vanna/charm/speed 等 | **未知** | — | 未探测二阶/三阶 endpoint |
| `underlying_price` | ✓ | ✓ | 与 `underlying_timestamp` 同桶 |
| `bid`/`ask` | ✓ | ✓ | 与 Greek 同 timestamp |
| 逐 tick Greek | **否**（1m） | | |
| rate/div 假设 | **未暴露** | | `rate_type='sofr'` 为库默认（**由代码确认**） |

**重要**：0DTE ML 若依赖 **gamma**，须在 ML-P2 验证是否存在 `option_history_greeks_second_order` 或改用自算 BS76 + quote。

---

## 9. Open Interest（关键）

**Endpoint**：`option_history_open_interest`（**已实测**）

| 项 | 观测 |
|----|------|
| 历史可用 | **5/5 测试日**（SPXW）；月度日 SPX 亦有 |
| 0DTE 当日 OI | **有**（`expiration == session_date`） |
| Timestamp | 集中在 **06:30–07:01 ET**（盘前），**非盘中 13:00** |
| 盘中多次请求 | **本次未测**（需 P2 同一交易日多时点对比） |
| 语义（EoD vs 开盘前 vs 次日） | **需要 ThetaData 官方说明或支持确认** |
| 避免 next-day OI | **尚无 API 字段可证明**；项目当前用 `_oi_snapshot_at_time` 取 at-or-before（**代码确认**） |

---

## 10. Underlying / SPX Spot

### 10.1 QuantLab 现状

- 日内：**ThetaData index**（**已实测**）
- EoD 研究：**非 ThetaData**（yfinance / Philipp Dubach）

### 10.2 已实测能力

| 方法 | 粒度 | 历史 |
|------|------|------|
| `index_at_time_price` | 时点 | 2022-01-03 – 2026-06-10 OK |
| `index_history_price` | **1m** | 同上 OK |
| tick / 1s index | **尚未确认** | 库有 `interval="1s"` 参数 |

### 10.3 与 option 同步

- Greek 响应含 `underlying_price` + `underlying_timestamp`，与 option 1m bar **对齐**（**已实测**）
- 独立 index 1m 与 option quote timestamp **一致到分钟**（**已实测**）

### 10.4 结论

**B. 部分足够，但需要验证/补齐**

- Indices Standard **足够**支撑 ML 研究 **1m 同步 underlying**
- **待补齐**：1s/tick index、早收盘 session 边界、是否与 CBOE 官方 SPX 完全一致

**yfinance 备用**（代码确认）：无 intraday point-in-time 保证，**不应**作为 0DTE ML 主 underlying。

---

## 11. Realtime

| 项 | 状态 |
|----|------|
| 权限 | **未知**（定价页不等于 entitlement，且未探测 streaming） |
| Python `ThetaClient` | **无 streaming 方法**（**由代码确认**） |
| 探测策略 | 本阶段 **未启动** stream（避免费用/负载） |

---

## 12. Timestamp 与 Schema

| 项 | 观测 |
|----|------|
| 时区 | **`America/New_York`**（含 DST） |
| 精度 | **微秒**（`datetime64[us, ...]`） |
| 语义 | **事件时间**（trade quote 非 receive time 字段） |
| Strike / price | 指数点，option price 为美元 |
| Schema 版本 | 响应无显式 version 字段 |

---

## 13. 历史起点

| 数据 | 已实测最早有效日 |
|------|------------------|
| SPXW quote/trade/Greek/OI | **2022-01-03** |
| SPX index 1m | **2022-01-03** |
| Expiration 列表 | SPXW **2012-06-01** 起（**列表 ≠ 必有 intraday**） |

更早日期 **尚未确认**（需 P2 单点探测 2012–2021）。

---

## 14. 请求限制

- 脚本硬 cap：`--max-requests`（默认 45）
- `strike_range` 有效限制返回宽度（**已实测**）
- 无并发（顺序 `_call`）
- 窄时间窗控制 trade 行数（仍可达 1000+ 行/窗）
- Pagination：**未见**（**未知**是否大请求会截断）

---

## 15. 错误行为

| 场景 | 异常 | 可重试 |
|------|------|--------|
| 未来日期 | `NoDataFoundError` | 否 |
| 无效时间窗 start>end | gRPC `_MultiThreadedRendezvous` | 否 |
| 不存在 strike | `NoDataFoundError` | 否 |
| SPX + max_dte=1 月度 | `NoDataFoundError` | 否（应用 SPXW 或去掉 max_dte） |

---

## 16. Point-in-time Replay 可行性

| 能力 | 评估 |
|------|------|
| raw tick event lake | **有条件**（trade tick 支持；quote 仅 1m NBBO） |
| 1s 状态 | **尚未确认** |
| 10s 状态 | **需自聚合**（无原生 10s） |
| 1m 状态 | **已实测可行** |
| historical chain replay | **有条件**（OI 语义 + gamma 来源待闭环） |
| dynamic Pin training | **依赖 OI 时点语义 + gamma**；P2 前为 **部分可行** |

---

## 17. ML 研究分辨率支持矩阵

| 目标 | 结论 |
|------|------|
| raw tick event lake | trade **支持**；quote **仅 1m** |
| 1s 状态 | **尚未确认** |
| 10s 状态 | 需从 tick/1s 聚合 |
| 1m 状态 | **已实测支持** |
| historical chain replay | **有条件** |
| dynamic Pin training | **有条件**（OI + gamma 缺口） |

---

## 18. 当前资源缺口

1. **OI 发布语义**未确认（06:30 ET timestamp 含义）
2. **`gamma` 不在一阶 Greek 响应**中
3. **1s quote/index** 未实测
4. **早收盘 trade 空窗**（2025-07-03）未解释
5. **Realtime** 未评估
6. **SPX 月度 AM 链**与 SPXW PM 0DTE 并存时的 discovery 规则需文档化
7. **`thetadata_client` 日志泄露 email**（非 manifest，但属运维风险）

---

## 19. ML-P2 是否允许开始

**允许开始 ML-P2**（storage estimator、窄窗口 1s 探测、OI 语义验证），**前提**：

- P2 首任务包含：**OI 时点语义**、**1s 分辨率 spot-check**、**gamma 来源决策**
- 仍 **禁止** bulk 回填与模型训练（属更后阶段）

---

## 20. Acceptance Gate（ML-P1）

| 判据 | 结果 |
|------|------|
| ≥2 历史日成功审计 | **通过**（5 日） |
| quote/trade/Greek/OI/underlying 有结论 | **通过**（trade 1 日例外已记录） |
| 最细分辨率结论 | **通过**（1m 实测；1s 待 P2） |
| SPX/SPXW discovery | **通过** |
| 独立 index 数据源结论 | **通过**（B） |
| 无批量下载 | **通过** |
| 无 secret 泄露（manifest） | **通过** |
| 测试全绿 | **通过**（332 passed） |
| Ruff（本阶段文件） | **通过** |
| 报告区分已实测/未确认 | **通过** |

---

## 附录：审计脚本

```bash
python scripts/audit_thetadata_capabilities.py --dry-run
python scripts/audit_thetadata_capabilities.py \
  --max-contracts 2 --max-rows 100 --max-requests 45 \
  --output artifacts/manifests/thetadata_capabilities.json
```

机器可读 schema 示例：`docs/ml/thetadata_capabilities_schema.json`
