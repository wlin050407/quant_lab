# quant_lab

**SPX 0DTE 期权 dealer positioning 研究仓库** — 从可审计的 EoD / 盘中期权链出发，推断做市商 gamma 暴露与 pin 磁吸结构，并在统一因子层上贯通历史 IC、EoD 近似回测、实时 Terminal 与后续执行路径。

> 私有仓库。勿提交 `.env`、凭证或 `data/` 目录内容。ThetaData、Terminal Basic Auth 等密钥仅通过环境变量配置。

| 文档 | 用途 |
|------|------|
| [`ROADMAP.md`](./ROADMAP.md) | 分阶段产出、决策门、实证结论 |
| [`AGENTS.md`](./AGENTS.md) | 模块边界、编码约定、SPX 常见坑 |
| [`docs/PIN_PLAY_SPEC.md`](./docs/PIN_PLAY_SPEC.md) | Pin Play @ King 策略规格（Phase 3 主线） |
| [`docs/ULTIMATE_TERMINAL.md`](./docs/ULTIMATE_TERMINAL.md) | Terminal 产品层与 L0–L6 能力规划 |
| [`docs/EQUITY_LIVE_MODULE_PLAN.md`](./docs/EQUITY_LIVE_MODULE_PLAN.md) | 个股多周期研究模块设计 |
| [`docs/DEPLOY.md`](./docs/DEPLOY.md) | 云端运行配置（运维参考，非 README 范围） |

---

## 研究定位

### 核心假设

0DTE 的可交易边缘主要来自 **dealer positioning 的非对称性**：做市商为流动性提供方，其 gamma / delta 仓位可通过 open interest（及盘中 flow 代理）推断；当现货与 **磁吸位**（King、gamma flip、call/put walls、max pain）相互作用时，波动与 pin 行为呈现可重复结构。

该假设要求 **先有可靠的日终 / 盘中 positioning 画像**，再谈 intraday 进出场；EoD 研究不是权宜之计，而是 0DTE 策略的数据基础。

### 终局目标

在 **SPX 0DTE** 上跑出有正期望、可执行、风险可控的策略（当前规格主线：**午后 Pin Play — iron butterfly @ King**，见 `docs/PIN_PLAY_SPEC.md`）。

### 研究代理与校准

| 标的 | 角色 |
|------|------|
| **SPY** | Philipp Dubach 18 年 EoD 链（含预计算 Greeks）— Phase 0/1 主历史代理 |
| **^SPX** | yfinance / ThetaData 增量 — SPX 专用校准与 Terminal 实盘链 |
| **SPY ↔ SPX** | `factors/spx_spy_calibration.py` — 理论尺度 \(k \approx (S_{SPX}/S_{SPY})^2\) 与配对日实证 |

SPY 与 SPX 在名义、结算、税务上不可 1:1 套用；所有跨标的结论需经校准模块或显式标注。

---

## 阶段状态（摘要）

项目按 **阶段门** 推进，未过出口判据不进入下一阶段（详见 `ROADMAP.md`）。

```
Phase 0  数据地基          ✓ 18y SPY EoD + ^SPX 增量 + 质量检查
Phase 1  Positioning 因子   ✓ GEX / max pain / PCR / IC / SpotGamma 校准
Phase 2  回测引擎 + 基线    ✓ engine + SPY Z-score 对账
Phase 3  EoD 0DTE 近似      ✓ 方向 IC / IC / conditional — 决策门 FAIL → pivot
         3e King 吸附        ✓ pin 高 + long γ 日 close 更贴近 King
         3f fly@King         ✓ 优于 fly@spot，仍负 — 待 Phase 4 intraday
Phase 4  付费 intraday 真回测   ← 下一花钱节点
Phase 5+ Paper / Live
```

**当前工程重心**：Terminal 将 L2–L3 因子产品化；研究主线沿 Pin Play spec 向 Phase 4 intraday 回测推进。EoD 宽 iron condor 等实验代码保留作对照，不再作为主 alpha 优化对象。

---

## 系统架构

研究数据流与模块职责严格分层，避免「研究 DataSource」与「执行 broker」混用：

```
                    ┌─────────────────────────────────────┐
                    │  Terminal (FastAPI + React)          │
                    │  snapshot 组装 · 双模式 UI · API      │
                    └──────────────────┬──────────────────┘
                                       │ 只读因子 + 链
┌──────────────┐    ┌──────────────────▼──────────────────┐    ┌─────────────┐
│  strategies/ │◄───│  factors/  (无 I/O · 纯函数)         │───►│  backtest/  │
│  时序逻辑    │    │  GEX · pin · trinity · equity · IC   │    │  PnL · 指标  │
└──────┬───────┘    └──────────────────▲──────────────────┘    └─────────────┘
       │                                 │
       │                    ┌────────────┴────────────┐
       │                    │  quality/  (只读校验)    │
       │                    └────────────▲────────────┘
       │                                 │
       └─────────────────────┌───────────┴───────────┐
                             │  data/  抓取 · Parquet │
                             │  yfinance · ThetaData  │
                             │  Philipp Dubach 导入    │
                             └────────────────────────┘
```

| 模块 | 职责 | 禁止 |
|------|------|------|
| `data/` | 抓取、落盘、`DataSource` 协议 | 因子计算 |
| `quality/` | 链完整性、IV、跨日连续性 | 修改数据 |
| `factors/` | 干净快照 → 标量 / 曲线 / 张量 | 网络、写盘 |
| `terminal/` | API 载荷组装、UI 静态资源 | 内联重复因子公式 |
| `backtest/` | 信号 → 收益、费用、滑点 | 改数据源 |
| `strategies/` | 因子组合 → 仓位序列 | 写盘、抓网 |

配置统一经 `quant_lab.config.settings`（`config/settings.yaml`）；路径一律 `pathlib.Path`；存储格式仅 **Parquet**。

---

## 数据层

### 来源

- **yfinance** — 默认 EoD：`^SPX` / `SPY` 标的与期权链；免费、有延迟；`^SPX` 可抓链，`^GSPC` 不可。
- **Philipp Dubach** — MIT，2008–2025 SPY EoD，含 delta/gamma/theta/vega/rho；经 `data/philippdubach_source.py` 转为与 yfinance 一致的 `chain.parquet` 布局。
- **ThetaData** — Terminal 盘中 0DTE（SPXW）、可选 equity 分钟线；支持 `pin` / `full` / `gex` 链构建模式。

### 落盘约定

```
data/raw/options/<SYMBOL>/<YYYY-MM-DD>/chain.parquet
data/processed/...          # GEX 历史、terminal 因子表等
```

读取统一走 `quant_lab.data.storage`，禁止脚本内随意 `pd.read_parquet`。

### 质量门禁

`quality/checks.py` 覆盖单日链字段、0DTE IV 不可靠标记（`dte ≤ 1`）、跨日 `check_snapshot_continuity` 等。研究用数据须 **0 error**；已知 warn（如 yfinance 0DTE IV）需在因子层过滤或标注。

---

## 因子层（Positioning）

实现位于 `src/quant_lab/factors/`，Terminal 与回测共用同一套数学。

### Dealer sign（必读）

默认 **SpotGamma 约定**（可参数覆盖）：

- Dealer **long calls** (+1)
- Dealer **short puts** (−1)

这是 flow 假设，非事实；0DTE 时代 retail 大量买 OTM call 时，翼部 sign 可能局部反转。回测方向错误时，首先检验 convention。

### GEX / VEX

- 单合约 gamma：**广义 Black-Scholes**（连续股息 yield `q`），指数期权与 SPY ETF 共用公式族；文档亦保留 Black-76 对照。
- 聚合（每 strike，显示单位 **bn USD per 1% spot move**）：

  \[
  \text{GEX} = 0.01 \times \sum (\text{dealer\_sign} \times \Gamma \times \text{OI} \times 100 \times S^2)
  \]

- **Gamma flip** — 净 GEX 过零价位；**King** — \|net GEX\| 最大 strike；**walls** — call/put 侧 GEX 峰值。
- **VEX** — 同 sign 约定下的 vanna × OI，用于 vol–spot 耦合语境。

Dataset gamma 交叉校验（Philipp Dubach）中位相对误差约 **0.67%**（`scripts/cross_check_gamma.py`）。

### Pin 与 regime

| 因子 | 说明 |
|------|------|
| `pin_score` | 距磁吸位、0DTE GEX 集中度、OI 集中度、距收盘时间（末两小时加权更陡） |
| `regime` | 由 net 0DTE GEX 判 long-γ / short-γ 环境 |
| `should_trade_zdte` | regime + pin + 0DTE GEX 占比 — Playbook 硬门槛 |
| `pin_cluster` | 相邻 magnet 形成 **pinning zone**（带宽、突破位、spot 相对 zone 状态） |
| `effective_oi` | 结算 OI + 置信度加权 flow 增量（对齐 FlashAlpha pin-risk 语义） |
| `expected_move_1sd` | ATM IV → 1σ 预期波动 |
| `trinity` | SPX / SPY / QQQ King 距离对齐 → Trinity Score（0–100） |

历史 IC 示例（18y SPY）：net_gex → 次日 \|return\| Spearman ≈ **−0.32**（`scripts/analyze_gex_ic.py`）。

### SPX 校准

`factors/spx_spy_calibration.py` + `scripts/calibrate_spx_spy.py`：配对日估计 GEX / strike 尺度；^SPX OI 稀疏时自动回退理论 proxy。

---

## 回测与策略研究

`backtest/engine.py` — 信号 @ *t* → 收益 @ *t+1*，含佣金与滑点；`backtest/bs76.py` — EoD 期权重估。

| 策略模块 | 用途 |
|----------|------|
| `baseline_zscore.py` | Phase 2 非期权基线（SPY 5 日 Z-score） |
| `zdte_directional_eod.py` | Phase 3a 方向 — OOS Sharpe **−0.09**，门 FAIL |
| `zdte_ic_eod.py` | Phase 3b long-γ 卖 IC — hit 高、Sharpe 仍负 |
| `zdte_ic_conditional.py` | Phase 3c–3d 条件/filter — 减损非 live-ready |
| `zdte_pin_fly_eod.py` | Phase 3f iron fly @ King vs @ spot |
| `zdte_pin_fly_intraday.py` | ThetaData 链上的 intraday 原型（Phase 4 前置） |

EoD 回测为 **粗近似**（无前日 intraday 链时，入场与 Greeks 均有 ±50% 量级误差）；产出用于 **方向性决策**，非可上线 PnL。真回测需 Phase 4 付费 intraday + 费用模型。

研究 CLI 集中于 `scripts/`（`build_gex_history.py`、`analyze_factor_ic.py`、`evaluate_intraday_pin.py` 等）。

---

## Quantlab Terminal

**研究面向的产品层**：把因子与链转为可审计 JSON + React 仪表盘，与 Skylit / SpotGamma / FlashAlpha 能力对齐，但强调 **可复现、可回测、可披露**（`model_metadata`、cohort、`data_mode`、`oi_mode` 等）。

### 双模式

| 模式 | 路由 | 回答问题 |
|------|------|----------|
| **Index 0DTE** | `#/index` | 今日 dealer gamma 分布、regime、磁吸位与 Pin Playbook |
| **Equity 结构** | `#/stock?t=TICKER` | 单票 short / mid / long 多周期结构（流动性、flow、RS、期权覆盖层 — 非基本面） |

### Index 0DTE 分析管线

1. **输入** — ThetaData 盘中 0DTE（`live` 或 pin-play 时刻如 13:00 ET）；历史日读 Parquet / 预构建 intraday 链。
2. **队列** — 默认 `dte ≤ 1`；空队列时回退全链并标记 `cohort_fallback`。
3. **链模式** — `pin`（ΔOI vs 09:30）、`full`（含 session trade flow）、`gex`（轻量，用于 Trinity 并行）。
4. **输出** — `GET /api/snapshot`：热力图、gamma profile、levels、metrics、trinity（`include_trinity=1`）、playbook、pin targets、**pin cluster**、magnet shift（live 轮询）。

### Equity 多周期（L0–L7）

按需拉取 bars → 分层因子 → 三独立 verdict（short / mid / long），含 `alignment`、`weakest_link`、证据等级 A/B/C。层定义见 `docs/EQUITY_LIVE_MODULE_PLAN.md`；`GET /api/equity/analyze?ticker=...`。

### 性能说明

首屏延迟主要来自 **外部数据构建**（ThetaData 链、yfinance 多序列），非前端渲染。默认 `include_trinity=0` 为单标的快路径；Trinity 三列需额外 lite 链并行拉取。Index 主链 `full` 模式因 effective OI / flow 质量不可再砍而不损语义。

---

## 工程与质量

- **语言** — Python ≥ 3.12；类型注解覆盖公开 API。
- **测试** — `tests/` 下 300+ 用例：因子手算样例、mock 数据源、Terminal JSON 契约、回测无 lookahead 等。
- **Lint** — Ruff（`pyproject.toml`）。
- **透明度** — `terminal/model_metadata.py` 暴露模型版本、flip 求解、cohort T 诊断；见 `docs/MODEL_TRANSPARENCY_PLAN_2026-06-01.md`。

### 已知限制（研究诚实性）

| 项 | 说明 |
|----|------|
| yfinance 0DTE IV | 不可信；因子与质量层对 `dte ≤ 1` 的 IV 过滤或重算 |
| Dealer sign | 假设，非观测 |
| EoD 回测 | 不能替代 intraday 真回测 |
| 执行 | Phase 5 前无自动下单 |
| Equity L4 签名 flow | 未配置；L6 期权覆盖为 best-effort |
| 云端实例 | 不捆绑 18y Philipp Dubach；长历史研究在本地 `data/` |

---

## 仓库布局

```
quant_lab/
├── config/                 # settings.yaml、SpotGamma 参考日等
├── data/                   # gitignore — raw / processed Parquet
├── docs/                   # 规格、Terminal、部署（运维）
├── scripts/                # CLI：抓取、历史构建、回测、Terminal 构建
├── src/quant_lab/
│   ├── config.py
│   ├── data/               # DataSource、storage、ThetaData、Philipp Dubach
│   ├── factors/            # positioning、gex、equity、pin_cluster、IC…
│   ├── quality/
│   ├── terminal/           # FastAPI、snapshot、React static/dist
│   ├── backtest/
│   └── strategies/
└── tests/
```

---

## 设计原则

1. **阶段门** — 无证据不晋级（`ROADMAP.md`）。
2. **单一存储** — Parquet + `storage` API。
3. **因子无状态** — 同一公式服务 IC、回测、Terminal。
4. **可审计** — 时间戳、dealer sign、cohort、数据源模式写入 payload。
5. **YAGNI** — 无 benchmark 不引入 Numba/CuPy；`broker/` 用到再建。

---

## 许可

私有项目 — 保留所有权利。第三方数据集遵循其各自许可（如 Philipp Dubach SPY options，MIT）。
